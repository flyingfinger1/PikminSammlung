"""Interactive menu of the Pikmin Herbarium: ADB scan, evaluation, apply, publish.

Start: py tools/pikmin.py   (or double-click pikmin.bat in the project folder)

Runs the single scripts one after another and remembers the scan folder used last
(captures/.last_run), so it never has to be typed.
"""
import csv
import json
import os
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from paths import FROZEN, ROOT
from ui import ask, location as show_loc, name as show_name, spot as show_spot, tr

TOOLS = ROOT / "tools"
# the packaged app runs each step as a subcommand of itself (tools/app.py)
COMMANDS = {"capture_adb.py": "capture", "parse_captures.py": "parse", "diff_capture.py": "diff",
            "apply_capture.py": "apply", "build_page.py": "build", "publish.py": "publish",
            "parse_seeds.py": "seeds"}
CAPTURES = ROOT / "captures"
LAST = CAPTURES / ".last_run"
SEEDS_DIR = CAPTURES / "seeds"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

PHONE_CHECK = tr("""
Vorbereitung am Handy:
  - per USB angeschlossen und entsperrt, 'Nicht stören' an
  - Pikmin Bloom auf Deutsch oder Englisch
  - Pikmin-Liste im Spiel NACH DEKO sortiert (sonst keine Sticker-Motive/Park-Sets)
  - das ERSTE Pikmin AUSSERHALB der Gruppe ist geöffnet""", """
Prepare the phone:
  - connected via USB and unlocked, 'Do not disturb' on
  - Pikmin Bloom in German or English
  - Pikmin list in the game sorted BY DECOR (otherwise no sticker motifs/park sets)
  - the FIRST Pikmin OUTSIDE the squad is open""")

SEED_CHECK = tr("""
Vorbereitung am Handy:
  - per USB angeschlossen und entsperrt, 'Nicht stören' an
  - Keim-Liste im Spiel NACH DEKO sortiert (sonst keine Sticker-Motive/Park-Sets)
  - den ERSTEN Keim der Liste geöffnet""", """
Prepare the phone:
  - connected via USB and unlocked, 'Do not disturb' on
  - seedling list in the game sorted BY DECOR (otherwise no sticker motifs/park sets)
  - the FIRST seedling of the list is open""")

REVIEW_HINT = tr("""
Im Bericht oben prüfen:
  - 'Nicht mehr gefunden'     -> nur okay, wenn du Pikmin freigelassen hast
  - 'Unsichere Zuordnungen'   -> genauer anschauen
  - 'SCHRITTE GESUNKEN'       -> Hinweis auf eine Verwechslung
  - 'Set offen'               -> nur ein Hinweis, kein Fehler""", """
Check the report above:
  - 'Not found any more'      -> only fine if you released Pikmin
  - 'Uncertain matches'       -> take a closer look
  - 'STEPS WENT DOWN'         -> points to a mix-up
  - 'set open'                -> just a note, not an error""")


# ---------- helpers ----------

def run_script(script, *args):
    print()
    step = [COMMANDS[script]] if FROZEN else [str(TOOLS / script)]
    result = subprocess.run([sys.executable, *step, *map(str, args)], cwd=ROOT, env=ENV)
    return result.returncode == 0


def wait(message=None):
    input(message or tr("Weiter mit Enter ...", "Press Enter to continue ..."))


def headline(text):
    print(f"\n=== {text} " + "=" * max(0, 60 - len(text)))


def all_runs():
    if not CAPTURES.exists():
        return []
    return sorted(p for p in CAPTURES.iterdir()
                  if p.is_dir() and p.name[:2] == "20" and not p.name.endswith("_test"))


def current_run():
    if LAST.exists():
        path = Path(LAST.read_text(encoding="utf-8").strip())
        if path.exists():
            return path
    runs = all_runs()
    return runs[-1] if runs else None


def remember(run):
    CAPTURES.mkdir(exist_ok=True)
    LAST.write_text(str(run), encoding="utf-8")


