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

sys.path.insert(0, str(Path(__file__).parent))
from ui import tr  # noqa: E402

from paths import ROOT  # noqa: E402
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
            sys.exit(tr("Upload-Token passt nicht zum Server. UPLOAD_TOKEN in der .env auf dem Server prüfen "
                        "(gleicher Wert wie 'token' in publish.local.json, ohne Anführungszeichen, "
                        "Unix-Zeilenenden) und danach 'docker compose up -d'.",
                        "The upload token does not match the server. Check UPLOAD_TOKEN in the .env on the "
                        "server (same value as 'token' in publish.local.json, no quotes, Unix line endings), "
                        "then run 'docker compose up -d'."))
        sys.exit(tr(f"Token-Prüfung: Server meldet {error.code}", f"Token check: server answers {error.code}"))
    except urllib.error.URLError as error:
        sys.exit(tr(f"Server nicht erreichbar ({url}): {error.reason}", f"Server not reachable ({url}): {error.reason}"))


def main():
    context = tls_context()
    if not CONFIG.exists():
        sys.exit(tr(f"{CONFIG.name} fehlt - Vorlage siehe README (url + token).",
                    f"{CONFIG.name} is missing - see the README for the template (url + token)."))
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    url = cfg["url"].rstrip("/")
    check_token(url, cfg["token"], context)
    for name in FILES:
        path = ROOT / "web" / name
        if not path.exists():
            sys.exit(tr(f"{path} fehlt - erst 'Übernehmen + Seite bauen'.",
                        f"{path} is missing - run 'Apply + build page' first."))
        data = path.read_bytes()
        request = urllib.request.Request(
            f"{url}/api/files/{name}", data=data, method="PUT",
            headers={"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/octet-stream"})
        try:
            with urllib.request.urlopen(request, timeout=180, context=context) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            sys.exit(tr(f"{name}: Server meldet {error.code}", f"{name}: server answers {error.code}")
                     + f" - {error.read().decode('utf-8', 'replace')}")
        except urllib.error.URLError as error:
            sys.exit(tr(f"Server nicht erreichbar ({url}): {error.reason}", f"Server not reachable ({url}): {error.reason}"))
        if result.get("sha256") != hashlib.sha256(data).hexdigest():
            sys.exit(tr(f"{name}: Prüfsumme stimmt nicht - bitte nochmal veröffentlichen.",
                        f"{name}: checksum does not match - please publish again."))
        print(tr(f"  {name}: {len(data) / 1024:.0f} KB hochgeladen, Prüfsumme ok",
                 f"  {name}: {len(data) / 1024:.0f} KB uploaded, checksum ok"))
    print(tr(f"Veröffentlicht: {url}", f"Published: {url}"))


if __name__ == "__main__":
    main()
