"""Upload the built page (web/thumbs.jpg + web/index.html) to the Pikmin-Herbarium server.

Config (never committed): publish.local.json in the project folder
    {"url": "https://pikmin-sammlung.flyingfinger.de", "token": "<UPLOAD_TOKEN of the server>"}

Usage: py tools/publish.py
"""
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "publish.local.json"
# portraits first: the new page never points at an outdated sprite
FILES = ["thumbs.jpg", "index.html"]


def main():
    if not CONFIG.exists():
        sys.exit(f"{CONFIG.name} fehlt - Vorlage siehe README (url + token).")
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    url = cfg["url"].rstrip("/")
    for name in FILES:
        path = ROOT / "web" / name
        if not path.exists():
            sys.exit(f"{path} fehlt - erst 'Übernehmen + Seite bauen'.")
        data = path.read_bytes()
        request = urllib.request.Request(
            f"{url}/api/files/{name}", data=data, method="PUT",
            headers={"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/octet-stream"})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
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