def need_run():
    run = current_run()
    if run is None:
        print(tr("Noch kein Scan-Ordner vorhanden - zuerst einen Scan machen.",
                 "No scan folder yet - make a scan first."))
    return run


def card_count(run):
    log = run / "log.jsonl"
    return sum(1 for _ in log.open(encoding="utf-8")) if log.exists() else 0


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def when(value):
    """A timestamp (ISO string or file) as "20.09. 15:12"."""
    if isinstance(value, Path):
        value = datetime.fromtimestamp(value.stat().st_mtime) if value.exists() else None
    elif value:
        value = datetime.fromisoformat(value)
    return value.strftime("%d.%m. %H:%M") if value else None


def report_of(run):
    """The report of the last comparison - only as long as it still describes this parsed.tsv."""
    report, parsed = read_json(run / "report.json"), run / "parsed.tsv"
    if not report or not parsed.exists():
        return None
    return report if (run / "report.json").stat().st_mtime >= parsed.stat().st_mtime else None


def collection():
    tsv = ROOT / "data/pikmin.tsv"
    if not tsv.exists():
        return 0, None
    with tsv.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return len(rows), max((r.get("seen") or "" for r in rows), default=None)


def seed_state():
    runs = seed_runs()
    if not runs:
        return None
    parsed = runs[-1] / "parsed.tsv"
    count = sum(1 for _ in parsed.open(encoding="utf-8")) - 1 if parsed.exists() else None
    return runs[-1].name[:10], count


def status():
    """What is in the collection, in the current scan and on the page - the menu shows it above
    every choice, so nothing has to be remembered between steps."""
    count, seen = collection()
    print(tr(f"\nHerbarium: {count} Pikmin" + (f" · zuletzt gescannt {seen}" if seen else ""),
             f"\nHerbarium: {count} Pikmin" + (f" · last scanned {seen}" if seen else "")))

    run = current_run()
    if run is None:
        print(tr("Scan: noch keiner vorhanden", "Scan: none yet"))
    else:
        parts = [f"{card_count(run)} " + tr("Karten", "cards")]
        report = report_of(run)
        if not (run / "parsed.tsv").exists():
            parts.append(tr("noch nicht ausgewertet", "not evaluated yet"))
        elif not report:
            parts.append(tr("Auswertung veraltet - 6", "evaluation out of date - 6"))
        else:
            parts.append(tr(f"{report['matched']} zugeordnet", f"{report['matched']} matched"))
            for count_, label in ((len(report["new"]), tr("neu", "new")),
                                  (len(report["gone"]), tr("nicht gefunden", "not found")),
                                  (len(report["weak"]) + len(report["problems"]),
                                   tr("zum Prüfen", "worth a look"))):
                if count_:
                    parts.append(f"{count_} {label}")
        applied = read_json(run / "applied.json")
        if applied:
            parts.append(tr(f"übernommen {when(applied['when'])}", f"applied {when(applied['when'])}"))
        elif seen and seen == run.name[:10]:  # applied before this mark existed, on the scan day
            parts.append(tr(f"übernommen am {seen}", f"applied on {seen}"))
        else:
            parts.append(tr("noch nicht übernommen", "not applied yet"))
        print(f"Scan {run.name}: " + " · ".join(parts))

    index, published = ROOT / "web/index.html", read_json(ROOT / "web/.published.json")
    if index.exists():
        line = tr(f"Seite: gebaut {when(index)}", f"Page: built {when(index)}")
        if published:  # without the mark nothing is known: it may have gone online by other means
            online = datetime.fromisoformat(published["when"]).timestamp() >= index.stat().st_mtime
            line += tr(f" · veröffentlicht {when(published['when'])}", f" · published {when(published['when'])}") \
                if online else tr(" · seit dem Bauen nicht veröffentlicht", " · not published since it was built")
        print(line)
    seeds = seed_state()
    if seeds:
        print(tr(f"Keime: {seeds[1]} vom {seeds[0]}", f"Seedlings: {seeds[1]} from {seeds[0]}"))


