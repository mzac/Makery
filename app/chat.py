"""A helper they can talk to, backed by whatever Ollama has.

Three things make this different from pointing a child at a chatbot:

1. **Every turn is logged where a parent can read it.** The transcript lives
   beside the media in `.chat.json` and is shown on the parent page. Nothing
   here is private from the grown-ups, and the helper is told to say so.
2. **The whole reply is checked before they see any of it**, which is the
   reason this does not stream. A streamed reply is shown as it arrives, so a
   filter on the finished text has nothing left to protect. Ten seconds of a
   "thinking" animation is the price of the check actually meaning something.
3. **It knows about this app**, so "what should I make?" is answered with
   something they can paste into the picture box rather than a lecture.

The blocklist used here is deliberately *not* the one used for prompts - see
CHAT_CATEGORIES below, which explains why, and how to change it back.
"""

import logging
import os
import json
import time

import httpx

from . import branding, config, gallery, i18n, notify, prompts, safety, scripts

log = logging.getLogger("makery.chat")

def ollama_url() -> str:
    """Where Ollama is. A box on the parent page now, with OLLAMA_URL in `.env`
    behind it - see app/config.py. Read at the call, so a corrected address
    reaches the next request with no restart."""
    return config.value("ollama_url")

# gemma4:12b is 7.6GB. It fits comfortably once ComfyUI has been asked to let
# go of the card, which is what every route here does first - but it does not
# fit *alongside* a render, so chat is refused while something is generating.
#
# The seed, not the answer: CHAT_MODEL fills the row in on the first start and
# the parent page owns it from then on. Read at the call, so changing it there
# reaches the next message without a restart.
SEED_MODEL = gallery.DEFAULT_SETTINGS["chat_model"]


def model() -> str:
    """Which model they are talking to, right now."""
    return gallery.text("chat_model") or SEED_MODEL
def keep_alive() -> str:
    """How long Ollama holds the chat model after a reply.

    Long enough that a back-and-forth does not reload 7.6GB every turn, short
    enough that a forgotten conversation is not still holding the card an hour
    later. Any render releases it explicitly regardless - see main._started.
    """
    return gallery.text("chat_keep_alive") or "5m"


TIMEOUT = float(os.getenv("CHAT_TIMEOUT", "180"))

MAX_MESSAGE_CHARS = 600
# How much of the conversation goes back to the model. Twelve turns is plenty
# for a child's conversation and keeps the prompt small enough to stay fast.
MAX_TURNS = 12

def helper_name() -> str:
    """Who they are talking to. A proper noun, so it is never translated - it
    goes into the instruction the model is given, into the greeting in all
    seven languages, and onto the tab."""
    return gallery.text("chat_name").strip() or "Sparky"


def _who() -> str:
    """How the instruction refers to them. Read at the call like the rest of
    this: renaming the child on the parent page should reach the next message
    they send, not the next rebuild."""
    name = branding.KID_NAME
    return f"a child called {name}" if name else "one child"

