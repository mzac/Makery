"""Turning a story into comic panels.

The model writes the panels; ComfyUI draws them; the **page** lays them out.
That last part is deliberate and follows the card maker: composing the finished
page in the browser means the server needs no font files, and the layout can be
tweaked without a rebuild.

Consistency between panels is the hard part and there is no honest way to
solve it with Flux alone, so this does the two cheap things that help most: a
single wardrobe-and-setting sentence written once and repeated in every panel's
prompt, and one shared style suffix. Panels then look like the same story even
though they are not the same character.
"""

import logging

from . import prompts, safety, scripts, styles

log = logging.getLogger("makery.comic")

MIN_PANELS = 3
MAX_PANELS = 6

SYSTEM = """You write short comic strips for a capable {age_old}.
Write it as you would for a capable {age_old}: vivid and specific, with a bit of wit. Not cutesy, not babyish - no "little" this and "tiny" that, no talking down.

Given a story idea and a number of panels, reply with ONLY a JSON object:
{"look": "...", "panels": [{"scene": "...", "says": "..."}, ...]}

"look" is one sentence naming the main character and exactly what they look
like - species or age, hair, clothes and colours - so every panel can repeat
it. Do not name a real person.

Each "scene" is one plain sentence describing what is happening in that panel,
as a picture: who is there, what they are doing, where. **Always write "look"
and "scene" in English**, whatever language the story was given in - they are
instructions for an artist who only reads English. Do not mention panels,
frames, text, speech bubbles or words appearing in the image.

Each "says" is what the character says in that panel: at most eight words,
cheerful, no quotation marks. It may be an empty string for a panel with no
talking. **Write "says" in the same language as the story**, because it is
printed on the page for the child to read.

The panels must tell one story from beginning to end. Keep everything
suitable for a child - but not babyish; they are {age}: no violence, no weapons, nothing frightening.
Reply with the JSON and nothing else."""

FRIENDLY_UNAVAILABLE = "The story helper is having a nap. Try again in a minute!"
FRIENDLY_REJECTED = "Let's tell a different story! Try something else."


async def panels(story: str, count: int) -> dict:
    """{look, panels:[{scene, says}]} for `story`. Raises scripts.ScriptError."""
    ok, message, _ = safety.check_prompt(story)
    if not ok:
        raise scripts.ScriptError(message)

    count = max(MIN_PANELS, min(MAX_PANELS, int(count)))

    # Translate the story *before* asking for panels, not during. Asking a 4b
    # model to restructure and translate at the same time went badly: one
    # French hedgehog came back as a musk ox in panel one and an otter in
    # panels two and three. Given an English story it only has to translate the
    # short spoken lines, which it does reliably.
    reading = scripts.reading_language(story)
    if reading != "en":
        story = await scripts.to_english(story)

    payload = {
        "model": scripts.model(),
        "system": prompts.text("comic_panels", SYSTEM),
        "prompt": (
            f"Story: {story.strip()}\nPanels: {count}\n"
            + _speech_note(reading)
        ),
        "stream": False,
        "think": False,
        "keep_alive": scripts.keep_alive(),
        "format": "json",
        "options": {"temperature": 0.8, "num_predict": 700},
    }

    data = scripts.extract_json(await scripts._ask(payload))
    if not data or not isinstance(data.get("panels"), list):
        log.info("comic helper gave nothing usable; retrying once")
        data = scripts.extract_json(await scripts._ask(payload))
    if not data or not isinstance(data.get("panels"), list):
        raise scripts.ScriptError(FRIENDLY_UNAVAILABLE)

    look = str(data.get("look") or "").strip()[:300]
    out = []
    for panel in data["panels"][:count]:
        if not isinstance(panel, dict):
            continue
        scene = str(panel.get("scene") or "").strip()[:400]
        says = str(panel.get("says") or "").strip().strip('"“”')[:80]
        if scene:
            out.append({"scene": scene, "says": says})
    if len(out) < MIN_PANELS:
        raise scripts.ScriptError(FRIENDLY_UNAVAILABLE)

    # Everything the model wrote gets the same check their typing does.
    for chunk in [look] + [p["scene"] for p in out] + [p["says"] for p in out]:
        if not chunk:
            continue
        ok, _, category = safety.check_prompt(chunk)
        if not ok:
            log.warning("comic helper output rejected (%s)", category)
            raise scripts.ScriptError(FRIENDLY_REJECTED)

    if not scripts._is_english(" ".join(p["scene"] for p in out)):
        raise scripts.ScriptError(FRIENDLY_UNAVAILABLE)

    # Belt and braces: if it wrote the scenes in their language anyway, they
    # still have to reach Flux in English.
    if scripts.detect(" ".join(p["scene"] for p in out)):
        log.info("comic scenes came back in their language; translating them")
        for panel in out:
            panel["scene"] = await scripts.to_english(panel["scene"])
        if look:
            look = await scripts.to_english(look)

    return {"look": look, "panels": out}


def _speech_note(code: str) -> str:
    """What to tell the model about the language the speech is in.

    The *story* has already been translated into English above, because a 4b
    model asked to restructure and translate at once loses track of who the
    character is. So the only thing left in their language is what somebody
    says - which is the half they read.
    """
    if code == "en":
        return "The story is in English."
    name = scripts.LANGUAGE_NAMES[code]
    return (f"The child speaks {name}: write every \"says\" in {name}, and "
            "keep \"look\" and \"scene\" in English.")


# Repeated verbatim in every panel. The "no text" half is not negotiable -
# Flux will happily letter its own speech bubbles over the ones the page draws
# - so it stays even when they have chosen a look of their own.
PANEL_RULES = (
    "full body visible, simple uncluttered background, "
    "no text, no speech bubbles, no lettering, no words"
)
# Only used when they have not picked a style themselves.
DEFAULT_LOOK = (
    "children's comic book art, bold clean outlines, flat bright colours"
)


