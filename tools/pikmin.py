"""Interaktives Menü für das Pikmin-Herbarium: Scan per ADB, Auswertung, Übernahme.

Start: py tools/pikmin.py   (oder Doppelklick auf pikmin.bat im Projektordner)

Führt die Einzelskripte nacheinander aus und merkt sich den zuletzt benutzten
Scan-Ordner (captures/.last_run), damit man ihn nicht abtippen muss.
"""
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
CAPTURES = ROOT / "captures"
LAST = CAPTURES / ".last_run"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

PHONE_CHECK = """
Vorbereitung am Handy:
  - per USB angeschlossen und entsperrt, 'Nicht stören' an
  - Pikmin-Liste im Spiel NACH DEKO sortiert (sonst keine Sticker-Motive/Park-Sets)
  - das ERSTE Pikmin AUSSERHALB der Gruppe ist geöffnet"""

REVIEW_HINT = """
Im Bericht oben prüfen:
  - 'Nicht mehr gefunden'     -> nur okay, wenn du Pikmin freigelassen hast
  - 'Unsichere Zuordnungen'   -> genauer anschauen
  - 'SCHRITTE GESUNKEN'       -> Hinweis auf eine Verwechslung
  - 'Set offen'               -> nur ein Hinweis, kein Fehler"""


# ---------- helpers ----------

def run_script(script, *args):
    print()
    result = subprocess.run([sys.executable, str(TOOLS / script), *map(str, args)], cwd=ROOT, env=ENV)
    return result.returncode == 0


def ask(prompt, default=True):
    hint = "J/n" if default else "j/N"
    while True:
        answer = input(f"{prompt} [{hint}] ").strip().lower()
        if not answer:
            return default
        if answer in ("j", "ja", "y", "yes"):
            return True
        if answer in ("n", "nein", "no"):
            return False


def wait(message="Weiter mit Enter ..."):
    input(message)


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
        print("Noch kein Scan-Ordner vorhanden - zuerst einen Scan machen.")
    return run


def card_count(run):
    log = run / "log.jsonl"
    return sum(1 for _ in log.open(encoding="utf-8")) if log.exists() else 0


# ---------- steps ----------

def step_scan():
    headline("Neuer Scan")
    print(PHONE_CHECK)
    if not ask("Alles bereit?"):
        return None
    before = set(all_runs())
    run_script("capture_adb.py")
    new = [p for p in all_runs() if p not in before]
    if not new:
        print("Es wurde kein Scan-Ordner angelegt.")
        return None
    run = new[-1]
    remember(run)
    step_resume_until_done(run)
    return run


def step_resume_until_done(run):
    """After a stop ('Abbruch') the user fixes the phone and continues in the same folder."""
    while not ask(f"Ist der Scan mit 'Ende: ...' fertig geworden? ({card_count(run)} Karten bisher)"):
        print("Problem am Handy beheben (Kabel, entsperren, Popup schließen), Pikmin Bloom offen lassen.")
        wait("Wenn bereit: Enter zum Fortsetzen ...")
        run_script("capture_adb.py", "--resume", run)


def step_group(run):
    headline("Gruppe anhängen")
    print("Öffne das ERSTE Pikmin in der Gruppe (nur nötig, wenn Pikmin in einer Gruppe sind).")
    wait("Wenn geöffnet: Enter ...")
    run_script("capture_adb.py", "--resume", run)
    step_resume_until_done(run)


def step_single(run):
    headline("Einzelkarte neu aufnehmen")
    print("Öffne das Pikmin, dessen Karte oder Porträt gestört war (Popup schließen).")
    wait("Wenn geöffnet: Enter ...")
    run_script("capture_adb.py", "--single", run)


def step_review(run):
    headline(f"Auswerten: {run.name}")
    if not run_script("parse_captures.py", run):
        print("Auswertung fehlgeschlagen - Meldung oben lesen.")
        return False
    headline("Abgleich mit dem Herbarium")
    run_script("diff_capture.py", run)
    print(REVIEW_HINT)
    return True


def step_apply(run):
    headline("Übernehmen und Seite bauen")
    if not (run / "parsed.tsv").exists():
        print("Erst auswerten.")
        return False
    if not ask("Bericht geprüft - ins Herbarium übernehmen? (Sicherung: data/pikmin.tsv.bak)", default=False):
        return False
    if run_script("apply_capture.py", run) and run_script("build_page.py"):
        print("\nFertig gebaut.")
        return True
    return False


def step_publish():
    headline("Veröffentlichen")
    if not (ROOT / "publish.local.json").exists():
        print("publish.local.json fehlt (Server-Adresse + Upload-Token) - siehe README.")
        return False
    return run_script("publish.py")


def open_page():
    page = ROOT / "web" / "index.html"
    if page.exists():
        webbrowser.open(page.as_uri())
    else:
        print("web/index.html gibt es noch nicht.")


def full_update():
    run = step_scan()
    if run is None:
        return
    if ask("Sind Pikmin in einer Gruppe?", default=False):
        step_group(run)
    if not step_review(run):
        return
    while ask("Einzelkarte neu aufnehmen (z. B. Popup im Porträt)?", default=False):
        step_single(run)
        step_review(run)
    if not step_apply(run):
        return
    if ask("Auf dem Server veröffentlichen?"):
        step_publish()
    elif ask("Seite lokal im Browser öffnen?", default=False):
        open_page()


def choose_run():
    runs = all_runs()
    if not runs:
        print("Keine Scan-Ordner vorhanden.")
        return
    for i, r in enumerate(runs[-9:], start=1):
        mark = " <- aktuell" if r == current_run() else ""
        print(f"  {i}) {r.name}  ({card_count(r)} Karten){mark}")
    choice = input("Nummer (Enter = abbrechen): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(runs[-9:]):
        remember(runs[-9:][int(choice) - 1])


MENU = """
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
  0) Beenden"""


def main():
    while True:
        run = current_run()
        print(MENU)
        print(f"  Aktueller Scan: {run.name + f' ({card_count(run)} Karten)' if run else '-'}")
        choice = input("Auswahl: ").strip()
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
            elif choice == "0":
                return
        except KeyboardInterrupt:
            print("\nAbgebrochen - zurück zum Menü.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print()
