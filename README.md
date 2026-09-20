# Pikmin-Herbarium

A personal catalogue of all your **Pikmin Bloom** Pikmin, built from your own phone:

- **Pikmin** – portrait, colour, decor, friendship (hearts and gold hearts), steps, favourite, where
  and when each Pikmin was found; filter, search and sort.
- **Decor matrix** – every decor type × colour in the order of the in-game decor collection, with
  the missing colours for which you already have a fitting Pikmin (candidates), rare decor marked,
  sums of open candidates and Pikmin that can still earn rare-decor points by reaching level 4.
- **Mushroom battle** – total attack power of your 40 strongest Pikmin for every mushroom type and
  head state (bare, leaf, flower, seasonal flower, flower of the month), including a selectable
  decor event; click a total to see which Pikmin would attack.
- **Seedlings** – which of your seedlings are worth planting now: those that bring a decor type you
  still miss, or give 30 decor points because the rare decor of their category is unlocked. The
  others wait: before the unlock plucking them earns nothing extra, and as a seedling a Pikmin
  cannot reach 4 hearts by accident and use up its decor.

Every view has its own address to share: `#deko-matrix`, `#pilzkampf`, `#keime`, a squad such as
`#pilzkampf/feuer/blume`, or a single Pikmin – the link icon on each card copies `#pikmin/<number>`.
The browser's Back button steps through tabs, matrix clicks and squads.

There is no official way to export your Pikmin, so the collection is read from the screen: a
script pages through the Pikmin detail view over **ADB**, reads each card with the built-in
**Windows OCR** and turns the result into a static page. A small server hosts that page; new
data is uploaded with a token, so updates need no rebuild.

> The game can be set to **German or English** while scanning. The page (switch at the top right)
> and the scripts' messages are available in **German and English**.

## Requirements

- **Windows 10/11** with the OCR language of your game language installed (German or English;
  Windows OCR via PowerShell is used for text recognition)
