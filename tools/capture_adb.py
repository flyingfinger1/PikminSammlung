"""Page through the Pikmin detail view over ADB and save one checked screenshot per Pikmin.

Open the first Pikmin's detail view on the phone, connect it via USB (USB debugging on,
"Nicht stören" recommended), then run:

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

ROOT = Path(__file__).resolve().parent.parent
OCR_PS1 = ROOT / "tools" / "ocr.ps1"
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


def adb_path():
    found = shutil.which("adb")
    if found:
        return found
    if ADB_FALLBACK.exists():
        return str(ADB_FALLBACK)
    sys.exit("adb not found - install Google.PlatformTools")


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
            print(f"  adb-Fehler ({last or 'ohne Meldung'}), neuer Versuch ...", flush=True)
            subprocess.run([ADB, "wait-for-device"], capture_output=True, timeout=60)
            time.sleep(2)
    raise AdbError(last or f"adb {' '.join(args[:2])} fehlgeschlagen")


def ensure_device():
    lines = [l for l in adb("devices").splitlines()[1:] if l.strip()]
    if not lines:
        sys.exit("Kein Handy gefunden. USB-Debugging an? Kabel mit Datenübertragung?")
    if any("unauthorized" in l for l in lines):
        sys.exit("Handy fragt nach Erlaubnis: auf dem Handy 'USB-Debugging zulassen' bestätigen.")


def foreground_app():
    out = adb("shell", "dumpsys", "window")
    for line in out.splitlines():
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            return line.strip()
    return ""


def screenshot():
    png = adb("exec-out", "screencap", "-p", binary=True)
    return Image.open(io.BytesIO(png)).convert("RGB")


def signature(img):
    w, h = img.size
    card = img.crop((0, int(h * CARD_TOP), w, int(h * CARD_BOTTOM))).convert("L")
    small = card.resize((216, round(card.height * 216 / w)))
    return np.asarray(small, dtype=np.int16)


def same(a, b):
    return np.abs(a - b).mean(axis=1).max() < SAME_CARD


def ocr(path):
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                          "-File", str(OCR_PS1), str(path)], capture_output=True)
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
    missing = [k for k, needle in (("Name", "Pikmin"), ("Schritte", "Schritte"),
                                   ("Entdeckt", "Entdeckt")) if needle not in text]
    return missing


def card_key(lines, height):
    """Name, steps and discovery date of a card - the floating egg button over the location
    text changes the image of an unchanged card, but not these lines."""
    return tuple(t for y, t in lines if height * CARD_TOP < y < SCROLLED_Y
                 and ("Pikmin" in t or "Schritte" in t or "Entdeckt" in t))


def swipe(size):
    w, h = size
    y = int(h * SWIPE_Y)
    adb("shell", "input", "swipe", str(int(w * SWIPE_FROM)), str(y),
        str(int(w * SWIPE_TO)), str(y), "300")


SCROLLED_Y = 5000  # y offset marking OCR lines taken from the scrolled-up screenshot


def reveal_lower_card(out_dir, n):
    """Long locations push 'Entdeckt' under the nav bar: scroll up, read, scroll back."""
    if PACKAGE_HINT not in foreground_app().lower():
        return []
    adb("shell", "input", "swipe", "540", "1750", "540", "1150", "600")
    time.sleep(1.5)
    path = out_dir / f"{n:03d}_b.png"
    screenshot().save(path)
    lines = [(y + SCROLLED_Y, t) for y, t in ocr(path)]
    adb("shell", "input", "swipe", "540", "1150", "540", "1750", "600")
    time.sleep(1.2)
    return lines


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
        why = "abgedunkelt (Dialog?)" if dimmed else "nicht lesbar: " + ", ".join(missing)
        print(f"  #{n:03d} {why} - Versuch {attempt}/{RETRIES_UNREADABLE}", flush=True)
        time.sleep(2)
    path.unlink()  # so --resume retakes this card instead of skipping it
    return None, None, None


def run(out_dir, start_n, test=False):
    try:
        _run(out_dir, start_n, test)
    except (AdbError, subprocess.TimeoutExpired) as e:
        print(f"\nAbbruch: Verbindung zum Handy unterbrochen ({e}).\n"
              f"Kabel prüfen, Handy entsperren, Pikmin Bloom offen lassen, dann weiter mit:\n"
              f"  py tools/capture_adb.py --resume {out_dir}")


def _run(out_dir, start_n, test=False):
    ensure_device()
    front = foreground_app()
    if PACKAGE_HINT not in front.lower():
        sys.exit(f"Pikmin Bloom ist nicht im Vordergrund: {front}")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Ordner: {out_dir}", flush=True)
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
            print(f"Karte #{start_n - 1:03d} ist schon gespeichert - wische weiter.", flush=True)
            swipe(Image.open(last).size)
            time.sleep(SETTLE)
            if same(signature(screenshot()), last_sig):
                print(f"Ende: nach #{start_n - 1:03d} ändert Wischen nichts mehr.")
                return
    while True:
        img, sig, lines = capture_checked(out_dir, n, base)
        if img is None:
            print(f"Abbruch bei #{n:03d}: Karte bleibt unlesbar. Problem am Handy beheben, dann "
                  f"weiter mit: py tools/capture_adb.py --resume {out_dir}")
            return
        base = sig.mean() if base is None else base
        key = card_key(lines, img.height)
        repeat = next((i for i, s in seen if same(s, sig)), None)
        if repeat is None and seen and key and key == seen_keys.get(seen[-1][0]):
            repeat = seen[-1][0]  # same text; only the floating egg button changed the image
        if repeat is not None:
            for suffix in ("", "_b"):
                (out_dir / f"{n:03d}{suffix}.png").unlink(missing_ok=True)
            print(f"Ende: Karte #{n:03d} gleicht #{repeat:03d}. {n - start_n} Pikmin erfasst.")
            return
        seen.append((n, sig))
        seen_keys[n] = key
        name = next((t for y, t in lines if "Pikmin" in t), "?")
        log.write(json.dumps({"n": n, "lines": lines}, ensure_ascii=False) + "\n")
        log.flush()
        print(f"#{n:03d} {name}", flush=True)
        if test:
            print("Test: wische einmal ...")
        # next card; retry the swipe if nothing changed
        for attempt in range(1, RETRIES_SWIPE + 1):
            if PACKAGE_HINT not in foreground_app().lower():
                print("Abbruch: Pikmin Bloom ist nicht mehr im Vordergrund.")
                return
            swipe(img.size)
            time.sleep(SETTLE)
            if not same(signature(screenshot()), sig):
                break
        else:
            print(f"Ende: nach #{n:03d} ändert Wischen nichts mehr. {n - start_n + 1} Pikmin erfasst.")
            return
        n += 1
        if test and n > start_n + 1:
            print("Test fertig.")
            return


def single(run_dir):
    """Re-take only the open card (e.g. a popup covered it) and replace its earlier shot."""
    from parse_captures import parse_card  # local import: parse_captures imports this module

    ensure_device()
    if PACKAGE_HINT not in foreground_app().lower():
        sys.exit("Pikmin Bloom ist nicht im Vordergrund.")
    tmp = 999
    for stale in run_dir.glob(f"{tmp}*.png"):
        stale.unlink()
    img, _, lines = capture_checked(run_dir, tmp, None)
    if img is None:
        sys.exit("Karte nicht lesbar - Popup schließen und nochmal.")
    card = parse_card(run_dir, {"n": tmp, "lines": lines})

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
    recs = [r for r in recs if r["n"] not in (n, tmp)] + [{"n": n, "lines": lines, "source": "single"}]
    recs.sort(key=lambda r: r["n"])
    with log_path.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    what = "ersetzt" if target else "neu angehängt"
    print(f"#{n:03d} {card['name']} ({card['steps']} Schritte, {card['date']}) {what}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--resume", type=Path)
    ap.add_argument("--single", type=Path, help="Laufordner: nur die offene Karte neu aufnehmen")
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
