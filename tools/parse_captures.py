"""Turn an ADB capture folder (NNN.png + log.jsonl from capture_adb.py) into parsed.tsv.

Text comes from the OCR lines in log.jsonl; hearts and the favourite star are read from
pixels. Anything doubtful is listed in the 'problems' column instead of being guessed.

Usage: py tools/parse_captures.py captures/<run>
"""
import csv
import datetime
import difflib
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from capture_adb import SCROLLED_Y, ocr  # noqa: E402

COLORS = {"Rot": "Rot", "Gelb": "Gelb", "Blau": "Blau", "Lila": "Lila", "Weiß": "Weiß",
          "Fels": "Fels", "Flügel": "Flügel", "Eis": "Eis"}
PLAIN = {"Rotes": "Rot", "Gelbes": "Gelb", "Blaues": "Blau", "Lila": "Lila",
         "Weißes": "Weiß", "Fels": "Fels", "Flügel": "Flügel", "Eis": "Eis"}
MONTHS = {"Jan": 1, "Feb": 2, "Mär": 3, "Mar": 3, "Apr": 4, "Mai": 5, "Jun": 6, "Jul": 7,
          "Aug": 8, "Sep": 9, "Okt": 10, "Nov": 11, "Dez": 12}
# the name is read up to the colour bracket (decor Pikmin) or "<Colour>es Pikmin"; the
# "aus" after it sits next to the star and OCR mangles it ("atJS", "a:-JS", "CIUS", ...)
BASE = re.compile(r"^(.+?-\s?Pikmin \([^)]+\)|(?:Rotes|Gelbes|Blaues|Lila|Weißes|Fels|Flügel|Eis)[ -]Pikmin)")
STEPS = re.compile(r"(\d{1,3}(?:\.\d{3})*)Schritte")  # fullmatch on the space-free line
ROOT = Path(__file__).resolve().parent.parent
# categories from the in-game decor collection (Sep 2026) plus whatever the data already has
_DATA = ROOT / "data/pikmin.json"
_SEEN_SPOTS = {p["spot"] for p in json.loads(_DATA.read_text(encoding="utf-8"))} if _DATA.exists() else set()
KNOWN_SPOTS = sorted(_SEEN_SPOTS | {
    "Restaurant", "Café", "Süßwarenladen", "Kino", "Apotheke", "Zoo", "Wald", "Am Wasser", "Post",
    "Kunstmuseum", "Flughafen", "Bahnhof", "Strand", "Burger-Bistro", "Eckladen", "Supermarkt",
    "Bäckerei", "Friseur", "Boutique", "Park", "Bibliothek/Bücherladen", "Straße", "Sushi-Restaurant",
    "Berg", "Stadion", "Regentag", "Schneetag", "Themenpark", "Bushaltestelle",
    "Italienisches Restaurant", "Ramen-Restaurant", "Brücke", "Hotel", "Kosmetik-Laden",
    "Schreine und Tempel", "Elektroladen", "Curry-Restaurant", "Baumarkt", "Universität & College",
    "Mexikanisches Restaurant", "Waschsalons & Reinigungen", "Koreanisches Restaurant",
    "Schreibwarenladen", "Extra"})


def steps_text(t):
    t = t.replace(" ", "")
    t = re.sub(r"^[OoD](?=Schritte)", "0", t)  # a lone 0 read as the letter O
    for _ in range(3):  # "27.1OO" -> "27.100"
        t = re.sub(r"(?<=[\d.])[OoD]", "0", t)
        t = re.sub(r"(?<=[\d.])[lI|]", "1", t)
    return t


def known_spot(spot):
    if not spot or spot in KNOWN_SPOTS:
        return spot, False
    lower = {s.lower(): s for s in KNOWN_SPOTS}
    hit = difflib.get_close_matches(spot.lower(), list(lower), n=1, cutoff=0.6)
    return (lower[hit[0]], True) if hit else (spot, False)
DATE = re.compile(r"Entdeckt:?\s*\w+,?\s*(\d{1,2})\.\s*([A-Za-zä]{3})\w*\.?\s+(\d{4})")

HEART_X0, HEART_DX, HEART_HALF = 200, 66, 22   # slot centres at full resolution (1080 wide)
HEART_DY = 22                                  # heart centre below the OCR top of "Schritte"
STAR_X = 957