# ---------- steps ----------

def step_scan():
    headline(tr("Neuer Scan", "New scan"))
    print(PHONE_CHECK)
    if not ask(tr("Alles bereit?", "All set?")):
        return None
    before = set(all_runs())
    run_script("capture_adb.py")
    new = [p for p in all_runs() if p not in before]
    if not new:
        print(tr("Es wurde kein Scan-Ordner angelegt.", "No scan folder was created."))
        return None
    run = new[-1]
    remember(run)
    step_resume_until_done(run)
    return run


def step_resume_until_done(run):
    """After a stop the user fixes the phone and continues in the same folder."""
    while not ask(tr(f"Ist der Scan mit 'Ende: ...' fertig geworden? ({card_count(run)} Karten bisher)",
                     f"Did the scan finish with 'End: ...'? ({card_count(run)} cards so far)")):
        print(tr("Problem am Handy beheben (Kabel, entsperren, Popup schließen), Pikmin Bloom offen lassen.",
                 "Fix the phone (cable, unlock, close the popup), keep Pikmin Bloom open."))
        wait(tr("Wenn bereit: Enter zum Fortsetzen ...", "When ready: press Enter to continue ..."))
        run_script("capture_adb.py", "--resume", run)


def step_group(run):
    headline(tr("Gruppe anhängen", "Append the squad"))
    print(tr("Öffne das ERSTE Pikmin in der Gruppe (nur nötig, wenn Pikmin in einer Gruppe sind).",
             "Open the FIRST Pikmin in the squad (only needed if Pikmin are in a squad)."))
    wait(tr("Wenn geöffnet: Enter ...", "When it is open: press Enter ..."))
    run_script("capture_adb.py", "--resume", run)
    step_resume_until_done(run)


def worth_a_look(report):
    """Cards of this scan that may need a second shot, with the reason."""
    if not report:
        return []
    out = {}
    for c in report["problems"]:
        out.setdefault(c["card"], (c, c["problem"]))
    for c in report["weak"]:
        out[c["card"]] = (c, tr(f"unsichere Zuordnung zu Nr. {c['no']}", f"uncertain match to no. {c['no']}"))
    for c in report["changes"]:
        if any(w.startswith(("SCHRITTE", "STEPS")) for w in c["what"]):
            out[c["card"]] = (c, " · ".join(c["what"]))
    for c in report["new"]:
        out.setdefault(c["card"], (c, tr("neu im Herbarium", "new to the herbarium")))
    return [out[k] for k in sorted(out)]


def step_single(run):
    headline(tr("Einzelkarte neu aufnehmen", "Re-take a single card"))
    picks = worth_a_look(report_of(run))
    target = None
    if picks:
        print(tr("Karten aus dem letzten Bericht, die einen zweiten Blick wert sind:",
                 "Cards from the last report that are worth a second look:"))
        for i, (c, why) in enumerate(picks[:9], start=1):
            print(f"  {i}) " + tr(f"Karte {c['card']}", f"card {c['card']}") + f" {show_name(c['name'])}"
                  f" · {show_spot(c['spot'])} · {show_loc(c['location'])} · {c['date']}\n     {why}")
        choice = input(tr("Nummer (Enter = die Karte, die gerade am Handy offen ist): ",
                          "Number (Enter = the card that is open on the phone now): ")).strip()
        if choice.isdigit() and 1 <= int(choice) <= len(picks[:9]):
            target = picks[int(choice) - 1][0]
    if target:
        print(tr(f"\nÖffne im Spiel: {show_name(target['name'])} · {show_spot(target['spot'])}"
                 f" · {show_loc(target['location'])} · {target['date']}",
                 f"\nOpen in the game: {show_name(target['name'])} · {show_spot(target['spot'])}"
                 f" · {show_loc(target['location'])} · {target['date']}"))
        # the card number is its place in the list: the same order the scan went through
        print(tr(f"  In der nach Deko sortierten Liste ist das Pikmin Nummer {target['card']}"
                 " (von oben gezählt, ohne die Gruppe).",
                 f"  In the list sorted by decor it is Pikmin number {target['card']}"
                 " (counted from the top, without the squad)."))
    else:
        print(tr("\nÖffne das Pikmin, dessen Karte oder Porträt gestört war (Popup schließen).",
                 "\nOpen the Pikmin whose card or portrait was covered (close the popup)."))
    wait(tr("Wenn geöffnet: Enter ...", "When it is open: press Enter ..."))
    extra = ["--replace", str(target["card"])] if target else []
    run_script("capture_adb.py", "--single", run, *extra)


