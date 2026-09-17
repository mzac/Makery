"""Turn a child's one-line idea into a fuller video prompt, using local Ollama.

LTX 2.5 renders audio, and it will speak a line of dialogue if the prompt
contains one. Writing a prompt that gets a good spoken line out of it is not
something a child will guess at, so this does it for them.

Two things make this safe to put in front of a child:

1. Their idea is checked by `safety.check_prompt` before it reaches the model,
   and the model's output is checked again before it reaches them. An LLM
   between their input and the renderer is exactly what the built-in
   `TextGenerateLTX2Prompt` node does, and why that node is left switched off -
   it has no such check on either side.
2. The model is asked to unload as soon as it is done. Ollama and ComfyUI share
   one 16GB card, and a video render peaks around 15.5GB of it, so an LLM still
   holding VRAM when a render starts would push it into OOM.
"""

import json
import logging
import os
import random
import re

import httpx

from . import config, gallery, i18n, prompts, safety

log = logging.getLogger("makery.scripts")

def ollama_url() -> str:
    """Where Ollama is. A box on the parent page now, with OLLAMA_URL in `.env`
    behind it - see app/config.py. Read at the call, so a corrected address
    reaches the next request with no restart."""
    return config.value("ollama_url")

# qwen3-vl:4b-instruct, from the models already on this box. Picked over the
# larger qwen3:8b on merit as well as size: it wrote richer scene descriptions
# and worked the spoken line in more naturally, while being 3.3GB instead of
# 5.2GB - which matters when ComfyUI peaks around 15.5GB of the same 16GB card.
#
# That is the *seed*: SCRIPT_MODEL fills the row in on the first start and the
# parent page owns it after that, so this is read once and never again. Which
# is why nothing here holds a module constant - see `model()`. It is taken off
# the seeding table rather than off the environment a second time, so there is
# one copy of what the default is.
SEED_MODEL = gallery.DEFAULT_SETTINGS["script_model"]


def model() -> str:
    """Which model writes the ideas, right now.

    A name a parent chose on the parent page, and a name they can change while
    the app is running - so it is read at the call, not at import. A row that
    has somehow been emptied falls back to the seed rather than asking Ollama
    for a model called "".
    """
    return gallery.text("script_model") or SEED_MODEL
def keep_alive() -> str:
    """How long Ollama holds this model after it has answered.

    "0" drops it at once. ComfyUI shares this card and a video render peaks
    near 15.5GB of 16.3GB, so nothing else may be holding VRAM - which is why 0
    is the default. The cost is that every tap pays the load time again; "60s"
    or "5m" on the parent page trades VRAM back for speed, and takes effect on
    the next tap rather than at the next rebuild.
    """
    return gallery.text("script_keep_alive") or "0"


TIMEOUT = float(os.getenv("SCRIPT_TIMEOUT", "180"))

SYSTEM_PROMPT = """You write short prompts for a text-to-video model. \
The person asking is {age} and reads well.
Write it as you would for a capable {age_old}: vivid and specific, with a bit of wit. Not cutesy, not babyish - no "little" this and "tiny" that, no talking down.

Rules:
- Completely safe for a child: no violence, no weapons, no romance, \
nothing scary, nothing gross, nothing rude. But not babyish either - aim \
for clever and vivid, not cute.
- Describe ONE continuous shot. No cuts and no scene changes.
- Describe the setting, what the character looks like, how the camera moves, \
and the lighting.
- Include exactly one short line of spoken dialogue inside double quotes. \
Keep it under twelve words, and short enough to say comfortably in the time \
available.
- Between 50 and 80 words in total.
- Output only the prompt itself. No headings, no lists, no preamble, no \
explanation, no quotation marks around the whole thing."""

PICTURE_SYSTEM = """You write short prompts for a text-to-image model. \
The person asking is {age} and reads well.
Write it as you would for a capable {age_old}: vivid and specific, with a bit of wit. Not cutesy, not babyish - no "little" this and "tiny" that, no talking down.

Rules:
- Completely safe for a child: no violence, no weapons, no romance, \
nothing scary, nothing gross, nothing rude. But not babyish either - aim \
for clever and vivid, not cute.
- Describe ONE still picture. Nothing moves, nobody speaks, there is no camera \
movement and no story - just what the picture shows.
- Say what the main thing looks like, where it is, what else is around it, \
the time of day and the light, and the art style.
- Between 35 and 60 words in total.
- Output only the prompt itself. No headings, no lists, no preamble, no \
explanation, no quotation marks around the whole thing."""

