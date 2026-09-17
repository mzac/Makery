"""Every instruction this app gives a model, in one list a parent can read.

There are twenty-one of them and they decide almost everything about what comes
out: the tone of the idea helper, what the chat helper will and will not talk
about, the rules a comic panel is drawn by, what the upload screen says no to.
They were spread across five modules as module-level constants, readable only
by opening the source.

This does not move them - each one still lives next to the code that uses it,
where it makes sense - it *registers* them, so `/api/parent/prompts` can list
them and a parent can override one. Call sites ask for their prompt by id and
pass their own constant as the fallback:

    payload = {"system": prompts.text("video_script", SYSTEM_PROMPT), ...}

so if the override file is unreadable or a key is missing, the built-in is
what runs. There is no state to get wrong.

Overrides live beside the media in `.prompt-overrides.json`, so they survive a
rebuild like the settings do.
"""

import json
import logging

from . import branding, gallery

log = logging.getLogger("makery.prompts")

FILE = ".prompt-overrides.json"
MAX_CHARS = 8000

# Whether a parent may edit each one from the page at all. Off by default:
# these instructions are the only thing standing between a child and whatever
# a 4b model feels like saying, and a page that invites editing them without
# the person having thought about it is worse than no page. PROMPT_EDITING=1
# in .env turns the Save buttons on.
def editable() -> bool:
    """Whether the parent page may rewrite these, not just read them. A switch
    on that page; `PROMPT_EDITING` in `.env` only seeds it."""
    from . import gallery

    return gallery.flag("prompt_editing", False)


class Prompt:
    """One instruction, and enough about it to be worth showing."""

    def __init__(self, ident, label, blurb, module, attr, safety=False, note=""):
        self.id = ident
        self.label = label
        self.blurb = blurb          # what it is for, in a sentence
        self.module = module        # where the built-in lives
        self.attr = attr
        self.safety = safety        # does it carry rules about what is allowed
        self.note = note            # anything a parent should know before editing


REGISTRY = [
    Prompt("video_script", "Writing a video",
           "Turns a few words into a full video prompt with a line of spoken dialogue. "
           "Behind “Help me write it” on the video card.",
           "scripts", "SYSTEM_PROMPT", safety=True),
    Prompt("picture_script", "Writing a picture",
           "The same, for a still. Asks for no camera movement and no dialogue, which "
           "the video one would otherwise put in and the image model would draw as text.",
           "scripts", "PICTURE_SYSTEM", safety=True),
    Prompt("surprise", "Surprise me",
           "Invents an idea from nothing. Gets one of twenty random themes with it, so "
           "repeated taps do not converge on the same handful of ideas.",
           "scripts", "SURPRISE_SYSTEM", safety=True),
    Prompt("story", "Turning words into a story",
           "A few words into two or three sentences with a beginning, a middle and an "
           "end - what a comic needs and a single scene is not.",
           "scripts", "STORY_SYSTEM", safety=True),
    Prompt("describe", "Looking at a picture",
           "What the vision model is told when they pick a picture and asks for help: "
           "describe what is really there, then write a prompt that animates it.",
           "scripts", "DESCRIBE_SYSTEM", safety=True),
    Prompt("look", "Describing a character",
           "One sentence about how somebody looks, written from a picture. That "
           "sentence is repeated into every later prompt they appear in, so it is the "
           "single thing that decides whether a saved character works.",
           "scripts", "LOOK_SYSTEM"),
    Prompt("screen", "Checking an uploaded photo",
           "The only thing that ever looks at a photo they upload. Deliberately a short "
           "list of things to say no to, so an innocent drawing is not refused by an "
           "over-cautious model.",
           "scripts", "SCREEN_SYSTEM", safety=True,
           note="This one fails *open*: if Ollama is unreachable the photo is let "
                "through and the event is logged. It is their own camera roll on a "
                "home network, and a broken model should not lock them out."),
    Prompt("translate", "French into English",
           "They type in either language; the picture models understand English much "
           "better, so what reaches them is translated. What they read is not.",
           "scripts", "TRANSLATE_SYSTEM"),
    Prompt("chat", "The chat helper",
           "Everything the chat tab is told about who it is talking to, what this app "
           "can do, and what it will not discuss. The longest and most consequential "
           "one here.",
           "chat", "SYSTEM", safety=True,
           note="{helper} and {who} are the helper's name and theirs, both on the "
                "parent page. Keep them if you edit it. Every turn is on the "
                "parent page whatever this says, and the word filter runs "
                "either way."),
    Prompt("comic_panels", "Breaking a story into panels",
           "Turns a story into a JSON list of panels plus one description of the main "
           "character that every panel reuses.",
           "comic", "SYSTEM", safety=True),
    Prompt("film_beats", "Breaking a story into film parts",
           "The same for “a little film”, with the extra rule that each part has to "
           "carry on from where the last one ended, because it is filmed from its "
           "last frame.",
           "comic", "BEAT_SYSTEM", safety=True),
    Prompt("panel_rules", "Rules every comic panel is drawn by",
           "Appended to every panel's prompt. The “no text, no speech bubbles” half is "
           "not optional: the image model letters its own bubbles over the ones the "
           "page draws.",
           "comic", "PANEL_RULES"),
    Prompt("panel_look", "Default comic style",
           "Used only when they have not chosen a style themselves.",
           "comic", "DEFAULT_LOOK"),
    Prompt("cutout", "Making a picture cuttable",
           "Appended when they ask for “a character” rather than “a picture”. This "
           "wording is what makes the sticker cut-out work rather than be a gamble.",
           "styles", "CUTOUT"),
    Prompt("song", "Writing a song",
           "Turns one line into what the song should sound like and the words that "
           "are sung, in one go. Behind \u201cHelp me write it\u201d on the music card.",
           "music", "SYSTEM", safety=True,
           note="The lyrics are the half they will read out loud, so they are "
                "safety-checked on the way back like everything else. Written in "
                "whichever language they asked in - unlike a picture prompt, they "
                "are never translated."),
    Prompt("telegram", "Answering a parent on Telegram",
           "What the bot is told when a parent asks it something in their own words. "
           "It is given today's real numbers and told to answer only from them - it "
           "cannot change anything, and it is told to say so.",
           "telegram", "SYSTEM",
           note="{who} is the child's name, {they} and {their} the pronoun "
                "and the possessive - all three from the parent page. Keep "
                "them if you edit it. Only reaches chat ids on the allowlist, "
                "and only when asking the bot things is on."),
    Prompt("restyle", "Keeping the scene while the style changes",
           "Goes after every one of the \u201cTurn it into...\u201d chips - a "
           "cartoon, a painting, a clay model. It is the half that makes the "
           "result the same picture drawn differently rather than a new "
           "picture of roughly that subject. Say what it should draw and never "
           "what it should not: there is no negative prompt in these graphs, "
           "so \u201cno faces\u201d only puts the word \u201cfaces\u201d in "
           "front of the model.",
           "restyles", "KEEP"),
    Prompt("outpaint", "Looking outside the frame",
           "What is said to the picture model when they tap \u201cWhat\u2019s outside "
           "the frame?\u201d and type nothing - and what goes in front of their words "
           "when they do. The \u201ckeeping everything already in the picture\u201d "
           "half is what stops it composing a new picture in the new space.",
           "styles", "OUTPAINT"),
    Prompt("banner", "Making a banner",
           "Appended when they make a new strip for the top of their own page. The "
           "\u201cno text, no letters\u201d half is not optional: the title is drawn "
           "over it as real text, and the image model would letter its own.",
           "styles", "BANNER"),
    Prompt("negative_image", "Hidden negative prompt (pictures)",
           "Injected into every picture job.",
           "safety", "NEGATIVE_IMAGE",
           note="Has no effect today. The workflows run at CFG 1.0, where negative "
                "conditioning is multiplied by zero and ignored. It is kept in full so "
                "it starts working if CFG is ever raised. The blocklist is the filter "
                "that actually runs."),
    Prompt("negative_video", "Hidden negative prompt (videos)",
           "Injected into every video job. Inert for the same reason.",
           "safety", "NEGATIVE_VIDEO",
           note="See the note on the picture one."),
]

