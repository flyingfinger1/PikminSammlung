"""Turn data/pikmin.tsv into pikmin.json / pikmin.csv and render web/index.html.

Usage: py tools/build_page.py
"""
import csv
import json
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SPRITE_COLS = 20  # must match make_thumbs.py
# in-game list order within the decor (verified on the sticker colour in the portraits)
MOTIF_NAMES = {"Sticker": {1: "grün", 2: "blau", 3: "gelb"}}
# Pikmin without decor: the set they will get, derived from their block in the list
PLAIN_SET_DECOR = {
    ("Straße", "Sticker"): {1: "Sticker · grün", 2: "Sticker · blau", 3: "Sticker · gelb"},
    ("Park", ""): {1: "Kleeblatt", 2: "Vierblättriger Klee"},  # in-game name confirmed 2026-09-16
}

PLAIN = {"Rotes": "Rot", "Gelbes": "Gelb", "Blaues": "Blau", "Lila": "Lila",
         "Weißes": "Weiß", "Fels": "Fels", "Flügel": "Flügel", "Eis": "Eis"}
DECOR_NAME = re.compile(r"^(.+?)-Pikmin \(([^)]+)\)")
PLAIN_NAME = re.compile(r"^(Rotes|Gelbes|Blaues|Lila|Weißes|Fels|Flügel|Eis)[ -]Pikmin")


def parse(row):
    name = row["name"]
    m = DECOR_NAME.match(name)
    if m:
        decor, color = m.group(1), m.group(2)
    else:
        p = PLAIN_NAME.match(name)
        if not p:
            raise ValueError(f"unparsed name: {name}")
        decor, color = None, PLAIN[p.group(1)]
    origin = name.split(" aus ", 1)[1] if " aus " in name else ""
    origin = origin.removeprefix("In der Nähe: ")
    hearts = row["hearts"]
    motif = (row.get("motif") or "").strip()
    if decor and motif:  # several motifs of one decor (Sticker), told apart by list order
        label = MOTIF_NAMES.get(row["decor"], {}).get(int(motif), f"Motiv {motif}")
        decor = f"{row['decor']} · {label}"
    return {
        "frame": int(row["frame"]),
        "name": name.split(" aus ", 1)[0],
        "origin": origin,
        "color": color,
        "decor": (decor if motif else row["decor"]) if decor else None,
        "motif": int(motif) if motif else None,
        "spot": row["spot"],
        "spotDecor": (PLAIN_SET_DECOR.get((row["spot"], row["decor"]), {}).get(int(motif))
                      if motif and not decor else None) or row["decor"] or None,
        "fav": row["fav"] == "1",
        "hearts": float(hearts.replace("+G", "")),
        "gold": hearts.endswith("+G"),
        "steps": int(row["steps"]),
        "location": row["location"],
        "date": row["date"],
    }


def main():
    with open(ROOT / "data/pikmin.tsv", encoding="utf-8") as f:
        rows = [parse(r) for r in csv.DictReader(f, delimiter="\t")]
    for rank, r in enumerate(rows, start=1):
        r["rank"] = rank  # in-game list order (friendship)

    (ROOT / "data/pikmin.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(ROOT / "data/pikmin.csv", "w", encoding="utf-8-sig", newline="") as f:
        cols = ["rank", "name", "color", "decor", "fav", "hearts", "gold",
                "steps", "spot", "spotDecor", "location", "origin", "date"]
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    sprite = Image.open(ROOT / "web/thumbs.jpg")
    frames = max(r["frame"] for r in rows)
    sprite_rows = -(-frames // SPRITE_COLS)
    meta = {"cols": SPRITE_COLS, "w": sprite.width // SPRITE_COLS,
            "h": sprite.height // sprite_rows, "rows": sprite_rows,
            "missing": 0}
    payload = json.dumps({"pikmin": rows, "sprite": meta}, ensure_ascii=False)
    template = (ROOT / "web/template.html").read_text(encoding="utf-8")
    html = template.replace("/*DATA*/null", payload.replace("</", "<\\/"))
    (ROOT / "web/index.html").write_text(html, encoding="utf-8")
    print(f"{len(rows)} Pikmin -> data/pikmin.json, data/pikmin.csv, web/index.html")


if __name__ == "__main__":
    main()