def step_review(run):
    headline(tr(f"Auswerten: {run.name}", f"Evaluate: {run.name}"))
    if not run_script("parse_captures.py", run):
        print(tr("Auswertung fehlgeschlagen - Meldung oben lesen.", "Evaluation failed - read the message above."))
        return False
    headline(tr("Abgleich mit dem Herbarium", "Compare with the herbarium"))
    run_script("diff_capture.py", run)
    print(REVIEW_HINT)
    return True


def step_apply(run):
    headline(tr("Übernehmen und Seite bauen", "Apply and build the page"))
    if not (run / "parsed.tsv").exists():
        print(tr("Erst auswerten.", "Evaluate first."))
        return False
    report = report_of(run)
    if report is None:
        print(tr("Der Bericht passt nicht mehr zum Scan - erst Punkt 6 (auswerten).",
                 "The report does not match the scan any more - run step 6 (evaluate) first."))
        return False
    print(tr(f"Der Bericht meldet: {report['matched']} zugeordnet, {len(report['new'])} neu, "
             f"{len(report['gone'])} nicht mehr gefunden",
             f"The report says: {report['matched']} matched, {len(report['new'])} new, "
             f"{len(report['gone'])} not found any more"))
    if not ask(tr("Bericht geprüft - ins Herbarium übernehmen? (Sicherung: data/pikmin.tsv.bak)",
                  "Report checked - apply it to the herbarium? (backup: data/pikmin.tsv.bak)"), default=False):
        return False
    remove = False
    if report["gone"]:
        # only worth asking when something really is missing - and only with the Pikmin in view
        print(tr(f"\nDiese {len(report['gone'])} Pikmin kommen im Scan nicht vor:",
                 f"\nThese {len(report['gone'])} Pikmin are not in the scan:"))
        for g in report["gone"]:
            print(tr(f"  Nr. {g['no']}", f"  no. {g['no']}") + f" {show_name(g['name'])}"
                  f" · {show_spot(g['spot'])} · {show_loc(g['location'])} · {g['date']}")
        remove = ask(tr("Aus dem Herbarium entfernen? (nur wenn du sie freigelassen hast oder es "
                        "Doppelte sind - sonst bleiben sie erhalten)",
                        "Remove them from the herbarium? (only if you released them or they are "
                        "duplicates - otherwise they stay)"), default=False)
    extra = ["--remove-missing"] if remove else []
    if run_script("apply_capture.py", run, *extra) and run_script("build_page.py"):
        print(tr("\nFertig gebaut.", "\nBuilt."))
        return True
    return False


def step_publish():
    headline(tr("Veröffentlichen", "Publish"))
    if not (ROOT / "publish.local.json").exists():
        print(tr("publish.local.json fehlt (Server-Adresse + Upload-Token) - siehe README.",
                 "publish.local.json is missing (server address + upload token) - see the README."))
        return False
    return run_script("publish.py")


def seed_runs():
    if not SEEDS_DIR.exists():
        return []
    return sorted(p for p in SEEDS_DIR.iterdir()
                  if p.is_dir() and p.name[:2] == "20" and not p.name.endswith("_test"))