SURPRISE_SYSTEM = """You invent fun picture and video ideas for a capable {age_old}.
Write it as you would for a capable {age_old}: vivid and specific, with a bit of wit. Not cutesy, not babyish - no "little" this and "tiny" that, no talking down.

Rules:
- Completely safe for a child: no violence, no weapons, no romance, \
nothing scary, nothing gross, nothing rude. But not babyish either - aim \
for clever and vivid, not cute.
- One single idea, as one sentence describing a scene. Be playful and \
unexpected - an unusual animal doing an unusual thing, a silly mix-up, a \
tiny adventure.
- Name a subject and what it is doing. Do not mention art styles, lighting, \
camera work or colours; those get added separately.
- Between 8 and 25 words.
- Output only the idea itself. No preamble, no explanation, no quotation marks."""

# Seeds for the idea generator. The model gets one at random so that repeated
# taps do not converge on the same handful of ideas, which is what happens when
# a small model is asked "anything you like" over and over.
SURPRISE_SEEDS = [
    "an animal somewhere it does not belong",
    "a food that has come to life",
    "a tiny creature on a big adventure",
    "a robot trying a hobby for the first time",
    "an everyday object that turned out to be magic",
    "a dinosaur in the modern world",
    "a creature made of weather",
    "an underwater celebration",
    "somebody very small meeting somebody very large",
    "an animal running a shop",
    "a vehicle that should not be able to fly, flying",
    "a mix-up between two completely different animals",
    "a sports match between unlikely players",
    "a musician in a strange concert hall",
    "a cosy scene in an impossible place",
    "an explorer finding something wonderful",
    "a bird building something unexpected",
    "a creature made of something soft",
    "a parade of unusual characters",
    "a garden where the plants are not plants",
]

FRIENDLY_UNAVAILABLE = (
    "The idea helper is having a think and didn't answer. "
    "Write it in your own words and it'll work just fine!"
)
FRIENDLY_REJECTED = (
    "Let's try a different idea! Tell me about a place, an animal, "
    "a character, or an adventure."
)


class ScriptError(RuntimeError):
    """The helper could not produce something usable."""


# Smaller models like to use typographic quotes. LTX looks for dialogue in
# plain double quotes, so fold them before the prompt goes anywhere.
_QUOTES = str.maketrans({"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'"})


# Which of the seven they just typed in. Only ever used to decide whether to
# spend a translation call and which language to answer in - a wrong guess
# costs a second or an answer in the wrong language, never a refusal.
#
# Stop words, because they are what a short sentence is made of: "un petit
# renard" has no rare word in it to look up. One list each, curated so they
# overlap as little as they can - which is most of the work, because five of
# the six are close relatives. The discriminating pairs are worth knowing
# before editing one: Spanish "con / y / muy" against Portuguese
# "com / e / muito", Spanish "el los las del" against Portuguese "o os as do
# da", and almost every Dutch word one letter off its German cousin
# ("een/ein", "met/mit", "van/von", "niet/nicht", "ook/auch").
#
# Words that are also ordinary English are left out however common they are -
# French "chat", which is a whole tab of this app, German "die" and "hat",
# Dutch "is" and "en" - because a sentence they wrote in English has to score
# zero in all six.
_HINTS = {
    "fr": r"le|la|les|un|une|des|du|de|dans|avec|qui|est|sont|et|pour|elle|"
          r"mon|ma|mes|son|sa|ses|ce|cette|au|aux|chien|petit|petite|grand|"
          r"grande|très|ne|pas|sur|ça|c'est|joue|mange|vole",
    "es": r"el|la|los|las|un|una|unos|unas|de|del|en|con|para|por|que|es|"
          r"está|están|muy|pequeño|pequeña|ella|su|sus|este|esta|también|"
          r"sobre|qué|cómo|y|pero|gato|perro|juega|come|vuela",
    "it": r"il|lo|la|gli|le|un|uno|una|di|del|della|nella|con|che|è|sono|per|"
          r"questo|questa|anche|molto|perché|piccolo|piccola|gatto|dei|degli|"
          r"un'|gioca|mangia|vola",
    "pt": r"um|uma|de|da|dos|das|em|na|com|que|não|muito|são|é|ela|ele|meu|"
          r"minha|seu|sua|este|esta|para|por|pequeno|pequena|gato|cão|joga|"
          r"come|voa|você|está",
    "de": r"der|das|ein|eine|einen|einer|einem|und|mit|von|auf|ist|sind|für|"
          r"nicht|sehr|klein|kleine|groß|große|katze|hund|dem|im|zum|zur|"
          r"auch|aber|spielt|fliegt",
    "nl": r"de|het|een|en|met|van|op|zijn|voor|niet|heel|klein|kleine|groot|"
          r"grote|kat|hond|deze|dit|haar|hij|zij|maar|ook|naar|wordt|speelt|"
          r"vliegt",
}

