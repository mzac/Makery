"""What a finished file is called.

Two things name files in this app and neither of them was ever a decision.
**ComfyUI** numbers its own output by scanning the output directory for the
highest `image_000NN_` it can see and adding one - which is why a delete hands
the number straight back, and why every gallery URL has to carry `?v=<mtime>`
to stop a browser serving the old file under the new one's name. **The app**
names the things it makes itself - an upload, a sticker, a joined film - with a
timestamp and six random hex digits, for no better reason than that a random
tail cannot collide with ComfyUI's counting.

A parent can now say what a name looks like, one pattern per kind of thing, on
the parent page. The pattern is a template of plain characters and tokens:

    image_{n:05}_        the default, and exactly what ComfyUI writes today
    {date}-{who}-{n}     2026-09-16-ada-7
    {kind}_{idea}_{n}    image_a-fox-on-a-bicycle_12

`{n}` is the piece that makes a name unique, and it is **ours, not ComfyUI's**:
one counter per bucket below, kept in `state.db`, that only ever goes up. A
number it has handed out is never handed out again, whatever is deleted - which
is the one thing ComfyUI's directory scan cannot promise.

**`filename_prefix` in the graphs is left alone.** Those files are untouched
API exports and the convention in this repo is to keep them that way; the
rename happens here instead, the moment the file lands (`jobs._run`, per landed
file, and the four functions in `gallery.py` that name their own output).

Nothing already on disk is ever renamed. A pattern applies to what is made
after it is set - an id in this app *is* a filename, so renaming their gallery
would break every sidecar, poster, thumbnail and open browser tab at once, for
no gain they would notice.
"""

import logging
import os
import re
import time
import unicodedata
import uuid

log = logging.getLogger("makery.naming")


class NamingError(ValueError):
    """A pattern a parent typed that we will not name a file with. The message
    is the sentence shown on the parent page, so it is written for them."""


# The eight buckets a parent sets a pattern for. One per row on the card, in
# the order the card draws them.
KIND_IDS = ("picture", "video", "song", "comic", "film", "photo", "sticker",
            "other")

LABELS = {
    "picture": "Pictures",
    "video": "Videos",
    "song": "Songs",
    "comic": "Comics",
    "film": "Films",
    "photo": "Photos and drawings",
    "sticker": "Stickers",
    "other": "Everything else",
}

WHAT = {
    "picture": "from words, changed, made huge, or grabbed out of a video",
    "video": "from words or a picture, made smooth, slowed down, given a sound or their voice",
    "song": "made in the Music tab",
    "comic": "the finished sheet, and each of its panels",
    "film": "several clips joined into one",
    "photo": "taken on the iPad, drawn on the drawing pad, or made into a card",
    "sticker": "cut out of a picture, and the moving ones",
    "other": "anything a later version of this makes that is not in the list above",
}

# Which bucket each kind of item falls in. The keys are exactly the `kind`
# written into the sidecar (`jobs._item_kind`, and the literals the gallery's
# own savers pass), so there is one spelling of a kind in this app and not two.
BUCKET = {
    "image": "picture", "edit": "picture", "outpaint": "picture",
    "inpaint": "picture", "restyle": "picture", "huge": "picture",
    "frame": "picture",
    "t2v": "video", "i2v": "video", "flf": "video",
    "smooth": "video", "slowmo": "video", "voice": "video", "sound": "video",
    # All three share one template row. A parent who names their songs
    # "{date} {time} {idea}" means their sounds, and a Rules tab with a
    # separate row for tunes and another for hums is three controls where
    # the answer is always the same.
    "music": "song", "jingle": "song", "ambience": "song",
    "comic": "comic", "panel": "comic",
    "movie": "film", "storyfilm": "film",
    "upload": "photo",
    "sticker": "sticker", "loop": "sticker",
}

# What `{kind}` becomes. The kind itself, except where ComfyUI's own
# `filename_prefix` says something else and today's names would otherwise
# change: an outpaint is written as `outside`, an inpaint as `fixed` and a
# restyle as `style`, because that is what the graphs put in front of the
# number. Anything not in here is its own name.
WORD = {"outpaint": "outside", "inpaint": "fixed", "restyle": "style"}

# One pattern, and it reproduces what ComfyUI writes today: `image_00043_.png`,
# `t2v_00028_.mp4`. `{kind}` rather than a literal word, because a bucket holds
# several kinds and an edit called `image_...` would lose which is which.
DEFAULT_PATTERN = "{kind}_{n:05}_"

DEFAULTS = {b: DEFAULT_PATTERN for b in KIND_IDS}

# Every token, with the sentence the parent page prints beside it. The page
# draws its own list from this, so there is one copy of it.
TOKENS = (
    ("{date}", "the day it was made - 2026-09-16"),
    ("{time}", "the time - 1432"),
    ("{kind}", "what it is - image, t2v, sticker"),
    ("{who}", "whose it is, from the name on their profile"),
    ("{n}", "counts up and never repeats a number. {n:05} pads it to 00007"),
    ("{idea}", "the first few words they asked for"),
    ("{seed}", "the number that drew it, where there is one"),
)
TOKEN_NAMES = tuple(t[0][1:-1] for t in TOKENS)

