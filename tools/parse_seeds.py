"""Turn a seedling scan (captures/seeds/<run>: NNN.png + log.jsonl from capture_adb.py --seeds)
into parsed.tsv: kind and type of every seedling, its place and decor, growth and discovery date.

Which seedlings are worth planting is decided on the page, against the current collection.

Usage: py tools/parse_seeds.py captures/seeds/<run>
"""
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from capture_adb import SCROLLED_Y  # noqa: E402
from lang import LANGS, en_decor, en_location, en_spot  # noqa: E402
from parse_captures import (COLOR_ORDER, EGG, assign_variants, date_fallback, known_spot,  # noqa: E402
                            parse_date)
from ui import tr  # noqa: E402

# name on the card -> colour, or the kind of a special seedling (its Pikmin type is random)
DE_SEED = re.compile(r"^(roter|gelber|blauer|lila|weißer|flügel|fels|eis|riesen|gold|silber)\s*-?\s*keim", re.I)
EN_SEED = re.compile(r"^(red|yellow|blue|purple|white|winged|rock|ice|huge|gold|silver)\s+seedling", re.I)
KINDS = {"roter": "Rot", "gelber": "Gelb", "blauer": "Blau", "lila": "Lila", "weißer": "Weiß",
         "flügel": "Flügel", "fels": "Fels", "eis": "Eis", "riesen": "Riesen", "gold": "Gold",
         "silber": "Silber",
         "red": "Rot", "yellow": "Gelb", "blue": "Blau", "purple": "Lila", "white": "Weiß",
         "winged": "Flügel", "rock": "Fels", "ice": "Eis", "huge": "Riesen", "silver": "Silber"}
SPECIAL = ("Riesen", "Gold", "Silber")
# "1.000 Schritte" to grow, or "7.261 / 10.000 Schritte" once planted
GROW = re.compile(r"(\d[\d.,]*)(?:/(\d[\d.,]*))?$")
DIGIT_LOOKALIKES = str.maketrans("OoDIl|", "000111")


def number(text):
    return int(re.sub(r"[.,]", "", text))


def grow(text, L):
    """(steps so far or None, steps needed) from the growth line; OCR reads 0 as O and 1 as I
    here ("O/ I .OOO Schritte" = "0 / 1.000")."""
    digits = text.split(L["steps"])[0].translate(DIGIT_LOOKALIKES).replace(" ", "")
    g = GROW.search(digits)
    if not g:
        return None, None
    return (number(g.group(1)), number(g.group(2))) if g.group(2) else (None, number(g.group(1)))


def parse_seed(run, rec):
    n = rec["n"]
    L = LANGS[rec.get("lang", "de")]
    en = L["code"] == "en"
    main = sorted([(y, t) for y, t in rec["lines"] if y < SCROLLED_Y])
    lower = sorted([(y - SCROLLED_Y, t) for y, t in rec["lines"] if y >= SCROLLED_Y])
    if lower and not any(L["discovered"] in t for _, t in main):
        main = lower  # long location: the scrolled-up shot has the whole card
    problems = []

    name_line = next(((y, t) for y, t in main if L["seed"] in t.lower()), (None, ""))
    m = (EN_SEED if en else DE_SEED).match(name_line[1].strip())
    kind = KINDS.get(m.group(1).lower()) if m else None
    if kind is None:
        problems.append(tr(f"Keim? '{name_line[1]}'", f"seedling? '{name_line[1]}'"))

    grow_line = next(((y, t) for y, t in main if L["steps"] in t), None)
    have, need = grow(grow_line[1], L) if grow_line else (None, None)
    if need is None:
        problems.append(tr("Schritte?", "steps?"))

    top = grow_line[0] if grow_line else (name_line[0] or 0)
    date_i = next((i for i, (_, t) in enumerate(main) if L["discovered"] in t), None)
    body = [t for y, t in (main[:date_i] if date_i is not None else main)
            if y > top + 100 and t != "O" and not EGG.fullmatch(t)]
    spot_line = body[0] if body else ""
    spot_part, sep, decor = spot_line.rpartition(" / ")
    spot, decor = (spot_part, decor) if sep else (spot_line, "")  # Park seedlings name no decor
    spot, decor = spot.strip(), decor.strip()
    if en:
        known = en_spot(spot)
        if spot and not known:
            problems.append(tr(f"Ort unbekannt: '{spot}'", f"unknown place: '{spot}'"))
        spot, decor = known or spot, en_decor(decor) if decor else ""
    spot, _ = known_spot(spot)
    location = " ".join(body[1:])
    if en:
        location = en_location(location)

    date = None
    if date_i is not None:
        y, text = main[date_i]
        if not re.search(r"\d", text) and date_i + 1 < len(main):
            text += " " + main[date_i + 1][1]
        date = parse_date(text, L)
        if not date:
            shot = run / (f"{n:03d}_b.png" if main is lower else f"{n:03d}.png")
            date = date_fallback(shot, y, run / "_date_tmp.png", L)
    if not date:
        problems.append(tr("Datum?", "date?"))

    return {"n": n, "kind": "special" if kind in SPECIAL else "normal",
            "color": kind or "", "decor": decor, "spot": spot, "spot_decor": decor,
            "location": location, "date": date or "",
            "grow_have": have if have is not None else "", "grow_need": need if need is not None else "",
            "planted": int(have is not None), "group": 0, "problems": "; ".join(problems)}


def main():
    run = Path(sys.argv[1])
    recs = [json.loads(l) for l in (run / "log.jsonl").open(encoding="utf-8")]
    rows = [parse_seed(run, r) for r in recs]
    # the seedling list sorted by decor has the same order as the Pikmin list, special seedlings
    # after the colours - so the sticker motif and the park set follow from it as well
    assign_variants(rows, order=COLOR_ORDER + list(SPECIAL))
    with (run / "parsed.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    bad = [r for r in rows if r["problems"]]
    planted = sum(r["planted"] for r in rows)
    print(tr(f"{len(rows)} Keime ({planted} eingepflanzt) -> {run / 'parsed.tsv'}, {len(bad)} mit Auffälligkeiten",
             f"{len(rows)} seedlings ({planted} planted) -> {run / 'parsed.tsv'}, {len(bad)} with remarks"))
    for r in bad:
        print(f"  #{r['n']:03d} {r['color']} {r['decor']}: {r['problems']}")


if __name__ == "__main__":
    main()
