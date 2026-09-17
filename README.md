# Pikmin-Herbarium

Übersicht über alle eigenen Pikmin aus **Pikmin Bloom**: Porträt, Deko, Freundschaft, Schritte,
Fundort und eine Deko-Matrix mit Kandidaten. Die Daten werden per **ADB** direkt vom Handy
gescannt, per Texterkennung (Windows OCR) ausgewertet und als statische Seite gebaut, die auf
einem eigenen Server hinter Passwort läuft.

## Bedienung

Doppelklick auf **`pikmin.bat`** (oder `py tools/pikmin.py`) öffnet das Menü:

| Punkt | Was passiert |
|---|---|
| 1 Komplettes Update | geführt: Scan → Gruppe → Auswerten → Einzelkarten → Übernehmen → Veröffentlichen |
| 2–5 | Scan, Fortsetzen nach Abbruch, Gruppe anhängen, Einzelkarte neu aufnehmen |
| 6 | Auswerten + Abgleich mit dem Herbarium (Bericht prüfen) |
| 7 | Übernehmen (Sicherung `data/pikmin.tsv.bak`) + Seite bauen |
| 8 | Veröffentlichen: lädt `web/index.html` + `web/thumbs.jpg` auf den Server |

Vorbereitung am Handy: USB-Debugging an, per USB verbunden, „Nicht stören“ an, Pikmin-Liste
**nach Deko sortiert**, erstes Pikmin außerhalb der Gruppe geöffnet.

## Ablauf der Skripte (`tools/`)

1. `capture_adb.py` – blättert per ADB durch die Detailansichten, prüft jede Karte (lesbar, nicht
   abgedunkelt), speichert `captures/<Datum_Zeit>/NNN.png` + `log.jsonl`
   (`--resume`, `--single`, `--test`)
2. `parse_captures.py` – OCR-Zeilen → `parsed.tsv` (Herzen und Favoriten-Stern per Pixel,
   Sticker-Motive und Park-Sets aus der Farbreihenfolge der Liste)
3. `diff_capture.py` – ordnet die Karten dem Herbarium zu (Farbe + Funddatum + Ort), Bericht
4. `apply_capture.py` – schreibt `data/pikmin.tsv`, schneidet alle Porträts neu (`web/thumbs.jpg`)
5. `build_page.py` – `data/pikmin.tsv` → `data/pikmin.json`, `data/pikmin.csv`, `web/index.html`
6. `publish.py` – Upload auf den Server

Gesammelte Daten (`captures/`, `data/`, gebaute Seite) bleiben lokal und sind nicht im Repo –
sie enthalten, wo die Pikmin gefunden wurden.

## Server

Kleiner Python-Server (`server/app.py`, nur Standardbibliothek) im Docker-Image
`ghcr.io/flyingfinger1/pikminsammlung`:

- `GET /` – Seite, geschützt per Basic Auth (`VIEW_USER` / `VIEW_PASSWORD`)
- `PUT /api/files/index.html|thumbs.jpg` – Upload mit `Authorization: Bearer <UPLOAD_TOKEN>`;
  atomar geschrieben, vorherige Version bleibt als `<name>.prev` im Volume
- `GET /health` – ohne Login, für den Healthcheck

Das Image enthält keine Daten; die Seite liegt im Volume `pikmin-data`, Updates brauchen daher
keinen neuen Build. Ein neues Image entsteht nur bei einem GitHub-Release (`.github/workflows/release.yml`).

### Deployment

Auf dem Server neben `docker-compose.yml` eine `.env` nach `.env.example` anlegen, dann:

```bash
docker compose pull
docker compose up -d
```

### Lokale Konfiguration zum Veröffentlichen

`publish.local.json` im Projektordner (nicht im Repo):

```json
{"url": "https://pikmin-sammlung.flyingfinger.de", "token": "<UPLOAD_TOKEN des Servers>"}
```
