"""The colour schemes they can choose between.

The colours themselves live in `static/style.css`, one `:root[data-theme=...]`
block each, because that is where they are used. This is the list of which ids
exist, so a name can be checked before it is written into the settings and so
the page can build the picker from something rather than a copy of the list.

The ids here and the blocks there have to agree. There is no clever way to
keep them in step - a theme is eighteen colours, and a file that generated CSS
from Python would be harder to read than two lists of six words.
"""

THEMES = [
    {"id": "midnight", "label": "Midnight", "emoji": "\U0001f319"},
    {"id": "bubblegum", "label": "Bubblegum", "emoji": "\U0001f36c"},
    {"id": "ocean", "label": "Ocean", "emoji": "\U0001f30a"},
    {"id": "forest", "label": "Forest", "emoji": "\U0001f333"},
    {"id": "sunset", "label": "Sunset", "emoji": "\U0001f305"},
    {"id": "daylight", "label": "Daylight", "emoji": "☀️"},
]

DEFAULT = THEMES[0]["id"]

_IDS = {t["id"] for t in THEMES}


def public() -> list[dict]:
    """The picker, with the names in their language. Labels only: the ids are
    written into their settings and into the CSS, and they never move."""
    from . import i18n

    return [{**theme, "label": i18n.label("theme", theme["id"], theme["label"])}
            for theme in THEMES]


def known(name: str) -> bool:
    return name in _IDS


def clean(name) -> str:
    """The id to store. An unknown one becomes the default rather than an
    error: the worst case is that their page looks the way it always did."""
    name = (name or "").strip().lower()
    return name if known(name) else DEFAULT
