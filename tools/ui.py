"""Language of the script messages: the environment variable PIKMIN_LANG, then "language" in
config.local.json ("de" or "en"), otherwise the language of the system. Messages are written in
place as tr("deutsch", "English").

The collection keeps the German game names; name(), spot() and location() show them in the
message language.
"""
import json
import locale
import os
import re
from pathlib import Path

from lang import COLOR_WORDS_DE, ENGLISH

ROOT = Path(__file__).resolve().parent.parent


def _pick():
    if os.environ.get("PIKMIN_LANG") in ("de", "en"):
        return os.environ["PIKMIN_LANG"]
    try:
        cfg = json.loads((ROOT / "config.local.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    if cfg.get("language") in ("de", "en"):
        return cfg["language"]
    system = (locale.getlocale()[0] or "").lower()  # "de_DE", or "German_Germany" on older Pythons
    return "de" if system.startswith(("de", "german")) else "en"


UI = _pick()


def tr(de, en):
    return de if UI == "de" else en


def _reverse(table):
    out = {}
    for en, de in table.items():
        out.setdefault(de, en)  # the first English spelling is the one on the card
    return out


_DECOR_EN = _reverse(ENGLISH["decor"])
_SPOT_EN = _reverse(ENGLISH["spots"])
_COLOR_EN = _reverse(ENGLISH["colors"])
_PLAIN = {v: k for k, v in COLOR_WORDS_DE.items()}  # "Blaues Pikmin" -> "Blau"


def decor(d):
    if UI == "de" or not d:
        return d
    rare = d.endswith(" (Selten)")
    base = d[:-len(" (Selten)")] if rare else d
    return _DECOR_EN.get(base, base) + (" (Rare)" if rare else "")


def name(n):
    """"Eichelhut-Pikmin (Rot) aus Nalbach" -> "Red Acorn Pikmin from Nalbach" for English."""
    if UI == "de" or not n:
        return n
    base, _, origin = n.partition(" aus ")
    m = re.match(r"^(.+?)-Pikmin \(([^)]+)\)$", base)
    if m:
        text = f"{_COLOR_EN.get(m.group(2), m.group(2))} {decor(m.group(1))} Pikmin"
    elif base in _PLAIN:
        text = f"{_COLOR_EN.get(_PLAIN[base], _PLAIN[base])} Pikmin"
    else:
        text = base
    return text + (" from " + location(origin) if origin else "")


def spot(s):
    return s if UI == "de" or not s else _SPOT_EN.get(s, s)


def location(text):
    if UI == "de" or not text:
        return text
    return "near " + text[len("In der Nähe: "):] if text.startswith("In der Nähe: ") else text
