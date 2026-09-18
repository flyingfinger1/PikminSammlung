"""Page through the Pikmin detail view over ADB and save one checked screenshot per Pikmin.

Open the first Pikmin's detail view on the phone, connect it via USB (USB debugging on,
"Do not disturb" recommended), then run:

    py tools/capture_adb.py --test          # one screenshot + one swipe, reports what it saw
    py tools/capture_adb.py                 # full run into captures/<date>/
    py tools/capture_adb.py --resume DIR    # continue a stopped run

The script only takes screenshots and swipes. Before every swipe it checks that Pikmin Bloom
is the app in front; otherwise it stops.
"""
import argparse
import datetime as dt
import io
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from lang import LANGS, detect  # noqa: E402
from paths import RES, ROOT  # noqa: E402
from ui import name, tr  # noqa: E402

OCR_PS1 = RES / "tools" / "ocr.ps1"
ADB_FALLBACK = (Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
                / "Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe")
PACKAGE_HINT = "pikmin"  # substring of the foreground package name

CARD_TOP, CARD_BOTTOM = 0.42, 0.93   # text card, fraction of screen height
SWIPE_Y = 0.50                        # across the name line; on the 3D model it only rotates
SWIPE_FROM, SWIPE_TO = 0.85, 0.15     # right-to-left = next Pikmin
SETTLE = 1.3                          # seconds for the page animation
SAME_CARD = 8.0                       # max row diff (gray, 216px wide) for "same card"
DIM_DROP = 40                         # card this much darker than the first = dialog on top
RETRIES_UNREADABLE = 5
RETRIES_SWIPE = 3
LANG = LANGS["de"]  # game language, detected from the first card of a run


ADB_LOCAL = ROOT / "platform-tools" / "adb.exe"  # downloaded next to the app
ADB_ZIP = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"


def adb_path():
    found = shutil.which("adb")
    if found:
        return found
    for path in (ADB_LOCAL, ADB_FALLBACK):
        if path.exists():
            return str(path)
    return download_adb()


def download_adb():
    """Google's licence does not allow passing the Platform-Tools on, so they are not part of the
    app: offer to fetch the official package from Google into the app folder instead."""
    print(tr("adb (Android Platform-Tools) wurde nicht gefunden. Es wird für den Scan gebraucht.\n"
             "Das offizielle Paket von Google (ca. 7 MB) kann jetzt nach\n"
             f"  {ADB_LOCAL.parent}\n"
             "geladen werden. Es gelten Googles Bedingungen:\n"
             "  https://developer.android.com/tools/releases/platform-tools",
             "adb (Android Platform-Tools) was not found. The scan needs it.\n"
             "The official package from Google (about 7 MB) can be downloaded to\n"
             f"  {ADB_LOCAL.parent}\n"
             "now. Google's terms apply:\n"
             "  https://developer.android.com/tools/releases/platform-tools"))
    answer = input(tr("Jetzt herunterladen? [j/N] ", "Download now? [y/N] ")) if sys.stdin.isatty() else ""
    if answer.strip().lower() not in ("j", "ja", "y", "yes"):
        sys.exit(tr("Ohne adb kein Scan. Alternative: winget install Google.PlatformTools",
                    "No scan without adb. Alternative: winget install Google.PlatformTools"))
    import ssl
    import urllib.request
    import zipfile
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    request = urllib.request.Request(ADB_ZIP, headers={"User-Agent": "PikminHerbarium"})
    with urllib.request.urlopen(request, timeout=120, context=context) as response:
        data = response.read()
    zipfile.ZipFile(io.BytesIO(data)).extractall(ROOT)  # the zip holds a platform-tools/ folder
    if not ADB_LOCAL.exists():
        sys.exit(tr("Download ohne adb.exe - bitte adb selbst installieren.",
                    "The download holds no adb.exe - please install adb yourself."))
    print(tr(f"adb liegt jetzt in {ADB_LOCAL.parent}", f"adb is now in {ADB_LOCAL.parent}"))
    return str(ADB_LOCAL)


ADB = None  # resolved on first use: parsing/applying imports this module but needs no adb


class AdbError(RuntimeError):
    pass


def adb(*args, binary=False, attempts=3):
    """Run adb; a short USB hiccup or standby gets retried after waiting for the device."""
    global ADB
    if ADB is None:
        ADB = adb_path()
    last = ""
    for attempt in range(attempts):
        out = subprocess.run([ADB, *args], capture_output=True)
        if out.returncode == 0:
            return out.stdout if binary else out.stdout.decode("utf-8", "replace")
        last = (out.stderr or out.stdout).decode("utf-8", "replace").strip()
        if attempt + 1 < attempts:
            print(tr(f"  adb-Fehler ({last or 'ohne Meldung'}), neuer Versuch ...",
                     f"  adb error ({last or 'no message'}), trying again ..."), flush=True)
            try:
                subprocess.run([ADB, "wait-for-device"], capture_output=True, timeout=30)
            except subprocess.TimeoutExpired:
                break  # no device came back - report instead of hanging
            time.sleep(2)
    raise AdbError(last or tr(f"adb {' '.join(args[:2])} fehlgeschlagen", f"adb {' '.join(args[:2])} failed"))


