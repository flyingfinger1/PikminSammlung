"""Game languages. The collection is stored with the German game names as canonical ids; cards
in another language are translated to them while parsing, so matching, collection and page do
not depend on the language the game was set to during a scan.

Each language lists the words on the detail card the scripts look for, and how to translate
colours, places and decor to the canonical names. Decor without a known German name keeps its
name from the card.
"""
import datetime
import difflib
import re

COLOR_WORDS_DE = {"Rot": "Rotes Pikmin", "Gelb": "Gelbes Pikmin", "Blau": "Blaues Pikmin",
                  "Lila": "Lila Pikmin", "Weiß": "Weißes Pikmin", "Fels": "Fels-Pikmin",
                  "Flügel": "Flügel-Pikmin", "Eis": "Eis-Pikmin"}

GERMAN = {
    "code": "de", "ocr": "de-DE",
    # words on the card (substring of an OCR line)
    "steps": "Schritte", "discovered": "Entdeckt", "squad": "Gruppe", "in_squad": "Aus der Gruppe",
    "rename": "Namen", "share": "teilen", "friendship": "Freundschaft", "walked": "gelaufen",
    "seed": "keim",  # "blauer Keim", "Flügelkeim", "Riesenkeim"
}

ENGLISH = {
    "code": "en", "ocr": "en-US",
    "steps": "steps", "discovered": "Discovered", "squad": "Squad", "in_squad": "Remove from",
    "rename": "Change Name", "share": "Share", "friendship": "Friendship", "walked": "Walked",
    "seed": "seedling",  # "Blue Seedling", "Huge Seedling" (spelling from the wiki, not seen on a card yet)
    "colors": {"Red": "Rot", "Yellow": "Gelb", "Blue": "Blau", "Purple": "Lila", "White": "Weiß",
               "Rock": "Fels", "Winged": "Flügel", "Ice": "Eis"},
    # place on the card -> German place (pikminwiki.com/Decor_Pikmin, in-game order; names
    # confirmed on English cards replace the wiki spelling)
    "spots": {
        "Restaurant": "Restaurant", "Café": "Café", "Sweetshop": "Süßwarenladen",
        "Movie Theater": "Kino", "Pharmacy": "Apotheke", "Zoo": "Zoo", "Forest": "Wald",
        "Waterside": "Am Wasser", "Post Office": "Post", "Art Gallery": "Kunstmuseum",
        "Airport": "Flughafen", "Station": "Bahnhof", "Beach": "Strand",
        "Burger Place": "Burger-Bistro", "Mini-mart": "Eckladen", "Supermarket": "Supermarkt",
        "Bakery": "Bäckerei", "Hair Salon": "Friseur", "Clothes Store": "Boutique", "Park": "Park",
        "Library & Bookstore": "Bibliothek/Bücherladen", "Roadside": "Straße",
        "Sushi Restaurant": "Sushi-Restaurant", "Mountain": "Berg", "Stadium": "Stadion",
        "Rainy Day": "Regentag", "Snowy Day": "Schneetag", "Theme Park": "Themenpark",
        "Bus Stop": "Bushaltestelle", "Italian Restaurant": "Italienisches Restaurant",
        "Ramen Restaurant": "Ramen-Restaurant", "Bridge": "Brücke", "Hotel": "Hotel",
        "Makeup Store": "Kosmetik-Laden", "Shrine": "Schreine und Tempel",
        "Appliances Store": "Elektroladen", "Curry Restaurant": "Curry-Restaurant",
        "DIY Store": "Baumarkt", "University & College": "Universität & College",
        "Mexican Restaurant": "Mexikanisches Restaurant", "Laundry": "Waschsalons & Reinigungen",
        "Korean Restaurant": "Koreanisches Restaurant", "Stationery Store": "Schreibwarenladen",
        "Special": "Extra",
    },
    # decor on the card -> German decor, as far as the German name is known
    "decor": {
        "Chef Hat": "Kochmütze", "Coffee Cup": "Kaffeetasse", "Popcorn Snack": "Popcorn",
        "Popcorn": "Popcorn", "Stag Beetle": "Hirschkäfer", "Acorn": "Eichelhut",
        "Fishing Lure": "Köder", "Toy Airplane": "Spielflugzeug", "Paper Train": "Papierzug",
        "Ticket": "Ticket", "Burger": "Burger", "Banana": "Banane", "Baguette": "Baguette",
        "Pastry": "Gebäck", "Scissors": "Schere", "Hair Tie": "Haargummi", "Clover": "Kleeblatt",
        "Four-Leaf Clover": "Vierblättriger Klee", "Tiny Book": "Buch", "Sticker": "Sticker",
        "Coin": "Münze", "Sushi": "Sushi", "Mountain Pin Badge": "Berg-Anstecknadel",
        "Bus Papercraft": "Papierbus", "Pizza": "Pizza", "Pasta": "Pasta",
        "Bridge Pin Badge": "Brücke-Anstecknadel", "Hotel Amenities": "Hotel-Annehmlichkeiten",
        "Makeup": "Kosmetik", "Curry Bowl": "Curry-Schale", "Tool": "Werkzeug",
        "College Crest Patch": "Uni-Wappen Aufnäher", "Stationery": "Schreibwaren",
        "Leaf Hat": "Blatthut", "Toothbrush": "Zahnpflege",
        "Ball Keychain": "Ball-Schlüsselanhänger",
        # special decor (Extra)
        "Balinese Carving": "Bali-Schnitzerei", "Fall Sticker": "Herbststicker",
        "Mooncake": "Mondkuchen", "Pacifier": "Schnuller", "Shaved Ice": "Shaved Ice",
        "Wurst": "Wurst",
    },
}

