"""Which rare decor sets are unlocked in the in-game collection.

The scan reads Pikmin cards, never the decor collection, so the unlock cannot be read there.
Two things in the collection do prove it, both for the whole place at once - rare decor
unlocks per place, not per decor:
- a Pikmin wearing rare decor, which can only exist after the unlock;
- every normal decor of that place collected in every colour, which is what unlocks it.
The second one needs to know which sets a place has (PLACE_SETS); where that is unknown, the
collection only suggests and the step asks. Letting a Pikmin go does not lock a place again, so
entries in config.local.json "rare_unlocked" are only ever added, never removed - the list is a
memory, not a snapshot of the collection right now.

A Pikmin only carries decor when its name says so ("Kochmützen-Pikmin (Fels)"); the decor column
of a Pikmin without decor merely names what this place gives.

A "no" is remembered ("rare_asked": place -> decor Pikmin there at the time), so the question
only comes back once more decor of that place has arrived.

Runs at the end of apply_capture.py; the answers land in config.local.json.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_page import parse  # noqa: E402
from ui import ask, decor as show_decor, spot as show_spot, tr  # noqa: E402

from paths import RES, ROOT  # noqa: E402
RARE = " (Selten)"
CONFIG = ROOT / "config.local.json"
# the normal decor sets of a place (pikminwiki.com/Decor_Pikmin, Sep 2026). Only the places whose
# decor has a known German name are listed; for the rest the collection cannot tell whether a set
# is missing entirely, so those are asked about instead of decided.
PLACE_SETS = {
    "Am Wasser": ["Köder"],
    "Apotheke": ["Zahnpflege"],
    "Bahnhof": ["Papierzug"],
    "Baumarkt": ["Werkzeug"],
    "Berg": ["Berg-Anstecknadel"],
    "Boutique": ["Haargummi"],
    "Brücke": ["Brücke-Anstecknadel"],
    "Burger-Bistro": ["Burger"],
    "Bushaltestelle": ["Papierbus"],
    "Bäckerei": ["Baguette", "Gebäck"],
    "Café": ["Kaffeetasse"],
    "Curry-Restaurant": ["Curry-Schale"],
    "Flughafen": ["Spielflugzeug"],
    "Friseur": ["Schere"],
    "Hotel": ["Hotel-Annehmlichkeiten"],
    "Italienisches Restaurant": ["Pizza", "Pasta"],
    "Kino": ["Popcorn"],
    "Park": ["Kleeblatt", "Vierblättriger Klee"],
    "Restaurant": ["Kochmütze"],
    "Schreibwarenladen": ["Schreibwaren"],
    "Stadion": ["Ball-Schlüsselanhänger"],
    "Sushi-Restaurant": ["Sushi"],
    "Wald": ["Hirschkäfer", "Eichelhut"],
}


def game_tables():
    """Colours per decor and the decor with a rare variant, read from the page template: the
    page and the scripts must not drift apart on game data."""
    text = (RES / "web/template.html").read_text(encoding="utf-8")

    def js(name):
        m = re.search(rf"const {name} = (?:new Set\()?(\[[^;]*\]|\{{[^;]*\}})\)?;", text)
        if not m:
            raise ValueError(f"{name} not found in web/template.html")
        return json.loads(m.group(1))

    return {"colors": [n for n, _ in js("COLORS")], "no_eis": set(js("NO_EIS")),
            "only": js("ONLY_COLORS"), "rare_exists": set(js("RARE_EXISTS"))}


def colors_for(d, t):
    """The colours this decor exists in; sticker motifs follow their plain decor."""
    base = d.split(" · ")[0]
    return t["only"].get(base) or [n for n in t["colors"] if not (n == "Eis" and base in t["no_eis"])]


def load():
    return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}


def save(unlocked, asked):
    """Keep the other settings; entries in "rare_unlocked" are only ever added."""
    cfg = load()
    cfg["rare_unlocked"] = list(dict.fromkeys(cfg.get("rare_unlocked", []) + unlocked))
    if asked:
        cfg["rare_asked"] = asked
    else:
        cfg.pop("rare_asked", None)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def collection(rows):
    """sets: place -> decor -> the colours actually worn there (a set with no decor Pikmin yet
    stays empty); size: decor Pikmin per place; worn_rare: place -> decor worn in its rare form."""
    sets, size, worn_rare = {}, Counter(), {}
    for row in rows:
        p = parse(row)
        here = sets.setdefault(p["spot"], {})
        if not p["decor"]:
            if p["spotDecor"]:  # this place gives that set, it is just not worn yet
                here.setdefault(p["spotDecor"], set())
            continue
        base = p["decor"][:-len(RARE)] if p["decor"].endswith(RARE) else p["decor"]
        if p["decor"].endswith(RARE):
            worn_rare.setdefault(p["spot"], set()).add(base)  # the normal slot stays filled too
        here.setdefault(base, set()).add(p["color"])
        size[p["spot"]] += 1
    return sets, size, worn_rare


def complete(place, here, t):
    """True when every normal decor set this place has is collected in every colour - that is
    what unlocks its rare decor. Only decidable for a place whose sets are known."""
    want = PLACE_SETS.get(place)
    if not want or not set(here) <= set(want):  # an unknown set: the wiki list is out of date
        return False
    return all(set(colors_for(d, t)) <= here.get(d, set()) for d in want)


def review(rows, interactive=True):
    """Note the rare decor the collection proves, ask about the places it suggests."""
    t = game_tables()
    sets, size, worn_rare = collection(rows)
    cfg = load()
    have = set(cfg.get("rare_unlocked", []))
    asked = dict(cfg.get("rare_asked", {}))
    add = []
    for place in sorted(sets):
        here = sets[place]
        open_rare = [d for d in sorted(set(here) | worn_rare.get(place, set()))
                     if (d in t["rare_exists"] or d in worn_rare.get(place, set()))
                     and d + RARE not in have]
        if not open_rare:
            continue
        full = ", ".join(f"{show_decor(d)} {len(colors_for(d, t))}/{len(colors_for(d, t))}" for d in sorted(here))
        proof = ""
        if worn_rare.get(place):
            proof = tr("du hast " + ", ".join(show_decor(d + RARE) for d in sorted(worn_rare[place]))
                       + " in der Sammlung",
                       "you have " + ", ".join(show_decor(d + RARE) for d in sorted(worn_rare[place]))
                       + " in the collection")
        elif complete(place, here, t):
            proof = tr(f"die Kategorie ist komplett ({full})",
                       f"all its normal decor is collected ({full})")
        if proof:
            add += [d + RARE for d in open_rare]
            print(tr(f"{show_spot(place)}: seltene Deko freigeschaltet, {proof}.",
                     f"{show_spot(place)}: rare decor unlocked, {proof}."))
            print("  " + ", ".join(show_decor(d + RARE) for d in open_rare))
            continue
        # the sets of this place are unknown: a complete collection here is only a hint
        if not all(set(colors_for(d, t)) <= worn for d, worn in here.items()):
            continue
        if asked.get(place) == size[place]:  # answered "no", nothing new there since
            continue
        keys = [d + RARE for d in open_rare]
        if interactive:
            try:
                if ask(tr(f"{show_spot(place)} ist vollständig ({full}) - seltene Deko im Spiel freigeschaltet?",
                          f"{show_spot(place)} is complete ({full}) - is its rare decor unlocked in the game?")):
                    add += keys
                    print("  " + ", ".join(show_decor(k) for k in keys))
                else:
                    asked[place] = size[place]
                    print(tr("  gemerkt - die Frage kommt erst wieder, wenn neue Deko dieser Kategorie dazukommt.",
                             "  noted - you are only asked again once new decor of that category arrives."))
                continue
            except EOFError:  # started without a console: report instead of asking
                interactive = False
        print(tr(f"{show_spot(place)} ist vollständig ({full}). Ist die seltene Deko freigeschaltet, "
                 f'in config.local.json unter "rare_unlocked" eintragen: {", ".join(keys)}',
                 f"{show_spot(place)} is complete ({full}). If its rare decor is unlocked, add it to "
                 f'"rare_unlocked" in config.local.json: {", ".join(keys)}'))
    asked = {p: n for p, n in asked.items() if p in sets}
    if add or asked != cfg.get("rare_asked", {}):
        save(add, asked)
    if add:
        print(tr(f"config.local.json: {len(add)} seltene Deko eingetragen - Einträge werden nie wieder entfernt.",
                 f"config.local.json: {len(add)} rare decor set(s) noted - entries are never removed again."))
    return add


if __name__ == "__main__":
    from diff_capture import load_old
    review(load_old())