_HINT_RE = {code: re.compile(rf"\b({words})\b", re.IGNORECASE)
            for code, words in _HINTS.items()}

# Letters only one of them uses, worth a point on their own: "ñ" is Spanish
# and nothing else, "ã" and "õ" are Portuguese, "ä ö ü ß" are German, "œ" is
# French. The accented letters the Romance languages *share* - é, è, à, ç -
# say only "not English", which is not enough to pick one, so they are
# deliberately not here. Italian and Dutch have no letter of their own and are
# found on their words alone.
_LETTERS = {"es": "ñ¿¡", "pt": "ãõ", "de": "äöüß", "fr": "œ"}


def detect(text: str) -> str:
    """Their language, or "" for English and for anything too short to tell.

    One point per distinct stop word, one more for a letter only that language
    uses, and two points to answer at all - a lone "de" is French, Spanish,
    Portuguese and Dutch at once, and on its own it means nothing.
    """
    if not text:
        return ""
    scores = {}
    for code, pattern in _HINT_RE.items():
        score = len({m.lower() for m in pattern.findall(text)})
        if any(ch in text for ch in _LETTERS.get(code, "")):
            score += 1
        scores[code] = score
    # max() keeps the first of a tie, and this dict is in the order of _HINTS
    # above, so a tie is decided the same way every time.
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else ""


def looks_translatable(text: str) -> bool:
    """Whether it is worth asking the helper to put this into English."""
    return bool(detect(text))


TRANSLATE_SYSTEM = """You translate a child's picture idea into English.

Reply with ONLY the English translation and nothing else - no quotes, no
explanation, no "here is". Keep every detail: the animals, the colours, the
clothes, the place, the weather, what is happening. Do not add anything that
was not there. If the text is already English, repeat it back unchanged."""


async def to_english(text: str) -> str:
    """Their idea in English, because that is what the picture models understand.

    Measured, not assumed: the same seed with "un petit renard roux portant un
    bonnet de laine... regardant les aurores boréales" lost the hat and the
    northern lights entirely, where the English gave both. So they write and
    reads French, and this is what ComfyUI is handed.

    Falls back to their own words if the helper is down - a worse picture beats
    no picture, and the safety check has already passed either way.
    """
    if not text or not detect(text):
        return text
    payload = {
        "model": model(),
        "system": prompts.text("translate", TRANSLATE_SYSTEM),
        "prompt": text.strip(),
        "stream": False,
        "think": False,
        "keep_alive": keep_alive(),
        "options": {"temperature": 0.1, "num_predict": 300},
    }
    try:
        out = _clean(await _ask(payload))
    except ScriptError:
        log.warning("could not translate; sending their own words through")
        return text
    if not out or not _is_english(out):
        return text
    ok, _, category = safety.check_prompt(out)
    if not ok:
        # The translation is what reaches the model, so it is what must pass.
        log.warning("translation rejected (%s)", category)
        raise ScriptError(FRIENDLY_REJECTED)
    return out


def _is_english(text: str) -> bool:
    """Reject output that slipped into another script.

    The 4b model occasionally drops a CJK word mid-sentence ("a cheerful
    octopus\u5439\u6ce1\u6ce1"). Flux and LTX would render that as garbage, and
    they cannot fix what they cannot read, so it is worth one retry.
    """
    return not any(
        "\u3000" <= ch <= "\u9fff" or "\uac00" <= ch <= "\ud7af" for ch in text
    )


# What to call each language when it is a *model* being told, not them. Kept
# apart from i18n.NAMES, which holds what each one calls itself - that is for
# a chip they read, and "Reply in Nederlands" is not an instruction.
LANGUAGE_NAMES = {
    "fr": "French", "es": "Spanish", "it": "Italian", "de": "German",
    "pt": "Portuguese", "nl": "Dutch",
}