def ensure_device():
    lines = [l for l in adb("devices").splitlines()[1:] if l.strip()]
    if not lines:
        sys.exit(tr("Kein Handy gefunden. USB-Debugging an? Kabel mit Datenübertragung?",
                    "No phone found. USB debugging on? A cable that carries data?"))
    if any("unauthorized" in l for l in lines):
        sys.exit(tr("Handy fragt nach Erlaubnis: auf dem Handy 'USB-Debugging zulassen' bestätigen.",
                    "The phone asks for permission: confirm 'Allow USB debugging' on the phone."))


def foreground_app():
    out = adb("shell", "dumpsys", "window")
    for line in out.splitlines():
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            return line.strip()
    return ""


REF_WIDTH = 1080  # every pixel constant of the analysis is calibrated for this width
DEVICE = None     # real screen size (w, h), for input events


def screenshot():
    """Screenshot scaled to REF_WIDTH. Pikmin Bloom scales its UI with the screen width, so the
    fixed positions (heart row, star, crops) hold on other resolutions; vertical differences
    are covered by anchoring on recognised text lines."""
    global DEVICE
    png = adb("exec-out", "screencap", "-p", binary=True)
    img = Image.open(io.BytesIO(png)).convert("RGB")
    DEVICE = img.size
    if img.width != REF_WIDTH:
        img = img.resize((REF_WIDTH, round(img.height * REF_WIDTH / img.width)), Image.LANCZOS)
    return img


def swipe_frac(x1, y1, x2, y2, ms):
    """Swipe given in fractions of the real screen."""
    if DEVICE is None:
        screenshot()
    w, h = DEVICE
    adb("shell", "input", "swipe", str(int(w * x1)), str(int(h * y1)),
        str(int(w * x2)), str(int(h * y2)), str(ms))


def signature(img):
    w, h = img.size
    card = img.crop((0, int(h * CARD_TOP), w, int(h * CARD_BOTTOM))).convert("L")
    small = card.resize((216, round(card.height * 216 / w)))
    return np.asarray(small, dtype=np.int16)


def same(a, b):
    return np.abs(a - b).mean(axis=1).max() < SAME_CARD


def ocr(path, lang=None):
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                          "-File", str(OCR_PS1), str(path), (lang or LANG)["ocr"]], capture_output=True)
    lines = []
    for raw in out.stdout.decode("utf-8", "replace").splitlines():
        y, _, text = raw.partition("\t")
        if y.strip().isdigit():
            lines.append((int(y), text.strip()))
    return lines


def readable(lines, height):
    """Card fields present below the model: name, steps, discovery date."""
    card = [t for y, t in lines if y > height * CARD_TOP]
    text = " ".join(card)
    return [k for k, needle in (("Name", "Pikmin"), ("Schritte", LANG["steps"]),
                                ("Entdeckt", LANG["discovered"])) if needle not in text]


def card_key(lines, height):
    """Name, steps and discovery date of a card - the floating egg button over the location
    text changes the image of an unchanged card, but not these lines."""
    return tuple(t for y, t in lines if height * CARD_TOP < y < SCROLLED_Y
                 and ("Pikmin" in t or LANG["steps"] in t or LANG["discovered"] in t))


def swipe():
    swipe_frac(SWIPE_FROM, SWIPE_Y, SWIPE_TO, SWIPE_Y, 300)


SCROLLED_Y = 5000  # y offset marking OCR lines taken from the scrolled-up screenshot


def reveal_lower_card(out_dir, n):
    """Long locations push 'Entdeckt' under the nav bar: scroll up, read, scroll back."""
    if PACKAGE_HINT not in foreground_app().lower():
        return []
    swipe_frac(0.5, 0.748, 0.5, 0.491, 600)  # was 540,1750 -> 540,1150 on 1080x2340
    time.sleep(1.5)
    path = out_dir / f"{n:03d}_b.png"
    screenshot().save(path)
    lines = [(y + SCROLLED_Y, t) for y, t in ocr(path)]
    swipe_frac(0.5, 0.491, 0.5, 0.748, 600)
    time.sleep(1.2)
    return lines