def classify(px):
    r, g, b = px[..., 0].astype(int), px[..., 1].astype(int), px[..., 2].astype(int)
    gold = (r > 215) & (g > 150) & (b < 130) & (r - b > 110)
    red = (r > 190) & (g < 150) & (b < 160) & ~gold
    grey = (abs(r - g) < 14) & (abs(g - b) < 14) & (r > 185) & (r < 240)
    return red, gold, grey


HEART_SCAN = (140, 470)   # x range of the heart row; the icons are centred, 1-4 of them


def heart_icons(band, x0):
    """Column runs of heart pixels = the heart icons (partly filled ones stay one run)."""
    red, gold, grey = classify(band[:, x0:HEART_SCAN[1]])
    mask = (red | gold | grey).any(axis=0)
    runs, start = [], None
    for x, on in enumerate(list(mask) + [False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            runs.append([start, x])
            start = None
    merged = []
    for run in runs:  # blended red/grey pixels of a scaled screenshot leave small gaps
        if merged and run[0] - merged[-1][1] <= 6:
            merged[-1][1] = run[1]
        else:
            merged.append(run)
    return [(x0 + s, x0 + e) for s, e in merged if e - s >= 15]


def read_hearts(img, steps_y):
    """Friendship from the heart icons. A heart is complete only when it shows the white
    highlight at its top left (red or gold); the heart in progress has none and counts with
    its fill. Returns (hearts, gold_any, completed gold hearts)."""
    a = np.asarray(img)
    y = steps_y + HEART_DY
    band = a[y - 12:y + 12]
    red_full = gold_full = 0
    partial, gold_any = 0.0, False
    for s, e in heart_icons(band, HEART_SCAN[0]):
        red, gold, grey = classify(band[:, s:e])
        filled = (red | gold).any(axis=0)
        gold_any |= bool(gold.sum() > 20)
        box = a[y - 10:y - 2, s + 8:s + 18].astype(int)
        highlight = ((box[..., 0] > 235) & (box[..., 1] > 235) & (box[..., 2] > 235)).sum() >= 6
        if highlight and gold.sum() > red.sum():
            gold_full += 1
        elif highlight:
            red_full += 1
        elif not gold.any():
            partial = max(partial, filled.sum() / (e - s))  # the one red heart being filled
    # a heart without highlight is not complete: its fill to the nearest quarter, at most 3/4
    hearts = 4.0 if gold_any else min(4.0, red_full + min(0.75, round(partial * 4) / 4))
    return hearts, gold_any, gold_full


def read_star(img, name_top, name_bottom):
    a = np.asarray(img)
    cy = (name_top + name_bottom) // 2
    box = a[max(cy - 45, 0):cy + 45, STAR_X - 40:STAR_X + 40]
    r, g, b = box[..., 0].astype(int), box[..., 1].astype(int), box[..., 2].astype(int)
    yellow = ((r > 220) & (g > 170) & (b < 110)).sum()
    return yellow > 150


def steps_fallback(path, steps_y, tmp):
    img = Image.open(path)
    crop = img.crop((560, max(steps_y - 25, 0), 1070, steps_y + 75))
    crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS).save(tmp)
    for _, t in ocr(tmp):
        m = STEPS.fullmatch(steps_text(t))
        if m:
            return int(m.group(1).replace(".", ""))
    return None


WEEKDAYS = {"Mo": 0, "Di": 1, "Mi": 2, "Do": 3, "Fr": 4, "Sa": 5, "So": 6}
NO_MONTH = re.compile(r"Entdeckt:?\s*(Mo|Di|Mi|Do|Fr|Sa|So),?\s*(\d{1,2})\.\s+(\d{4})")


def month_from_weekday(wd, day, year):
    """OCR sometimes drops the month; weekday + day usually pins it down."""
    today = datetime.date.today()
    hits = []
    for month in range(1, 13):
        try:
            d = datetime.date(year, month, day)
        except ValueError:
            continue
        if d.weekday() == wd and d <= today:
            hits.append(d)
    return hits[0].isoformat() if len(hits) == 1 else None


def parse_date(text):
    t = re.sub(r"(\d)\s+(?=[\d.])", r"\1", text)   # "1 1 . Sep" -> "11. Sep"
    t = re.sub(r"\s+\.", ".", t)
    dm = DATE.search(t)
    if not dm:
        nm = NO_MONTH.search(t)
        return month_from_weekday(WEEKDAYS[nm.group(1)], int(nm.group(2)), int(nm.group(3))) if nm else None
    month = MONTHS.get(dm.group(2)[:3].capitalize())
    day = int(dm.group(1))
    if not month or not 1 <= day <= 31:
        return None
    return f"{dm.group(3)}-{month:02d}-{day:02d}"


def date_fallback(path, y, tmp):
    img = Image.open(path)
    crop = img.crop((230, max(y - 25, 0), 1000, y + 75))
    crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS).save(tmp)
    text = " ".join(t for _, t in ocr(tmp))
    return parse_date(text if "Entdeckt" in text else "Entdeckt: " + text)