def reading_language(sample: str = "") -> str:
    """Which of the seven what comes back should be in.

    The switch in their Settings wins whenever it is not English: they asked for
    that page, and a helper answering in English halfway down it is the page
    changing language under them. Otherwise it follows what they typed, which is
    all there was to go on before there was a switch - and still the right
    answer on an English page, where a sentence in another language is a
    request for one back.
    """
    chosen = i18n.lang()
    if chosen != "en":
        return chosen
    return detect(sample) or "en"


def _reply_language(sample: str) -> str:
    """Tell the model which language to answer in.

    They read what comes back, so it has to be their language. What ComfyUI gets
    is translated separately - see to_english.
    """
    code = reading_language(sample)
    if code == "en":
        return "Reply in English."
    return (f"Reply in {LANGUAGE_NAMES[code]}, because that is the language "
            "the child reads.")


def _clean(text: str) -> str:
    text = (text or "").strip().translate(_QUOTES)
    # Some models wrap the whole thing in quotes; that would confuse the
    # dialogue quoting the video model looks for.
    if len(text) > 1 and text[0] == '"' and text[-1] == '"' and text.count('"') == 2:
        text = text[1:-1].strip()
    for prefix in ("Prompt:", "Video prompt:", "Here is", "Here's"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].lstrip(": ").strip()
    return " ".join(text.split())


# What the last call looked like, for /api/health. Ollama silently falls back to
# CPU when it cannot fit a model in VRAM, and the only visible symptom is that
# everything gets slow, so it is worth being able to see it.
last_run: dict = {}

# A 4b model on this card runs at hundreds of tokens/sec. On CPU it is one to
# two orders of magnitude slower. Anything under this is CPU, or close enough.
GPU_TOKENS_PER_SEC = 25.0


def _timing(payload: dict, name: str) -> dict:
    """How fast a reply came back, out of Ollama's own counters.

    One arithmetic, two readers: the helper's last run on `/api/health` and the
    Test button on the parent page, which asks the same question of a model
    nobody has committed to yet.
    """
    eval_count = payload.get("eval_count") or 0
    eval_ns = payload.get("eval_duration") or 0
    rate = (eval_count / (eval_ns / 1e9)) if eval_count and eval_ns else None
    return {
        "model": name,
        "tokens_per_sec": round(rate, 1) if rate else None,
        "load_seconds": round((payload.get("load_duration") or 0) / 1e9, 1),
        "total_seconds": round((payload.get("total_duration") or 0) / 1e9, 1),
        "looked_gpu_accelerated": rate is not None and rate >= GPU_TOKENS_PER_SEC,
    }


def _record_run(payload: dict) -> None:
    run = _timing(payload, model())
    rate = run["tokens_per_sec"]
    on_gpu = run["looked_gpu_accelerated"]
    last_run.update(run)
    if rate is not None and not on_gpu:
        log.warning(
            "ollama looks CPU-bound: %.1f tokens/sec for %s. VRAM was probably "
            "still held when it loaded.",
            rate,
            model(),
        )


async def _ask(payload: dict) -> str:
    try:
        async with httpx.AsyncClient(base_url=ollama_url(), timeout=TIMEOUT) as http:
            r = await http.post("/api/generate", json=payload)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPError as exc:
        log.warning("ollama unavailable: %s", exc)
        raise ScriptError(FRIENDLY_UNAVAILABLE) from exc

    _record_run(body)
    return body.get("response", "")


async def placement() -> dict:
    """What Ollama currently has loaded, and whether it is on the GPU.

    `size_vram` against `size` is the honest answer: equal means fully on the
    card, zero means it is running on the CPU.
    """
    try:
        async with httpx.AsyncClient(base_url=ollama_url(), timeout=5.0) as http:
            r = await http.get("/api/ps")
            r.raise_for_status()
            models = r.json().get("models") or []
    except httpx.HTTPError:
        return {"reachable": False, "loaded": []}

    return {
        "reachable": True,
        "loaded": [
            {
                "name": m.get("name"),
                "size_mb": round((m.get("size") or 0) / 1e6),
                "vram_mb": round((m.get("size_vram") or 0) / 1e6),
                "fully_on_gpu": bool(m.get("size_vram")) and m.get("size_vram") == m.get("size"),
            }
            for m in models
        ],
    }


# What `/api/show` said about a model, kept by digest rather than by name: a
# tag that has been re-pulled is a different model with the same name, and the
# digest is the only part of the answer that says so. Capabilities do not
# change under a digest, so this is cached for the life of the process.
_CAPABILITIES: dict[str, list] = {}