- either the **Windows app** – no Python needed: download `PikminHerbarium-<version>.zip` from the
  [releases](https://github.com/flyingfinger1/pikmin-herbarium/releases), unzip it and start
  `PikminHerbarium.exe` – or **Python 3.12+** with the packages from `requirements.txt`
  (`py -m pip install -r requirements.txt`)
- **Android Platform-Tools** (`adb`), e.g. `winget install Google.PlatformTools`; if it is missing,
  the scan offers to download Google's official package into the app folder
- An **Android phone** with USB debugging enabled and Pikmin Bloom set to **German or English**.
  Screenshots are scaled to a width of 1080 px, so other resolutions work too; tested with
  720 × 1560, 1080 × 2340, 1080 × 2400 and 1440 × 3120. Below ~1000 px width, steps and dates are
  read from enlarged crops.

## Usage

Start **`PikminHerbarium.exe`**, or with Python double-click **`pikmin.bat`** (or run
`py tools/pikmin.py`), for the interactive menu:

| Option | What it does |
|---|---|
| 1 Full update | guided: scan → group → parse → re-take single cards → apply → publish |
| 2–5 | scan, resume after an interruption, append the Pikmin of a group, re-take the open card |
| 6 | parse the scan and compare it with the collection (review the report) |
| 7 | apply (backup `data/pikmin.tsv.bak`) and build the page |
| 8 | publish `web/index.html` + `web/thumbs.jpg` to your server |
| 11 | scan the seedling list (sorted by decor, first seedling open) and evaluate it for the page |

Before scanning: phone connected via USB, *Do not disturb* on, the Pikmin list **sorted by decor**
(needed to tell the sticker motifs and park sets apart), the first Pikmin **outside** a group opened.
Pikmin in a group are a separate list – append them with option 4.

## Your own settings (not in the repo)

| File | Content |
|---|---|
| `config.local.json` | collection settings, see `config.example.json`: `rare_unlocked` lists the rare decor sets unlocked in your in-game collection (German names, e.g. `"Eichelhut (Selten)"` for the rare Acorn) – applying a scan keeps this list up to date: rare decor unlocks per place, not per decor, and two things in the collection prove it - a Pikmin wearing rare decor, and a place whose normal decor is collected in every colour; both are noted for the whole place without asking. Where the decor sets of a place are not known, a complete collection there is only a hint and you are asked. An entry is never removed again (a released Pikmin does not lock the place); `rare_asked` remembers a "no" and is written by the tool; `language` (`"de"` or `"en"`, optional) is the language of the script messages and the default language of the page – without it the scripts follow the system language and the page the visitor's browser (`PIKMIN_LANG=en` overrides it for a single run); `show_locations: false` keeps where your Pikmin and seedlings were found out of the built page (the place category and the date stay) |
| `publish.local.json` | server URL and upload token, see `publish.example.json` |
| `legal/imprint.html`, `legal/privacy.html` | optional legal notice and privacy policy: built into the page and linked in its footer. Start from the examples `legal/*.example*.html` (German and English; `<name>.en.html` is shown on the English page, `<name>.html` in every language). They are examples, not legal advice – check yourself what your page needs |

Everything you collect – `captures/`, `data/`, the built page – stays local and is ignored by git,
because it contains where your Pikmin were found. The Windows app keeps it next to the exe; to
update the app, replace `PikminHerbarium.exe` and `_internal/` and keep the rest.

## Pipeline (`tools/`)

1. `capture_adb.py` – pages through the detail views over ADB, checks every card (readable, not
   dimmed), stores `captures/<date_time>/NNN.png` + `log.jsonl` (`--resume`, `--single`, `--test`)
2. `parse_captures.py` – OCR lines → `parsed.tsv`; hearts, gold hearts and the favourite star are
   read from pixels; sticker motifs and park sets from the colour order of the list
3. `diff_capture.py` – matches the cards to the collection (colour + discovery date + place), report
4. `apply_capture.py` – writes `data/pikmin.tsv` and recuts all portraits (`web/thumbs.jpg`)
5. `build_page.py` – `data/pikmin.tsv` → `data/pikmin.json`, `data/pikmin.csv`, `web/index.html`
6. `publish.py` – uploads the page to the server

Seedlings: `capture_adb.py --seeds` pages through the seedling detail views into
`captures/seeds/<date_time>/`, `parse_seeds.py` reads type, decor, place and growth; the page
compares them with the collection.

The game language is detected from the first card of a scan. The collection keeps the German game
names as canonical names, so scans in both languages match the same Pikmin; `tools/lang.py`
translates English cards (places, decor, colours, dates). Decor whose German name is not known yet
keeps its English name – add the pair to `ENGLISH["decor"]` in `tools/lang.py`.

The Windows app runs the same steps as subcommands (`PikminHerbarium.exe parse captures/<run>`,
entry point `tools/app.py`); `py packaging/build.py [version]` builds it with PyInstaller into
`dist/`, and every GitHub release attaches the zip (`.github/workflows/release-app.yml`). The app
is not signed, so Windows SmartScreen asks once: "More info" → "Run anyway".

`extract_frames.py`, `make_sheets.py` and `make_thumbs.py` belong to the older workflow that read a
screen recording instead of using ADB.

Game data such as available colours per decor, rare variants and the attack power formula comes
from the [Pikmin Wiki](https://www.pikminwiki.com/Decor_Pikmin) ([mushroom battle](https://www.pikminwiki.com/Mushroom_battle)).

## Server

A small Python server (`server/app.py`, standard library only), published as Docker image
`ghcr.io/flyingfinger1/pikmin-herbarium`:

- `GET /` – the page; public unless `VIEW_USER` and `VIEW_PASSWORD` are set (then Basic Auth).
  Responses carry `X-Robots-Tag: noindex` so search engines do not list the page
- `PUT /api/files/index.html|thumbs.jpg` – upload with `Authorization: Bearer <UPLOAD_TOKEN>`,
  written atomically; the previous version stays as `<name>.prev` in the volume
- `GET /health` – no login, used by the health check

Requests are logged without IP addresses. The page itself loads nothing from other servers: its
fonts are embedded when it is built.

The image contains no data; the page lives in the volume `pikmin-data`. A new image is only built
for a GitHub release (`.github/workflows/release.yml`).

### Deployment

Create a `.env` from `.env.example` with a long random `UPLOAD_TOKEN`. Then run the container in
one of these ways:

**Plain, without a reverse proxy** – the page on port 8080 of the host:

```bash
docker run -d --name pikmin-herbarium --restart unless-stopped --env-file .env -p 8080:8080 -v pikmin-data:/data ghcr.io/flyingfinger1/pikmin-herbarium:latest
```

or as `docker-compose.yml`:

```yaml
services:
  pikmin-herbarium:
    image: ghcr.io/flyingfinger1/pikmin-herbarium:latest
    restart: unless-stopped
    env_file: .env
    volumes:
      - pikmin-data:/data
    ports:
      - "8080:8080"

volumes:
  pikmin-data:
```

Plain HTTP sends the upload token (and the optional login) unencrypted – fine in your home network,
but on the internet put HTTPS in front, e.g. with any reverse proxy (Caddy, Traefik, nginx).

**Behind [caddy-docker-proxy](https://github.com/lucaslorentz/caddy-docker-proxy)** – HTTPS for your
domain: the `docker-compose.yml` of this repo expects its external network `caddy-net`; set your
domain in the `caddy` label and remove the port mapping.

With Compose, start or update it with:

```bash
docker compose pull
docker compose up -d
```

Put the server address (e.g. `http://<host>:8080` or `https://pikmin.example.com`) and the same
token into `publish.local.json` and publish from the menu (option 8).

## License

[MIT](LICENSE). The embedded fonts Figtree and Bricolage Grotesque (`web/fonts/`) are licensed
under the SIL Open Font License 1.1. Pikmin and Pikmin Bloom are trademarks of Nintendo; this is an unofficial fan
project and not affiliated with Nintendo or the developers of the game. Game data comes from the Pikmin Wiki.