def parse_card(run, rec):
    n = rec["n"]
    lines = [(y, t) for y, t in rec["lines"]]
    main = sorted([(y, t) for y, t in lines if y < SCROLLED_Y], key=lambda l: l[0])
    lower = sorted([(y - SCROLLED_Y, t) for y, t in lines if y >= SCROLLED_Y], key=lambda l: l[0])
    problems = []
    group = any("Aus der Gruppe" in t for _, t in main)

    button_y = next((y for y, t in main if "Gruppe" in t), 990)
    rename_y = next((y for y, t in main if "Namen" in t), None)
    name_lines = [(y, t) for y, t in main if button_y < y < (rename_y or 0) - 30 and "teilen" not in t]
    name = ""
    for _, t in name_lines:
        t = t.strip()
        if name and (name.endswith("-") or (name[-1].isalpha() and t[:1].islower())):
            name += t                      # word broken across lines: "-Pik" + "min", "Anstecknadel-" + "Pikmin"
        else:
            name += (" " if name else "") + t
    bm = BASE.match(name)
    base = re.sub(r"-\s+Pikmin", "-Pikmin", bm.group(1)) if bm else name
    rest = name[len(bm.group(1)):].strip() if bm else ""
    origin = rest.split(" ", 1)[1].strip() if " " in rest else ""  # drop the mangled "aus"

    m = re.match(r"^(.+?)-Pikmin \(([^)]+)\)", base)
    if m:
        decor, color = m.group(1).strip(), m.group(2).strip().capitalize()
        base = f"{decor}-Pikmin ({color})"
    else:
        p = re.match(r"^(Rotes|Gelbes|Blaues|Lila|Weißes|Fels|Flügel|Eis)[ -]Pikmin", base)
        decor, color = None, PLAIN.get(p.group(1)) if p else None
    if color not in COLORS:
        problems.append(f"Farbe? '{base}'")

    steps_line = next(((y, t) for y, t in main if "Schritte" in t), None)
    steps = None
    if steps_line:
        m = STEPS.fullmatch(steps_text(steps_line[1]))
        steps = int(m.group(1).replace(".", "")) if m else None
        if steps is None or (rec.get("device") and rec["device"][0] < 1000):  # small text: read enlarged
            steps = steps_fallback(run / f"{n:03d}.png", steps_line[0], run / "_steps_tmp.png") or steps
            if steps is None:
                problems.append(f"Schritte? '{steps_line[1]}'")
    else:
        problems.append("Schritte fehlen")

    img = Image.open(run / f"{n:03d}.png").convert("RGB")
    hearts, gold, gold_full = read_hearts(img, steps_line[0]) if steps_line else (None, False, 0)
    fav = read_star(img, name_lines[0][0], name_lines[-1][0] + 70) if name_lines else False

    # card block below the steps; the spot line ("Wald / Eichelhut" or just "Park") comes first
    card = [(y, t) for y, t in main if steps_line and y > steps_line[0] + 100]
    date_i = next((i for i, (_, t) in enumerate(card) if "Entdeckt" in t), None)
    body = [t for _, t in (card[:date_i] if date_i is not None else card)
            if t != "O" and "Freundschaft" not in t and "gelaufen" not in t]
    if len(body) > 1 and body[0].rstrip().endswith("/"):
        body = [body[0].rstrip() + " " + body[1]] + body[2:]  # "Universität & College /" + "Uni-Wappen Aufnäher"
    spot_line = body[0] if body else ""
    spot_part, sep, spot_decor = spot_line.rpartition(" / ")
    spot, spot_decor = (spot_part, spot_decor) if sep else (spot_line, "")  # "Bibliothek/Bücherladen" has its own slash
    spot, spot_decor = spot.strip(), spot_decor.strip()
    spot, _ = known_spot(spot)  # OCR: "BOUtiCIUe" -> "Boutique"; spot_line stays raw for matching
    location = " ".join(body[1:])
    def date_line(block, i):
        text = block[i][1]
        if not re.search(r"\d", text) and i + 1 < len(block):
            text += " " + block[i + 1][1]  # "Entdeckt:" and the date on separate OCR lines
        return text, block[i][0]

    date_text, date_y, date_img = "", None, run / f"{n:03d}.png"
    if date_i is not None:
        date_text, date_y = date_line(card, date_i)
    if lower:
        # scrolled-up shot: full location and the date; find the same spot line there
        li = next((i for i, (_, t) in enumerate(lower) if t.strip() and spot_line.startswith(t.strip())), None)
        if li is not None and li + 1 < len(lower) and lower[li][1].rstrip().endswith("/"):
            li += 1  # wrapped spot line in the scrolled shot as well
        ld = next((i for i, (_, t) in enumerate(lower) if "Entdeckt" in t), None)
        if ld is not None:
            date_text, date_y = date_line(lower, ld)
            date_img = run / f"{n:03d}_b.png"
            if li is not None and li < ld:
                location = " ".join(t for _, t in lower[li + 1:ld])
            else:
                problems.append("Fundort evtl. abgeschnitten")
    date = parse_date(date_text)
    lowres = rec.get("device") and rec["device"][0] < 1000  # upscaled screenshot: small text
    if (lowres or not date) and date_y is not None:
        date = date_fallback(date_img, date_y, run / "_date_tmp.png") or date
    if not date:
        problems.append(f"Datum? '{date_text}'")
    if decor and spot_decor and decor != spot_decor:
        problems.append(f"Deko Name/Karte: {decor} ≠ {spot_decor}")

    return {"n": n, "name": base, "origin": origin,
            "color": color or "", "decor": decor or "", "fav": int(fav), "hearts": hearts,
            "gold": int(gold), "gold_hearts": gold_full, "steps": steps if steps is not None else "", "spot": spot,
            "spot_decor": spot_decor, "location": location, "date": date or "",
            "group": int(group), "problems": "; ".join(problems)}