async def _capabilities(http: httpx.AsyncClient, name: str, digest: str) -> list:
    """What a model can do, for an Ollama too old to say so in `/api/tags`.

    `/api/show` reads the manifest; it does not load the model, so asking is
    free of VRAM. One call per model ever, and a failure is cached as "no idea"
    rather than retried on every page load.
    """
    if digest in _CAPABILITIES:
        return _CAPABILITIES[digest]
    caps: list = []
    try:
        r = await http.post("/api/show", json={"model": name})
        r.raise_for_status()
        caps = r.json().get("capabilities") or []
    except httpx.HTTPError as exc:
        log.debug("could not ask Ollama about %s: %s", name, exc)
    _CAPABILITIES[digest] = caps
    return caps


async def catalogue() -> dict:
    """Every model Ollama has pulled, with enough about each one to choose it.

    **The app never downloads a model.** This is a list of what is already
    there; a name that is not in it is a name somebody has to `ollama pull`
    first. Anything that can only make embeddings is left out - it cannot
    answer a question, so offering it would only be a way to break the helper.
    """
    try:
        async with httpx.AsyncClient(base_url=ollama_url(), timeout=15.0) as http:
            r = await http.get("/api/tags")
            r.raise_for_status()
            rows = r.json().get("models") or []
            out = []
            for m in rows:
                name = m.get("name") or ""
                if not name:
                    continue
                details = m.get("details") or {}
                # Ollama 0.34 puts capabilities straight into /api/tags. Older
                # ones do not, and then it is one /api/show per model, cached.
                caps = m.get("capabilities")
                if caps is None:
                    caps = await _capabilities(http, name, m.get("digest") or name)
                if caps and "completion" not in caps:
                    continue
                out.append({
                    "name": name,
                    "size_mb": round((m.get("size") or 0) / 1e6),
                    "family": details.get("family") or "",
                    "parameter_size": details.get("parameter_size") or "",
                    "quantization": details.get("quantization_level") or "",
                    # None rather than False when nothing would say: "we could
                    # not find out" and "it cannot see" want different sentences.
                    "vision": ("vision" in caps) if caps else None,
                })
    except httpx.HTTPError as exc:
        log.warning("could not list Ollama's models: %s", exc)
        return {"reachable": False, "models": []}
    out.sort(key=lambda m: m["name"])
    return {"reachable": True, "models": out}


async def installed(names) -> tuple[bool, set]:
    """Which of `names` Ollama actually has. `(did it answer, what it has)`.

    The pair matters: an unreachable Ollama must not be read as "none of these
    exist", which would throw away a parent's choice over a container that is
    merely still starting.
    """
    listing = await catalogue()
    if not listing["reachable"]:
        return False, set()
    have = {m["name"] for m in listing["models"]}
    # A tag that was written without one: Ollama answers "llama3" as
    # "llama3:latest", and refusing the shorter spelling would be pedantry.
    have |= {n.split(":")[0] for n in have}
    return True, {n for n in names if n and (n in have or n.split(":")[0] in have)}


# One short question, so the answer is a sentence rather than an essay and the
# measurement is of the model rather than of how much it wanted to say.
TEST_PROMPT = "Say hello to a child in one short, friendly sentence."


async def try_out(name: str) -> dict:
    """Ask one model one question, and say how fast it answered.

    `keep_alive: 0`, like everything else here: a parent trying three models in
    a row must not leave three of them on the card. The caller clears ComfyUI
    off it first, the same way every other Ollama call does.
    """
    payload = {
        "model": name,
        "prompt": TEST_PROMPT,
        "stream": False,
        "think": False,
        "keep_alive": 0,
        "options": {"temperature": 0.2, "num_predict": 60},
    }
    try:
        async with httpx.AsyncClient(base_url=ollama_url(), timeout=TIMEOUT) as http:
            r = await http.post("/api/generate", json=payload)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPError as exc:
        log.warning("could not try %s: %s", name, exc)
        raise ScriptError(f"Ollama could not run {name}. Is it pulled?") from exc
    reply = " ".join((body.get("response") or "").split())
    if "</think>" in reply:
        reply = reply.rsplit("</think>", 1)[1].strip()
    return {"reply": reply[:400], **_timing(body, name)}


