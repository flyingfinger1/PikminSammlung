"""Where things live. Run from source, everything is in the project folder. As the packaged app
(PyInstaller, one folder) the collection - captures/, data/, web/, the *.local.json settings -
lives next to PikminHerbarium.exe, while the bundled files (page template, OCR script) are
inside the app.
"""
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent
RES = Path(getattr(sys, "_MEIPASS", ROOT))
