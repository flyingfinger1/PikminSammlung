"""Pikmin-Herbarium web server.

Serves the uploaded page (optionally behind Basic Auth) and accepts uploads of the two page files
(index.html, thumbs.jpg) with a bearer token. Standard library only.

Environment:
  VIEW_USER, VIEW_PASSWORD  optional login for viewing; unset = page is public
  UPLOAD_TOKEN              secret for PUT /api/files/<name> (required, >= 24 chars)
  DATA_DIR                  where the page files live (default /data)
  PORT                      listen port (default 8080)
  MAX_UPLOAD_MB             per-file upload limit (default 20)

Requests are logged without IP addresses.
"""
import base64
import hashlib
import hmac
import json
import os
import shutil
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

def env(name, default=""):
    # tolerate .env files edited on Windows (\r) or with quoted values
    return os.environ.get(name, default).strip().strip("'\"").strip()


DATA_DIR = Path(env("DATA_DIR", "/data"))
PORT = int(env("PORT", "8080"))
VIEW_USER = env("VIEW_USER")
VIEW_PASSWORD = env("VIEW_PASSWORD")
UPLOAD_TOKEN = env("UPLOAD_TOKEN")
MAX_BYTES = int(float(env("MAX_UPLOAD_MB", "20")) * 1024 * 1024)

FILES = {"index.html": "text/html; charset=utf-8", "thumbs.jpg": "image/jpeg"}
ROUTES = {"/": "index.html", "/index.html": "index.html", "/thumbs.jpg": "thumbs.jpg"}

PLACEHOLDER = """<!doctype html><html lang="de"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pikmin-Herbarium</title>
<body style="font:16px/1.5 system-ui,sans-serif;margin:3rem auto;max-width:34rem;padding:0 1rem;color:#1d2b21">
<h1>Pikmin-Herbarium</h1>
<p>Noch keine Daten hochgeladen. Im Menü <code>pikmin.bat</code> den Punkt
<strong>Veröffentlichen</strong> wählen.</p></body></html>""".encode("utf-8")


PUBLIC = not (VIEW_USER or VIEW_PASSWORD)


def check_config():
    if not UPLOAD_TOKEN:
        sys.exit("Fehlende Umgebungsvariable: UPLOAD_TOKEN")
    if bool(VIEW_USER) != bool(VIEW_PASSWORD):
        sys.exit("VIEW_USER und VIEW_PASSWORD nur zusammen setzen (oder beide weglassen = öffentlich).")
    if len(UPLOAD_TOKEN) < 24:
        sys.exit("UPLOAD_TOKEN ist zu kurz (mindestens 24 Zeichen).")


def same(a, b):
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class Handler(BaseHTTPRequestHandler):
    server_version = "PikminHerbarium"
    sys_version = ""

    def log_message(self, format, *args):
        # without the client address: the log tells what happened, not who asked
        sys.stderr.write(f"{self.log_date_time_string()} {format % args}\n")

    def send(self, status, body=b"", ctype="text/plain; charset=utf-8", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def viewer_ok(self):
        if PUBLIC:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            user, _, password = base64.b64decode(header[6:], validate=True).decode("utf-8").partition(":")
        except (ValueError, UnicodeDecodeError):
            return False
        return same(user, VIEW_USER) & same(password, VIEW_PASSWORD)  # no short-circuit timing

    def uploader_ok(self):
        header = self.headers.get("Authorization", "")
        return header.startswith("Bearer ") and same(header[7:].strip(), UPLOAD_TOKEN)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            return self.send(200, b"ok")
        if not self.viewer_ok():
            return self.send(401, "Anmeldung erforderlich".encode("utf-8"),
                             extra={"WWW-Authenticate": 'Basic realm="Pikmin-Herbarium", charset="UTF-8"'})
        name = ROUTES.get(path)
        if name is None:
            return self.send(404, b"Nicht gefunden")
        file = DATA_DIR / name
        if not file.exists():
            if name == "index.html":
                return self.send(200, PLACEHOLDER, FILES[name], {"Cache-Control": "no-cache"})
            return self.send(404, b"Nicht gefunden")
        return self.send(200, file.read_bytes(), FILES[name], {"Cache-Control": "no-cache"})

    do_HEAD = do_GET

    def do_PUT(self):
        path = self.path.split("?", 1)[0]
        if not path.startswith("/api/files/"):
            return self.send(404, b"Nicht gefunden")
        if not self.uploader_ok():
            return self.send(401, "Upload-Token fehlt oder ist falsch".encode("utf-8"))
        name = path[len("/api/files/"):]
        if name not in FILES:
            return self.send(403, "Dateiname nicht erlaubt".encode("utf-8"))
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self.send(411, b"Content-Length fehlt")
        if not 0 < length <= MAX_BYTES:
            return self.send(413, "Datei leer oder zu groß".encode("utf-8"))

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=f".{name}.", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as out:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        raise ConnectionError("Upload abgebrochen")
                    out.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
                out.flush()
                os.fsync(out.fileno())
            target = DATA_DIR / name
            if target.exists():
                shutil.copy2(target, DATA_DIR / f"{name}.prev")  # previous version stays as backup
            os.replace(tmp, target)  # atomic: viewers never see a half-written file
        except Exception as error:  # noqa: BLE001 - report any failure to the uploader
            Path(tmp).unlink(missing_ok=True)
            return self.send(400, f"Upload fehlgeschlagen: {error}".encode("utf-8"))
        body = json.dumps({"name": name, "bytes": length, "sha256": digest.hexdigest()}).encode("utf-8")
        return self.send(200, body, "application/json")


def main():
    check_config()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    access = "öffentlich" if PUBLIC else "mit Login"
    print(f"Pikmin-Herbarium läuft auf Port {PORT} ({access}), Daten in {DATA_DIR}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