async def generate(idea: str, seconds: int) -> str:
    """Expand `idea` into a video prompt. Raises ScriptError with a kid-safe message."""
    ok, message, _ = safety.check_prompt(idea)
    if not ok:
        raise ScriptError(message)

    payload = {
        "model": model(),
        "system": prompts.text("video_script", SYSTEM_PROMPT),
        "prompt": (
            f"Idea: {idea.strip()}\nThe video is {seconds} seconds long.\n"
            + _reply_language(idea)
        ),
        "stream": False,
        "think": False,
        "keep_alive": keep_alive(),
        "options": {"temperature": 0.8, "num_predict": 260},
    }

    text = _clean(await _ask(payload))

    if not text:
        raise ScriptError(FRIENDLY_UNAVAILABLE)
    if not _is_english(text):
        log.info("script helper drifted out of English; retrying once")
        text = _clean(await _ask(payload))
        if not text or not _is_english(text):
            raise ScriptError(FRIENDLY_UNAVAILABLE)

    # The model's own output gets the same check their typing does.
    ok, _, category = safety.check_prompt(text)
    if not ok:
        log.warning("script helper output rejected (%s)", category)
        raise ScriptError(FRIENDLY_REJECTED)

    return text


async def picture(idea: str) -> str:
    """Expand a few words into a fuller description of one still picture.

    The video helper's prompt is the wrong shape here: it asks for camera
    movement and a line of dialogue, neither of which a picture has, and the
    words get rendered as literal text in the image often enough to matter.
    """
    ok, message, _ = safety.check_prompt(idea)
    if not ok:
        raise ScriptError(message)

    payload = {
        "model": model(),
        "system": prompts.text("picture_script", PICTURE_SYSTEM),
        "prompt": f"Idea: {idea.strip()}\n" + _reply_language(idea),
        "stream": False,
        "think": False,
        "keep_alive": keep_alive(),
        "options": {"temperature": 0.8, "num_predict": 220},
    }

    text = _clean(await _ask(payload))
    if not text or not _is_english(text):
        text = _clean(await _ask(payload))
    if not text or not _is_english(text):
        raise ScriptError(FRIENDLY_UNAVAILABLE)

    ok, _, category = safety.check_prompt(text)
    if not ok:
        log.warning("picture helper output rejected (%s)", category)
        raise ScriptError(FRIENDLY_REJECTED)
    return text


STORY_SYSTEM = """You help a capable {age_old} turn a few words into a short story \
for a comic strip.

Rules:
- Completely safe for a child: no violence, no weapons, no romance, \
nothing scary, nothing gross, nothing rude. But not babyish either - aim \
for clever and vivid, not cute.
- Two or three sentences, no more. It must have a beginning, something that \
happens, and a happy ending - that is what makes it work as panels.
- Name the main character and say what they are like.
- Keep it simple enough to draw: one or two characters, one or two places.
- Output only the story. No headings, no lists, no preamble, no explanation, \
no quotation marks around the whole thing."""


def extract_json(text: str) -> dict | None:
    """The first JSON object in the reply.

    Small models like to wrap JSON in prose or a code fence however firmly they
    are told not to, and failing a whole comic - or a whole song - over a stray
    "Here you go:" would be silly.

    Here rather than in comic.py, where it started: the song writer wants the
    same thing, and music importing comic to get at it would be a dependency
    that says nothing true about either.
    """
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except ValueError:
                        break
        start = text.find("{", start + 1)
    return None


async def story(idea: str) -> str:
    """A few words into a little story with a beginning, middle and end.

    Not the same job as the picture or video helper: a comic needs something
    to *happen* across panels, and "a hedgehog in a pond" is a picture, not a
    story. Written in their language, because they read and edits it - the panel
    descriptions are translated separately on the way to ComfyUI.
    """
    ok, message, _ = safety.check_prompt(idea)
    if not ok:
        raise ScriptError(message)

    payload = {
        "model": model(),
        "system": prompts.text("story", STORY_SYSTEM),
        "prompt": f"Idea: {idea.strip()}\n" + _reply_language(idea),
        "stream": False,
        "think": False,
        "keep_alive": keep_alive(),
        "options": {"temperature": 0.9, "num_predict": 220},
    }

    text = _clean(await _ask(payload))
    if not text or not _is_english(text):
        text = _clean(await _ask(payload))
    if not text or not _is_english(text):
        raise ScriptError(FRIENDLY_UNAVAILABLE)

    ok, _, category = safety.check_prompt(text)
    if not ok:
        log.warning("story helper output rejected (%s)", category)
        raise ScriptError(FRIENDLY_REJECTED)
    return text