# {helper} and {who} are filled in at use, not at import, so a parent editing
# this on the parent page can keep them and they still resolve.
SYSTEM = """You are {helper}, a cheerful helper inside a picture-and-video
making app used by {who}, who is {age} and reads well.

WHO YOU ARE
- You are a computer program, not a person. If they ask, say so plainly and
  kindly. Never claim to be human, and never pretend to be someone real.
- Their grown-ups can read everything said here. If they ask whether it is
  private, tell them the truth: their parents can see it.

HOW YOU TALK
- Warm, funny and encouraging. Never babyish, never preachy - talk to them
  the way you would to a sharp {age_old}, not a small child.
- SHORT. Two or three sentences most of the time. They are reading on a tablet.
- They may write in any of the seven languages this app speaks. Always reply
  in whichever language they used. If they switch, switch with them.
- Use an emoji now and then, not in every sentence.

WHAT THE APP CAN DO, so you can help them use it
- The Picture tab makes a picture from a sentence they type. They can ask for
  one picture or four to choose between, and pick a shape.
- The Video tab makes a short video with sound, from words, from a picture they
  already has, or as "a little film" - two to four linked clips where each one
  carries on from the last, joined into one film. Words inside "speech marks"
  get spoken out loud.
- The Comic tab turns a story into a comic strip with several drawings.
- "Help me write it" turns a few words into a fuller description.
- "Surprise me" invents an idea from nothing, and "Mix up an old one" takes
  something they asked for before and gives it a brand new look.
- The Gallery holds everything they have made. From there they can favourite it,
  name it, tag it, turn a picture into a sticker, grab a picture out of a
  video, record their voice over a video, add a sound effect, compare two
  pictures side by side, or save a character they can put in later pictures.
- "Make it again, but..." keeps the same picture and changes only the words they
  edits. "Make another like this" starts over from scratch instead.
- There is a limit on how many pictures and videos they can make each day, set
  by their parents. If they have run out, tell them kindly to come back tomorrow.

HELPING THEM MAKE THINGS
- When they want an idea, give them ONE they can copy straight into the box, as a
  single vivid sentence. Say what it is, where it is, and what it looks like.
- When their idea is thin, suggest what to add: the place, the light, the
  colours, the art style, what the character is doing.
- Never write the words "speech marks" into a prompt for a picture - a picture
  cannot talk.

WHAT YOU WILL NOT DO
- Nothing scary, violent, gory, sexual, romantic, rude or frightening, and
  nothing about drugs, alcohol, smoking, weapons or self-harm. If they ask,
  say cheerfully that it is not something you can help with here, and offer
  something fun instead. Do not explain the rule at length and do not lecture.
- Do not ask for their full name, their school, where they live, their age,
  or any password. If they offer, gently tell them not to put that online.
- Do not give medical, legal or money advice. Point them at a grown-up.
- No links, no web addresses, no telling them to search the internet.
- If something is upsetting them, be kind, keep it short, and tell them to talk
  to a grown-up they trust.

Answer them now."""

FRIENDLY_REJECTED = (
    "Let's talk about something else! Ask me for a picture idea, "
    "or tell me what you're making."
)
# The same sentence in the other six. Keyed by code so `_rejected()` is a
# lookup rather than a chain of ifs that grows by one every time they ask for
# another language.
FRIENDLY_REJECTED_IN = {
    "fr": (
        "Parlons plutôt d'autre chose ! Demande-moi une idée de dessin, "
        "ou raconte-moi ce que tu fabriques."
    ),
    "es": (
        "¡Hablemos de otra cosa! Pídeme una idea para un dibujo, "
        "o cuéntame qué estás haciendo."
    ),
    "it": (
        "Parliamo di qualcos'altro! Chiedimi un'idea per un disegno, "
        "o raccontami che cosa stai facendo."
    ),
    "de": (
        "Reden wir über etwas anderes! Frag mich nach einer Bildidee, "
        "oder erzähl mir, was du gerade machst."
    ),
    "pt": (
        "Vamos falar de outra coisa! Pede-me uma ideia para um desenho, "
        "ou conta-me o que estás a fazer."
    ),
    "nl": (
        "Laten we het over iets anders hebben! Vraag me om een idee voor een "
        "tekening, of vertel me wat je aan het maken bent."
    ),
}


def _rejected(code: str) -> str:
    return FRIENDLY_REJECTED_IN.get(code, FRIENDLY_REJECTED)
def greeting() -> str:
    """The line the helper opens with, in their language. Its own name is a
    proper noun and stays whatever a parent has called it."""
    return i18n.t("Hi! I'm {name}. Ask me for an idea, or tell me what you'd "
                  "like to make and I'll help you write it. ✨",
                  name=helper_name())


