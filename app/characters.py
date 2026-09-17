"""Characters they can keep and put in things again.

A character is a name plus one sentence describing how they look, written by
the vision model from a picture they already made. That sentence is repeated in
later prompts, which is the whole trick.

Be honest about what this does: it is a **family resemblance**, not the same
character twice. Flux cannot promise identity without extra models, and
pretending otherwise would only disappoint them. What it reliably gets is "a
hedgehog with spiky brown fur in a blue swimsuit" every time, which is enough
for a story to read as being about one person - and the picture is kept too,
so animating *that* gives a genuinely identical starting frame.

Stored as one small JSON file beside the media, like the settings: there are
only ever a handful, and a file they can read is easier to fix than a database.
"""

import json
import logging
import re
import time
import uuid

from . import gallery

log = logging.getLogger("makery.characters")

FILE = ".characters.json"
def limit() -> int:
    """How many they may keep. A number on the parent page; `MAX_CHARACTERS`
    only seeds it."""
    return gallery.whole("max_characters", 1, 100)


class CharacterError(RuntimeError):
    """Something about the cast list is wrong, with a sayable reason."""


def _path():
    return gallery.STATE_DIR / FILE


def listing() -> list[dict]:
    try:
        data = json.loads(_path().read_text())
    except (OSError, ValueError):
        return []
    return [c for c in data if isinstance(c, dict) and c.get("id") and c.get("name")]


def _save(cast: list[dict]) -> None:
    # Atomic: `listing()` treats a file it cannot parse as an empty cast, so a
    # plain write_text interrupted halfway is the whole cast gone. See
    # gallery.write_json.
    gallery.write_json(_path(), cast)


def get(character_id: str) -> dict | None:
    if not character_id:
        return None
    for c in listing():
        if c["id"] == character_id:
            return c
    return None


def add(name: str, look: str, picture_id: str = "") -> dict:
    cast = listing()
    name = " ".join(name.split())[:30]
    if not name:
        raise CharacterError("Give them a name first!")
    most = limit()
    if len(cast) >= most:
        raise CharacterError(f"That's {most} characters already! Say goodbye to one first.")
    if any(c["name"].lower() == name.lower() for c in cast):
        raise CharacterError("You already have someone with that name!")

    character = {
        "id": uuid.uuid4().hex[:8],
        "name": name,
        "look": " ".join(look.split())[:300],
        "picture_id": picture_id,
        "created": time.time(),
    }
    cast.append(character)
    _save(cast)
    log.info("new character %r", name)
    return character


def update(character_id: str, name=None, look=None) -> dict:
    """Rename someone, or reword how they look. Returns the character.

    The look matters more than it sounds: it is the sentence repeated into
    every later prompt, so it is the one knob that actually changes what comes
    out. The model writes a first draft from a picture and it is usually good,
    but "spiky brown fur" when they meant "spiky GINGER fur" is exactly the kind
    of thing they should be able to correct without starting again.
    """
    cast = listing()
    for character in cast:
        if character["id"] == character_id:
            break
    else:
        raise CharacterError("Who's that?")

    if name is not None:
        name = " ".join(str(name).split())[:30]
        if not name:
            raise CharacterError("Give them a name first!")
        clash = any(
            c["name"].lower() == name.lower() and c["id"] != character_id
            for c in cast
        )
        if clash:
            raise CharacterError("You already have someone with that name!")
        character["name"] = name

    if look is not None:
        look = " ".join(str(look).split())[:300]
        if not look:
            raise CharacterError("Say what they look like!")
        character["look"] = look

    _save(cast)
    log.info("updated character %r", character["name"])
    return character


def remove(character_id: str) -> None:
    cast = [c for c in listing() if c["id"] != character_id]
    _save(cast)


def in_prompt(text: str, character_id: str) -> str:
    """Their words with the character worked in, or their words unchanged.

    The name goes in as well as the look, because they wrote "Luna goes to the
    moon" and the model should be told who Luna is rather than have the name
    quietly replaced by a description.
    """
    character = get(character_id)
    if character is None:
        return text
    who = character["name"]
    look = (character.get("look") or "").strip()
    text = text.strip()
    if not text:
        text = who
    if look:
        # The model writes "A round peach with..."; mid-sentence that reads as
        # a typo, so drop the capital unless the word is a name in its own right.
        lead = re.match(r"[A-Za-z]+", look)
        acronym = bool(lead) and len(lead.group(0)) > 1 and lead.group(0).isupper()
        if look[:1].isupper() and not acronym:
            look = look[0].lower() + look[1:]
        text = f"{text.rstrip('. ')}. {who} is {look.rstrip('. ')}."
    return text
