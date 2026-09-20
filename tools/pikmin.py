"""Interactive menu of the Pikmin Herbarium: ADB scan, evaluation, apply, publish.

Start: py tools/pikmin.py   (or double-click pikmin.bat in the project folder)

Runs the single scripts one after another and remembers the scan folder used last
(captures/.last_run), so it never has to be typed.
"""
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from paths import FROZEN, ROOT
from ui import ask, tr

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


def step_single(run):
    headline(tr("Einzelkarte neu aufnehmen", "Re-take a single card"))
    print(tr("Öffne das Pikmin, dessen Karte oder Porträt gestört war (Popup schließen).",
             "Open the Pikmin whose card or portrait was covered (close the popup)."))
    wait(tr("Wenn geöffnet: Enter ...", "When it is open: press Enter ..."))
    run_script("capture_adb.py", "--single", run)


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
    if not ask(tr("Bericht geprüft - ins Herbarium übernehmen? (Sicherung: data/pikmin.tsv.bak)",
                  "Report checked - apply it to the herbarium? (backup: data/pikmin.tsv.bak)"), default=False):
        return False
    remove = ask(tr("Pikmin, die der Bericht als 'Nicht mehr gefunden' zeigt, entfernen? "
                    "(nur wenn du sie freigelassen hast oder es Doppelte sind)",
                    "Remove the Pikmin the report lists as 'Not found any more'? "
                    "(only if you released them or they are duplicates)"), default=False)
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
        run = current_run()
        print(MENU)
        print(tr("  Aktueller Scan: ", "  Current scan: ")
              + (f"{run.name} ({card_count(run)} {tr('Karten', 'cards')})" if run else "-"))
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