# A pattern is a template, not a path. These are the two caps: how much a
# parent may type, and how long a name we will actually write.
MAX_PATTERN = 80
MAX_NAME = 100

# How much of their idea goes in, when `{idea}` is asked for.
IDEA_WORDS = 5
IDEA_CHARS = 40

# {token} or {token:05}. The format spec is digits only and means "pad to this
# width" - there is no room here for anything cleverer, and `{n:%s}` should not
# be a way to get a slash into a filename.
_TOKEN = re.compile(r"\{([a-z]+)(?::(\d{1,2}))?\}")
# What a parent may type *between* the tokens. No separators, no spaces, and
# nothing that means something to a shell or to a URL.
_LITERAL = re.compile(r"^[A-Za-z0-9._-]*$")
# The same set, for scrubbing a rendered name - their idea and a profile name are
# already slugged down to it, but a belt is cheap here.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def bucket_of(kind: str) -> str:
    return BUCKET.get(kind or "", "other")


def word_for(kind: str) -> str:
    return WORD.get(kind or "", kind or "thing")


def setting_key(bucket: str) -> str:
    return "filename_" + bucket


def env_key(bucket: str) -> str:
    return "FILENAME_" + bucket.upper()


def seed_default(bucket: str) -> str:
    """The row this bucket is seeded with on a first start.

    Its own reader rather than `gallery._env_text`, because gallery imports
    this module and not the other way round. A pattern in the environment that
    the parent page would refuse is ignored with a warning - an unusable name
    is worse than the default one.
    """
    raw = (os.getenv(env_key(bucket)) or "").strip()
    if not raw:
        return DEFAULT_PATTERN
    try:
        return check(raw)
    except NamingError as exc:
        log.warning("%s is not a name pattern (%s); using %s",
                    env_key(bucket), exc, DEFAULT_PATTERN)
        return DEFAULT_PATTERN


def check(pattern: str) -> str:
    """A pattern as typed, cleaned - or `NamingError` with a sentence to show.

    Every rule here exists so that `gallery._safe_path` accepts every name this
    can produce: no separator, no leading dot, a direct child of the gallery
    directory, and a known media suffix - which is always the file's own and
    never the pattern's.
    """
    pattern = (pattern or "").strip()
    if not pattern:
        raise NamingError("Give it a pattern, or put the default back.")
    if len(pattern) > MAX_PATTERN:
        raise NamingError(f"That is longer than {MAX_PATTERN} characters.")

    for name, width in _TOKEN.findall(pattern):
        if name not in TOKEN_NAMES:
            raise NamingError(
                "There is no {%s}. The ones there are: %s."
                % (name, ", ".join(t[0] for t in TOKENS)))
        if width and name != "n":
            raise NamingError(
                "Only {n} can be padded with a number, not {%s}." % name)

    rest = _TOKEN.sub("", pattern)
    if "/" in rest or "\\" in rest:
        raise NamingError("A name cannot have a / or a \\ in it - everything "
                          "lands in one folder.")
    if not _LITERAL.match(rest):
        bad = sorted({c for c in rest if not _LITERAL.match(c)})
        raise NamingError("Letters, numbers, dots, dashes and underscores only "
                          "- not " + " ".join("'%s'" % c for c in bad) + ".")
    if pattern.startswith("."):
        raise NamingError("A name cannot start with a dot - that hides the file.")

    asked = {m.group(1) for m in _TOKEN.finditer(pattern)}
    if "n" not in asked and "time" not in asked:
        raise NamingError("Put {n} or {time} in it, or every file would want "
                          "the same name.")
    return pattern


def pattern_for(bucket: str) -> str:
    """What a parent has chosen for one bucket, or the default.

    `gallery` is imported here rather than at the top: it imports this module
    for the defaults it seeds its settings table with, so the arrow only points
    one way at import time.
    """
    from . import gallery

    try:
        return check(gallery.text(setting_key(bucket)))
    except NamingError as exc:
        log.warning("the %s name pattern is unusable (%s); using %s",
                    bucket, exc, DEFAULT_PATTERN)
        return DEFAULT_PATTERN


def slug(words: str, limit_words: int = IDEA_WORDS, limit: int = IDEA_CHARS) -> str:
    """Their words, safe to put in a filename.

    ASCII and short. `safety.check_prompt` has already passed whatever comes in
    here, so this is not the filter - it is the same scrub a profile name gets,
    so that "Le renard d'Amelie" is `le-renard-d-amelie` and not a byte that a
    filesystem, a zip or a URL will argue about.
    """
    flat = unicodedata.normalize("NFKD", words or "")
    flat = flat.encode("ascii", "ignore").decode("ascii").lower()
    parts = [p for p in re.split(r"[^a-z0-9]+", flat) if p]
    return "-".join(parts[:max(1, limit_words)])[:limit].strip("-")