def detect_language(out_dir):
    """Set LANG from the open card: OCR it once, the card words work with either OCR language."""
    global LANG
    path = out_dir / "_lang.png"
    screenshot().save(path)
    code = detect(ocr(path, LANGS["de"]))
    path.unlink()
    if code is None:
        sys.exit(tr("Keine Pikmin-Detailansicht erkannt (Sprache unklar). Karte öffnen und nochmal.",
                    "No Pikmin detail view found (language unclear). Open a card and try again."))
    LANG = LANGS[code]
    print(tr(f"Spielsprache: {code}", f"Game language: {code}"), flush=True)
    return code


def capture_checked(out_dir, n, base_brightness):
    """Screenshot until the card is readable and not dimmed; returns (img, sig, lines)."""
    for attempt in range(1, RETRIES_UNREADABLE + 1):
        img = screenshot()
        path = out_dir / f"{n:03d}.png"
        img.save(path)
        sig = signature(img)
        dimmed = base_brightness is not None and sig.mean() < base_brightness - DIM_DROP
        lines = ocr(path)
        missing = readable(lines, img.height)
        if not dimmed and missing == ["Entdeckt"]:
            lines += reveal_lower_card(out_dir, n)
            missing = readable(lines, img.height)
        if not dimmed and not missing:
            return img, sig, lines
        shown = {"Schritte": tr("Schritte", "steps"), "Entdeckt": tr("Entdeckt", "Discovered")}
        why = tr("abgedunkelt (Dialog?)", "dimmed (dialog?)") if dimmed else \
            tr("nicht lesbar: ", "not readable: ") + ", ".join(shown.get(m, m) for m in missing)
        print(tr(f"  #{n:03d} {why} - Versuch {attempt}/{RETRIES_UNREADABLE}",
                 f"  #{n:03d} {why} - attempt {attempt}/{RETRIES_UNREADABLE}"), flush=True)
        time.sleep(2)
    path.unlink()  # so --resume retakes this card instead of skipping it
    return None, None, None


def run(out_dir, start_n, test=False):
    try:
        _run(out_dir, start_n, test)
    except (AdbError, subprocess.TimeoutExpired) as e:
        print(tr(f"\nAbbruch: Verbindung zum Handy unterbrochen ({e}).\n"
                 f"Kabel prüfen, Handy entsperren, Pikmin Bloom offen lassen, dann weiter mit:\n",
                 f"\nStopped: connection to the phone lost ({e}).\n"
                 f"Check the cable, unlock the phone, keep Pikmin Bloom open, then continue with:\n")
              + f"  py tools/capture_adb.py --resume {out_dir}")


def _run(out_dir, start_n, test=False):
    ensure_device()
    front = foreground_app()
    if PACKAGE_HINT not in front.lower():
        sys.exit(tr(f"Pikmin Bloom ist nicht im Vordergrund: {front}", f"Pikmin Bloom is not in front: {front}"))
    out_dir.mkdir(parents=True, exist_ok=True)
    print(tr(f"Ordner: {out_dir}", f"Folder: {out_dir}"), flush=True)
    code = detect_language(out_dir)
    log = (out_dir / "log.jsonl").open("a", encoding="utf-8")
    seen = []
    seen_keys = {}
    base = None
    n = start_n
    last = out_dir / f"{start_n - 1:03d}.png"
    if last.exists():
        # resuming: if the phone still shows the last saved card, move on first
        last_sig = signature(Image.open(last).convert("RGB"))
        if same(signature(screenshot()), last_sig):
            print(tr(f"Karte #{start_n - 1:03d} ist schon gespeichert - wische weiter.",
                     f"Card #{start_n - 1:03d} is already saved - swiping on."), flush=True)
            swipe()
            time.sleep(SETTLE)
            if same(signature(screenshot()), last_sig):
                print(tr(f"Ende: nach #{start_n - 1:03d} ändert Wischen nichts mehr.",
                         f"End: swiping changes nothing after #{start_n - 1:03d}."))
                return
    while True:
        img, sig, lines = capture_checked(out_dir, n, base)
        if img is None:
            print(tr(f"Abbruch bei #{n:03d}: Karte bleibt unlesbar. Problem am Handy beheben, dann weiter mit: ",
                     f"Stopped at #{n:03d}: the card stays unreadable. Fix the phone, then continue with: ")
                  + f"py tools/capture_adb.py --resume {out_dir}")
            return
        base = sig.mean() if base is None else base
        key = card_key(lines, img.height)
        repeat = next((i for i, s in seen if same(s, sig)), None)
        if repeat is None and seen and key and key == seen_keys.get(seen[-1][0]):
            repeat = seen[-1][0]  # same text; only the floating egg button changed the image
        if repeat is not None:
            for suffix in ("", "_b"):
                (out_dir / f"{n:03d}{suffix}.png").unlink(missing_ok=True)
            print(tr(f"Ende: Karte #{n:03d} gleicht #{repeat:03d}. {n - start_n} Pikmin erfasst.",
                     f"End: card #{n:03d} equals #{repeat:03d}. {n - start_n} Pikmin captured."))
            return
        seen.append((n, sig))
        seen_keys[n] = key
        name = next((t for y, t in lines if "Pikmin" in t), "?")
        log.write(json.dumps({"n": n, "lines": lines, "device": list(DEVICE), "lang": code},
                             ensure_ascii=False) + "\n")
        log.flush()
        print(f"#{n:03d} {name}", flush=True)
        if test:
            print(tr("Test: wische einmal ...", "Test: swiping once ..."))
        # next card; retry the swipe if nothing changed
        for attempt in range(1, RETRIES_SWIPE + 1):
            if PACKAGE_HINT not in foreground_app().lower():
                print(tr("Abbruch: Pikmin Bloom ist nicht mehr im Vordergrund.",
                         "Stopped: Pikmin Bloom is no longer in front."))
                return
            swipe()
            time.sleep(SETTLE)
            if not same(signature(screenshot()), sig):
                break
        else:
            print(tr(f"Ende: nach #{n:03d} ändert Wischen nichts mehr. {n - start_n + 1} Pikmin erfasst.",
                     f"End: swiping changes nothing after #{n:03d}. {n - start_n + 1} Pikmin captured."))
            return
        n += 1
        if test and n > start_n + 1:
            print(tr("Test fertig.", "Test done."))
            return


