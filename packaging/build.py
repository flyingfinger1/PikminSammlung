"""Build the Windows app: dist/PikminHerbarium/ (PikminHerbarium.exe + _internal/) and a zip of it.

Usage: py packaging/build.py [version]      (needs: py -m pip install -r requirements.txt pyinstaller)
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP = DIST / "PikminHerbarium"

QUICKSTART = """Pikmin Herbarium {version}
=========================

Start PikminHerbarium.exe - it opens the menu (German or English, following Windows or
"language" in config.local.json).

Your collection is kept in this folder, next to the exe: captures/, data/, web/ and your
settings. To update the app, replace PikminHerbarium.exe and _internal/ and keep the rest.

Needed on the PC:
- Windows 10/11 with the OCR language of your game language (German or English)
- adb (Android Platform-Tools): found automatically if installed
  (winget install Google.PlatformTools), otherwise the app offers to download it from Google

Settings (copy the example and edit it):
- config.local.json   <- config.example.json   (rare decor you unlocked, language)
- publish.local.json  <- publish.example.json  (your server, only for publishing)

Windows may warn on the first start because the app is not signed:
"More info" -> "Run anyway".

Full documentation: https://github.com/flyingfinger1/PikminSammlung
"""


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "dev"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(DIST), "--workpath", str(ROOT / "build"),
                    str(ROOT / "packaging" / "PikminHerbarium.spec")], check=True)
    for name in ("config.example.json", "publish.example.json", "LICENSE"):
        shutil.copy(ROOT / name, APP / name)
    (APP / "README.txt").write_text(QUICKSTART.format(version=version), encoding="utf-8")
    archive = shutil.make_archive(str(DIST / f"PikminHerbarium-{version}"), "zip", DIST, APP.name)
    print(f"-> {archive}")


if __name__ == "__main__":
    main()
