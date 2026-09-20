"""Match a parsed capture (parsed.tsv) against data/pikmin.tsv and report what changed.

Stable identity of a Pikmin: colour + discovery date + spot, refined by location text.
Names change when decor arrives and locations can switch from coordinates to street names,
so those only break ties. Nothing is written; the report is the review step.

Usage: py tools/diff_capture.py captures/<run>
"""
import csv
import difflib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ui import location as show_loc, name as show_name, spot as show_spot, tr  # noqa: E402

from paths import ROOT  # noqa: E402


def load_old():
    tsv = ROOT / "data/pikmin.tsv"
    if not tsv.exists():  # first scan: empty collection
        return []
    with tsv.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    for r in rows:
        name = r["name"].split(" aus ", 1)[0]
        r["color"] = color_of(name)
        r["hearts_f"] = float(r["hearts"].replace("+G", ""))
        r["gold"] = r["hearts"].endswith("+G")
    return rows


def color_of(name):
    if "(" in name:
        return name.rsplit("(", 1)[1].rstrip(")")
    first = name.split(" ")[0].split("-")[0]
    return {"Rotes": "Rot", "Gelbes": "Gelb", "Blaues": "Blau", "Weißes": "Weiß"}.get(first, first)


def sim(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def score(new, old):
    if new["color"] != old["color"] or new["date"] != old["date"]:
        return -1
    s = 2.0 if new["spot"] == old["spot"] else 0.0
    if not (is_coords(new["location"]) or is_coords(old["location"])):  # names load late in-game
        s += 2 * sim(new["location"], old["location"])
    else:
        s += 1
    s += 1 if new["name"] == old["name"].split(" aus ", 1)[0] else 0
    new_steps, old_steps = int(new["steps"] or 0), int(old["steps"])
    if new_steps >= old_steps:  # steps never go down; among twins prefer the closest count
        s += 0.5 - min(new_steps - old_steps, 100_000) / 200_000
    else:
        s -= 1.5
    return s


def is_coords(text):
    return text.strip().startswith("(") and any(c.isdigit() for c in text)


def load_new(run):
    with (run / "parsed.tsv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def same_pikmin(earlier, later):
    """Two captures of one Pikmin, "later" taken after "earlier": same type, discovery day and
    place, steps unchanged or a little higher - twins found on one day differ exactly there. The
    name may change in between: a Pikmin that reaches level 4 gets the decor of its place, so
    "Fels-Pikmin" becomes "Kochmützen-Pikmin (Fels)"."""
    if (earlier["color"], earlier["date"], earlier["spot"]) != (later["color"], later["date"], later["spot"]):
        return False
    if not 0 <= int(later["steps"] or 0) - int(earlier["steps"] or 0) <= 5000:
        return False
    if earlier["name"] != later["name"] and not (not earlier["decor"] and later["decor"]
                                                 and later["decor"] == later["spot_decor"]):
        return False
    coords = is_coords(earlier["location"]) or is_coords(later["location"])  # street names load late
    return coords or sim(earlier["location"], later["location"]) >= 0.8


def dedupe(rows):
    """One Pikmin captured twice - at the end of the list, or it changed while scanning: same
    colour, discovery date, spot and step count. A Pikmin that got its decor in between shows a
    new name and more steps, so those are matched by same_pikmin(). Keep the later capture, it is
    the current state. Step count 0 is not unique enough (fresh Pikmin), those are kept."""
    kept, dropped, first = [], [], {}
    for r in sorted(rows, key=lambda r: int(r["n"])):
        steps = int(r["steps"] or 0)
        key = (r["color"], r["date"], r["spot"], steps) if steps > 0 else None
        if key in first:
            kept.remove(first[key])
            dropped.append((first[key], r))
        if key:
            first[key] = r
        kept.append(r)
    for later in [r for r in kept if r["decor"]]:
        # the decor arrived between the two captures - only when exactly one card can be meant
        earlier = [e for e in kept if not e["decor"] and same_pikmin(e, later)]
        if len(earlier) == 1:
            kept.remove(earlier[0])
            dropped.append((earlier[0], later))
    return kept, dropped


def match_rows(new_rows, old_rows):
    """Greedy best-first assignment; returns {new index: (old index, score)}."""
    pairs = sorted(((score(n, o), i, j) for i, n in enumerate(new_rows)
                    for j, o in enumerate(old_rows)), reverse=True)
    used_new, used_old, match = set(), set(), {}
    for s, i, j in pairs:
        if s < 0 or i in used_new or j in used_old:
            continue
        used_new.add(i); used_old.add(j); match[i] = (j, s)
    return match


HEARTS = tr("Herzen", "hearts")


def no(o):
    """A Pikmin in the herbarium: its number never changes and is the one in a deep link."""
    return tr(f"Nr. {o['frame']}", f"no. {o['frame']}")


def card(n):
    """A card of this scan: its number is the position in the scan, nothing more."""
    return tr(f"Karte {n['n']}", f"card {n['n']}")


def where(r):
    return f"{show_spot(r['spot'])} · {show_loc(r['location'])} · {r['date']}"


def main():
    run = Path(sys.argv[1])
    new_rows, dropped = dedupe(load_new(run))
    old_rows = load_old()
    print(tr("Nr. = Platz im Herbarium (bleibt gleich) · Karte = Position in diesem Scan",
             "no. = place in the herbarium (never changes) · card = position in this scan"))
    if dropped:
        print(tr(f"Doppelt im Scan ({len(dropped)}), die ältere Aufnahme wird ignoriert:",
                 f"Twice in the scan ({len(dropped)}), the earlier capture is ignored:"))
        for earlier, later in dropped:
            print(f"  {card(earlier)} {show_name(earlier['name'])} = {card(later)} {show_name(later['name'])}"
                  f" · {later['steps']} {tr('Schritte', 'steps')}")
    match = match_rows(new_rows, old_rows)
    used_new = set(match)
    used_old = {j for j, _ in match.values()}

    changes, weak = [], []
    for i, (j, s) in sorted(match.items()):
        n, o = new_rows[i], old_rows[j]
        diff = []
        if n["name"] != o["name"].split(" aus ", 1)[0]:
            diff.append(f"Name: {show_name(o['name'].split(' aus ', 1)[0])} → {show_name(n['name'])}")
        if int(n["fav"]) != int(o["fav"]):
            diff.append(tr("Favorit", "favorite") + f": {o['fav']} → {n['fav']}")
        if float(n["hearts"] or 0) != o["hearts_f"] or bool(int(n["gold"])) != o["gold"]:
            diff.append(HEARTS + f": {o['hearts']} → {n['hearts']}{'+G' if n['gold'] == '1' else ''}")
        if int(n["steps"] or 0) < int(o["steps"]):
            diff.append(tr("SCHRITTE GESUNKEN", "STEPS WENT DOWN") + f" {o['steps']} → {n['steps']}")
        if not is_coords(n["location"]) and sim(n["location"], o["location"]) < 0.8:
            diff.append(tr("Fundort", "location") + f": {show_loc(o['location'])} → {show_loc(n['location'])}")
        if s < 3:
            weak.append((n, o, s))
        if diff:
            changes.append((n, o, diff))

    new_only = [new_rows[i] for i in range(len(new_rows)) if i not in used_new]
    gone = [old_rows[j] for j in range(len(old_rows)) if j not in used_old]

    print(tr(f"Erfasst: {len(new_rows)} · Herbarium: {len(old_rows)} · zugeordnet: {len(match)}",
             f"Captured: {len(new_rows)} · herbarium: {len(old_rows)} · matched: {len(match)}"))
    print(tr(f"\nNeu ({len(new_only)}):", f"\nNew ({len(new_only)}):"))
    for n in new_only:
        print(f"  {card(n)} {show_name(n['name'])} · {where(n)}")
    print(tr(f"\nNicht mehr gefunden ({len(gone)}):", f"\nNot found any more ({len(gone)}):"))
    for o in gone:
        print(f"  {no(o)} {show_name(o['name'])} · {where(o)}")
    print(tr(f"\nUnsichere Zuordnungen ({len(weak)}):", f"\nUncertain matches ({len(weak)}):"))
    for n, o, s in weak:
        print(f"  {card(n)} {show_name(n['name'])} / {show_loc(n['location'])}  ⇄  "
              f"{no(o)} {show_name(o['name'])} / {show_loc(o['location'])}  (Score {s:.1f})")
    notable = [(n, o, d) for n, o, d in changes if any(not x.startswith(HEARTS) for x in d)]
    print(tr(f"\nÄnderungen außer Herzen/Schritten ({len(notable)}):",
             f"\nChanges besides hearts/steps ({len(notable)}):"))
    for n, o, d in notable:
        print(f"  {no(o)} ({card(n)}): " + " · ".join(d))
    print(tr(f"\nNur Herzen geändert: {len(changes) - len(notable)}", f"\nOnly hearts changed: {len(changes) - len(notable)}"))
    write_report(run, new_rows, old_rows, match, dropped, new_only, gone, weak, notable)


def write_report(run, new_rows, old_rows, match, dropped, new_only, gone, weak, notable):
    """What the menu needs to talk about this scan without parsing the text above: which cards
    are worth another look, and what applying it would change."""
    from parse_captures import card_problems  # local: parse_captures pulls in the OCR side

    def scan_card(n, **extra):
        return {"card": int(n["n"]), "name": n["name"], "spot": n["spot"],
                "location": n["location"], "date": n["date"], **extra}

    report = {
        "run": run.name,
        "when": datetime.now().isoformat(timespec="seconds"),
        "cards": len(new_rows), "collection": len(old_rows), "matched": len(match),
        "new": [scan_card(n) for n in new_only],
        "gone": [{"no": int(o["frame"]), "name": o["name"], "spot": o["spot"],
                  "location": o["location"], "date": o["date"]} for o in gone],
        "weak": [scan_card(n, no=int(o["frame"]), score=round(s, 1)) for n, o, s in weak],
        "changes": [scan_card(n, no=int(o["frame"]), what=d) for n, o, d in notable],
        "dropped": [scan_card(e, same_as=int(l["n"])) for e, l in dropped],
        # only what is wrong with a card: an open set says nothing about the shot itself
        "problems": [scan_card(n, problem=card_problems(n)) for n in new_rows if card_problems(n)],
    }
    (run / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