def step_seeds():
    headline(tr("Keime scannen", "Scan seedlings"))
    print(SEED_CHECK)
    if not ask(tr("Alles bereit?", "All set?")):
        return
    before = set(seed_runs())
    run_script("capture_adb.py", "--seeds")
    new = [p for p in seed_runs() if p not in before]
    if not new:
        print(tr("Es wurde kein Scan-Ordner angelegt.", "No scan folder was created."))
        return
    step_resume_until_done(new[-1])
    if run_script("parse_seeds.py", new[-1]) and run_script("build_page.py"):
        print(tr("\nFertig: Reiter 'Keime' auf der Seite (lokal: 9, online nach 8).",
                 "\nDone: tab 'Seedlings' on the page (locally: 9, online after 8)."))


def open_page():
    page = ROOT / "web" / "index.html"
    if page.exists():
        webbrowser.open(page.as_uri())
    else:
        print(tr("web/index.html gibt es noch nicht.", "web/index.html does not exist yet."))


def full_update():
    run = step_scan()
    if run is None:
        return
    if ask(tr("Sind Pikmin in einer Gruppe?", "Are Pikmin in a squad?"), default=False):
        step_group(run)
    if not step_review(run):
        return
    while ask(tr("Einzelkarte neu aufnehmen (z. B. Popup im Porträt)?",
                 "Re-take a single card (e.g. a popup over the portrait)?"), default=False):
        step_single(run)
        step_review(run)
    if not step_apply(run):
        return
    if ask(tr("Auf dem Server veröffentlichen?", "Publish on the server?")):
        step_publish()
    elif ask(tr("Seite lokal im Browser öffnen?", "Open the page locally in the browser?"), default=False):
        open_page()


def choose_run():
    runs = all_runs()
    if not runs:
        print(tr("Keine Scan-Ordner vorhanden.", "No scan folders yet."))
        return
    for i, r in enumerate(runs[-9:], start=1):
        mark = tr(" <- aktuell", " <- current") if r == current_run() else ""
        print(f"  {i}) {r.name}  ({card_count(r)} {tr('Karten', 'cards')}){mark}")
    choice = input(tr("Nummer (Enter = abbrechen): ", "Number (Enter = cancel): ")).strip()
    if choice.isdigit() and 1 <= int(choice) <= len(runs[-9:]):
        remember(runs[-9:][int(choice) - 1])


MENU = tr("""
Pikmin-Herbarium
  1) Komplettes Update (geführt)
  -- einzelne Schritte --
  2) Neuer Scan
  3) Scan fortsetzen (nach Abbruch)
  4) Gruppe anhängen
  5) Einzelkarte neu aufnehmen
  6) Auswerten + Abgleich anzeigen
  7) Übernehmen + Seite bauen
  8) Veröffentlichen (Server)
  9) Seite lokal im Browser öffnen
 10) Scan-Ordner wählen
 11) Keime scannen + auswerten
  0) Beenden""", """
Pikmin Herbarium
  1) Full update (guided)
  -- single steps --
  2) New scan
  3) Continue a scan (after a stop)
  4) Append the squad
  5) Re-take a single card
  6) Evaluate + show comparison
  7) Apply + build page
  8) Publish (server)
  9) Open the page locally in the browser
 10) Choose scan folder
 11) Scan + evaluate seedlings
  0) Quit""")


def main():
    while True:
        print(MENU)
        status()
        run = current_run()
        choice = input(tr("Auswahl: ", "Choice: ")).strip()
        try:
            if choice == "1":
                full_update()
            elif choice == "2":
                step_scan()
            elif choice in ("3", "4", "5", "6", "7") and (run := need_run()):
                {"3": lambda: (run_script("capture_adb.py", "--resume", run), step_resume_until_done(run)),
                 "4": lambda: step_group(run),
                 "5": lambda: step_single(run),
                 "6": lambda: step_review(run),
                 "7": lambda: step_apply(run)}[choice]()
            elif choice == "8":
                step_publish()
            elif choice == "9":
                open_page()
            elif choice == "10":
                choose_run()
            elif choice == "11":
                step_seeds()
            elif choice == "0":
                return
        except KeyboardInterrupt:
            print(tr("\nAbgebrochen - zurück zum Menü.", "\nCancelled - back to the menu."))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print()