def panel_prompt(look: str, scene: str, chosen: dict | None = None) -> str:
    """One panel's prompt: what happens, who it happens to, and how it looks.

    Their style choices are appended to *every* panel, which together with the
    repeated character description is what makes six separate renders read as
    one strip.
    """
    text = scene
    if look:
        text = f"{text.rstrip('. ')}. {look.rstrip('. ')}"
    if chosen:
        text = styles.compose(text, chosen)
    else:
        text = f"{text.rstrip('. ')}. {prompts.text('panel_look', DEFAULT_LOOK)}"
    return f"{text.rstrip('. ')}. {prompts.text('panel_rules', PANEL_RULES)}."


# --- the same trick, but as a little film -----------------------------------
#
# A story is the comic idea pointed at the video maker: the model writes the
# beats, the first is filmed from words, and every one after starts from the
# last frame of the one before, so the clips actually join up instead of being
# three unrelated videos about the same subject.

MIN_BEATS = 2
MAX_BEATS = 4

BEAT_SYSTEM = """You plan short films for a capable {age_old}.
Write it as you would for a capable {age_old}: vivid and specific, with a bit of wit. Not cutesy, not babyish - no "little" this and "tiny" that, no talking down.

Given a story idea and a number of parts, reply with ONLY a JSON object:
{"look": "...", "beats": [{"scene": "...", "says": "..."}, ...]}

"look" is one sentence naming the main character and exactly what they look
like - species or age, hair, clothes and colours - so every part can repeat it.
Do not name a real person.

Each "scene" is ONE continuous shot of a few seconds: who is there, what they
are doing, how the camera moves. **Write "look" and "scene" in English**,
whatever language the story was given in - they are instructions for a camera
operator who only reads English.

The parts are filmed one after another, and each one starts from the last
picture of the part before it. So every scene must carry on from where the one
before ended, in the same place, with the same character, wearing the same
things. Do not change location between parts and do not start a part with a
new establishing shot.

Each "says" is one short line the character says out loud in that part: at most
eight words, cheerful, no quotation marks. It may be an empty string. **Write
"says" in the same language as the story**, because it is spoken aloud.

Together the parts tell one story from beginning to end. Keep everything
suitable for a child - but not babyish; they are {age}: no violence, no weapons, nothing frightening.
Reply with the JSON and nothing else."""


async def beats(story: str, count: int) -> dict:
    """{look, beats:[{scene, says}]} for `story`. Raises scripts.ScriptError."""
    ok, message, _ = safety.check_prompt(story)
    if not ok:
        raise scripts.ScriptError(message)

    count = max(MIN_BEATS, min(MAX_BEATS, int(count)))

    # Translated up front for the same reason the comic is: asked to restructure
    # and translate at once, a 4b model loses track of who the character is.
    reading = scripts.reading_language(story)
    if reading != "en":
        story = await scripts.to_english(story)

    payload = {
        "model": scripts.model(),
        "system": prompts.text("film_beats", BEAT_SYSTEM),
        "prompt": (
            f"Story: {story.strip()}\nParts: {count}\n"
            + _speech_note(reading)
        ),
        "stream": False,
        "think": False,
        "keep_alive": scripts.keep_alive(),
        "format": "json",
        "options": {"temperature": 0.8, "num_predict": 600},
    }

    data = scripts.extract_json(await scripts._ask(payload))
    if not data or not isinstance(data.get("beats"), list):
        log.info("story helper gave nothing usable; retrying once")
        data = scripts.extract_json(await scripts._ask(payload))
    if not data or not isinstance(data.get("beats"), list):
        raise scripts.ScriptError(FRIENDLY_UNAVAILABLE)

    look = str(data.get("look") or "").strip()[:300]
    out = []
    for beat in data["beats"][:count]:
        if not isinstance(beat, dict):
            continue
        scene = str(beat.get("scene") or "").strip()[:400]
        says = str(beat.get("says") or "").strip().strip('"“”')[:80]
        if scene:
            out.append({"scene": scene, "says": says})
    if len(out) < MIN_BEATS:
        raise scripts.ScriptError(FRIENDLY_UNAVAILABLE)

    # Everything the model wrote gets the same check their typing does.
    for chunk in [look] + [b["scene"] for b in out] + [b["says"] for b in out]:
        if not chunk:
            continue
        ok, _, category = safety.check_prompt(chunk)
        if not ok:
            log.warning("story helper output rejected (%s)", category)
            raise scripts.ScriptError(FRIENDLY_REJECTED)

    if not scripts._is_english(" ".join(b["scene"] for b in out)):
        raise scripts.ScriptError(FRIENDLY_UNAVAILABLE)

    if scripts.detect(" ".join(b["scene"] for b in out)):
        log.info("story scenes came back in their language; translating them")
        for beat in out:
            beat["scene"] = await scripts.to_english(beat["scene"])
        if look:
            look = await scripts.to_english(look)

    return {"look": look, "beats": out}


def beat_prompt(look: str, beat: dict, chosen: dict | None = None) -> str:
    """One part's video prompt, in the same order main._checked builds one:
    what happens, who it happens to, what they say, then how it looks."""
    text = (beat.get("scene") or "").rstrip(". ")
    if look:
        text = f"{text}. {look.rstrip('. ')}"
    says = (beat.get("says") or "").strip().strip('"“” ')
    if says:
        text = f'{text.rstrip(". ")}. The main character says "{says}".'
    return styles.compose(text, chosen)