LANGS = {"de": GERMAN, "en": ENGLISH}


def detect(lines):
    """Language of a card from its OCR lines (read with any OCR language); None if unclear."""
    text = " ".join(t for _, t in lines)
    hits = {code: sum(L[k] in text for k in ("steps", "discovered", "friendship", "walked"))
            for code, L in LANGS.items()}
    code, score = max(hits.items(), key=lambda kv: kv[1])
    return code if score >= 2 else None


def _lookup(table, text):
    """Exact or OCR-near entry of a translation table; None if nothing is close."""
    if text in table:
        return table[text]
    lower = {k.lower(): v for k, v in table.items()}
    # strict: "Leaf Hat" and "Chef Hat" are 0.75 alike
    hit = difflib.get_close_matches(text.lower(), list(lower), n=1, cutoff=0.85)
    return lower[hit[0]] if hit else None


# ---- English ----------------------------------------------------------------------------

EN_NAME = re.compile(r"^(Red|Yellow|Blue|Purple|White|Rock|Winged|Ice)\s+(?:(.+?)\s+)?Pikmin\b\s*(.*)$")


def en_decor(text):
    """English decor -> canonical German decor; rare decor as "<decor> (Selten)"."""
    text = text.strip()
    rare = re.match(r"^Rare\s+(.+)$", text) or re.match(r"^(.+?)\s*\(Rare\)$", text)
    base = rare.group(1) if rare else text
    de = _lookup(ENGLISH["decor"], base) or base
    return de + " (Selten)" if rare else de


def en_spot(text):
    return _lookup(ENGLISH["spots"], text.strip())


def en_location(text):
    """As the German card writes it: "near Corner Bakery" -> "In der Nähe: Corner Bakery",
    "Hauptstraße, Musterstadt" -> "Hauptstraße Musterstadt"."""
    text = text.strip()
    if text.lower().startswith("near "):
        return "In der Nähe: " + text[5:].strip()
    return re.sub(r"\s*,\s*", " ", text)


def en_name(name):
    """"Blue Baguette Pikmin from near Corner Bakery" -> (canonical name, decor, colour, origin)."""
    m = EN_NAME.match(name.strip())
    if not m:
        return None
    color = ENGLISH["colors"][m.group(1)]
    decor = en_decor(m.group(2)) if m.group(2) else None
    rest = m.group(3)
    origin = en_location(re.sub(r"^.*?\bfrom\s+", "", rest)) if "from" in rest else ""
    base = f"{decor}-Pikmin ({color})" if decor else COLOR_WORDS_DE[color]
    return base, decor, color, origin


EN_WEEKDAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
EN_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
EN_DATE = re.compile(r"Discovered(?:\s*on)?:?\s*([A-Za-z]{3})\w*,?\s*([A-Za-z]{3})\w*\.?\s*(\d{1,2})"
                     r"(?:,?\s*(\d{4}))?")


def en_date(text):
    """"Discovered on: Tue, Sep 8, 2026" -> "2026-09-08". The floating egg button can cover the
    year; then the latest year up to today in which the date falls on that weekday is taken."""
    t = re.sub(r"(\d)\s+(?=\d)", r"\1", text)
    m = EN_DATE.search(t)
    if not m:
        return None
    month = EN_MONTHS.get(m.group(2).capitalize())
    day = int(m.group(3))
    if not month:
        return None
    wd = EN_WEEKDAYS.get(m.group(1).capitalize())
    year = int(m.group(4)) if m.group(4) else None
    if year is not None and not (2021 <= year and _valid(year, month, day)
                                 and datetime.date(year, month, day).weekday() == wd):
        year = None  # misread ("2026" as "2020"): the weekday decides
    if year is None:
        today = datetime.date.today()
        year = next((y for y in range(today.year, 2020, -1)  # the game started in 2021
                     if _valid(y, month, day) and datetime.date(y, month, day) <= today
                     and datetime.date(y, month, day).weekday() == wd), None)
        if wd is None or year is None:
            return None
    return f"{year}-{month:02d}-{day:02d}" if _valid(year, month, day) else None


def _valid(y, m, d):
    try:
        datetime.date(y, m, d)
        return True
    except ValueError:
        return False


EN_STEPS = re.compile(r"(\d{1,3}(?:,\d{3})*)steps")  # fullmatch on the space-free line
