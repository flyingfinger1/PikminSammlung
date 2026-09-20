"""Turn data/pikmin.tsv into pikmin.json / pikmin.csv and render web/index.html.

Usage: py tools/build_page.py
"""
import base64
import csv
import json
import re
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from lang import ENGLISH  # noqa: E402
from ui import tr  # noqa: E402

from paths import RES, ROOT  # noqa: E402
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


# places in the order of the in-game decor collection (video 2026-09-14), special decor last
CATEGORY_ORDER = [
    "Restaurant", "Café", "Süßwarenladen", "Kino", "Apotheke", "Zoo", "Wald", "Am Wasser", "Post",
    "Kunstmuseum", "Flughafen", "Bahnhof", "Strand", "Burger-Bistro", "Eckladen", "Supermarkt",
    "Bäckerei", "Friseur", "Boutique", "Park", "Bibliothek/Bücherladen", "Straße", "Sushi-Restaurant",
    "Berg", "Stadion", "Regentag", "Schneetag", "Themenpark", "Bushaltestelle",
    "Italienisches Restaurant", "Ramen-Restaurant", "Brücke", "Hotel", "Kosmetik-Laden",
    "Schreine und Tempel", "Elektroladen", "Curry-Restaurant", "Baumarkt", "Universität & College",
    "Mexikanisches Restaurant", "Waschsalons & Reinigungen", "Koreanisches Restaurant",
    "Schreibwarenladen", "Extra",
]


def load_config():
    """Settings of this collection, kept out of the repo (template: config.example.json)."""
    path = ROOT / "config.local.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def english_names():
    """German game names -> English ones for the page; the first English spelling wins (the
    tables list the spelling of the card first)."""
    out = {}
    for kind in ("decor", "spots"):
        rev = {}
        for en, de in ENGLISH[kind].items():
            rev.setdefault(de, en)
        out[kind] = rev
    return out


def set_order():
    """Sets within a place in the order of the latest scan: the in-game list sorted by decor
    follows the collection (e.g. Hirschkäfer before Eichelhut, Sticker grün/blau/gelb, Münze)."""
    scans = sorted(p for p in (ROOT / "captures").glob("20*/parsed.tsv") if "_test" not in p.parent.name)
    if not scans:
        return []
    with scans[-1].open(encoding="utf-8") as f:
        cards = sorted(csv.DictReader(f, delimiter="\t"), key=lambda r: int(r["n"]))
    order = []
    for r in cards:
        variant = int(r["variant"]) if r.get("variant") else None
        if r["decor"]:
            name = r["decor"]
            if variant and name in MOTIF_NAMES:
                name = f"{name} · {MOTIF_NAMES[name].get(variant, f'Motiv {variant}')}"
        else:
            name = PLAIN_SET_DECOR.get((r["spot"], r["spot_decor"]), {}).get(variant) or r["spot_decor"]
        if name and name not in order:
            order.append(name)
    return order


def fonts_css():
    """web/fonts/fonts.css with its font files inlined, so the page loads no fonts from elsewhere."""
    folder = RES / "web" / "fonts"
    css = (folder / "fonts.css").read_text(encoding="utf-8")
    return re.sub(r"url\(fonts/([\w.-]+\.woff2)\)", lambda m: "url(data:font/woff2;base64,"
                  + base64.b64encode((folder / m.group(1)).read_bytes()).decode() + ")", css)


def legal():
    """Your own legal notice / privacy policy (legal/imprint.html, legal/privacy.html; examples in
    legal/*.example*.html). A file named <name>.en.html or <name>.de.html serves that page language,
    <name>.html every language. None of them = no footer on the page."""
    out = {}
    for name in ("imprint", "privacy"):
        texts = {}
        for lang in ("de", "en"):
            for path in (ROOT / "legal" / f"{name}.{lang}.html", ROOT / "legal" / f"{name}.html"):
                if path.exists():
                    texts[lang] = path.read_text(encoding="utf-8")
                    break
        if texts:
            out[name] = texts
    return out


def seeds():
    """Seedlings of the latest seedling scan (captures/seeds/<run>/parsed.tsv). `options` are the
    sets a seedling can grow into: one, or all motifs of a decor whose set the list left open."""
    scans = sorted(p for p in (ROOT / "captures" / "seeds").glob("20*/parsed.tsv") if "_test" not in p.parent.name)
    if not scans:
        return None
    out = []
    with scans[-1].open(encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="	"):
            variant = int(r["variant"]) if r.get("variant") else None
            if r["decor"] in MOTIF_NAMES:
                names = MOTIF_NAMES[r["decor"]]
                options = [f"{r['decor']} · {names[variant]}"] if variant else [f"{r['decor']} · {m}" for m in names.values()]
            elif (r["spot"], r["decor"]) in PLAIN_SET_DECOR:  # Park: the card names no decor
                sets = PLAIN_SET_DECOR[(r["spot"], r["decor"])]
                options = [sets[variant]] if variant else list(sets.values())
            else:
                options = [r["decor"]] if r["decor"] else []
            out.append({"n": int(r["n"]), "kind": r["kind"], "color": r["color"], "options": options,
                        "spot": r["spot"], "location": r["location"], "date": r["date"],
                        "growHave": int(r["grow_have"]) if r["grow_have"] else None,
                        "growNeed": int(r["grow_need"]) if r["grow_need"] else None,
                        "planted": r["planted"] == "1"})
    return {"scan": scans[-1].parent.name[:10], "list": out}


def gold_hearts(row):
    """Gold hearts: the completed ones plus the fraction of the one in progress."""
    value = float(row.get("goldhearts") or 0)
    return int(value) if value.is_integer() else value


def parse(row):
    name = row["name"]
    m = DECOR_NAME.match(name)
    if m:
        decor, color = m.group(1), m.group(2)
    else:
        p = PLAIN_NAME.match(name)
        if not p:
            raise ValueError(tr(f"Name nicht lesbar: {name}", f"unparsed name: {name}"))
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
        "goldHearts": gold_hearts(row),  # gold hearts, the one in progress as a fraction
        "steps": int(row["steps"]),
        "location": row["location"],
        "date": row["date"],
        "seen": row.get("seen") or None,  # date of the scan this row comes from
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
    order = {"spots": CATEGORY_ORDER, "sets": set_order()}
    cfg = load_config()
    config = {"rareUnlocked": cfg.get("rare_unlocked", []), "language": cfg.get("language")}
    seedlings = seeds()
    page_rows = rows
    if cfg.get("show_locations") is False:
        # "show_locations": false - where a Pikmin was found stays out of the page altogether
        # (hiding it on the page would still leave it in the page source); pikmin.json keeps it
        page_rows = [{**r, "location": "", "origin": ""} for r in rows]
        for s in (seedlings or {}).get("list", []):
            s["location"] = ""
    payload = json.dumps({"pikmin": page_rows, "sprite": meta, "order": order, "config": config,
                          "names": {"en": english_names()}, "seeds": seedlings, "legal": legal()},
                         ensure_ascii=False)
    template = (RES / "web/template.html").read_text(encoding="utf-8")
    html = template.replace("/*DATA*/null", payload.replace("</", "<\\/")).replace("/*FONTS*/", fonts_css())
    (ROOT / "web/index.html").write_text(html, encoding="utf-8")
    print(f"{len(rows)} Pikmin -> data/pikmin.json, data/pikmin.csv, web/index.html")


if __name__ == "__main__":
    main()