def next_number(bucket: str) -> int:
    """The next number for one bucket, from the database.

    One row per bucket, incremented under the store's write lock, so four
    pictures at once get four numbers and two processes sharing the state
    volume cannot both be handed the same one. It only ever goes up: that is
    the whole difference from ComfyUI's directory scan, which hands a number
    back the moment the file that had it is deleted.
    """
    from . import store

    try:
        return store.bump("filename_" + bucket)
    except OSError as exc:
        # A counter we cannot read is not a reason to lose a render. The clock
        # is unique enough to get this one file onto the disk.
        log.warning("could not take the next %s number (%s)", bucket, exc)
        return int(time.time()) % 100000


def render(kind: str, suffix: str, *, idea: str = "", who: str = "",
           seed=None, when: float | None = None, taken=None) -> str:
    """The name one new file should have, collisions already settled.

    `taken(name)` says whether something of that name is there already; the
    gallery passes one that looks for the media file *and* its sidecar. A
    pattern with `{n}` in it simply takes the next number until it finds a free
    name, which is also what carries an upgrade over the top of a directory
    that already holds forty `image_000NN_` files.
    """
    bucket = bucket_of(kind)
    pattern = pattern_for(bucket)
    counted = "{n" in pattern
    stamp = time.localtime(when if when is not None else time.time())
    fixed = {
        "date": time.strftime("%Y-%m-%d", stamp),
        "time": time.strftime("%H%M", stamp),
        "kind": slug(word_for(kind), 4, 24) or "thing",
        "who": _who_slug(who),
        "idea": slug(idea),
        "seed": "" if seed in (None, "") else re.sub(r"\D", "", str(seed))[:20],
    }

    for attempt in range(200):
        stem = _fill(pattern, fixed, next_number(bucket) if counted else 0)
        name = stem + suffix if counted or not attempt else f"{stem}-{attempt + 1}{suffix}"
        if taken is None or not taken(name):
            return name
    # Two hundred taken names in a row means the pattern is not doing its job.
    # The file still has to land somewhere, so it lands under something
    # unmistakable rather than not at all.
    return _fill(pattern, fixed, 0) + "-" + uuid.uuid4().hex[:6] + suffix


def _fill(pattern: str, fixed: dict, number: int) -> str:
    def one(match: re.Match) -> str:
        name, width = match.group(1), match.group(2)
        if name == "n":
            return f"{number:0{int(width)}d}" if width else str(number)
        return fixed.get(name, "")

    out = _UNSAFE.sub("", _TOKEN.sub(one, pattern)).lstrip(".")
    # `{who}_{idea}_{n}` with no profile and no words would be `__7`. A run of
    # separators is always a token that came back empty, so it collapses to the
    # first of them, and a name never begins with one. A *trailing* one is left
    # alone on purpose: the default is `{kind}_{n:05}_`, and ComfyUI's own
    # `image_00043_.png` ends in exactly that underscore.
    out = re.sub(r"([-_])[-_]+", r"\1", out).lstrip("-_")
    return (out or "file")[:MAX_NAME]


def _who_slug(who: str) -> str:
    """A profile id into the name on it. Falls back to the id, which is at
    least stable, and to nothing at all when there is no profile to ask."""
    if not who:
        return ""
    try:
        from . import profiles

        return slug(profiles.name_of(who), 3, 24) or slug(who, 1, 24)
    except Exception:
        return slug(who, 1, 24)


# What one row of the card previews itself with: the kind that bucket mostly
# holds, and the suffix that kind's files carry.
SAMPLE_KIND = {
    "picture": "image", "video": "t2v", "song": "music", "comic": "panel",
    "film": "movie", "photo": "upload", "sticker": "sticker", "other": "thing",
}
SAMPLE_SUFFIX = {
    "picture": ".png", "video": ".mp4", "song": ".mp3", "comic": ".png",
    "film": ".mp4", "photo": ".png", "sticker": ".png", "other": ".png",
}


def sample(bucket: str) -> dict:
    """The values the parent page substitutes for its live preview.

    The page does the substituting rather than asking the server on every
    keystroke, but it does not work out what any token *means* - that is here,
    once.
    """
    stamp = time.localtime()
    return {
        "date": time.strftime("%Y-%m-%d", stamp),
        "time": time.strftime("%H%M", stamp),
        "kind": word_for(SAMPLE_KIND[bucket]),
        "who": _sample_who(),
        "n": 7,
        "idea": "a-fox-on-a-bicycle",
        "seed": "884213",
        "suffix": SAMPLE_SUFFIX[bucket],
    }


def _sample_who() -> str:
    try:
        from . import profiles

        return slug(profiles.default().get("name") or "", 3, 24) or "kid"
    except Exception:
        return "kid"


def public() -> dict:
    """Everything the parent page needs to draw the card: the eight rows with
    what is set on each, the token list, and the pieces the live preview
    substitutes."""
    return {
        "kinds": [{
            "id": bucket,
            "label": LABELS[bucket],
            "what": WHAT[bucket],
            "pattern": pattern_for(bucket),
            "default": DEFAULT_PATTERN,
            "sample": sample(bucket),
        } for bucket in KIND_IDS],
        "tokens": [{"token": token, "what": what} for token, what in TOKENS],
        "max": MAX_PATTERN,
    }