def system_prompt() -> str:
    """The instructions, with the two names filled in. A parent may have
    replaced the text on the parent page; the placeholders are documented
    there and a missing one just leaves the template's brace alone."""
    text = prompts.text("chat", SYSTEM)
    try:
        return text.format(helper=helper_name(), who=_who())
    except (KeyError, IndexError, ValueError):
        log.warning("the chat prompt has a placeholder I do not know; using it as written")
        return text


class ChatError(RuntimeError):
    """The helper could not answer, with something sayable as the reason."""


# Which parts of the blocklist apply to *chat*.
#
# The full list exists to keep things out of a picture, so it blocks ordinary
# words that only matter to an image model: "blood", "wound", "gun", "beer",
# "terrifying". Applying it to a conversation would refuse "why is blood red?"
# and "my knee is injured", which is both useless and baffling to them.
#
# So chat checks only the categories where a match is almost never innocent,
# and leaves the rest to the system prompt above, which tells the model to
# decline and redirect - with the transcript on the parent page as the real
# backstop. "Check the chat against the whole picture list" on the parent page
# uses the whole blocklist instead; CHAT_STRICT seeds that switch on the first
# start and is not read again.
# Named by family rather than one by one: `in_every_language` adds each
# language's copy, so a seventh language cannot arrive with the chat still
# checking English.
CHAT_CATEGORIES = safety.in_every_language(
    "sexual", "minors_sexual", "hate", "real_people",
)
def strict() -> bool:
    from . import gallery

    return gallery.flag("chat_strict", False)


def _check(text: str) -> tuple[bool, str]:
    """(ok, category). The reduced chat list unless a parent asked for all."""
    if not text or not text.strip():
        return False, "empty"
    if len(text) > MAX_MESSAGE_CHARS:
        return False, "length"
    if strict():
        ok, _, category = safety.check_prompt(text)
        return ok, category
    # `safety` runs the loop, not this file. It used to be written out here,
    # which is how the chat tab came to be checking an older filter than the
    # picture card - the glued-together and the short-word passes were added
    # there and this copy knew nothing about either.
    return safety.check_categories(text, CHAT_CATEGORIES)


# --- the transcript ---------------------------------------------------------
#
# Beside the media, like everything else here, so it survives a rebuild and a
# parent can read it without a database. Capped: this is a record of what was
# said lately, not an archive.

FILE = ".chat.json"
def keep_messages() -> int:
    """How much of the conversation is kept for a parent to read."""
    return gallery.whole("chat_keep_messages", 20, 20000)


def _path():
    return gallery.STATE_DIR / FILE