_BY_ID = {p.id: p for p in REGISTRY}


# --- the overrides ----------------------------------------------------------

def _path():
    return gallery.STATE_DIR / FILE


def _overrides() -> dict:
    try:
        data = json.loads(_path().read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k in _BY_ID and isinstance(v, str) and v.strip()}


def text(prompt_id: str, default: str) -> str:
    """What to actually send. The caller's own constant if nothing is set.

    `{age}` and `{age_old}` are filled in here, from their profile's age, so that
    they work
    the same in a parent's edited version as in the built-in - and so that the
    age is written once rather than spelled into fourteen separate prompts.

    Never raises: a bad override file means the built-in runs, which is the
    right way round for something in front of a child.
    """
    try:
        return branding.about(_overrides().get(prompt_id) or default)
    except Exception:  # pragma: no cover
        log.warning("could not read the prompt overrides; using the built-in")
        return branding.about(default)


def _default_for(p: Prompt) -> str:
    """The built-in, imported late so this module does not import in a circle."""
    from importlib import import_module

    try:
        value = getattr(import_module(f".{p.module}", __package__), p.attr, "")
        return value if isinstance(value, str) else str(value)
    except Exception as exc:
        log.warning("could not read the built-in for %s: %s", p.id, exc)
        return ""


def listing() -> dict:
    """Everything, for the parent page."""
    over = _overrides()
    return {
        "editable": editable(),
        "prompts": [
            {
                "id": p.id,
                "label": p.label,
                "blurb": p.blurb,
                "safety": p.safety,
                "note": p.note,
                "where": f"app/{p.module}.py",
                "default": _default_for(p),
                "text": over.get(p.id) or _default_for(p),
                "overridden": p.id in over,
            }
            for p in REGISTRY
        ],
    }


def set_override(prompt_id: str, value: str) -> dict:
    """Set one, or clear it with an empty value. Returns the new listing entry."""
    if prompt_id not in _BY_ID:
        raise KeyError(prompt_id)
    data = _overrides()
    value = (value or "").strip()[:MAX_CHARS]
    if value and value != _default_for(_BY_ID[prompt_id]):
        data[prompt_id] = value
    else:
        data.pop(prompt_id, None)
    # Atomic: `_overrides()` reads a half-written file as "no overrides", which
    # would silently put every instruction back to the built-in. See
    # gallery.write_json.
    gallery.write_json(_path(), data)
    log.info("prompt %r %s", prompt_id, "overridden" if value else "reset to the built-in")
    return next(p for p in listing()["prompts"] if p["id"] == prompt_id)