def single(run_dir):
    """Re-take only the open card (e.g. a popup covered it) and replace its earlier shot."""
    from parse_captures import parse_card  # local import: parse_captures imports this module

    ensure_device()
    if PACKAGE_HINT not in foreground_app().lower():
        sys.exit(tr("Pikmin Bloom ist nicht im Vordergrund.", "Pikmin Bloom is not in front."))
    code = detect_language(run_dir)
    tmp = 999
    for stale in run_dir.glob(f"{tmp}*.png"):
        stale.unlink()
    img, _, lines = capture_checked(run_dir, tmp, None)
    if img is None:
        sys.exit(tr("Karte nicht lesbar - Popup schließen und nochmal.",
                    "Card not readable - close the popup and try again."))
    card = parse_card(run_dir, {"n": tmp, "lines": lines, "device": list(DEVICE), "lang": code})

    log_path = run_dir / "log.jsonl"
    recs = [json.loads(l) for l in log_path.open(encoding="utf-8")]
    parsed = run_dir / "parsed.tsv"
    if parsed.exists():  # already evaluated: no need to OCR all cards again
        import csv
        others = list(csv.DictReader(parsed.open(encoding="utf-8"), delimiter="\t"))
    else:
        others = [parse_card(run_dir, r) for r in recs if r["n"] != tmp]
    target = None
    for other in others:
        other["n"] = int(other["n"])
        if (other["date"], other["color"], other["name"]) == (card["date"], card["color"], card["name"]) \
                and abs(int(other["steps"] or 0) - int(card["steps"] or 0)) <= 5000:
            if target is None or abs(int(other["steps"] or 0) - int(card["steps"] or 0)) < target[1]:
                target = (other["n"], abs(int(other["steps"] or 0) - int(card["steps"] or 0)))
    n = target[0] if target else max(r["n"] for r in recs) + 1

    for suffix in ("", "_b"):
        src = run_dir / f"{tmp}{suffix}.png"
        dst = run_dir / f"{n:03d}{suffix}.png"
        if dst.exists():
            dst.unlink()
        if src.exists():
            src.rename(dst)
    recs = [r for r in recs if r["n"] not in (n, tmp)] + [{"n": n, "lines": lines, "source": "single",
                                                          "device": list(DEVICE), "lang": code}]
    recs.sort(key=lambda r: r["n"])
    with log_path.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    what = tr("ersetzt", "replaced") if target else tr("neu angehängt", "appended")
    print(f"#{n:03d} {name(card['name'])} ({card['steps']} {tr('Schritte', 'steps')}, {card['date']}) {what}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--resume", type=Path)
    ap.add_argument("--single", type=Path, help=tr("Laufordner: nur die offene Karte neu aufnehmen",
                                                   "run folder: re-take only the open card"))
    args = ap.parse_args()
    if args.single:
        single(args.single)
    elif args.resume:
        done = sorted(args.resume.glob("[0-9][0-9][0-9].png"))
        run(args.resume, int(done[-1].stem) + 1 if done else 1)
    else:
        stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
        run(ROOT / "captures" / (stamp + ("_test" if args.test else "")), 1, test=args.test)


if __name__ == "__main__":
    main()