def transcript() -> list[dict]:
    try:
        data = json.loads(_path().read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [m for m in data if isinstance(m, dict) and m.get("text")]


# Who said a line, in the transcript file and as a CSS class on both pages.
# It was "her" until this app stopped being about one particular child;
# everything that *reads* a transcript tests for the helper instead, so a
# file written before the rename still shows the child's lines as the
# child's.
CHILD = "kid"


def _note(who: str, text: str, flagged: str = "") -> None:
    try:
        kept = transcript()
        entry = {"at": time.time(), "who": who, "text": text[:MAX_MESSAGE_CHARS]}
        if flagged:
            entry["flagged"] = flagged
        kept.append(entry)
        _path().write_text(json.dumps(kept[-keep_messages():], indent=1))
    except OSError as exc:
        log.warning("could not write the chat transcript: %s", exc)


def today_count() -> int:
    """How many things the child has said today, for the parent page and the email."""
    lt = time.localtime()
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    return len([m for m in transcript() if m["who"] != "helper" and m.get("at", 0) >= midnight])


def forget() -> None:
    try:
        _path().write_text("[]")
    except OSError as exc:
        log.warning("could not clear the chat transcript: %s", exc)


# --- talking ----------------------------------------------------------------


def _language_note() -> str:
    """The switch in their Settings overrules the prompt's own language rule.

    SYSTEM says "reply in whichever language they used", which is right on an
    English page - a French sentence there is a request for French. With the
    switch set to any of the other six they have asked for the whole page in
    that language, and a helper answering in English halfway down it is the
    page changing language under them. Appended at use rather than edited into SYSTEM, so a parent's
    own version of the instruction gets it too.
    """
    code = i18n.lang()
    if code == "en":
        return ""
    name = scripts.LANGUAGE_NAMES[code].upper()
    return (f"\n\nHER PAGE IS SET TO {name}. Reply in "
            f"{scripts.LANGUAGE_NAMES[code]}, every time, even when they "
            "writes to you in English.")


async def reply(message: str, history: list[dict]) -> dict:
    """One turn. Returns {reply, blocked}. Raises ChatError if it could not ask.

    `history` is what the page has been holding, oldest first, as
    [{"who": "kid"|"helper", "text": ...}]. It is trusted only as far as it is
    trimmed and re-checked here: it comes from the browser.
    """
    reading = scripts.reading_language(message)
    ok, category = _check(message)
    if not ok:
        if category == "length":
            raise ChatError(i18n.t("That's a long one! Say it in fewer words."))
        if category == "empty":
            raise ChatError(i18n.t("Type something first!"))
        log.info("chat message blocked (%s)", category)
        _note(CHILD, message, flagged=category)
        # The same escalation the picture box gets: tell the grown-ups, and
        # close the factory if that is what they asked for.
        from . import lockdown

        lockdown.fire(lockdown.refused("words", "the chat", text=message))
        return {
            "reply": _rejected(reading),
            "blocked": True,
        }

    turns = []
    for item in history[-MAX_TURNS * 2:]:
        text = str(item.get("text") or "")[:MAX_MESSAGE_CHARS].strip()
        if not text:
            continue
        role = "assistant" if item.get("who") == "helper" else "user"
        # Their own past turns are re-checked: the page could have been reloaded
        # with anything in localStorage, and this is what goes to the model.
        if role == "user" and not _check(text)[0]:
            continue
        turns.append({"role": role, "content": text})

    payload = {
        "model": model(),
        "messages": (
            [{"role": "system", "content": system_prompt() + _language_note()}]
            + turns
            + [{"role": "user", "content": message.strip()}]
        ),
        "stream": False,
        "think": False,
        "keep_alive": keep_alive(),
        "options": {"temperature": 0.8, "top_p": 0.95, "num_predict": 320},
    }

    try:
        async with httpx.AsyncClient(base_url=ollama_url(), timeout=TIMEOUT) as http:
            r = await http.post("/api/chat", json=payload)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPError as exc:
        log.warning("chat unavailable: %s", exc)
        raise ChatError(i18n.t("{name} is having a nap right now. Try again in a minute!", name=helper_name())) from exc

    text = ((body.get("message") or {}).get("content") or "").strip()
    if not text:
        raise ChatError(i18n.t("{name} is having a nap right now. Try again in a "
                               "minute!", name=helper_name()))
    # Some models still emit a reasoning block even with think off.
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1].strip()
    text = text[:1200]

    _note(CHILD, message)
    ok, category = _check(text)
    if not ok:
        log.warning("chat reply blocked (%s)", category)
        _note("helper", text, flagged=category)
        return {
            "reply": _rejected(reading),
            "blocked": True,
        }

    _note("helper", text)
    return {"reply": text, "blocked": False}


async def release() -> None:
    """Drop the chat model now, so a render has the whole card.

    Called before every generate, not merely hoped for: gemma4:12b is 7.6GB and
    a video render peaks near 15.5GB of a 16.3GB card.
    """
    await scripts.unload(model())


async def available() -> bool:
    """Whether the chat model is actually installed, for the parent page."""
    try:
        async with httpx.AsyncClient(base_url=ollama_url(), timeout=5.0) as http:
            r = await http.get("/api/tags")
            r.raise_for_status()
            names = [m.get("name", "") for m in (r.json().get("models") or [])]
    except httpx.HTTPError:
        return False
    chosen = model()
    return any(n == chosen or n.split(":")[0] == chosen.split(":")[0]
               for n in names)