# colour order of the in-game Pikmin list (not the slot order of the decor collection)
COLOR_ORDER = ["Rot", "Gelb", "Blau", "Lila", "Weiß", "Flügel", "Fels", "Eis"]
# sets that share one label on the card -> how many sets follow each other in the list
MULTI_SETS = {
    ("decor", "Sticker"): 3,            # Sticker grün, blau, gelb
    ("plain", "Straße", "Sticker"): 3,  # sticker motif a Pikmin without decor will get
    ("plain", "Park", ""): 2,           # Kleeblatt, vierblättriges Kleeblatt
}


def assign_variants(rows):
    """The in-game list sorted by decor keeps every set together, colours ascending: first
    Pikmin with decor, then those without, again per set. A restart of the colour order
    starts the next set. Sets are only numbered when the block count equals the known number
    of sets - otherwise a set starting with a later colour than the previous one ended with
    could have merged unnoticed, e.g. when there are only few Pikmin."""
    blocks = {}
    prev_key, prev_idx, block = None, -1, 0
    for r in sorted(rows, key=lambda r: r["n"]):
        r["variant"] = ""
        key = ("decor", r["decor"]) if r["decor"] else ("plain", r["spot"], r["spot_decor"])
        if key not in MULTI_SETS or r["group"] == 1:
            prev_key = None
            continue
        idx = COLOR_ORDER.index(r["color"]) if r["color"] in COLOR_ORDER else -1
        if key != prev_key:
            block = 1
        elif idx < prev_idx:
            block += 1
        blocks.setdefault(key, []).append((r, block))
        prev_key, prev_idx = key, idx
    for key, members in blocks.items():
        found = max(b for _, b in members)
        if found == MULTI_SETS[key]:
            for r, b in members:
                r["variant"] = b
        else:
            note = f"Set offen: {found} statt {MULTI_SETS[key]} Blöcke"
            for r, _ in members:
                r["problems"] = "; ".join(filter(None, [r["problems"], note]))


def main():
    run = Path(sys.argv[1])
    recs = [json.loads(l) for l in (run / "log.jsonl").open(encoding="utf-8")]
    rows = [parse_card(run, r) for r in recs]
    assign_variants(rows)
    with (run / "parsed.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    bad = [r for r in rows if r["problems"]]
    print(f"{len(rows)} Karten -> {run / 'parsed.tsv'}, {len(bad)} mit Auffälligkeiten")
    for r in bad:
        print(f"  #{r['n']:03d} {r['name']}: {r['problems']}")


if __name__ == "__main__":
    main()
