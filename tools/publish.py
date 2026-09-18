"""Upload the built page (web/thumbs.jpg + web/index.html) to the Pikmin-Herbarium server.

Config (never committed): publish.local.json in the project folder, see publish.example.json
    {"url": "https://pikmin.example.com", "token": "<UPLOAD_TOKEN of the server>"}

Usage: py tools/publish.py
"""
import hashlib
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "publish.local.json"
# portraits first: the new page never points at an outdated sprite
FILES = ["thumbs.jpg", "index.html"]


def tls_context():
    """Prefer certifi's current CA bundle: the Windows store can still hold an expired
    'ISRG Root X2' (2025-09-15) that OpenSSL picks for Let's Encrypt chains -> 'certificate has expired'."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def check_token(url, token, context):
    """Tiny request first: the server rejects a wrong token before reading a large upload and
    closes the connection, which the client would only see as 'connection aborted'.
    A not-allowed file name is checked after the token: 403 = token ok, 401 = token wrong."""
    request = urllib.request.Request(f"{url}/api/files/token-check", data=b"x", method="PUT",
                                     headers={"Authorization": f"Bearer {token}"})
    try:
        urllib.request.urlopen(request, timeout=30, context=context)
    except urllib.error.HTTPError as error:
        if error.code == 403:
            return
        if error.code == 401:
            sys.exit("Upload-Token passt nicht zum Server. UPLOAD_TOKEN in der .env auf dem Server prüfen "
                     "(gleicher Wert wie 'token' in publish.local.json, ohne Anführungszeichen, "
                     "Unix-Zeilenenden) und danach 'docker compose up -d'.")
        sys.exit(f"Token-Prüfung: Server meldet {error.code}")
    except urllib.error.URLError as error:
        sys.exit(f"Server nicht erreichbar ({url}): {error.reason}")


def main():
    context = tls_context()
    if not CONFIG.exists():
        sys.exit(f"{CONFIG.name} fehlt - Vorlage siehe README (url + token).")
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    url = cfg["url"].rstrip("/")
    check_token(url, cfg["token"], context)
    for name in FILES:
        path = ROOT / "web" / name
        if not path.exists():
            sys.exit(f"{path} fehlt - erst 'Übernehmen + Seite bauen'.")
        data = path.read_bytes()
        request = urllib.request.Request(
            f"{url}/api/files/{name}", data=data, method="PUT",
            headers={"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/octet-stream"})
        try:
            with urllib.request.urlopen(request, timeout=180, context=context) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            sys.exit(f"{name}: Server meldet {error.code} - {error.read().decode('utf-8', 'replace')}")
        except urllib.error.URLError as error:
            sys.exit(f"Server nicht erreichbar ({url}): {error.reason}")
        if result.get("sha256") != hashlib.sha256(data).hexdigest():
            sys.exit(f"{name}: Prüfsumme stimmt nicht - bitte nochmal veröffentlichen.")
        print(f"  {name}: {len(data) / 1024:.0f} KB hochgeladen, Prüfsumme ok")
    print(f"Veröffentlicht: {url}")


if __name__ == "__main__":
    main()