async def surprise(seconds: int | None = None) -> str:
    """Invent an idea from nothing, for the Surprise me button.

    Same two-sided check as `generate`: whatever the model returns is run
    through `safety.check_prompt` before it is shown to them.
    """
    seed = random.choice(SURPRISE_SEEDS)
    ask = f"Think of an idea about: {seed}."
    if seconds:
        ask += f" It will become a {seconds} second video."
    # This one invents from nothing, so there is no sentence of theirs to read
    # the language off - which is exactly the case the switch in Settings was
    # for. `_is_english` below only rejects CJK drift, so French passes it.
    ask += "\n" + _reply_language("")

    payload = {
        "model": model(),
        "system": prompts.text("surprise", SURPRISE_SYSTEM),
        "prompt": ask,
        "stream": False,
        "think": False,
        "keep_alive": keep_alive(),
        # Hot, because the whole point is that it is different every time.
        "options": {"temperature": 1.1, "top_p": 0.95, "num_predict": 120},
    }

    text = _clean(await _ask(payload))

    if not text:
        raise ScriptError(FRIENDLY_UNAVAILABLE)
    if not _is_english(text):
        log.info("surprise drifted out of English; retrying once")
        text = _clean(await _ask(payload))
        if not text or not _is_english(text):
            raise ScriptError(FRIENDLY_UNAVAILABLE)

    ok, _, category = safety.check_prompt(text)
    if not ok:
        log.warning("surprise idea rejected (%s)", category)
        raise ScriptError(FRIENDLY_REJECTED)

    return text


DESCRIBE_SYSTEM = """You help a capable {age_old} turn a picture they have chosen into a \
short video. Look at the picture carefully.

Write exactly two parts:
1. One sentence saying what is in the picture, starting "I can see".
2. A blank line, then a video prompt of 40 to 70 words describing how this \
exact scene comes to life: what moves, how the camera moves, and one short \
line of spoken dialogue in double quotes if there is a character or creature. \
Describe only what is really in the picture - do not add new characters or \
change the setting.

Completely safe for a young child. If the picture is a drawing, keep it in the \
spirit of the drawing. Output only those two parts, nothing else."""

# The model does not need a 1280px image to see what is in it, and a smaller
# one is faster to encode and to ship to Ollama.
DESCRIBE_MAX_SIDE = 768


def _shrink_for_model(image_bytes: bytes) -> str:
    """Downscale and return base64 JPEG for Ollama's `images` field."""
    import base64
    import io

    from PIL import Image, ImageOps

    image = Image.open(io.BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((DESCRIBE_MAX_SIDE, DESCRIBE_MAX_SIDE))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85)
    return base64.b64encode(out.getvalue()).decode("ascii")


async def describe(image_bytes: bytes, idea: str, seconds: int, made_from: str = "") -> dict:
    """Look at their picture and suggest how to animate it.

    The same model as the text helper - qwen3-vl is a vision model, which is
    what the "vl" stands for. Their typed words, if any, go in as a steer. Both
    the description and the suggested prompt go through the safety check
    before they see them, exactly like the text-only helper.
    """
    if idea and idea.strip():
        ok, message, _ = safety.check_prompt(idea)
        if not ok:
            raise ScriptError(message)

    ask = f"Here is the picture. It will become a {seconds} second video."
    if made_from and made_from.strip():
        # Checked when it was first typed, and it is their own picture's words.
        ask += f' It was made from this description: "{made_from.strip()[:400]}"'
    if idea and idea.strip():
        ask += f" The child says they would like: {idea.strip()}"
    ask += "\n" + _reply_language(idea or "")

    payload = {
        "model": model(),
        "system": prompts.text("describe", DESCRIBE_SYSTEM),
        "prompt": ask,
        "images": [_shrink_for_model(image_bytes)],
        "stream": False,
        "think": False,
        "keep_alive": keep_alive(),
        "options": {"temperature": 0.7, "num_predict": 260},
    }

    text = _clean_multiline(await _ask(payload))
    if not text or not _is_english(text):
        text = _clean_multiline(await _ask(payload))
        if not text or not _is_english(text):
            raise ScriptError(FRIENDLY_UNAVAILABLE)

    # First paragraph is what it saw; the rest is the prompt.
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(parts) >= 2:
        seen, prompt = parts[0], " ".join(parts[1:])
    else:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        seen, prompt = (lines[0], " ".join(lines[1:])) if len(lines) > 1 else ("", text)
    prompt = " ".join(prompt.split())

    for candidate, label in ((seen, "description"), (prompt, "prompt")):
        ok, _, category = safety.check_prompt(candidate) if candidate else (True, "", "")
        if not ok:
            log.warning("describe helper %s rejected (%s)", label, category)
            raise ScriptError(FRIENDLY_REJECTED)

    if not prompt:
        raise ScriptError(FRIENDLY_UNAVAILABLE)
    return {"description": seen, "prompt": prompt}


