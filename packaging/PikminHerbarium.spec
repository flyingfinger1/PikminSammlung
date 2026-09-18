# PyInstaller spec of the Windows app (one folder). Build with: py packaging/build.py
from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "tools" / "app.py")],
    pathex=[str(ROOT / "tools")],
    datas=[
        (str(ROOT / "tools" / "ocr.ps1"), "tools"),
        (str(ROOT / "web" / "template.html"), "web"),
    ],
    excludes=["tkinter", "unittest", "pydoc_data"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PikminHerbarium",
    console=True,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PikminHerbarium", upx=False)
