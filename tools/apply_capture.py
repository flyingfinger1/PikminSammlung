"""Write a reviewed capture into data/pikmin.tsv and rebuild the portrait sprite.

Run diff_capture.py first and read its report. This step then:
- updates matched Pikmin (name/decor, favourite, hearts, steps, spot decor, location)
- keeps an existing street name when the capture only shows coordinates
- appends new Pikmin with fresh frame numbers
- recuts every portrait from the capture screenshots into web/thumbs.jpg

Usage: py tools/apply_capture.py captures/<run>
"""
import argparse
import csv
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from capture_adb import SCROLLED_Y  # noqa: E402
from lang import LANGS  # noqa: E402
from ui import location as show_loc, name as show_name, spot as show_spot, tr  # noqa: E402
from diff_capture import dedupe, is_coords, load_new, load_old, match_rows, sim  # noqa: E402

from paths import ROOT  # noqa: E402
CROP = (0.13, 0.10, 0.87, 0.385)   # same framing as make_thumbs.py
REF_HEIGHT = 2340                    # captures are 1080 wide; taller screens only add height
BUTTON_Y, BUTTON_GAP = 993, 93      # OCR top of "Zur Gruppe hinzufügen" on an unscrolled card; crop ends 93px above
THUMB_W, THUMB_H, COLS = 160, 133, 20
FIELDS = ["frame", "name", "fav", "hearts", "steps", "spot", "decor", "location", "date", "seen", "motif",
          "goldhearts"]


def hearts_text(n):
    h = float(n["hearts"] or 0)
    return f"{h:g}" + ("+G" if n["gold"] == "1" else "")


def clean_origin(text):
    return re.sub(r"\bInder\b", "In der", text).strip(" :") if text else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--remove-missing", action="store_true",
                    help=tr("Pikmin entfernen, die im Scan nicht mehr vorkommen (freigelassen)",
                            "remove Pikmin that are not in the scan any more (released)"))
    args = ap.parse_args()
    run = args.run
    seen = run.name[:10]
    new_rows, _ = dedupe(load_new(run))
    old_rows = load_old()
    match = match_rows(new_rows, old_rows)
    source = {}  # frame -> capture number (for the portrait)

    for i, (j, _) in match.items():
        n, o = new_rows[i], old_rows[j]
        old_base, _, old_origin = o["name"].partition(" aus ")
        o["name"] = n["name"] + (" aus " + old_origin if old_origin else "")
        o["fav"] = n["fav"]
        o["hearts"] = hearts_text(n)
        o["steps"] = n["steps"]
        o["decor"] = n["spot_decor"] or o["decor"]
        # OCR adds small typos ("Matze/s"): only replace coordinates or a clearly different place
        if n["location"] and not is_coords(n["location"]) and (
                is_coords(o["location"]) or sim(n["location"], o["location"]) < 0.8):
            o["location"] = n["location"]
        o["seen"] = seen
        # a Pikmin never changes its set: keep the known one when the scan could not tell
        o["motif"] = n.get("variant") or o.get("motif", "")
        o["goldhearts"] = n.get("gold_hearts", "")
        source[o["frame"]] = int(n["n"])

    # before removal: frame numbers are never reused
    next_frame = max((int(o["frame"]) for o in old_rows), default=0) + 1
    matched_old = {j for j, _ in match.values()}
    gone = [o for j, o in enumerate(old_rows) if j not in matched_old]
    if gone and args.remove_missing:
        old_rows = [o for j, o in enumerate(old_rows) if j in matched_old]
    added = []
    for i, n in enumerate(new_rows):
        if i in match:
            continue
        origin = clean_origin(n["origin"])
        row = {"frame": f"{next_frame:03d}", "name": n["name"] + (" aus " + origin if origin else ""),
               "fav": n["fav"], "hearts": hearts_text(n), "steps": n["steps"], "spot": n["spot"],
               "decor": n["spot_decor"], "location": n["location"], "date": n["date"], "seen": seen,
               "motif": n.get("variant", ""), "goldhearts": n.get("gold_hearts", "")}
        old_rows.append(row)
        source[row["frame"]] = int(n["n"])
        added.append(row)
        next_frame += 1

    tsv = ROOT / "data/pikmin.tsv"
    tsv.parent.mkdir(parents=True, exist_ok=True)
    if tsv.exists():
        shutil.copy(tsv, tsv.with_suffix(".tsv.bak"))
    with tsv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(old_rows)

    frames = max(int(o["frame"]) for o in old_rows)
    rows = -(-frames // COLS)
    sheet = Image.new("RGB", (COLS * THUMB_W, rows * THUMB_H), "white")
    if (ROOT / "web/thumbs.jpg").exists():  # frames without a capture keep their old portrait
        sheet.paste(Image.open(ROOT / "web/thumbs.jpg"), (0, 0))
    # anchor the portrait on the group button: a slightly scrolled page moves everything up
    button_y = {}
    for line in (run / "log.jsonl").open(encoding="utf-8"):
        rec = json.loads(line)
        squad = LANGS[rec.get("lang", "de")]["squad"]
        ys = [y for y, t in rec["lines"] if squad in t and y < SCROLLED_Y]
        if ys:
            button_y[rec["n"]] = ys[0]
    for frame, cap in source.items():
        img = Image.open(run / f"{cap:03d}.png").convert("RGB")
        w = img.width
        height = int((CROP[3] - CROP[1]) * REF_HEIGHT)
        bottom = button_y.get(cap, BUTTON_Y) - BUTTON_GAP
        top = max(bottom - height, 0)
        crop = img.crop((int(CROP[0] * w), top, int(CROP[2] * w), top + height))
        k = int(frame) - 1
        sheet.paste(crop.resize((THUMB_W, THUMB_H)), ((k % COLS) * THUMB_W, (k // COLS) * THUMB_H))
    (ROOT / "web").mkdir(exist_ok=True)
    sheet.save(ROOT / "web/thumbs.jpg", quality=85)

    print(tr(f"{len(match)} aktualisiert, {len(added)} neu, {len(source)} Porträts neu geschnitten",
             f"{len(match)} updated, {len(added)} new, {len(source)} portraits recut"))
    for r in added:
        print(f"  [{r['frame']}] {show_name(r['name'])} · {show_spot(r['spot'])} · {show_loc(r['location'])} · {r['date']}")
    if gone:
        what = tr("entfernt", "removed") if args.remove_missing else \
            tr("nicht im Scan, bleiben erhalten", "not in the scan, kept")
        print(f"{len(gone)} {what}:")
        for o in gone:
            print(f"  [{o['frame']}] {show_name(o['name'])} · {show_loc(o['location'])} · {o['date']}")


if __name__ == "__main__":
    main()
