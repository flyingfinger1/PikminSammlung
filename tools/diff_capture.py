"""Match a parsed capture (parsed.tsv) against data/pikmin.tsv and report what changed.

Stable identity of a Pikmin: colour + discovery date + spot, refined by location text.
Names change when decor arrives and locations can switch from coordinates to street names,
so those only break ties. Nothing is written; the report is the review step.

Usage: py tools/diff_capture.py captures/<run>
"""
import csv
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_old():
    with (ROOT / "data/pikmin.tsv").open(encoding="utf-8") as f:
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


def dedupe(rows):
    """One Pikmin captured twice - at the end of the list, or it changed while scanning (e.g. got
    its decor): same colour, discovery date, spot and step count. Keep the later capture, it is
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


def main():
    run = Path(sys.argv[1])
    new_rows, dropped = dedupe(load_new(run))
    old_rows = load_old()
    if dropped:
        print(f"Doppelt im Scan ({len(dropped)}), die ältere Aufnahme wird ignoriert:")
        for earlier, later in dropped:
            print(f"  #{earlier['n']} {earlier['name']} = #{later['n']} {later['name']} · {later['steps']} Schritte")
    match = match_rows(new_rows, old_rows)
    used_new = set(match)
    used_old = {j for j, _ in match.values()}

    changes, weak = [], []
    for i, (j, s) in sorted(match.items()):
        n, o = new_rows[i], old_rows[j]
        diff = []
        if n["name"] != o["name"].split(" aus ", 1)[0]:
            diff.append(f"Name: {o['name'].split(' aus ', 1)[0]} → {n['name']}")
        if int(n["fav"]) != int(o["fav"]):
            diff.append(f"Favorit: {o['fav']} → {n['fav']}")
        if float(n["hearts"] or 0) != o["hearts_f"] or bool(int(n["gold"])) != o["gold"]:
            diff.append(f"Herzen: {o['hearts']} → {n['hearts']}{'+G' if n['gold'] == '1' else ''}")
        if int(n["steps"] or 0) < int(o["steps"]):
            diff.append(f"SCHRITTE GESUNKEN {o['steps']} → {n['steps']}")
        if not is_coords(n["location"]) and sim(n["location"], o["location"]) < 0.8:
            diff.append(f"Fundort: {o['location']} → {n['location']}")
        if s < 3:
            weak.append((n, o, s))
        if diff:
            changes.append((n, o, diff))

    new_only = [new_rows[i] for i in range(len(new_rows)) if i not in used_new]
    gone = [old_rows[j] for j in range(len(old_rows)) if j not in used_old]

    print(f"Erfasst: {len(new_rows)} · Herbarium: {len(old_rows)} · zugeordnet: {len(match)}")
    print(f"\nNeu ({len(new_only)}):")
    for n in new_only:
        print(f"  #{n['n']} {n['name']} · {n['spot']} · {n['location']} · {n['date']}")
    print(f"\nNicht mehr gefunden ({len(gone)}):")
    for o in gone:
        print(f"  [{o['frame']}] {o['name']} · {o['spot']} · {o['location']} · {o['date']}")
    print(f"\nUnsichere Zuordnungen ({len(weak)}):")
    for n, o, s in weak:
        print(f"  #{n['n']} {n['name']} / {n['location']}  ⇄  [{o['frame']}] {o['name']} / {o['location']}  (Score {s:.1f})")
    notable = [(n, o, d) for n, o, d in changes if any(not x.startswith("Herzen") for x in d)]
    print(f"\nÄnderungen außer Herzen/Schritten ({len(notable)}):")
    for n, o, d in notable:
        print(f"  [{o['frame']}] #{n['n']}: " + " · ".join(d))
    print(f"\nNur Herzen geändert: {len(changes) - len(notable)}")


if __name__ == "__main__":
    main()