LOOK_SYSTEM = """You describe a character in a picture so an artist can draw
them again.

Reply with ONE sentence and nothing else. Say what kind of creature or person
they are, and their colours, hair, clothes and any hat, glasses or accessory -
only what you can actually see. Do not describe the background, the weather,
the mood or what they are doing. Do not use a real person's name. Keep it
suitable for a young child."""


async def look(image_bytes: bytes) -> str:
    """One sentence describing the character in a picture, for reusing them.

    This is what makes "my characters" work at all: a saved sentence, repeated
    in later prompts, gets a family resemblance. It is not the same character
    twice - Flux cannot promise that without extra models - but it is close
    enough that a story reads as being about one person.
    """
    payload = {
        "model": model(),
        "system": prompts.text("look", LOOK_SYSTEM),
        "prompt": "Describe the character in this picture.",
        "images": [_shrink_for_model(image_bytes)],
        "stream": False,
        "think": False,
        "keep_alive": keep_alive(),
        "options": {"temperature": 0.4, "num_predict": 120},
    }

    text = _clean(await _ask(payload))
    if not text or not _is_english(text):
        text = _clean(await _ask(payload))
    if not text or not _is_english(text):
        raise ScriptError(FRIENDLY_UNAVAILABLE)

    ok, _, category = safety.check_prompt(text)
    if not ok:
        log.warning("character look rejected (%s)", category)
        raise ScriptError(FRIENDLY_REJECTED)
    return text[:300]


def _clean_multiline(text: str) -> str:
    """Like _clean, but keeps the paragraph break the describe prompt relies on."""
    text = (text or "").strip().translate(_QUOTES)
    for prefix in ("Prompt:", "Video prompt:", "Here is", "Here's"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].lstrip(": ").strip()
    return text


SCREEN_SYSTEM = """You check pictures for a children's app. Answer with exactly one word.

Answer NO only if the picture shows nudity or sexual content, gore or graphic \
injury, a real weapon pointed at someone, drugs or drug use, or a hateful \
symbol. Everything else - ordinary photos, children's drawings, toys, animals, \
people in normal clothes, cartoons, scenery, food, rooms - is YES.

Answer YES or NO and nothing else."""


async def screen(image_bytes: bytes) -> bool | None:
    """Is this picture fine for a child to animate? True, False, or None if the
    model could not be asked.

    The blocklist only ever sees text; a photo was the one input nothing
    looked at. Written to say NO only for a short, explicit list, so an
    innocent drawing is not refused by an over-cautious model. None means the
    caller decides - the app lets their own camera roll through when the model
    is unreachable, and logs it.
    """
    payload = {
        "model": model(),
        "system": prompts.text("screen", SCREEN_SYSTEM),
        "prompt": "Is this picture fine for a child to use?",
        "images": [_shrink_for_model(image_bytes)],
        "stream": False,
        "think": False,
        "keep_alive": keep_alive(),
        "options": {"temperature": 0, "num_predict": 4},
    }
    try:
        answer = (await _ask(payload)).strip().upper()
    except ScriptError:
        return None
    if answer.startswith("NO"):
        return False
    if answer.startswith("YES"):
        return True
    log.warning("screen: unparseable answer %r", answer)
    return None


async def unload(name: str) -> None:
    """Ask Ollama to drop one named model now.

    By name rather than by role, because the other caller is a parent changing
    which model a job uses: the one they have just stopped using would
    otherwise sit on the card until its own keep-alive ran out.
    """
    if not name:
        return
    try:
        async with httpx.AsyncClient(base_url=ollama_url(), timeout=10.0) as http:
            await http.post(
                "/api/generate",
                json={"model": name, "prompt": "", "keep_alive": 0},
            )
    except httpx.HTTPError as exc:
        log.debug("ollama release failed (harmless): %s", exc)


async def release() -> None:
    """Ask Ollama to drop the model now, freeing VRAM for a render."""
    await unload(model())
