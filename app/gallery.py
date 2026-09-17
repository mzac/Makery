"""Everything they have made, read straight off ComfyUI's output directory.

ComfyUI already writes everything this app produces into one directory (its
output dir plus a `makery/` prefix). Bind-mounting that same directory
here as `GALLERY_DIR` turns it into a gallery without copying anything or
keeping a second source of truth.

Prompts are kept in a sidecar JSON per media file rather than one index: there
is nothing to rewrite when a file is added, nothing to corrupt when two writes
race, and deleting a picture is just deleting its two files. A media file with
no sidecar still lists - it simply has no prompt to show, which is what happens
to anything generated before this existed, or straight from ComfyUI.

The container runs with gid 987 (`comfyui`), and the directory is group-writable
with setgid, so deleting works. See the ComfyUI file ownership section of the
top-level CLAUDE.md before changing any of that.
"""

import contextvars
import json
import logging
import os
import shutil
import time
from pathlib import Path

from . import audit, i18n, naming, store

log = logging.getLogger("makery.gallery")

GALLERY_DIR = Path(os.getenv("GALLERY_DIR", "/gallery"))

# Everything the app decides rather than makes: the settings, the prompt
# overrides, the chat transcript, their characters, the timings, their banner.
#
# It used to live in GALLERY_DIR, which is ComfyUI's own output directory -
# shared, wiped by whoever tidies up, and documented in the stack's notes as
# something to `rm -rf` when the disk fills. Losing their characters and every
# parent-page setting to a disk cleanup is not a risk worth carrying.
#
# STATE_DIR splits it out. Left unset it *is* GALLERY_DIR, so an install that
# predates this keeps working with nothing to do; set it and whatever is in the
# old place is moved across once, at startup.
STATE_DIR = Path(os.getenv("STATE_DIR", "") or GALLERY_DIR)

# The settings live in a SQLite file in there - see app/store.py for why, and
# for what migrated out of the JSON files. Told rather than worked out again,
# so the rule above is the only copy of it.
store.use(STATE_DIR)

MEDIA_SUFFIXES = {
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".webp": ("image", "image/webp"),
    ".mp4": ("video", "video/mp4"),
    ".webm": ("video", "video/webm"),
    ".mkv": ("video", "video/x-matroska"),
    # Songs. ACE-Step saves mp3; the others are here so a re-exported workflow
    # with a different SaveAudio format does not produce files the gallery
    # cannot see.
    ".mp3": ("audio", "audio/mpeg"),
    ".flac": ("audio", "audio/flac"),
    ".wav": ("audio", "audio/wav"),
    ".opus": ("audio", "audio/ogg"),
    ".m4a": ("audio", "audio/mp4"),
}

SIDECAR_SUFFIX = ".makery.json"

# What the suffix was before the project was renamed to Makery. Every item made
# before that has its prompt, its seed, its star, its tags and whose it is in a
# file ending in this - so it is still read, and still moved and deleted along
# with its media file. It is never written: `_write_sidecar` puts the notes
# under the new name and drops the old file, so anything that gets starred,
# tagged, renamed, trashed or restored converges on its own and there is only
# ever one sidecar per item. A mass rewrite at startup was the alternative and
# is a worse trade - it would touch every file in a gallery that can hold
# thousands, most of them owned by ComfyUI's user at 644, for no gain over
# reading the old name where it still sits.
LEGACY_SIDECAR_SUFFIX = ".easy-iv-gen.json"

# The ResolutionSelector aspect strings, back to the names used here. Kept
# local rather than imported from workflows to avoid a circular import.
_ORIENTATION_BY_ASPECT = {
    "16:9 (Widescreen)": "landscape",
    "3:4 (Portrait Standard)": "portrait",
    "1:1 (Square)": "square",
}

# Poster frames for videos, kept in a hidden subdirectory so they never show up
# in the listing themselves. A tile showing a real still is what lets the
# gallery use plain <img> for videos: iOS limits how many <video> elements can
# decode at once (around sixteen), and past that the tiles simply go blank.
POSTER_DIR_NAME = ".posters"
POSTER_WIDTH = 640

# Small cover-cropped tiles for the parent page, cached beside the posters.
# Serving the full PNG to a grid of thumbnails is 3MB a tile for nothing.
THUMB_DIR_NAME = ".thumbs"
THUMB_SIZE = (400, 300)

# Deleting moves things here instead of unlinking them. A four-second armed
# button is a fine guard against a slip of the thumb, but not against changing
# their mind an hour later; the janitor empties anything older than the number of
# days on the parent page (`trash_days`).
TRASH_DIR_NAME = ".trash"

# Things they have chosen for themselves - the banner across the top of their page.
# Beside the media rather than in static/, because static/ is inside the image
# and would be thrown away by every rebuild; this directory is the bind mount
# that already survives one.
CUSTOM_DIR_NAME = ".custom"
BANNER_NAME = "banner.png"
# The slot it is drawn into. Cover-cropped to exactly this, so a tall picture
# becomes a strip rather than a squashed picture.
BANNER_SIZE = (1536, 384)

# Uploads the screen said no to, kept small so a parent can judge the call.
REFUSED_DIR_NAME = ".refused"

# The settings used to be this file, with `.settings-<id>.json` laid over it
# per child. They are rows in `state.db` now - see app/store.py, and
# `migrate_settings()` below, which is the only thing that still reads these
# names. The files are renamed to `.migrated` once they have been imported.
SETTINGS_FILE = ".settings.json"

# Whose page this is, for the length of one request. Set once by the ASGI
# middleware in main.py from the profile cookie, and read by everything that
# has to know - the settings, the listing, the day's counts - so that per-child
# rules did not mean threading an argument through sixty call sites.
#
# `None` means the household: no profile in play. That is what the janitor, the
# nightly email and the Telegram bot see, and it is the right answer for all
# three - they are about the whole family.
#
# The value is a plain dict rather than a profile, so this module never has to
# import profiles.py, which imports this one.
#   {"id": "ada-3f2a", "adopts": True, "shared": False}
WHO = contextvars.ContextVar("who", default=None)


def _who() -> dict | None:
    return WHO.get()


def _who_id() -> str:
    current = WHO.get()
    return (current or {}).get("id") or ""


def settings_file(who: str = "") -> str:
    """What one scope's settings used to be called on disk. Only the migration
    and the profile cleanup still say these names."""
    return f".settings-{who}.json" if who else SETTINGS_FILE


def write_json(path: Path, data) -> None:
    """Save one of the small JSON state files without ever showing half of it.

    `write_text` truncates before it writes, so a reader landing in that gap
    sees an empty file - and every reader of these files treats an unparseable
    one as "there is nothing here". That is a cast list, a set of overrides or
    a profile list erased by a restart landing at the wrong millisecond. The
    temporary file is written whole and `os.replace`d into position, which is
    atomic: a reader sees the old file or the new one.

    The temporary name is a fresh one every time, because a single fixed one is
    worse than none: two threads saving at once would write into the same file
    over each other, and then each rename it into place - one save landing
    twice and the other not at all, or a file half from each.
    """
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{os.urandom(4).hex()}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=1))
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def owned(meta: dict) -> dict:
    """Stamp a *new* item with whoever is making it.

    Only ever called where something is created. Updating an existing sidecar
    deliberately does not go through this: a parent trashing one child's
    picture while their browser is signed in as another would otherwise hand
    the file to the wrong one.
    """
    if not meta.get("who"):
        meta["who"] = _who_id()
    return meta


def belongs_to_me(item_id: str, trashed: bool = False) -> bool:
    """Whether the signed-in child may change this item.

    A curtain rather than a lock, and worth being straight about which: a
    sibling cannot find another child's work in any listing and cannot star,
    rename, trash or build on it. A direct media URL is not blocked, because
    the parent page shows those pictures in plain <img> tags that cannot carry
    a PIN. For siblings on a home network that is the right weight.
    """
    if _who() is None or shared_now():
        return True
    try:
        path = (_trash_dir() / Path(item_id).name) if trashed else _safe_path(item_id)
    except (GalleryError, ValueError):
        return True     # not a real id; the route's own error is the better one
    return mine(_read_sidecar(path).get("who") or "")


def shared_now() -> bool:
    return bool((_who() or {}).get("shared"))


# "No `who` was given", which is emphatically not the same value as `None`.
# `None` is the household - nobody signed in, everything is theirs - and it is
# what `listing(everyone=True)` passes down. The two used to share `None`, so
# every household-wide call made from a page that *did* have a profile cookie
# quietly answered with one child's things: the parent dashboard, the nightly
# clean-up and emptying the trash all said "everyone" and did one.
ASK = object()


def mine(meta_who: str, who=ASK) -> bool:
    """Whether a file belongs to whoever is looking.

    Three answers, not two. `who` left out asks the request context. `who=None`
    is the household and owns everything - the janitor, the nightly email and
    the parent page's household-wide listings mean exactly that. A dict is one
    child.

    An empty owner is a file made before profiles existed, and belongs to
    whichever profile carries `adopts` - which on every single-child
    installation is the only one there is.
    """
    if who is ASK:
        who = _who()
    if who is None or who.get("shared"):
        return True
    return meta_who == who["id"] if meta_who else bool(who.get("adopts"))
# --- what the environment is still for --------------------------------------
#
# Every setting below is a real row in the database with a control on the
# parent page. The variable in `.env` beside its name is read **once** - on the
# first start, to fill that row in - and never consulted again. That is the
# whole of the rule: `.env` seeds, the parent page owns.
#
# It replaces a tri-state that ran through the whole file, where -1 (or "-",
# or "") in a setting meant "whatever the environment says". It was one value
# in two places with a third value to say which of them counted, and the honest
# answer to "is the nightly email on?" was "open the compose file and see". The
# sentinels are gone; `_LEGACY_UNSET` below is only there to read the old files
# on the way in.

def _env_flag(name: str, default: bool) -> int:
    """0 or 1 - stored as an int because that is what the tri-state stored and
    every route, page and reader of it already speaks that."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return int(default)
    return int(raw.strip().lower() not in ("0", "false", "no", "off"))


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(float(os.getenv(name, "").strip() or default))))
    except (TypeError, ValueError):
        return default


def _env_num(name: str, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(os.getenv(name, "").strip() or default)))
    except (TypeError, ValueError):
        return default


def _env_text(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    return default if raw is None else raw.strip()


def _env_one_of(name: str, choices, default: str) -> str:
    chosen = _env_text(name, default).lower()
    return chosen if chosen in choices else default


def _env_list(name: str, choices, default: str) -> str:
    """A comma-separated subset, in the order `choices` gives, unknowns
    dropped, falling back to the default if nothing usable is left. Its own
    rather than quiz.clean_ops: that module imports this one."""
    asked = {bit.strip().lower()
             for bit in _env_text(name, default).replace(" ", ",").split(",")}
    return ",".join(c for c in choices if c in asked) or default


DEFAULT_SETTINGS = {
    "paused": False,
    "daily_video_limit": 0,
    "daily_image_limit": 0,
    "daily_music_limit": 0,
    # A top-up for today only. Editing the limit itself to let them have one
    # more means remembering to edit it back tomorrow; this expires on its own
    # at midnight because it carries the day it was granted.
    "bonus_video": 0,
    "bonus_image": 0,
    "bonus_music": 0,
    "bonus_day": "",
    # One email the first time they run out of each kind on a given day; the
    # date is what stops a second one when they tap again.
    "limit_mail_image": "",
    "limit_mail_video": "",
    "limit_mail_music": "",
    "limit_mail_enabled": _env_flag("DIGEST_LIMIT_NOTICE", True),
    # Three sums before the factory opens, once a calendar day.
    # Off unless a parent asks for it. Sums in front of the thing a child
    # sat down to do are a house rule, not a safety one, and a tool that
    # imposes one out of the box is picking a fight on the first evening.
    "quiz_enabled": _env_flag("DAILY_QUIZ", False),
    "quiz_questions": _env_int("QUIZ_QUESTIONS", 3, 1, 10),
    # How long "I'm a grown-up" on the sums overlay lasts.
    "quiz_bypass_minutes": _env_int("QUIZ_BYPASS_MINUTES", 60, 1, 1440),
    # How hard, and which kinds: easy/medium/hard, and a list like
    # "add,sub,mul,div". See app/quiz.py for what each level draws.
    "quiz_level": _env_one_of("QUIZ_LEVEL", ("easy", "medium", "hard"), "medium"),
    "quiz_ops": _env_list("QUIZ_OPS", ("add", "sub", "mul", "div"),
                          "add,sub,mul,div"),
    "quiz_passed_day": "",
    "quiz_passed_at": "",
    "quiz_bypassed_day": "",
    "quiz_secret": "",
    # Which "you have made 50 pictures!" notes have already been shown. Stored
    # so a milestone is a moment, not a message that repeats every reload.
    "milestones_seen": [],
    # When the trash was last emptied and by what. An empty trash is otherwise
    # indistinguishable from "nothing was ever deleted", which is exactly the
    # question a parent asks when they know something was.
    "trash_emptied_at": 0,
    "trash_emptied_count": 0,
    "trash_emptied_by": "",
    # The nightly email: whether it goes, when, and how much of the day it
    # carries.
    "digest_enabled": _env_flag("DIGEST_ENABLED", False),
    "digest_at": _env_text("DIGEST_AT", "19:30"),
    "digest_max_items": _env_int("DIGEST_MAX_ITEMS", 24, 1, 200),
    "digest_last_sent": "",
    # And where it goes, which is here too now. An address and a relay are
    # things a parent changes - they move house, they switch provider - and
    # asking them to edit a file and rebuild a container for that was the
    # same mistake as the daily limit. **The two credentials are the
    # exception** and are not rows at all: a secret written into one is a
    # secret in every backup file, and the backup is the thing a parent emails
    # to themselves. They are boxes on the same card, kept in app/config.py's
    # own store, which the backup skips.
    "digest_to": _env_text("DIGEST_TO", ""),
    # `digest_url` - one Apprise URL used as it is, for a relay this shape
    # cannot express - was a row here until it was noticed that the example
    # everything documents it with is `mailtos://user:apppassword@gmail.com`.
    # It is a credential like the relay password, so it went the same way: a
    # box on the same card, kept in app/config.py's own scope.
    "digest_smtp_host": _env_text("DIGEST_SMTP_HOST", ""),
    "digest_smtp_port": _env_int("DIGEST_SMTP_PORT", 25, 1, 65535),
    "digest_smtp_starttls": _env_flag("DIGEST_SMTP_STARTTLS", False),
    "digest_smtp_user": _env_text("DIGEST_SMTP_USER", ""),
    "digest_from": _env_text("DIGEST_FROM", ""),
    # Empty on either of these means "work one out" - see app/digest.py, which
    # builds them from the app's title and the child's name.
    "digest_from_name": _env_text("DIGEST_FROM_NAME", ""),
    "digest_subject": _env_text("DIGEST_SUBJECT", ""),
    "digest_limit_subject": _env_text("DIGEST_LIMIT_SUBJECT", ""),
    # Messages to a parent's phone (Telegram, WhatsApp, ntfy, ...). Where they
    # go is a box on the same card and *not* a row here, because those URLs
    # carry tokens - app/config.py, again. Which of them are worth sending, and
    # how big a file may be attached, are rows and are here.
    "notify_made": _env_flag("NOTIFY_ON_MADE", False),
    "notify_attach": _env_flag("NOTIFY_ATTACH", False),
    "notify_limit": _env_flag("NOTIFY_ON_LIMIT", True),
    "notify_digest": _env_flag("NOTIFY_ON_DIGEST", False),
    "notify_flagged": _env_flag("NOTIFY_ON_FLAGGED", True),
    # Somebody getting the parent PIN wrong. Governs the email and the phone
    # message together: wanting to be told is one want, not two.
    "notify_pin": _env_flag("NOTIFY_ON_PIN", True),
    # The biggest file worth attaching. A property of the service at the other
    # end - Telegram takes 50MB, most others less - but it is still the person
    # holding the phone who knows which service that is.
    "notify_max_mb": _env_num("NOTIFY_MAX_MB", 20.0, 0.0, 2000.0),
    # Whether a refusal closes the factory as well as reporting it, and why it
    # was closed if something did. "" is "just tell me" - see app/lockdown.py
    # for why that is the default.
    "close_on": _env_one_of("CLOSE_ON_REFUSAL", ("", "photo", "words"), ""),
    # Whether an uploaded photo is shown to the vision model first. Fails open
    # if Ollama is unreachable either way.
    "screen_uploads": _env_flag("SCREEN_UPLOADS", True),
    "closed_reason": "",
    "closed_at": 0,
    # The parent page bolted shut, on top of the PIN. Set from Telegram and
    # only unset from there - the page that would carry the switch is the page
    # it locks.
    "parent_locked": False,
    # Answering a parent's questions on Telegram. Off by default, because it
    # is a way *in* rather than a way out.
    "telegram_ask": _env_flag("TELEGRAM_ASK", False),
    # Who may talk to it: chat ids or @names, comma- or space-separated.
    # Empty falls back to the ids inside the `tgram://` URL in NOTIFY_URLS,
    # which is how this has always been derived - the field on the parent page
    # shows those as its placeholder. The bot *token* is a box on the same
    # card and not a row, for the reason above; a chat id is not a secret and
    # is exactly the thing that changes when somebody new should be allowed
    # to ask, which is why this one is.
    "telegram_chat_ids": _env_text("TELEGRAM_CHAT_IDS", ""),
    # How long to wait for the model answering a question on the phone.
    "telegram_timeout": _env_num("TELEGRAM_TIMEOUT", 120.0, 5.0, 900.0),
    # Which makers exist at all. See app/modules.py.
    "module_picture": _env_flag("ENABLE_PICTURE", True),
    "module_video": _env_flag("ENABLE_VIDEO", True),
    "module_comic": _env_flag("ENABLE_COMIC", True),
    "module_music": _env_flag("ENABLE_MUSIC", True),
    "module_chat": _env_flag("ENABLE_CHAT", True),
    "module_story": _env_flag("ENABLE_STORY", True),
    # When it is open by the clock, rather than by the switch above. See
    # app/schedule.py for the format. -1 on schedule_on means "on if there is a
    # timetable at all", since setting times and then having to tick a box to
    # make them apply is a trap - that one is *not* an environment indirection
    # and is the only tri-state left in this table. schedule_override is the
    # epoch second that "open it anyway" runs out, always the end of the day it
    # was granted.
    "schedule": _env_text("OPEN_HOURS", ""),
    "schedule_on": -1,
    "schedule_override": 0,
    # Theirs: the colour scheme, chosen in the Settings tab. Kept here rather
    # than in the browser so their page looks the same on the iPad and on the
    # laptop. Empty means whichever one style.css leads with.
    "theme": "",

    # --- the rest of what used to be .env only ------------------------------
    # How long the trash keeps something, and how long a frame left in
    # ComfyUI's input directory survives. Both are the janitor's.
    "trash_days": _env_num("TRASH_DAYS", 7.0, 0.0, 3650.0),
    "input_sweep_hours": _env_num("INPUT_SWEEP_HOURS", 24.0, 0.0, 8760.0),
    # How many of each kind of backup file to keep. Seven is a week, which is
    # the span in which somebody notices "the parent page has gone funny", and
    # they are a few hundred kilobytes each. See app/backup.py.
    "backup_keep": _env_int("BACKUP_KEEP", 7, 1, 365),
    # How long a video and a song may be. **Raising the video ceiling is the
    # one control here that can make a render fail rather than merely look
    # different**: VRAM goes with pixels times frames, and 15s at 0.9MP peaks
    # near 15.5GB of a 16.3GB card. The page takes its slider bounds from
    # these, so a change reaches them without a rebuild.
    "video_min_seconds": _env_int("VIDEO_MIN_SECONDS", 5, 1, 600),
    "video_max_seconds": _env_int("VIDEO_MAX_SECONDS", 15, 1, 600),
    "video_default_seconds": _env_int("VIDEO_DEFAULT_SECONDS", 5, 1, 600),
    # Sharper is more pixels per frame, so it runs out of card sooner. Its own
    # number rather than a fraction of the above: what fits is a measurement.
    "video_max_seconds_sharp": _env_int("VIDEO_MAX_SECONDS_SHARP", 10, 1, 600),
    "music_min_seconds": _env_int("MUSIC_MIN_SECONDS", 10, 1, 600),
    "music_max_seconds": _env_int("MUSIC_MAX_SECONDS", 120, 1, 600),
    "music_default_seconds": _env_int("MUSIC_DEFAULT_SECONDS", 30, 1, 600),
    # Whether the whole picture blocklist is applied to the chat and to song
    # lyrics as well. Off by default: that list stops words a picture model
    # cares about and a conversation does not - "blood", "gun", "beer".
    "chat_strict": _env_flag("CHAT_STRICT", False),
    "music_strict": _env_flag("MUSIC_STRICT", False),
    # Whether the parent page may edit the model instructions, not just read
    # them. Off by default: they are the only thing between a child and
    # whatever the model feels like saying.
    "prompt_editing": _env_flag("PROMPT_EDITING", False),
    # How many characters they may keep.
    "max_characters": _env_int("MAX_CHARACTERS", 12, 1, 100),
    # Which language their page opens in on a browser that has never chosen.
    # Their own chip in Settings still wins, and that is a cookie - see i18n.py.
    "ui_lang": _env_one_of("UI_LANG", i18n.LANGS, "en"),
    # she | he | they, for the parent-facing sentences only. A profile owns the
    # name and the age; this is wording about them and stays the household's.
    "kid_pronoun": _env_one_of("KID_PRONOUN", ("she", "he", "they"), "they"),
    # What the whole thing is called. Empty builds it from whose page it is -
    # "Ada's AI Factory", and the six other languages have their own shapes for
    # that - so a household that has not named it still gets a sentence rather
    # than a product name. See app/branding.py.
    "app_title": _env_text("APP_TITLE", ""),

    # --- the activity log (app/audit.py) ------------------------------------
    # How long it is kept. **0, the default, is for ever**: a log that quietly
    # throws the oldest week away is not the thing that was asked for, so
    # forgetting has to be something a parent chooses.
    "audit_keep_days": _env_num("AUDIT_KEEP_DAYS", 0.0, 0.0, 3650.0),
    # Whether a refusal records the words that were refused, or only which
    # category stopped them. Off: the category answers "is the filter working"
    # and the words are theirs.
    "audit_words": _env_flag("AUDIT_WORDS", False),

    # Which model in Ollama does which job. The app never downloads one: these
    # are names of models somebody has already pulled, and the parent page only
    # offers what `/api/tags` reports. The idea helper's **must be a vision
    # model** - the picture-aware "help me write it", saving a character and
    # the upload screen all hand it a picture. An empty telegram_model follows
    # the idea helper, which is what an empty TELEGRAM_MODEL always meant.
    "script_model": _env_text("SCRIPT_MODEL", "qwen3-vl:4b-instruct"),
    "chat_model": _env_text("CHAT_MODEL", "gemma4:12b"),
    "telegram_model": _env_text("TELEGRAM_MODEL", ""),
    # And how they are *held*, which is the other half of the same decision.
    # Ollama's keep_alive: "0" drops the model the moment it has answered,
    # "60s" or "5m" keeps it resident and pays the load time once. ComfyUI
    # shares this card and a video render peaks near 15.5GB of 16.3, so
    # nothing else may be holding VRAM when they tap Go - which is what
    # comfy_free_after_job is for as well.
    "script_keep_alive": _env_text("SCRIPT_KEEP_ALIVE", "0"),
    "chat_keep_alive": _env_text("CHAT_KEEP_ALIVE", "5m"),
    "comfy_free_after_job": _env_flag("COMFY_FREE_AFTER_JOB", True),
    # The chat helper's own name. It is a proper noun: it goes into the
    # instruction the model is given, into the line it opens with in all seven
    # languages, and onto the tab.
    "chat_name": _env_text("CHAT_NAME", "Sparky"),
    # How much of the conversation is kept on disk for a parent to read.
    "chat_keep_messages": _env_int("CHAT_KEEP_MESSAGES", 400, 20, 20000),
    # What a finished file is called, one template per kind of thing. See
    # app/naming.py for the tokens and for why the rename happens after the
    # file lands rather than in the graph's own `filename_prefix`.
    **{naming.setting_key(b): naming.seed_default(b) for b in naming.KIND_IDS},
}


# What each behavioural setting is seeded from, for the docs and for the
# "nobody has ever set this" pass at startup.
#
# What is *not* in here is what `.env` still answers, and it is two different
# kinds of thing now:
#
# - **Seven that only `.env` can answer**, because compose reads them to build
#   the container and there is no app yet when they are read: GALLERY_DIR,
#   STATE_VOLUME, COMFY_INPUT_DIR_HOST, RUN_AS, NETWORK_NAME, HOST_PORT,
#   CONTAINER_NAME.
# - **Nine that app/config.py owns**: COMFY_URL, OLLAMA_URL, TZ, LOG_LEVEL,
#   PARENT_PIN, DIGEST_SMTP_PASS, DIGEST_URL, NOTIFY_URLS and
#   TELEGRAM_BOT_TOKEN. Those are on the parent page too, but they are
#   deliberately **not seeded into this table**: the page overrides `.env`
#   rather than copying it, so an upgrade changes nothing, and the five that
#   are credentials stay out of the rows - because every row in this table
#   goes into the backup file.
#
# KID_NAME and KID_AGE are not here either, and are not deployment: they make
# the *first profile* and nothing else. After that a name and an age belong to
# a profile, under "Who uses it" - see app/branding.py.
SEEDED_FROM_ENV = {
    "quiz_enabled": "DAILY_QUIZ",
    "quiz_questions": "QUIZ_QUESTIONS",
    "quiz_bypass_minutes": "QUIZ_BYPASS_MINUTES",
    "quiz_level": "QUIZ_LEVEL",
    "quiz_ops": "QUIZ_OPS",
    "digest_enabled": "DIGEST_ENABLED",
    "digest_at": "DIGEST_AT",
    "digest_max_items": "DIGEST_MAX_ITEMS",
    "limit_mail_enabled": "DIGEST_LIMIT_NOTICE",
    "digest_to": "DIGEST_TO",
    "digest_smtp_host": "DIGEST_SMTP_HOST",
    "digest_smtp_port": "DIGEST_SMTP_PORT",
    "digest_smtp_starttls": "DIGEST_SMTP_STARTTLS",
    "digest_smtp_user": "DIGEST_SMTP_USER",
    "digest_from": "DIGEST_FROM",
    "digest_from_name": "DIGEST_FROM_NAME",
    "digest_subject": "DIGEST_SUBJECT",
    "digest_limit_subject": "DIGEST_LIMIT_SUBJECT",
    "notify_made": "NOTIFY_ON_MADE",
    "notify_attach": "NOTIFY_ATTACH",
    "notify_limit": "NOTIFY_ON_LIMIT",
    "notify_digest": "NOTIFY_ON_DIGEST",
    "notify_flagged": "NOTIFY_ON_FLAGGED",
    "notify_pin": "NOTIFY_ON_PIN",
    "notify_max_mb": "NOTIFY_MAX_MB",
    "telegram_ask": "TELEGRAM_ASK",
    "telegram_chat_ids": "TELEGRAM_CHAT_IDS",
    "telegram_timeout": "TELEGRAM_TIMEOUT",
    "module_picture": "ENABLE_PICTURE",
    "module_video": "ENABLE_VIDEO",
    "module_comic": "ENABLE_COMIC",
    "module_music": "ENABLE_MUSIC",
    "module_chat": "ENABLE_CHAT",
    "module_story": "ENABLE_STORY",
    "close_on": "CLOSE_ON_REFUSAL",
    "screen_uploads": "SCREEN_UPLOADS",
    "schedule": "OPEN_HOURS",
    "trash_days": "TRASH_DAYS",
    "input_sweep_hours": "INPUT_SWEEP_HOURS",
    "backup_keep": "BACKUP_KEEP",
    "video_min_seconds": "VIDEO_MIN_SECONDS",
    "video_max_seconds": "VIDEO_MAX_SECONDS",
    "video_default_seconds": "VIDEO_DEFAULT_SECONDS",
    "video_max_seconds_sharp": "VIDEO_MAX_SECONDS_SHARP",
    "music_min_seconds": "MUSIC_MIN_SECONDS",
    "music_max_seconds": "MUSIC_MAX_SECONDS",
    "music_default_seconds": "MUSIC_DEFAULT_SECONDS",
    "chat_strict": "CHAT_STRICT",
    "music_strict": "MUSIC_STRICT",
    "prompt_editing": "PROMPT_EDITING",
    "max_characters": "MAX_CHARACTERS",
    "ui_lang": "UI_LANG",
    "kid_pronoun": "KID_PRONOUN",
    "app_title": "APP_TITLE",
    "audit_keep_days": "AUDIT_KEEP_DAYS",
    "audit_words": "AUDIT_WORDS",
    "script_model": "SCRIPT_MODEL",
    "chat_model": "CHAT_MODEL",
    "telegram_model": "TELEGRAM_MODEL",
    "script_keep_alive": "SCRIPT_KEEP_ALIVE",
    "chat_keep_alive": "CHAT_KEEP_ALIVE",
    "comfy_free_after_job": "COMFY_FREE_AFTER_JOB",
    "chat_name": "CHAT_NAME",
    "chat_keep_messages": "CHAT_KEEP_MESSAGES",
    **{naming.setting_key(b): naming.env_key(b) for b in naming.KIND_IDS},
}

# What each of those held in the old JSON files when nobody had chosen and the
# environment was to be asked. Only the migration reads this: a value equal to
# the sentinel is dropped on the way in, so the seeded value applies - which is
# what the file meant. A child's file is read the same way, and dropping the
# sentinel there leaves the child falling through to the household, which is
# also what it meant.
_LEGACY_UNSET = {
    "quiz_enabled": -1,
    "quiz_questions": 0,
    "quiz_level": "-",
    "quiz_ops": "",
    "digest_enabled": -1,
    "digest_at": "",
    "limit_mail_enabled": -1,
    "notify_made": -1,
    "notify_attach": -1,
    "notify_limit": -1,
    "notify_digest": -1,
    "notify_flagged": -1,
    "notify_pin": -1,
    "telegram_ask": -1,
    "module_picture": -1,
    "module_video": -1,
    "module_comic": -1,
    "module_music": -1,
    "module_chat": -1,
    "close_on": "-",
    "schedule": "-",
}


class GalleryError(RuntimeError):
    """The gallery directory is unusable."""


# Every file that belongs to the app rather than to the media, listed here
# because the mover has to know them and the modules that own them import
# gallery rather than the other way round. Keep this in step with the FILE
# constant in each one.
STATE_FILES = (
    ".settings.json",          # this module, SETTINGS_FILE - now migrated
                               # into state.db, but still moved across so an
                               # install that predates STATE_DIR migrates once
                               # rather than losing them
    ".prompts.json",           # this module, HISTORY_FILE - what they have typed
    ".prompt-overrides.json",  # prompts.py
    ".chat.json",              # chat.py
    ".characters.json",        # characters.py
    ".timings.json",           # timings.py
    ".profiles.json",          # profiles.py - who uses this
    # The settings themselves, and SQLite's two sidecars. Only ever found in
    # the old place on an install that ran this app before STATE_DIR existed.
    "state.db",
    "state.db-wal",
    "state.db-shm",
)
# Per-child settings are `.settings-<id>.json`, which cannot be listed here
# because the names are not known until there are children. Nothing predates
# profiles, so there is never one to move.
STATE_DIRS = (CUSTOM_DIR_NAME, ".avatars")   # their banner, and their faces


def prepare_state() -> int:
    """Make sure STATE_DIR exists, and move anything left in the old place.

    Runs once at startup. Moving rather than copying, so there is exactly one
    of each file afterwards and no question about which one is being read. If
    STATE_DIR was never set this is GALLERY_DIR and the whole thing is a no-op.
    """
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.error("could not make the state directory %s: %s", STATE_DIR, exc)
        return 0
    if STATE_DIR.resolve() == GALLERY_DIR.resolve():
        return 0
    moved = 0
    for name in STATE_FILES + STATE_DIRS:
        old, new = GALLERY_DIR / name, STATE_DIR / name
        if not old.exists() or new.exists():
            continue
        try:
            shutil.move(str(old), str(new))
            moved += 1
            log.info("moved %s out of the gallery and into %s", name, STATE_DIR)
        except OSError as exc:
            log.warning("could not move %s into the state directory: %s", name, exc)
    return moved


def available() -> bool:
    return GALLERY_DIR.is_dir()


def _sidecar_for(path: Path) -> Path:
    """Where this file's notes are written. Always the current suffix."""
    return path.with_name(path.name + SIDECAR_SUFFIX)


def _sidecars_for(path: Path) -> tuple[Path, ...]:
    """Every name this file's notes could be under, current one first.

    Anything that moves or removes a media file has to take all of these with
    it, or an item made before the rename loses its prompt on the way into the
    trash - or, worse, leaves a stale sidecar behind for the next file that
    happens to reuse the name.
    """
    return tuple(path.with_name(path.name + suffix)
                 for suffix in (SIDECAR_SUFFIX, LEGACY_SIDECAR_SUFFIX))


def _safe_path(item_id: str) -> Path:
    """Resolve an id to a file inside the gallery, or raise.

    The id is a bare filename. Anything with a separator or a parent reference
    is refused outright, and the resolved path is checked to be inside the
    directory, so a crafted id cannot read or delete elsewhere on the disk.
    """
    if not item_id or "/" in item_id or "\\" in item_id or item_id.startswith("."):
        raise GalleryError("bad id")
    path = (GALLERY_DIR / item_id).resolve()
    if path.parent != GALLERY_DIR.resolve() or not path.is_file():
        raise GalleryError("not found")
    if path.suffix.lower() not in MEDIA_SUFFIXES:
        raise GalleryError("not media")
    return path


def _poster_for(path: Path) -> Path:
    return GALLERY_DIR / POSTER_DIR_NAME / (path.name + ".jpg")


def _trash_poster_for(path: Path) -> Path:
    """Posters for trashed videos are prefixed, so a reused filename cannot
    make a deleted clip and a new one share one. Dropped on the way out of the
    trash, either direction, or they would pile up forever."""
    return GALLERY_DIR / POSTER_DIR_NAME / ("trash-" + path.name + ".jpg")


def _trash_dir() -> Path:
    return GALLERY_DIR / TRASH_DIR_NAME


def _safe_trash_path(item_id: str) -> Path:
    """Like _safe_path, but for something sitting in the trash."""
    if not item_id or "/" in item_id or "\\" in item_id or item_id.startswith("."):
        raise GalleryError("bad id")
    path = (_trash_dir() / item_id).resolve()
    if path.parent != _trash_dir().resolve() or not path.is_file():
        raise GalleryError("not found")
    if path.suffix.lower() not in MEDIA_SUFFIXES:
        raise GalleryError("not media")
    return path


def _free(name: str) -> bool:
    """Whether a name is going spare - the media file *and* its sidecar.

    Both, because a sidecar left behind by something that has since been
    deleted for good would otherwise become the new file's own notes.
    """
    path = GALLERY_DIR / name
    return not path.exists() and not any(c.exists() for c in _sidecars_for(path))


def name_for(kind: str, suffix: str, **facts) -> str:
    """The name a new file of this kind should have, per the parent's pattern.

    The one door to app/naming.py from this module: it knows the patterns and
    the counter, and this knows what is already on the disk.
    """
    return naming.render(kind, suffix, taken=lambda n: not _free(n), **facts)


def rename_new(filename: str, kind: str, **facts) -> str:
    """Give a file that has just landed the name the parent's pattern asks for.

    Called on every output of a job the moment ComfyUI writes it, before the
    sidecar exists and before the page is told anything - so the name the job
    reports, the gallery id and the file on disk are the same string from the
    first poll onwards.

    Returns the new bare filename, or the old one if there was nothing to do.
    **Never raises.** A file with an unfashionable name is a far better outcome
    than a render that was made and then lost.
    """
    name = Path(filename).name
    try:
        path = GALLERY_DIR / name
        if not path.is_file():
            return name
        wanted = name_for(kind, path.suffix.lower(), **facts)
        if wanted == name:
            return name
        target = GALLERY_DIR / wanted
        os.replace(path, target)
        # Whichever spelling the notes are under, they land under the current
        # one; any other copy is litter and goes.
        for sidecar in _sidecars_for(path):
            if not sidecar.exists():
                continue
            if _sidecar_for(target).exists():
                sidecar.unlink()
            else:
                os.replace(sidecar, _sidecar_for(target))
        # Posters and thumbnails are keyed by name and mtime and remake
        # themselves on the next request; the ones under the old name are just
        # litter, and the old name can come round again.
        _poster_for(path).unlink(missing_ok=True)
        _thumb_for(path).unlink(missing_ok=True)
        log.info("named %s -> %s", name, wanted)
        return wanted
    except (OSError, ValueError) as exc:
        log.warning("could not rename %s: %s", name, exc)
        return name


def _write_sidecar(path: Path, meta: dict) -> None:
    """Write beside the file, then swap it in.

    A temp file and os.replace rather than write_text, because that needs
    write on the *directory* and not on the sidecar itself. Fifteen of the
    sidecars turned out to be owned by ComfyUI's user at 644 - the app runs
    as its own user in ComfyUI's group - so starring or renaming any of them
    was a 500 for as long as anyone can remember. The directory is
    group-writable and setgid (see "File ownership" in the README); the
    files inside it need not be.
    """
    target = _sidecar_for(path)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(meta, indent=1))
    os.replace(tmp, target)
    # Migrate on write: the notes are now under the current name, so a copy
    # under the old one is stale and would outlive the file it describes.
    for old in _sidecars_for(path)[1:]:
        try:
            old.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            log.warning("left an old sidecar beside %s: %s", path.name, exc)


def set_favourite(item_id: str, on: bool) -> dict:
    """Star or unstar. Creates a sidecar for files that never had one."""
    path = _safe_path(item_id)
    meta = _read_sidecar(path)
    meta["favourite"] = bool(on)
    meta.setdefault("created", path.stat().st_mtime)
    _write_sidecar(path, meta)
    return meta


def set_family(item_id: str, on: bool) -> dict:
    """Put one of their own things on the family shelf, or take it off again.

    Stored exactly like the star - one flag in the sidecar - so it travels with
    the file into the trash and back, survives a rebuild, and needs no index to
    go stale. It is the middle ground between "each child sees only their own"
    and the parent switch that shows everybody everything: they choose, one
    picture at a time.
    """
    path = _safe_path(item_id)
    meta = _read_sidecar(path)
    meta["family"] = bool(on)
    meta.setdefault("created", path.stat().st_mtime)
    _write_sidecar(path, meta)
    return meta


MAX_NAME = 60
MAX_TAGS = 8
MAX_TAG = 24


def set_name(item_id: str, name: str) -> dict:
    """Give something a name of their own. An empty name takes it away again."""
    path = _safe_path(item_id)
    meta = _read_sidecar(path)
    meta["name"] = " ".join(name.split())[:MAX_NAME]
    meta.setdefault("created", path.stat().st_mtime)
    _write_sidecar(path, meta)
    return meta


def _clean_tag(tag: str) -> str:
    return " ".join(tag.split()).strip("#").lower()[:MAX_TAG]


def set_tag(item_id: str, tag: str, on: bool = True) -> list[str]:
    """Add or remove one tag. Returns the item's tags afterwards."""
    tag = _clean_tag(tag)
    if not tag:
        return read_tags(item_id)
    path = _safe_path(item_id)
    meta = _read_sidecar(path)
    tags = [t for t in (meta.get("tags") or []) if isinstance(t, str)]
    tags = [t for t in tags if t != tag]
    if on:
        tags.append(tag)
    meta["tags"] = tags[:MAX_TAGS]
    meta.setdefault("created", path.stat().st_mtime)
    _write_sidecar(path, meta)
    return meta["tags"]


def read_tags(item_id: str) -> list[str]:
    try:
        return [t for t in (_read_sidecar(_safe_path(item_id)).get("tags") or [])
                if isinstance(t, str)]
    except GalleryError:
        return []


def all_tags() -> list[str]:
    """Every tag in use, most used first, so the common ones lead."""
    counts: dict[str, int] = {}
    for item in listing():
        for tag in item["tags"]:
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts, key=lambda t: (-counts[t], t))


def last_frame(item_id: str) -> bytes:
    """The final frame of a video as PNG, for "what happens next?".

    Seeks to half a second before the end and decodes from there, rather than
    decoding all 120-360 frames to reach the last one.
    """
    import io

    import av

    path = _safe_path(item_id)
    if MEDIA_SUFFIXES[path.suffix.lower()][0] != "video":
        raise GalleryError("not a video")

    last = None
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if container.duration:
            target = max(0, container.duration - 500_000)  # microseconds
            try:
                container.seek(target, backward=True, any_frame=False)
            except Exception:
                pass  # fall through to a full decode
        for frame in container.decode(stream):
            last = frame
    if last is None:
        raise GalleryError("no frames")

    out = io.BytesIO()
    last.to_image().save(out, "PNG")
    return out.getvalue()


def poster(item_id: str) -> Path | None:
    """A JPEG for anything that is not already a picture, cached on first ask.

    A video's first frame, or a song's waveform.

    Cached next to a version stamp check: if the media file is newer than the
    poster (a reused filename after a delete), the poster is remade.
    """
    return _poster_at(_safe_path(item_id), item_id)


def trash_poster(item_id: str) -> Path | None:
    """The same, for something sitting in the trash.

    Cached under a "trash-" prefix rather than the plain name: ComfyUI reuses
    a filename once its file is gone, so a deleted clip and a new one can share
    a name, and they must not share a poster.
    """
    return _poster_at(_safe_trash_path(item_id), item_id, prefix="trash-")


def still(item_id: str, trashed: bool = False) -> Path | None:
    """A path to *something showable* for any item, in the gallery or the trash.

    For a picture that is the file itself; for a video, its cached poster
    frame; for a song, a picture of its waveform. Anything that wants to draw a
    thumbnail wants this rather than three branches of its own.
    """
    try:
        path = _safe_trash_path(item_id) if trashed else _safe_path(item_id)
    except GalleryError:
        return None
    if MEDIA_SUFFIXES[path.suffix.lower()][0] == "image":
        return path
    # Straight to _poster_at with the path already in hand: going back through
    # poster()/trash_poster() would resolve and stat the id a second time, and
    # would raise rather than return None if the file vanished in between.
    return _poster_at(path, item_id, prefix="trash-" if trashed else "")


def _poster_at(path: Path, item_id: str, prefix: str = "") -> Path | None:
    media = MEDIA_SUFFIXES[path.suffix.lower()][0]
    if media == "image":
        return None

    target = GALLERY_DIR / POSTER_DIR_NAME / (prefix + path.name + ".jpg")
    try:
        if target.is_file() and target.stat().st_mtime >= path.stat().st_mtime:
            return target
    except OSError:
        pass

    if media == "audio":
        return _waveform_at(path, item_id, target)

    try:
        import av
        from PIL import Image

        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            for frame in container.decode(stream):
                image = frame.to_image()
                break
            else:
                return None
        if image.width > POSTER_WIDTH:
            ratio = POSTER_WIDTH / image.width
            image = image.resize((POSTER_WIDTH, round(image.height * ratio)), Image.LANCZOS)
        target.parent.mkdir(exist_ok=True)
        image.convert("RGB").save(target, "JPEG", quality=82, optimize=True)
        return target
    except Exception as exc:  # decode failures, odd containers, permissions
        log.warning("could not make a poster for %s: %s", item_id, exc)
        return None


# A song's "poster". Drawn rather than photographed, because there is nothing
# to photograph - and a wall of identical music-note icons would tell them
# nothing about which song is which, where a waveform is recognisably the shape
# of *that* song.
WAVE_SIZE = (POSTER_WIDTH, 240)
WAVE_BG = (26, 16, 51)
WAVE_INK = (120, 209, 255)


def _waveform_at(path: Path, item_id: str, target: Path) -> Path | None:
    try:
        import av
        import numpy as np
        from PIL import Image, ImageDraw

        peaks = []
        with av.open(str(path)) as container:
            stream = container.streams.audio[0]
            stream.thread_type = "AUTO"
            for frame in container.decode(stream):
                samples = frame.to_ndarray()
                if samples.size:
                    # Mono for drawing: which channel was louder is not
                    # something a picture this size can show anyway.
                    peaks.append(np.abs(samples).mean(axis=0)
                                 if samples.ndim > 1 else np.abs(samples))
        if not peaks:
            return None
        wave = np.concatenate(peaks).astype("float32")
        # Integer formats come back as integers; scale by the type's range so
        # the picture looks the same whatever the decoder handed over.
        if wave.max() > 1.5:
            wave = wave / float(np.iinfo("int16").max)

        width, height = WAVE_SIZE
        # One column per pixel, each the loudest moment in its slice: the peak
        # and not the mean, or every song looks like a flat grey bar.
        columns = np.array_split(wave, width) if wave.size >= width else [wave]
        loud = np.array([c.max() if c.size else 0.0 for c in columns])
        if loud.max() > 0:
            loud = loud / loud.max()

        image = Image.new("RGB", WAVE_SIZE, WAVE_BG)
        draw = ImageDraw.Draw(image)
        middle = height / 2
        for x, value in enumerate(loud):
            half = max(1.0, value * (height / 2 - 6))
            draw.line([(x, middle - half), (x, middle + half)], fill=WAVE_INK)
        target.parent.mkdir(exist_ok=True)
        image.save(target, "JPEG", quality=82, optimize=True)
        return target
    except Exception as exc:
        log.warning("could not draw a waveform for %s: %s", item_id, exc)
        return None


def _thumb_for(path: Path) -> Path:
    return GALLERY_DIR / THUMB_DIR_NAME / (path.name + ".jpg")


def thumb(item_id: str) -> Path | None:
    """A small cover-cropped JPEG of any item, made once and cached.

    Videos are thumbnailed from their poster frame and songs from their drawn
    waveform, so this works for the whole gallery rather than only for
    pictures. Like the poster, it is remade if the media file is newer -
    ComfyUI reuses filenames after a delete.
    """
    path = _safe_path(item_id)
    drawn = MEDIA_SUFFIXES[path.suffix.lower()][0] != "image"
    target = _thumb_for(path)
    try:
        if target.is_file() and target.stat().st_mtime >= path.stat().st_mtime:
            return target
    except OSError:
        pass

    source = poster(item_id) if drawn else path
    if source is None:
        return None
    try:
        from PIL import Image, ImageOps

        with Image.open(source) as image:
            image.load()
            tile = ImageOps.fit(image.convert("RGB"), THUMB_SIZE, Image.LANCZOS, centering=(0.5, 0.4))
        target.parent.mkdir(exist_ok=True)
        tile.save(target, "JPEG", quality=80, optimize=True)
        return target
    except Exception as exc:
        log.warning("could not make a thumbnail for %s: %s", item_id, exc)
        return None


def save_upload(png: bytes, source: str) -> str:
    """Put a photo or drawing into the gallery. Returns its id.

    Named by us, not ComfyUI, so no collision with its numbering and no reuse
    after a delete. `source` is "camera" or "drawing", for the badge.
    """
    # A comic page is its own thing in the gallery, not a photo they took - it
    # gets its own shelf, its own badge and its own name pattern.
    kind = "comic" if source == "comic" else "upload"
    name = name_for(kind, ".png")
    path = GALLERY_DIR / name
    path.write_bytes(png)
    _write_sidecar(
        path,
        owned({
            "kind": kind,
            "source": source if source in ("camera", "drawing", "card", "comic") else "camera",
            "prompt": "",
            "idea": "",
            "created": time.time(),
        }),
    )
    log.info("kept %s (%s, %d bytes) in the gallery", name, source, len(png))
    return name


def read_bytes(item_id: str) -> tuple[bytes, str]:
    """The file's bytes and media kind, for animating a gallery picture."""
    path = _safe_path(item_id)
    return path.read_bytes(), MEDIA_SUFFIXES[path.suffix.lower()][0]


def rewrite(item_id: str, data: bytes) -> None:
    """New bytes over an existing file, for a finishing step that improves it.

    A temp file and os.replace rather than write_bytes, like the sidecars: this
    directory is ComfyUI's output directory and the page lists it while jobs
    are running, so a half-written picture is a picture they can open.

    The listing's `version` is the file's mtime, so the new bytes get a new URL
    and no browser serves the old bytes. Thumbnails are remade whenever the
    file is newer than the thumbnail, which this makes it.
    """
    path = _safe_path(item_id)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def record(filename: str, **meta) -> None:
    """Write the sidecar for a finished job. Never fatal - it is only metadata.

    `who` comes in with the rest: the job carries whose it is from the moment
    it is submitted, rather than this reading the request context, because by
    the time a video finishes the request that started it is long gone.
    """
    try:
        path = GALLERY_DIR / Path(filename).name
        meta.setdefault("created", time.time())
        owned(meta)
        _sidecar_for(path).write_text(json.dumps(meta, indent=1))
    except OSError as exc:
        log.warning("could not write gallery metadata for %s: %s", filename, exc)
    # Every finished file passes through here, whichever route started it, so
    # this is the one call that covers "they made something".
    audit.record("render.finished", actor=meta.get("who") or "",
                 id=Path(filename).name, kind=meta.get("kind") or "",
                 words=meta.get("idea") or meta.get("prompt") or "")


def _read_sidecar(path: Path) -> dict:
    """The notes beside a file, under whichever name they were written."""
    for sidecar in _sidecars_for(path):
        try:
            return json.loads(sidecar.read_text())
        except (OSError, ValueError):
            continue
    return {}


def _dimensions(path: Path) -> tuple[int, int] | None:
    """(width, height) read off the file. Cheap: Pillow reads a PNG header
    without decoding it, and PyAV reads an mp4's moov box without decoding a
    frame. Still, the listing writes it into the sidecar so this runs once
    per file, not once per file per page load."""
    try:
        media = MEDIA_SUFFIXES.get(path.suffix.lower(), ("", ""))[0]
        if media == "audio":
            return None   # a song has no width; see _seconds() instead
        if media == "video":
            import av

            with av.open(str(path)) as container:
                v = container.streams.video[0]
                return int(v.width), int(v.height)
        from PIL import Image

        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None


def _seconds(path: Path) -> float | None:
    """How long a song is, from the file. A song's equivalent of _dimensions:
    it is the one number the viewer can show under it, and the one the sidecar
    may not have if the file was recovered rather than made here."""
    try:
        import av

        with av.open(str(path)) as container:
            if container.duration:
                return round(container.duration / av.time_base, 1)
            stream = container.streams.audio[0]
            if stream.duration and stream.time_base:
                return round(float(stream.duration * stream.time_base), 1)
    except Exception:
        pass
    return None


def listing(everyone: bool = False, family: bool = False) -> list[dict]:
    """Everything in the directory, newest first.

    Filtered to whoever the request belongs to, unless `everyone` - which the
    parent page, the nightly email and the disk-space sums all want, because
    all three are about the household rather than about one child.

    `family` adds back the things another child has put on the family shelf.
    It is **off by default on purpose**, because almost every caller of this
    function is asking "what is theirs" rather than "what may they see": the daily
    limits count what they have made (`usage_today`), `all_tags` lists the words
    they have typed, the character counts are their cast's, and the sticker and
    frame routes are looking up the item they were just handed. Exactly one
    caller - `GET /api/gallery`, the page itself - is asking the other
    question, and it is the one that passes `family=True`. Defaulting the other
    way would have quietly charged a sibling's shared picture against their three
    a day.

    A family item that is not theirs still comes back with `mine: False` on it,
    so the page can show whose it is and offer none of the buttons that would
    change it. `belongs_to_me` is deliberately untouched: seeing is not
    changing, and every route that changes something still asks that.
    """
    if not available():
        return []
    who = None if everyone else _who()

    items = []
    try:
        entries = list(GALLERY_DIR.iterdir())
    except OSError as exc:
        raise GalleryError(str(exc)) from exc

    for path in entries:
        kind = MEDIA_SUFFIXES.get(path.suffix.lower())
        if kind is None or not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue

        meta = _read_sidecar(path)
        if kind[0] == "audio":
            # A song has a length rather than a size, and measuring it is the
            # same deal: once, into the sidecar, not on every page load.
            if not meta.get("duration"):
                seconds = _seconds(path)
                if seconds:
                    meta["duration"] = seconds
                    try:
                        meta.setdefault("created", stat.st_mtime)
                        _write_sidecar(path, meta)
                    except OSError:
                        pass
        elif not meta.get("width") or not meta.get("height"):
            # They want to see the size in the viewer; measured once, kept.
            dims = _dimensions(path)
            if dims:
                meta["width"], meta["height"] = dims
                try:
                    meta.setdefault("created", stat.st_mtime)
                    _write_sidecar(path, meta)
                except OSError:
                    pass
        # An item an older version of this app kept off a child's shelves.
        # Nothing stamps this any more, and the check stays only so that
        # upgrading cannot put one of them in front of a child. `who is None`
        # is the parent page, the nightly email and the space sums, all of
        # which are about the household and see everything.
        if meta.get("adult") and who is not None:
            continue
        is_mine = mine(meta.get("who") or "", who)
        if not is_mine and not (family and meta.get("family")):
            continue
        items.append(
            {
                "id": path.name,
                "media": kind[0],
                # Who made it. The parent page puts a name under each
                # thumbnail once there is more than one child, and the page
                # itself puts a face on any family-shelf tile that is somebody
                # else's - a picture that is not theirs must not read as theirs.
                "who": meta.get("who") or "",
                # Theirs to change, or somebody else's to look at. Worked out
                # here rather than by comparing ids in the browser, because
                # "no owner recorded" means the profile that carries `adopts`
                # and only the server knows which one that is.
                "mine": is_mine,
                "family": bool(meta.get("family")),
                "width": meta.get("width") or 0,
                "height": meta.get("height") or 0,
                "prompt": meta.get("prompt") or "",
                "idea": meta.get("idea") or meta.get("prompt") or "",
                "kind": meta.get("kind") or "",
                "source": meta.get("source") or "",
                "duration": meta.get("duration"),
                "orientation": meta.get("orientation") or "",
                "styles": meta.get("styles") or {},
                "favourite": bool(meta.get("favourite")),
                "recovered": bool(meta.get("recovered")),
                # Who is in it, and the seed it was drawn with - between them,
                # "everything with Luna in" and "the same picture but at night".
                "character": meta.get("character") or "",
                "seed": meta.get("seed"),
                "cutout": bool(meta.get("cutout")),
                # What they asked the character to say, so "make another like
                # this" can put it back in the box they typed it into.
                "said": meta.get("said") or "",
                # Which of their own pictures a made-from-one-they-have picture was
                # made out of, and - for a restyle - which chip and which words
                # made it. All four are what "make it again, but..." reopens
                # the right sheet on; without them in the listing the viewer
                # has the file and no idea where it came from.
                "edit_of": meta.get("edit_of") or "",
                "restyle_of": meta.get("restyle_of") or "",
                "turned_into": meta.get("turned_into") or "",
                "twist": meta.get("twist") or "",
                # A story film knows all three things it was made of, so the
                # viewer can say where it came from and the Story card can
                # find its way back to them after a reload.
                "story_of": meta.get("story_of") or None,
                # And what a song actually sings. Without it, opening one shows
                # a description of the sound and none of the words.
                "lyrics": meta.get("lyrics") or "",
                "name": meta.get("name") or "",
                # An album was the earlier shape of this; anything still
                # carrying one reads as a tag rather than being lost.
                "tags": sorted(set(
                    [t for t in (meta.get("tags") or []) if isinstance(t, str)]
                    + ([meta["album"].lower()] if meta.get("album") else [])
                )),
                # Fall back to the file's own mtime for anything with no sidecar.
                "created": meta.get("created") or stat.st_mtime,
                "bytes": stat.st_size,
                # ComfyUI numbers files by scanning the directory, so deleting
                # one frees its name for the next render. The URL would then be
                # stale in the browser cache and they would be shown the old
                # picture under the new one's name. Changing the URL whenever
                # the bytes change is what makes that impossible.
                "version": int(stat.st_mtime),
            }
        )

    items.sort(key=lambda i: i["created"], reverse=True)
    return items


def media_type(item_id: str) -> str:
    return MEDIA_SUFFIXES.get(Path(item_id).suffix.lower(), ("", "application/octet-stream"))[1]


def path_for(item_id: str) -> Path:
    return _safe_path(item_id)


def zip_into(item_ids: list[str], destination) -> int:
    """Write the named items into `destination` as a zip. Returns how many.

    Stored, not deflated: PNGs and MP4s are already compressed, so deflating
    them burns CPU to save almost nothing. Unknown ids are skipped rather than
    failing the whole download.
    """
    import zipfile

    written = 0
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_STORED) as archive:
        for item_id in item_ids:
            try:
                path = _safe_path(item_id)
            except GalleryError:
                log.warning("skipping unknown item in zip: %s", item_id)
                continue
            archive.write(path, arcname=path.name)
            written += 1
    return written


def delete_many(item_ids: list[str]) -> tuple[list[str], list[str]]:
    """Delete several. Returns (deleted, failed) rather than stopping at the first problem."""
    deleted, failed = [], []
    for item_id in item_ids:
        try:
            delete(item_id)
            deleted.append(item_id)
        except (GalleryError, OSError) as exc:
            log.warning("could not delete %s: %s", item_id, exc)
            failed.append(item_id)
    return deleted, failed


def delete(item_id: str) -> None:
    """Move to the trash. The poster is dropped; it is remade on restore."""
    path = _safe_path(item_id)
    trash = _trash_dir()
    trash.mkdir(exist_ok=True)

    meta = _read_sidecar(path)
    meta["deleted_at"] = time.time()
    meta.setdefault("created", path.stat().st_mtime)

    # ComfyUI reuses a filename once its file is gone from the output
    # directory, so the trash can already hold an older image_00007_.png when
    # a newer one is deleted. shutil.move would silently overwrite it - the
    # exact thing a trash exists to prevent. Give the newer one a new name,
    # the way restore() does going the other way.
    target = trash / path.name
    if target.exists():
        target = trash / f"{path.stem}_{int(time.time())}{path.suffix}"
    shutil.move(str(path), str(target))
    _write_sidecar(target, meta)
    for extra in (*_sidecars_for(path), _poster_for(path), _thumb_for(path)):
        try:
            extra.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            log.warning("left a stray %s for %s: %s", extra.name, item_id, exc)
    log.info("moved %s to the trash", item_id)
    audit.record("gallery.deleted", id=item_id, kind=meta.get("kind") or "",
                 words=meta.get("idea") or meta.get("prompt") or "",
                 whose=meta.get("who") or "")


def trash_listing(everyone: bool = False) -> list[dict]:
    """What is in the trash, most recently deleted first."""
    trash = _trash_dir()
    if not trash.is_dir():
        return []
    who = None if everyone else _who()
    items = []
    for path in trash.iterdir():
        kind = MEDIA_SUFFIXES.get(path.suffix.lower())
        if kind is None or not path.is_file():
            continue
        meta = _read_sidecar(path)
        try:
            stat = path.stat()
        except OSError:
            continue
        if not mine(meta.get("who") or "", who):
            continue
        if meta.get("adult") and who is not None:
            continue
        deleted_at = meta.get("deleted_at") or stat.st_mtime
        items.append(
            {
                "id": path.name,
                "media": kind[0],
                "who": meta.get("who") or "",
                "kind": meta.get("kind") or "",
                "idea": meta.get("idea") or meta.get("prompt") or "",
                "created": meta.get("created") or stat.st_mtime,
                "deleted_at": deleted_at,
                "purge_at": deleted_at + trash_days() * 86400,
                "bytes": stat.st_size,
                "version": int(stat.st_mtime),
            }
        )
    items.sort(key=lambda i: i["deleted_at"], reverse=True)
    return items


def trash_path_for(item_id: str) -> Path:
    return _safe_trash_path(item_id)


def restore(item_id: str) -> None:
    """Put something back from the trash, keeping its prompt and star."""
    path = _safe_trash_path(item_id)
    meta = _read_sidecar(path)
    meta.pop("deleted_at", None)
    target = GALLERY_DIR / path.name
    if target.exists():
        # Its name has been reused by a newer render; give the old one a new one.
        target = GALLERY_DIR / f"{path.stem}_restored_{int(time.time())}{path.suffix}"
    shutil.move(str(path), str(target))
    _write_sidecar(target, meta)
    for extra in (*_sidecars_for(path), _trash_poster_for(path)):
        try:
            extra.unlink()
        except OSError:
            pass
    log.info("restored %s from the trash as %s", item_id, target.name)
    audit.record("gallery.restored", id=item_id, back_as=target.name,
                 kind=meta.get("kind") or "", whose=meta.get("who") or "")


def destroy(item_id: str) -> None:
    """Delete from the trash for good."""
    path = _safe_trash_path(item_id)
    meta = _read_sidecar(path)
    path.unlink()
    for extra in (*_sidecars_for(path), _trash_poster_for(path)):
        try:
            extra.unlink()
        except OSError:
            pass
    log.info("destroyed %s", item_id)
    audit.record("gallery.destroyed", id=item_id, kind=meta.get("kind") or "",
                 words=meta.get("idea") or meta.get("prompt") or "",
                 whose=meta.get("who") or "")


def purge_trash(days: float | None = None) -> int:
    """Empty anything that has sat in the trash longer than `days`.

    `None` asks the setting, rather than freezing it into a default at import:
    a parent changing "keep deleted things for" on the page has to reach the
    next sweep without a restart.
    """
    days = trash_days() if days is None else days
    cutoff = time.time() - days * 86400
    gone = 0
    # The whole household's. This runs from the janitor, where nobody is signed
    # in, and from the parent page, where somebody's cookie is - and a sweep
    # that quietly skipped the other children's would leave a trash that says
    # it was emptied and was not.
    for item in trash_listing(everyone=True):
        if item["deleted_at"] < cutoff:
            try:
                destroy(item["id"])
                gone += 1
            except (GalleryError, OSError) as exc:
                log.warning("could not purge %s: %s", item["id"], exc)
    if gone:
        note_trash_emptied(gone, f"the {int(days)}-day clean-up")
    return gone


def note_trash_emptied(count: int, by: str) -> None:
    """Remember that the trash was emptied, and by what."""
    audit.record("gallery.emptied", entries=count, by=by)
    try:
        update_settings(
            trash_emptied_at=time.time(),
            trash_emptied_count=count,
            trash_emptied_by=by,
        )
    except OSError as exc:
        log.warning("could not record the trash emptying: %s", exc)


# --- joining clips into a movie ---------------------------------------------

# "film" is the one word they and their grown-ups see for a video made of several
# clips. There are still two *kinds* underneath - `story`, which the model
# plans from their sentence and films part by part, and `movie`, which they
# assembles from clips they already have - because those strings are written into
# every sidecar already and renaming them would orphan everything they have made.
# They are a record of how a file came about, not a label for the page.


def join(item_ids: list[str], title_card: bytes | None, title_seconds: float = 2.0,
         title: str = "") -> str:
    """Stitch several clips (and an optional title card) into one new video.

    Everything is re-encoded to the first clip's size and 24fps, with audio
    resampled to 48kHz stereo AAC, so clips of different shapes can be mixed -
    a portrait clip in a landscape movie is letterboxed rather than refused.
    CPU-bound and blocking: call it from a thread. A 45s movie takes ~10s.
    """
    import io
    import uuid
    from fractions import Fraction

    import av
    from PIL import Image

    paths = [_safe_path(i) for i in item_ids]
    if not paths:
        raise GalleryError("nothing to join")
    for p in paths:
        if MEDIA_SUFFIXES[p.suffix.lower()][0] != "video":
            raise GalleryError("only videos can be joined")

    with av.open(str(paths[0])) as first:
        width, height = first.streams.video[0].width, first.streams.video[0].height
    fps = 24
    name = name_for("movie", ".mp4", idea=title, who=_who_id())
    target = GALLERY_DIR / name
    tmp = GALLERY_DIR / (name + ".part")

    # The temp name ends in .part, so name the container format explicitly.
    out = av.open(str(tmp), "w", format="mp4")
    vs = out.add_stream("libx264", rate=fps)
    vs.width, vs.height, vs.pix_fmt = width, height, "yuv420p"
    vs.options = {"crf": "20", "preset": "veryfast"}
    aus = out.add_stream("aac", rate=48000)
    aus.layout = "stereo"
    aus.format = "fltp"
    resampler = av.AudioResampler(format="fltp", layout="stereo", rate=48000)
    vpts = 0
    apts = 0

    def fit(image: Image.Image) -> Image.Image:
        """Letterbox onto the movie's frame size."""
        if image.size == (width, height):
            return image
        scale = min(width / image.width, height / image.height)
        inner = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
        canvas = Image.new("RGB", (width, height), (0, 0, 0))
        canvas.paste(inner, ((width - inner.width) // 2, (height - inner.height) // 2))
        return canvas

    def push_video(image: Image.Image) -> None:
        nonlocal vpts
        frame = av.VideoFrame.from_image(fit(image.convert("RGB")))
        frame.pts = vpts
        frame.time_base = Fraction(1, fps)
        vpts += 1
        for packet in vs.encode(frame):
            out.mux(packet)

    def push_audio(frame) -> None:
        nonlocal apts
        for rf in resampler.resample(frame):
            rf.pts = apts
            rf.time_base = Fraction(1, 48000)
            apts += rf.samples
            for packet in aus.encode(rf):
                out.mux(packet)

    def push_silence(seconds: float) -> None:
        silence = av.AudioFrame(format="fltp", layout="stereo", samples=1024)
        silence.sample_rate = 48000
        for plane in silence.planes:
            plane.update(bytes(plane.buffer_size))
        for _ in range(int(48000 * seconds / 1024) + 1):
            push_audio(silence)

    try:
        if title_card:
            still = Image.open(io.BytesIO(title_card))
            still.load()
            for _ in range(int(fps * title_seconds)):
                push_video(still)
            push_silence(title_seconds)

        for path in paths:
            with av.open(str(path)) as clip:
                v = clip.streams.video[0]
                a = clip.streams.audio[0] if clip.streams.audio else None
                v.thread_type = "AUTO"
                # Keep the tracks from drifting apart: if a clip has no audio,
                # pad silence for its length.
                if a is None:
                    length = (clip.duration or 0) / 1e6
                for packet in clip.demux([st for st in (v, a) if st is not None]):
                    for frame in packet.decode():
                        if packet.stream.type == "video":
                            push_video(frame.to_image())
                        else:
                            push_audio(frame)
                if a is None and clip.duration:
                    push_silence(length)

        for packet in vs.encode():
            out.mux(packet)
        for packet in aus.encode():
            out.mux(packet)
        out.close()
        tmp.rename(target)
    except Exception:
        try:
            out.close()
        except Exception:
            pass
        tmp.unlink(missing_ok=True)
        raise

    _write_sidecar(target, owned({
        "kind": "movie",
        "prompt": title or "",
        "idea": title or "",
        "parts": [p.name for p in paths],
        "orientation": "landscape" if width >= height else "portrait",
        "duration": round(vpts / fps),
        "created": time.time(),
    }))
    log.info("joined %d clips into %s (%.0fs)", len(paths), name, vpts / fps)
    return name


# --- reading the prompt back out of the file itself -------------------------
#
# ComfyUI embeds the whole submitted graph in what it writes: a PNG text chunk
# for images, an mp4 metadata field for videos. That is a better source of
# truth than anything we could keep alongside, because it survives everything -
# a container restarted mid-render, a crash, a file made straight from ComfyUI,
# or a sidecar someone deleted by hand.
#
# It recovers the *composed* prompt (their words plus the style phrases), not
# the raw idea, which was never in the graph. Recovered sidecars say so.

# Where the prompt text sits in each of the three graphs. Falls back to a scan
# when a workflow has been re-exported with different ids.
_PROMPT_NODES = ("6", "405:376", "398:376", "251:252", "74")
_DURATION_NODES = ("405:362", "398:362", "251:198")
_ASPECT_NODES = ("409", "403")


def _embedded_graph(path: Path) -> dict | None:
    """The API graph ComfyUI stored inside the file, if it is there."""
    try:
        if path.suffix.lower() == ".png":
            from PIL import Image

            with Image.open(path) as image:
                raw = image.info.get("prompt")
        elif MEDIA_SUFFIXES.get(path.suffix.lower(), ("", ""))[0] in ("video", "audio"):
            # ComfyUI writes the graph into an mp3's tags as well as an mp4's,
            # which is what makes a song's words recoverable at all.
            import av

            with av.open(str(path)) as container:
                raw = container.metadata.get("prompt")
        else:
            return None
        return json.loads(raw) if raw else None
    except Exception as exc:
        log.debug("no embedded graph in %s: %s", path.name, exc)
        return None


def _from_graph(graph: dict) -> dict:
    """Whatever the graph can tell us about how this was made."""
    meta: dict = {}

    # A song first: its text lives in named fields rather than in a prompt
    # node, and the words are the half worth having back.
    for node in graph.values():
        if not str(node.get("class_type", "")).startswith("TextEncodeAceStep"):
            continue
        inputs = node.get("inputs", {}) or {}
        tags = inputs.get("tags")
        lyrics = inputs.get("lyrics")
        if isinstance(tags, str) and tags.strip():
            meta["prompt"] = tags.strip()[:4000]
        if isinstance(lyrics, str) and lyrics.strip():
            meta["lyrics"] = lyrics.strip()[:4000]
        for field in ("bpm", "duration"):
            if isinstance(inputs.get(field), (int, float)):
                meta[field] = inputs[field]
        break
    if meta.get("prompt"):
        return meta

    text = ""
    for nid in _PROMPT_NODES:
        node = graph.get(nid) or {}
        value = node.get("inputs", {}).get("value") or node.get("inputs", {}).get("text")
        if isinstance(value, str) and value.strip():
            text = value.strip()
            break
    if not text:
        # A re-exported workflow with different ids: take the longest positive
        # string that is not the negative prompt.
        candidates = []
        for node in graph.values():
            if node.get("class_type") not in ("PrimitiveStringMultiline", "CLIPTextEncode"):
                continue
            value = node.get("inputs", {}).get("value") or node.get("inputs", {}).get("text")
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
        # The negative is a long comma-separated list; the positive reads as
        # prose. Prefer the one with the fewest commas per word.
        if candidates:
            text = min(candidates, key=lambda c: c.count(",") / max(1, len(c.split())))
    if text:
        meta["prompt"] = text[:4000]

    for node in graph.values():
        prefix = node.get("inputs", {}).get("filename_prefix")
        if isinstance(prefix, str) and "/" in prefix:
            stem = prefix.rsplit("/", 1)[1]
            if stem in ("image", "t2v", "i2v", "flf"):
                meta["kind"] = stem
            break

    for nid in _DURATION_NODES:
        value = (graph.get(nid) or {}).get("inputs", {}).get("value")
        if isinstance(value, int) and 1 <= value <= 120:
            meta["duration"] = value
            break

    for nid in _ASPECT_NODES:
        aspect = (graph.get(nid) or {}).get("inputs", {}).get("aspect_ratio")
        if isinstance(aspect, str):
            meta["orientation"] = _ORIENTATION_BY_ASPECT.get(aspect, "")
            break
    if "orientation" not in meta:
        for node in graph.values():
            w = node.get("inputs", {}).get("width")
            h = node.get("inputs", {}).get("height")
            if isinstance(w, int) and isinstance(h, int) and w and h:
                meta["orientation"] = (
                    "landscape" if w > h * 1.05 else "portrait" if h > w * 1.05 else "square"
                )
                break
    return meta


def recover_sidecar(path: Path) -> bool:
    """Fill in what a sidecar is missing, from what ComfyUI wrote into the file.

    Fills gaps rather than replacing: a file can already have a star or an
    album while still having no idea what prompt made it, which is exactly what
    happens to anything whose job was interrupted after they had filed it.
    """
    existing = _read_sidecar(path)
    # A song made before the words were being recorded has a prompt - the tags,
    # what it should *sound* like - and no lyrics, which is the half worth
    # reading. So "has a prompt" is not the same as "has nothing missing".
    audio = MEDIA_SUFFIXES.get(path.suffix.lower(), ("", ""))[0] == "audio"
    wants_prompt = not existing.get("prompt")
    wants_lyrics = audio and not existing.get("lyrics")
    if not wants_prompt and not wants_lyrics:
        return False
    graph = _embedded_graph(path)
    if not graph:
        return False
    found = _from_graph(graph)
    if not found.get("prompt") and not found.get("lyrics"):
        return False

    try:
        stat = path.stat()
    except OSError:
        return False
    # Anything already recorded wins; this only adds what was missing.
    meta = {**found, **existing}
    meta.setdefault("created", stat.st_mtime)
    # Their own words were never in the graph - only the composed prompt - so the
    # viewer can be honest about where this came from. Adding a song's lyrics
    # to a sidecar that already had their idea is not that: nothing was guessed,
    # so it would be a warning about a file that is fine.
    if wants_prompt:
        meta["recovered"] = True
    try:
        _write_sidecar(path, meta)
    except OSError as exc:
        log.warning("could not write a recovered sidecar for %s: %s", path.name, exc)
        return False
    log.info("recovered the notes for %s from the file itself", path.name)
    return True


def recover_missing() -> int:
    """Every media file with no sidecar gets one back, where the file knows."""
    if not available():
        return 0
    done = 0
    for path in GALLERY_DIR.iterdir():
        try:
            if not path.is_file() or path.suffix.lower() not in MEDIA_SUFFIXES:
                continue
            if recover_sidecar(path):
                done += 1
        except OSError:
            continue
    return done


# --- their own voice over a video ---------------------------------------------

VOICE_RATE = 48000
# How far the video's own sound drops while they are talking. Loud enough to
# still hear the music, quiet enough that their words win.
VOICE_DUCK = 0.22
VOICE_FADE = 0.25          # seconds to come back up once they have finished


def _pcm(source, seconds: float | None = None):
    """Decode any audio to stereo float32 at 48kHz, shape (2, n)."""
    import av
    import numpy as np

    resampler = av.AudioResampler(format="fltp", layout="stereo", rate=VOICE_RATE)
    chunks = []
    with av.open(source) as container:
        if not container.streams.audio:
            return np.zeros((2, 0), dtype="float32")
        for frame in container.decode(container.streams.audio[0]):
            for resampled in resampler.resample(frame):
                chunks.append(resampled.to_ndarray())
    for resampled in resampler.resample(None):
        chunks.append(resampled.to_ndarray())
    if not chunks:
        return np.zeros((2, 0), dtype="float32")
    pcm = np.concatenate(chunks, axis=1).astype("float32")
    if pcm.shape[0] == 1:
        pcm = np.repeat(pcm, 2, axis=0)
    if seconds is not None:
        want = int(seconds * VOICE_RATE)
        pcm = pcm[:, :want] if pcm.shape[1] > want else np.pad(
            pcm, ((0, 0), (0, want - pcm.shape[1]))
        )
    return pcm


def _mixed(video_path, voice_bytes: bytes, seconds: float, keep_original: bool):
    """Their voice over the video's own sound, or on its own.

    Ducked rather than crossfaded: the music drops while they are talking and
    comes back up a quarter of a second after they stop, which is what makes
    their words carry without the video going silent.
    """
    import io
    import numpy as np

    voice = _pcm(io.BytesIO(voice_bytes), seconds)
    if not keep_original:
        return voice

    original = _pcm(str(video_path), seconds)
    if original.shape[1] == 0:
        return voice

    # Where they are actually talking, to the nearest 20ms, then held so the
    # gaps between words do not make the music pump up and down.
    n = voice.shape[1]
    block = int(VOICE_RATE * 0.02)
    loud = np.abs(voice).max(axis=0)
    blocks = loud[: (n // block) * block].reshape(-1, block).max(axis=1) > 0.02
    hold = int(VOICE_FADE / 0.02)
    talking = np.convolve(blocks.astype("float32"), np.ones(hold), mode="same") > 0
    gain = np.where(np.repeat(talking, block), VOICE_DUCK, 1.0).astype("float32")
    gain = np.pad(gain, (0, n - gain.shape[0]), constant_values=1.0)
    # Smooth the steps so the duck sounds like a fade, not a switch.
    window = np.ones(int(VOICE_RATE * 0.05), dtype="float32")
    gain = np.convolve(gain, window / window.sum(), mode="same")

    mixed = original * gain + voice
    # Only touch the level if it would actually clip.
    peak = float(np.abs(mixed).max()) if mixed.size else 0.0
    if peak > 1.0:
        mixed /= peak
    return mixed


def _with_new_audio(path, mixed, kind: str, extra: dict, replace: bool = False,
                    ratio: float | None = None) -> str:
    """A new video: this one's pictures, remuxed, with `mixed` as its sound.

    With `replace`, the result is written over `path` itself and its sidecar
    gains `extra` rather than being a new item - for a sound they asked for at
    the same time as the video, where a second copy would only be clutter.

    With `ratio`, `mixed` is the *new* track alone and this file's own sound is
    added underneath it at that gain, for the whole length. That is the shape
    the story maker's song needs and it is deliberately **not** the voice-over's
    duck: `_mixed` drops the original only while they are actually talking, and a
    song is talking from the first second to the last, so the detector would be
    on throughout and would only cost a convolution to say what one number
    says. `ratio=None` means `mixed` is already the finished soundtrack, which
    is what their voice and the sound effects hand over.

    The video stream is **remuxed**, not re-encoded - the frames are already
    exactly what they want, so copying the packets is both instant and lossless
    where a decode/encode round trip would be neither.

    Shared by their voice and the sound effects, which are the same operation
    with a different array. The original file is never touched: everything in
    here is a new item, so "that sounded wrong" is deleting one file rather
    than having lost the video.
    """
    from fractions import Fraction

    import av
    import numpy as np

    if ratio is not None:
        # Truncated to the new track's length so the two cannot drift, which
        # `_pcm` does on the way past.
        own = _pcm(str(path), mixed.shape[1] / VOICE_RATE)
        if own.shape[1]:
            mixed = mixed + own * float(ratio)
            peak = float(np.abs(mixed).max()) if mixed.size else 0.0
            if peak > 1.0:
                mixed /= peak

    source = _read_sidecar(path)
    if replace:
        name = path.name
        target = path
    else:
        name = name_for(kind, ".mp4",
                        idea=str(source.get("idea") or source.get("prompt") or ""),
                        who=str(source.get("who") or _who_id()))
        target = GALLERY_DIR / name
    tmp = GALLERY_DIR / (name + ".part")

    out = av.open(str(tmp), "w", format="mp4")
    try:
        with av.open(str(path)) as src:
            vin = src.streams.video[0]
            # PyAV 18 spells the remux helper this way; add_stream(template=)
            # was the older name and is gone.
            vout = out.add_stream_from_template(vin)
            aout = out.add_stream("aac", rate=VOICE_RATE)
            aout.layout = "stereo"
            aout.format = "fltp"

            for packet in src.demux(vin):
                # The flush packet at the end has no dts and nothing to mux.
                if packet.dts is None:
                    continue
                packet.stream = vout
                out.mux(packet)

        step = 1024
        for start in range(0, mixed.shape[1], step):
            block = np.ascontiguousarray(mixed[:, start:start + step])
            frame = av.AudioFrame.from_ndarray(block, format="fltp", layout="stereo")
            frame.sample_rate = VOICE_RATE
            frame.pts = start
            frame.time_base = Fraction(1, VOICE_RATE)
            for p in aout.encode(frame):
                out.mux(p)
        for p in aout.encode():
            out.mux(p)
        out.close()
        # rename() over an existing file is fine on Linux; replace() says so.
        tmp.replace(target)
    except Exception:
        try:
            out.close()
        except Exception:
            pass
        tmp.unlink(missing_ok=True)
        raise

    if replace:
        # The item it already was, plus what was just done to it. The poster
        # and thumbnail are keyed on mtime and remake themselves.
        source.update(extra)
        _write_sidecar(target, source)
        return name
    meta = owned({
        "prompt": source.get("prompt") or "",
        "idea": source.get("idea") or source.get("prompt") or "",
        "name": source.get("name") or "",
        "orientation": source.get("orientation") or "",
        "duration": source.get("duration"),
        "character": source.get("character") or "",
        # A new item made from one of theirs stays theirs, whoever is looking.
        "who": source.get("who") or _who_id(),
        "created": time.time(),
    })
    meta.update(extra)
    _write_sidecar(target, meta)
    return name


# How quiet the end of a render has to be before it counts as nothing, and
# how much of it has to be quiet before trimming is worth the risk.
#
# ACE-Step is given a length and writes something shorter, then leaves the
# rest of the file silent. Measured over fourteen renders on this box, the
# gap between the last sound and the end of the file was a median of 3.0
# seconds and as much as 6.2: a twelve-second jingle that stopped playing at
# 6.9, a fifteen-second hum that stopped at 8.8. For a two-minute song nobody
# notices. For a ten-second jingle it is half the file, and they think it
# broke.
#
# -45 dBFS rather than absolute zero because an mp3 decode of digital silence
# is not digital silence; and the tail has to be a whole second before
# anything is done, so that a piece which really does fade to nothing keeps
# its fade. `TRIM_KEEP` leaves a breath on the end rather than cutting on the
# last sample, which clicks.
TRIM_FLOOR_DB = -45.0
TRIM_MIN_TAIL = 1.0
TRIM_KEEP = 0.35


def trim_tail(name: str) -> float | None:
    """Cut the silence ACE-Step leaves on the end of an instrumental.

    Returns the new length in seconds, or None if nothing was done - which is
    the common case for a song and the right answer whenever the measurement
    is not confident. **Never raises**: this is a tidy-up, and a jingle with a
    silent tail is a far better outcome than a jingle they never get.

    Only the audio is re-encoded, because an mp3 cannot be cut on a packet
    boundary without a gap. ComfyUI writes the graph into the file's tags and
    `recover_sidecar` reads it back, so the metadata is carried across
    deliberately - dropping it would quietly break recovery for exactly the
    files this touches.
    """
    from fractions import Fraction

    import av
    import numpy as np

    path = GALLERY_DIR / Path(name).name
    try:
        with av.open(str(path)) as src:
            stream = src.streams.audio[0]
            rate = stream.rate
            layout = "stereo" if stream.channels > 1 else "mono"
            meta = dict(src.metadata or {})
            res = av.AudioResampler(format="fltp", layout=layout, rate=rate)
            blocks = []
            for frame in src.decode(stream):
                for out in res.resample(frame):
                    blocks.append(out.to_ndarray())
            for out in res.resample(None):
                blocks.append(out.to_ndarray())
        if not blocks:
            return None
        audio = np.concatenate(blocks, axis=1)
    except Exception as exc:
        log.warning("could not read %s to trim it: %s", name, exc)
        return None

    total = audio.shape[1]
    if not total:
        return None
    # A 50ms window, so one stray sample cannot hold the whole tail open.
    window = max(1, int(rate * 0.05))
    loud = np.sqrt(np.mean(audio ** 2, axis=0))
    edge = total
    floor = 10.0 ** (TRIM_FLOOR_DB / 20.0) * float(np.max(np.abs(audio)) or 1.0)
    while edge > window:
        block = loud[edge - window:edge]
        if float(np.sqrt(np.mean(block ** 2))) > floor:
            break
        edge -= window
    tail = (total - edge) / rate
    if tail < TRIM_MIN_TAIL:
        return None
    keep = min(total, edge + int(rate * TRIM_KEEP))
    if keep >= total:
        return None
    audio = np.ascontiguousarray(audio[:, :keep])

    tmp = GALLERY_DIR / (path.name + ".part")
    try:
        out = av.open(str(tmp), "w", format="mp3")
        try:
            out.metadata.update(meta)
            aout = out.add_stream("mp3", rate=rate)
            aout.layout = layout
            aout.format = "fltp"
            step = 1152
            for start in range(0, keep, step):
                block = np.ascontiguousarray(audio[:, start:start + step])
                frame = av.AudioFrame.from_ndarray(block, format="fltp",
                                                   layout=layout)
                frame.sample_rate = rate
                frame.pts = start
                frame.time_base = Fraction(1, rate)
                for packet in aout.encode(frame):
                    out.mux(packet)
            for packet in aout.encode():
                out.mux(packet)
        finally:
            out.close()
        tmp.replace(path)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        log.warning("could not trim the end off %s: %s", name, exc)
        return None

    seconds = round(keep / rate, 2)
    log.info("trimmed %.1fs of silence off %s, now %.1fs", tail, name, seconds)
    return seconds


def add_voice(item_id: str, audio_bytes: bytes, keep_original: bool = True) -> str:
    """A new video: the same pictures, with their recording on the soundtrack.

    Only the audio is rebuilt, by _with_new_audio below - their iPad hands us
    whatever container Safari felt like using, and it has to be mixed with what
    the video already had.

    By default their voice goes **over** the video's own sound, which LTX
    generates and is usually half the fun; `keep_original=False` throws that
    away and leaves only the recording.

    The original is left alone. This is a new item, so "that sounded wrong" is
    just deleting one file rather than having lost the video.
    """
    import av

    path = _safe_path(item_id)
    if MEDIA_SUFFIXES[path.suffix.lower()][0] != "video":
        raise GalleryError("only videos can have a voice added")

    with av.open(str(path)) as probe:
        seconds = (probe.duration or 0) / 1e6
    if seconds <= 0:
        raise GalleryError("that video has no length")

    mixed = _mixed(path, audio_bytes, seconds, keep_original)
    if mixed.shape[1] == 0:
        raise GalleryError("that recording has no sound in it")

    name = _with_new_audio(path, mixed, "voice", {
        # Its own kind: it costs no GPU time, so it should not count against
        # their daily video limit.
        "kind": "voice",
        "voice_of": item_id,
        "kept_original_sound": bool(keep_original),
    })
    log.info("added a voice track to %s as %s (%.1fs, kept original sound: %s)",
             item_id, name, mixed.shape[1] / VOICE_RATE, keep_original)
    return name


# --- a sound effect dropped into a video ------------------------------------

# How far the video's own sound drops under an effect. Lighter than the duck
# used for their voice: a boing has to land on top of the music, not replace it.
SOUND_DUCK = 0.55


def add_sound(item_id: str, effect_id: str, at_seconds: float = 0.0,
              replace: bool = False) -> str:
    """One of the little sound effects, mixed into a video at a moment.

    `at_seconds` may also be one of "start", "middle", "end", for a sound
    chosen before the video existed, when a number of seconds meant nothing.
    """
    import av
    import numpy as np

    from . import sounds

    path = _safe_path(item_id)
    if MEDIA_SUFFIXES[path.suffix.lower()][0] != "video":
        raise GalleryError("only videos can have a sound added")
    try:
        effect = sounds.render(effect_id)
    except KeyError as exc:
        raise GalleryError("no such sound") from exc

    with av.open(str(path)) as probe:
        seconds = (probe.duration or 0) / 1e6
    if seconds <= 0:
        raise GalleryError("that video has no length")

    total = int(seconds * VOICE_RATE)
    original = _pcm(str(path), seconds)
    if original.shape[1] == 0:
        original = np.zeros((2, total), dtype="float32")

    if at_seconds in ("start", "middle", "end"):
        length = effect.shape[1] / VOICE_RATE
        at_seconds = {"start": 0.15, "middle": max(0.0, seconds / 2 - length / 2),
                      "end": max(0.0, seconds - length - 0.15)}[at_seconds]
    start = max(0, min(int(float(at_seconds) * VOICE_RATE), max(0, total - 1)))
    take = min(effect.shape[1], total - start)
    if take <= 0:
        raise GalleryError("that moment is past the end of the video")

    # Duck the video underneath, with the step smoothed into a fade - a hard
    # multiply on and off is audible as a click on either side of the effect.
    gain = np.ones(total, dtype="float32")
    gain[start:start + take] = SOUND_DUCK
    window = np.ones(int(VOICE_RATE * 0.04), dtype="float32")
    gain = np.convolve(gain, window / window.sum(), mode="same").astype("float32")

    mixed = original * gain
    mixed[:, start:start + take] += effect[:, :take]
    peak = float(np.abs(mixed).max()) if mixed.size else 0.0
    if peak > 1.0:
        mixed /= peak

    extra = {"effect": effect_id, "effect_at": round(start / VOICE_RATE, 2)}
    if not replace:
        # Like a voice-over: no GPU time, so not one of their daily videos.
        extra.update({"kind": "sound", "sound_of": item_id})
    name = _with_new_audio(path, mixed, "sound", extra, replace=replace)
    log.info("put a %r into %s at %.1fs as %s", effect_id, item_id,
             start / VOICE_RATE, name)
    return name


# --- the story maker's last step: their song under their film --------------------

# How far the film's own sound sits under the song. A film LTX rendered has
# music, effects and a spoken line in it; the song is the soundtrack now, but
# throwing the rest away would lose the line their character says. Lighter than
# the voice duck (0.22) and lighter than a sound effect's (0.55) because this
# one is on for the whole film rather than for a word or a boing.
SONG_UNDER = 0.25


def add_song(item_id: str, song_id: str, keep_original: bool = True,
             story_of: dict | None = None) -> str:
    """The last step of a story: their film with their song as its soundtrack.

    A new item of its own - `kind: "storyfilm"` - rather than a rewrite of the
    film, so the film and the song both survive their deciding they liked them
    better apart. It is `_with_new_audio` like the voice-over and the sound
    effects: the pictures are remuxed packet for packet, and only the audio is
    built, so this costs no GPU and loses not one bit of the film.

    The song is truncated to the film's length. Audio running past the last
    frame confuses some players and helps nobody - and the song is asked for at
    the film's length in the first place, so the trim is usually a fraction of
    a second of tail.
    """
    import av

    path = _safe_path(item_id)
    song = _safe_path(song_id)
    if MEDIA_SUFFIXES[path.suffix.lower()][0] != "video":
        raise GalleryError("only a video can have a song put under it")
    if MEDIA_SUFFIXES[song.suffix.lower()][0] != "audio":
        raise GalleryError("that is not a song")

    with av.open(str(path)) as probe:
        seconds = (probe.duration or 0) / 1e6
    if seconds <= 0:
        raise GalleryError("that video has no length")

    track = _pcm(str(song), seconds)
    if track.shape[1] == 0:
        raise GalleryError("that song has no sound in it")

    extra = {
        "kind": "storyfilm",
        "song_of": item_id,
        "song_id": song_id,
        "kept_original_sound": bool(keep_original),
    }
    if story_of:
        # What the whole story was made of, so the viewer can say where each
        # part came from and a reload can find them all again.
        extra["story_of"] = story_of
    name = _with_new_audio(path, track, "storyfilm", extra,
                           ratio=SONG_UNDER if keep_original else None)
    log.info("put song %s under film %s as %s (%.1fs, kept the film's sound: %s)",
             song_id, item_id, name, seconds, keep_original)
    return name


# --- a frame out of the middle of a video -----------------------------------

def frame_at(item_id: str, at_seconds: float) -> bytes:
    """The frame nearest `at_seconds`, as PNG.

    Seeks first and decodes forward from there, so pulling a frame out of the
    end of a fifteen-second clip does not mean decoding 360 frames to reach it.
    """
    import io

    import av

    path = _safe_path(item_id)
    if MEDIA_SUFFIXES[path.suffix.lower()][0] != "video":
        raise GalleryError("not a video")

    chosen = None
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        length = (container.duration or 0) / 1e6
        want = max(0.0, float(at_seconds))
        if length:
            want = min(want, max(0.0, length - 0.05))
        if container.duration:
            try:
                # A keyframe at or before the moment; decoding forward from
                # there is what actually lands on the right picture.
                container.seek(int(want * 1e6), backward=True, any_frame=False)
            except Exception:
                pass
        for frame in container.decode(stream):
            chosen = frame
            if frame.time is not None and frame.time >= want:
                break
    if chosen is None:
        raise GalleryError("no frames")

    out = io.BytesIO()
    chosen.to_image().save(out, "PNG")
    return out.getvalue()


# --- what a video is, before something is made out of it ---------------------

def video_facts(item_id: str) -> dict:
    """Length, frame rate, frame size and whether it has a soundtrack.

    All four are wanted before the interpolation graph can be built: the new
    frame rate is this one doubled, the length and the frame count decide
    whether it is allowed at all, and a clip with **no** audio stream must not
    have an audio wire in its graph - ComfyUI stops with an error they did
    nothing to cause. Read off the header, so it costs no decoding.
    """
    import av

    path = _safe_path(item_id)
    if MEDIA_SUFFIXES[path.suffix.lower()][0] != "video":
        raise GalleryError("not a video")
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        return {
            "seconds": round((container.duration or 0) / 1e6, 2),
            # A container with no rate at all would divide by nothing further
            # down; 24 is what everything this app makes comes out at.
            "fps": float(stream.average_rate or 24) or 24.0,
            "width": int(stream.codec_context.width),
            "height": int(stream.codec_context.height),
            "frames": int(stream.frames or 0),
            "sound": bool(container.streams.audio),
        }


# --- a sticker that moves ----------------------------------------------------
#
# A second of one of their videos, looping for ever. No GPU and no model: it is
# their own frames, fewer of them and smaller, which is the whole trick. Two
# seconds at twelve a second on a 320px side is about twenty-four small
# pictures - a file they can send somebody, where the clip it came from is
# megabytes.
#
# WebP rather than GIF: GIF is 256 colours and dithers a rendered video into
# mud, and every browser they will ever open this in has done animated WebP for
# years.

LOOP_MAX_SECONDS = 2.0
LOOP_FPS = 12
LOOP_SIDE = 320


def moving_sticker(item_id: str, at_seconds: float = 0.0,
                   seconds: float = LOOP_MAX_SECONDS) -> bytes:
    """A window of a video as a looping animated WebP."""
    import io

    import av
    from PIL import Image

    path = _safe_path(item_id)
    if MEDIA_SUFFIXES[path.suffix.lower()][0] != "video":
        raise GalleryError("only videos can become moving stickers")

    want = max(0.2, min(LOOP_MAX_SECONDS, float(seconds)))
    start = max(0.0, float(at_seconds))
    step = 1.0 / LOOP_FPS
    pictures: list = []

    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        length = (container.duration or 0) / 1e6
        if length:
            # Always leave something to loop over, wherever they put the slider.
            start = min(start, max(0.0, length - 0.3))
        try:
            container.seek(int(start * 1e6), backward=True, any_frame=False)
        except Exception:
            pass
        # Keep the frame nearest each twelfth of a second rather than thinning
        # afterwards: a 24fps clip then gives exactly every other frame and a
        # 30fps one gives an even-enough twelve, with no special case for
        # either. The clock is what matters, not the source's rate.
        due = start
        for frame in container.decode(stream):
            if frame.time is None or frame.time < start:
                continue
            if frame.time > start + want:
                break
            if frame.time + 1e-6 < due:
                continue
            picture = frame.to_image()
            picture.thumbnail((LOOP_SIDE, LOOP_SIDE), Image.LANCZOS)
            pictures.append(picture.convert("RGB"))
            due += step

    if len(pictures) < 2:
        raise GalleryError("not enough frames")

    out = io.BytesIO()
    pictures[0].save(out, "WEBP", save_all=True, append_images=pictures[1:],
                     duration=round(step * 1000), loop=0, quality=80, method=4)
    data = out.getvalue()
    log.info("made a moving sticker out of %s (%d frames from %.1fs, %d bytes)",
             item_id, len(pictures), start, len(data))
    return data


# --- turning a picture into a sticker ---------------------------------------
#
# Flood fill inwards from the edges and make everything it reaches transparent.
# That is the honest description of what this does, and it is why it works
# beautifully on "a hedgehog on a plain blue background" and not at all on a
# forest scene: there is no subject-detection model here, only "the background
# is whatever touches the edge and looks like the edge".
#
# The fill is repeated dilation in numpy rather than a per-pixel queue in
# Python - each pass is four array shifts - and it runs on a downscaled copy,
# so a picture that would take the best part of a minute pixel by pixel takes
# a few milliseconds.

STICKER_WORK_SIDE = 320      # the mask is computed at this size and scaled up
STICKER_PASSES = 900         # a cap, not a target; it stops when nothing grows
# Tried in order, and the *first* one that clears the edge wins: a bigger
# tolerance always removes more, and the extra it removes is the subject.
STICKER_TOLERANCES = (22.0, 30.0, 40.0, 52.0, 66.0, 82.0, 100.0)
# The test for "did this work" is how much of the picture's own border the fill
# reached, not how much of the picture it removed. Measured across a plain
# background, a gradient and two real photos, that is the line that separates
# them cleanly: a subject on a plain background clears 100% of the border at
# the very first tolerance, and a photo of a room never gets past 79% at any of
# them. Total area removed is not that signal - a busy photo happily gives up
# a third of itself and still looks half-eaten.
STICKER_MIN_EDGE = 0.90
# And a floor: nothing was cut, so it is not a sticker. There is deliberately
# no ceiling on the proportion removed - a duck on a plain white background is
# 95% background, and that is the *ideal* case for this, not a failure. What
# actually catches "the subject went with the background" is the empty bounding
# box below, which is the honest test for it.
STICKER_MIN_REMOVED = 0.04
# What is left has to be an object, not the whole frame with holes in it.
# Measured: a subject on a plain background keeps 16-23% of the frame, while a
# photo of a room whose walls happen to be uniform keeps 80%. 0.72 sits in the
# gap with room to spare either side.
STICKER_MAX_KEPT = 0.72


def _cutout_alpha(image, tolerance: float):
    """(alpha mask at working size, fraction removed, fraction of border removed)."""
    import numpy as np
    from PIL import Image

    work = image.convert("RGB")
    scale = STICKER_WORK_SIDE / max(work.size)
    if scale < 1:
        work = work.resize(
            (max(1, round(work.width * scale)), max(1, round(work.height * scale))),
            Image.BILINEAR,
        )
    arr = np.asarray(work, dtype="float32")
    height, width = arr.shape[:2]

    border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    background = np.median(border, axis=0)
    similar = np.sqrt(((arr - background) ** 2).sum(axis=2)) < tolerance

    reach = np.zeros((height, width), dtype=bool)
    reach[0] = similar[0]
    reach[-1] = similar[-1]
    reach[:, 0] = similar[:, 0]
    reach[:, -1] = similar[:, -1]
    for _ in range(STICKER_PASSES):
        grown = reach.copy()
        grown[1:] |= reach[:-1]
        grown[:-1] |= reach[1:]
        grown[:, 1:] |= reach[:, :-1]
        grown[:, :-1] |= reach[:, 1:]
        grown &= similar
        if np.array_equal(grown, reach):
            break
        reach = grown

    edge = float(
        np.concatenate([reach[0], reach[-1], reach[:, 0], reach[:, -1]]).mean()
    )
    alpha = np.where(reach, 0, 255).astype("uint8")
    return Image.fromarray(alpha, "L"), float(reach.mean()), edge


def sticker(item_id: str) -> bytes:
    """A picture with its background taken out, cropped in, as a PNG with alpha.

    Raises GalleryError with a reason worth showing them when the picture is not
    one this can work on.
    """
    import io

    from PIL import Image, ImageFilter

    path = _safe_path(item_id)
    if MEDIA_SUFFIXES[path.suffix.lower()][0] != "image":
        raise GalleryError("only pictures can become stickers")

    with Image.open(path) as opened:
        opened.load()
        full = opened.convert("RGBA")

    best = None
    for tolerance in STICKER_TOLERANCES:
        mask, removed, edge = _cutout_alpha(full, tolerance)
        if edge >= STICKER_MIN_EDGE:
            best = (mask, removed, edge, tolerance)
            break
    if best is None:
        raise GalleryError("busy background")
    mask, removed, edge, tolerance = best
    if removed < STICKER_MIN_REMOVED:
        raise GalleryError("busy background")

    # Up to full size and softened, so the edge is a cut rather than a staircase.
    mask = mask.resize(full.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.4))
    full.putalpha(mask)

    # Crop in to what is left - a sticker with half a picture of empty space
    # around it is not a sticker.
    box = mask.point(lambda v: 255 if v > 12 else 0).getbbox()
    if not box:
        raise GalleryError("nothing left")
    # And if what is left still fills the frame, the cut found a wall behind a
    # room rather than an object on a background. The border test lets that
    # through - the border really was uniform - but the result is a picture
    # with holes in it, not a sticker, so it is refused here instead.
    if (box[2] - box[0]) * (box[3] - box[1]) > full.width * full.height * STICKER_MAX_KEPT:
        raise GalleryError("busy background")
    pad = max(4, round(max(full.size) * 0.012))
    full = full.crop((
        max(0, box[0] - pad), max(0, box[1] - pad),
        min(full.width, box[2] + pad), min(full.height, box[3] + pad),
    ))

    out = io.BytesIO()
    full.save(out, "PNG", optimize=True)
    log.info("cut a sticker out of %s (tolerance %.0f, %.0f%% removed, %.0f%% of the edge)",
             item_id, tolerance, removed * 100, edge * 100)
    return out.getvalue()


# --- anything the app itself makes out of something else --------------------

def save_derived(data: bytes, kind: str, meta: dict | None = None,
                 suffix: str = ".png") -> str:
    """Keep something made *from* another item - a sticker, a grabbed frame.

    Named by us rather than by ComfyUI, so there is no collision with its
    numbering and no reuse of the name after a delete.
    """
    meta = meta or {}
    name = name_for(kind, suffix, idea=str(meta.get("idea") or ""),
                    who=str(meta.get("who") or _who_id()))
    path = GALLERY_DIR / name
    path.write_bytes(data)
    record = owned({"kind": kind, "prompt": "", "idea": "", "created": time.time()})
    record.update(meta)
    _write_sidecar(path, record)
    log.info("kept %s (%s, %d bytes)", name, kind, len(data))
    return name


# --- their own banner ---------------------------------------------------------

def _custom_dir() -> Path:
    path = STATE_DIR / CUSTOM_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def banner_path() -> Path | None:
    """Their banner, if they have chosen one. None means the one that ships."""
    path = STATE_DIR / CUSTOM_DIR_NAME / BANNER_NAME
    return path if path.is_file() else None


def set_banner(item_id: str) -> None:
    """Use one of their own pictures as the banner.

    Cover-cropped to the slot rather than letterboxed: the page draws this
    behind the title at a fixed aspect, and a picture with bars on it looks
    like a mistake in a way a crop does not. A video's poster frame is used,
    so "that one" works for anything in their gallery.
    """
    from PIL import Image

    source = still(item_id) or path_for(item_id)
    with Image.open(source) as img:
        img = img.convert("RGB")
        want_w, want_h = BANNER_SIZE
        scale = max(want_w / img.width, want_h / img.height)
        wide = img.resize((max(want_w, round(img.width * scale)),
                           max(want_h, round(img.height * scale))),
                          Image.LANCZOS)
        left = (wide.width - want_w) // 2
        # Off centre vertically, the way the shipped one is: faces and
        # subjects sit above the middle far more often than below it.
        top = max(0, min(wide.height - want_h, round((wide.height - want_h) * 0.42)))
        wide.crop((left, top, left + want_w, top + want_h)).save(
            _custom_dir() / BANNER_NAME, "PNG", optimize=True)
    log.info("banner set from %s", item_id)


def clear_banner() -> bool:
    """Put the one that ships back. True if there was one to remove."""
    path = STATE_DIR / CUSTOM_DIR_NAME / BANNER_NAME
    try:
        path.unlink()
        log.info("banner put back to the one that ships")
        return True
    except FileNotFoundError:
        return False


# --- what the screen refused, for a parent to look at -----------------------

def _refused_dir() -> Path:
    return GALLERY_DIR / REFUSED_DIR_NAME


def save_refused(png: bytes) -> str:
    import uuid

    _refused_dir().mkdir(exist_ok=True)
    name = f"refused_{time.strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:6]}.png"
    (_refused_dir() / name).write_bytes(png)
    return name


def refused_listing() -> list[dict]:
    d = _refused_dir()
    if not d.is_dir():
        return []
    items = []
    for path in d.glob("refused_*.png"):
        try:
            st = path.stat()
        except OSError:
            continue
        items.append({"id": path.name, "when": st.st_mtime, "bytes": st.st_size})
    items.sort(key=lambda i: i["when"], reverse=True)
    return items


def refused_path(item_id: str) -> Path:
    if not item_id.startswith("refused_") or "/" in item_id or "\\" in item_id or ".." in item_id:
        raise GalleryError("bad id")
    path = (_refused_dir() / item_id).resolve()
    if path.parent != _refused_dir().resolve() or not path.is_file():
        raise GalleryError("not found")
    return path


def allow_refused(item_id: str) -> str:
    """A parent overrode the screen: it becomes an ordinary upload."""
    path = refused_path(item_id)
    new_id = save_upload(path.read_bytes(), "camera")
    path.unlink()
    return new_id


def drop_refused(item_id: str) -> None:
    refused_path(item_id).unlink()


# --- the things they have written ---------------------------------------------
#
# Kept beside the media rather than in the browser, so it follows them from the
# iPad to a laptop and survives clearing the browser. Their own words only - the
# composed prompt with the style phrases on the end is not something anyone
# wants to read back.

HISTORY_FILE = ".prompts.json"
HISTORY_PER_KIND = 30
# The only lists there are. Anything else is not a list we ever write, so
# it is not a list anyone can ask us to forget either.
HISTORY_KINDS = ("image", "video", "comic", "music")


def _history_path() -> Path:
    """Their own "things I've asked for before". The adopting profile keeps the
    file that already exists; anyone added later gets their own, the way the
    settings do - a sibling's typed ideas are not a shelf to browse."""
    who = _settings_owner(None)
    return STATE_DIR / (f".prompts-{who}.json" if who else HISTORY_FILE)


def _history() -> dict:
    try:
        data = json.loads(_history_path().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def remember_prompt(kind: str, idea: str) -> None:
    """Add one of their ideas to the list, newest first. Never fatal."""
    idea = " ".join((idea or "").split())[:300]
    if not idea:
        return
    bucket = {"image": "image", "t2v": "video", "i2v": "video", "flf": "video",
              "comic": "comic", "story": "video", "music": "music",
              # One list of typed ideas for all three kinds of sound: they
              # come out of the same box on the same card, and splitting them
              # would mean "things I've asked for before" forgetting what they
              # typed the moment they changed the chip.
              "jingle": "music", "ambience": "music"}.get(kind)
    if bucket is None:
        return
    try:
        data = _history()
        items = [i for i in data.get(bucket, []) if isinstance(i, str)]
        # Same idea twice just moves it back to the top rather than repeating.
        items = [i for i in items if i.lower() != idea.lower()]
        data[bucket] = ([idea] + items)[:HISTORY_PER_KIND]
        _history_path().write_text(json.dumps(data, indent=1))
    except OSError as exc:
        log.warning("could not remember that prompt: %s", exc)


def prompt_history() -> dict:
    data = _history()
    return {k: [i for i in data.get(k, []) if isinstance(i, str)][:HISTORY_PER_KIND]
            for k in HISTORY_KINDS}


def forget_prompts(kind: str = "", idea: str = "") -> dict:
    """Clear one entry, one whole list, or the lot.

    An entry at a time is the one they will actually use: the list is things they
    typed, and something they have gone off should be removable without throwing
    away everything else they have written.
    """
    # A name we never write to is nothing to forget, and one entry without a
    # list to take it out of is not an instruction we can carry out - saying so
    # beats guessing, because the only guess available here is "then wipe the
    # lot", which is the one outcome they would never have meant.
    if kind and kind not in HISTORY_KINDS:
        return prompt_history()
    if idea and not kind:
        return prompt_history()
    try:
        if idea:
            wanted = " ".join(idea.split()).lower()
            data = _history()
            data[kind] = [
                i for i in (data.get(kind) or [])
                if isinstance(i, str) and i.lower() != wanted
            ]
        elif kind:
            data = {k: v for k, v in _history().items() if k != kind}
        else:
            data = {}
        _history_path().write_text(json.dumps(data, indent=1))
    except OSError as exc:
        log.warning("could not clear the prompt history: %s", exc)
    return prompt_history()


# --- settings and usage, for the parent page --------------------------------

def _stored(scope: str = "") -> dict:
    """One scope's rows, filtered to keys this version knows about.

    The filter is not decoration: a key left behind by an older version would
    otherwise turn up in `public_settings()` and on the parent page.
    """
    return {k: v for k, v in store.scope(scope).items() if k in DEFAULT_SETTINGS}


def get_settings(who: str | None = None) -> dict:
    """The household's settings, with one child's own laid over the top.

    Laid over rather than copied into: a setting nobody has touched for this
    child still follows the household default when a parent changes it, which
    is what "they have their own rules" has to mean if it is not to become "they have
    a frozen snapshot of the rules from the day they were added".

    `who` defaults to whoever the request belongs to. Pass "" for the
    household's own, which is what a parent editing the email wants.

    Cheap enough to call on the request path, which is where it is called from:
    the whole settings table is a few hundred small rows and app/store.py keeps
    it in memory until something writes.
    """
    who = _settings_owner(who)
    base = _stored("")
    if who:
        # Only the per-child keys from the child's scope. If a household key
        # ever got written there it would shadow the household's own, and one
        # child's page would be quietly deciding whether the nightly email
        # goes out.
        base = {**base, **{k: v for k, v in _stored(who).items()
                           if k in PER_CHILD}}
    return {**DEFAULT_SETTINGS, **base}


# Settings the browser has no business seeing. quiz_secret signs the daily
# pass cookie: hand it out and they can forge a pass instead of doing the sums.
PRIVATE_SETTINGS = ("quiz_secret",)


def flag(key: str, default: bool = False) -> bool:
    """A parent-page switch, as a bool.

    It used to be tri-state - -1 meant "whatever the environment said" - and
    every caller had to pass the environment's answer in. It does not any more:
    the environment seeds the row once and the row is the answer from then on,
    so `default` is only reached by a key that is missing or unreadable, which
    is a broken database rather than a configuration.
    """
    try:
        chosen = int(get_settings().get(key, -1))
    except (TypeError, ValueError):
        return default
    return default if chosen < 0 else bool(chosen)


def number(key: str, low: float | None = None, high: float | None = None) -> float:
    """A numeric setting, clamped. Falls back to the seeded default rather than
    to zero: a garbled row should not mean "no trash at all"."""
    fallback = float(DEFAULT_SETTINGS.get(key) or 0)
    try:
        value = float(get_settings().get(key, fallback))
    except (TypeError, ValueError):
        value = fallback
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def whole(key: str, low: int | None = None, high: int | None = None) -> int:
    return int(number(key, low, high))


def text(key: str) -> str:
    value = get_settings().get(key, DEFAULT_SETTINGS.get(key, ""))
    return value if isinstance(value, str) else str(value)


def trash_days() -> float:
    """How long the trash keeps something. A setting now, not TRASH_DAYS."""
    return number("trash_days", 0.0, 3650.0)


def public_settings(settings: dict | None = None) -> dict:
    """get_settings(), or a dict one of these functions just returned, with the
    private keys stripped. Anything that answers a route wants this."""
    current = get_settings() if settings is None else settings
    return {k: v for k, v in current.items() if k not in PRIVATE_SETTINGS}


# Filled in by profiles.py at import, so this module does not import it back.
# Empty until then, which means "everything is the household's" - the right
# behaviour for a version of the app with no profiles at all.
PER_CHILD: frozenset = frozenset()

# Also filled in by profiles.py. The profile that adopts the pre-profiles files
# *is* the household as far as settings go: its rules live in the "" scope,
# exactly where they lived before profiles existed. That is what keeps a
# one-child installation writing the one set of rows it always wrote, and what
# keeps the Telegram bot - which runs with nobody signed in - reading the same
# numbers the parent page just saved.
IS_ADOPTER = lambda pid: False   # noqa: E731


def _settings_owner(who: str | None) -> str:
    """Which scope a request's settings live in: "" for the household."""
    who = _who_id() if who is None else who
    return "" if not who or IS_ADOPTER(who) else who


def update_settings(who: str | None = None, **changes) -> dict:
    """Write some settings, each into the scope it belongs in.

    A change splits: the daily limits and the timetable go into this child's
    scope, the email address and the pause switch into the household's. Doing
    it by key rather than by caller is what stops a parent having to know which
    is which, and what stops a route accidentally giving one child their own
    copy of the SMTP settings.

    Both halves go in one transaction, so a crash in the middle cannot leave
    half a save behind. Raises `OSError` on a failure, which is what every
    caller already catches - see app/store.py.
    """
    who = _settings_owner(who)
    wanted = {k: v for k, v in changes.items()
              if k in DEFAULT_SETTINGS and v is not None}
    if who and PER_CHILD:
        buckets = {"": {k for k in wanted if k not in PER_CHILD},
                   who: {k for k in wanted if k in PER_CHILD}}
    else:
        buckets = {"": set(wanted)}
    rows: dict[str, dict] = {}
    for target, keys in buckets.items():
        if not keys:
            continue
        # Typed off the default, so a "3" from a form is stored as 3 and stays
        # 3 when it comes back out - JSON keeps types, unlike a form post.
        rows[target] = {key: type(DEFAULT_SETTINGS[key])(wanted[key])
                        for key in keys}
    # What each scope held before, so the log can say old → new. Read before
    # the write, obviously, and only for the scopes this save touches.
    was = {scope: dict(_stored(scope)) for scope in rows}
    store.write_many(rows)
    # This is the *only* place a setting is written, which is why the activity
    # log hangs off it rather than off the eleven routes that call it.
    for scope, values in rows.items():
        audit.settings_changed(scope, was.get(scope, {}), values)
    return get_settings(who)


def forget_settings(who: str) -> None:
    """Everything stored for one child, when the profile is removed."""
    if who:
        store.forget(who)


def drop_unknown_settings() -> int:
    """Delete stored rows that no key in `DEFAULT_SETTINGS` claims.

    A row can only get into the table through `update_settings`, which writes
    keys it knows and nothing else, so a key that is not in the defaults is one
    a previous version of this app had and this one does not. Nothing reads it
    again, but it is not harmless either: `public_settings()` would hand it to
    the browser, and the next backup would carry it forward for ever. The same
    rule `_clean_legacy` applies to a settings file coming in from disk, run
    once at startup against the table itself.

    The deployment scope is left alone - `app/config.py` owns its keys and
    knows its own names for them. Returns how many rows went, for the log.
    """
    from . import config

    gone = 0
    for scope in store.scopes():
        if scope == config.SCOPE:
            continue
        stale = [k for k in store.scope(scope) if k not in DEFAULT_SETTINGS]
        if not stale:
            continue
        try:
            store.forget(scope, stale)
        except OSError as exc:
            log.warning("could not tidy %d old setting(s) out of %s: %s",
                        len(stale), scope or "the household", exc)
            continue
        gone += len(stale)
    return gone


# --- moving in from the JSON files ------------------------------------------

def _clean_legacy(data, scope: str) -> dict:
    """One old settings file, as rows.

    Keys this version does not know are dropped, and so is any value still
    holding the old "ask the environment" sentinel - for the household because
    the seeded row says the same thing, for a child because falling through to
    the household is what it meant.
    """
    if not isinstance(data, dict):
        return {}
    out = {}
    for key, value in data.items():
        if key not in DEFAULT_SETTINGS:
            continue
        if scope and key not in PER_CHILD:
            continue
        if key in _LEGACY_UNSET and value == _LEGACY_UNSET[key]:
            continue
        try:
            out[key] = type(DEFAULT_SETTINGS[key])(value)
        except (TypeError, ValueError):
            continue
    return out


def migrate_settings() -> dict:
    """Move `.settings.json` and `.settings-<id>.json` into the database.

    Runs once, at startup, and only when the database has no settings at all -
    so a second start finds rows and does nothing. The files are **renamed**,
    never deleted: if any of this turns out to be wrong, the answer is still on
    disk beside the database.

    Returns `{scope: how many values}` for the log.
    """
    files = sorted(STATE_DIR.glob(".settings*.json"))
    if not files:
        return {}
    if not store.empty():
        # Already migrated, or settings were made here first. Leave the files
        # alone rather than guessing which of the two is the truth.
        return {}
    imported: dict[str, dict] = {}
    for path in files:
        scope = "" if path.name == SETTINGS_FILE else path.name[len(".settings-"):-len(".json")]
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            log.warning("settings: could not read %s to migrate it: %s", path.name, exc)
            continue
        rows = _clean_legacy(data, scope)
        if rows:
            imported[scope] = rows
    if imported:
        store.write_many(imported)
    for path in files:
        try:
            path.replace(path.with_suffix(".json.migrated"))
        except OSError as exc:
            log.warning("settings: could not rename %s after migrating it: %s",
                        path.name, exc)
    store.note("migrated_at", time.time())
    return {scope: len(rows) for scope, rows in imported.items()}


def seed_settings() -> list[str]:
    """Fill in every behavioural setting nobody has ever set.

    This is the one moment `.env` is read for any of them. After it, the row
    exists and the environment is never consulted again - which is the whole
    point of the exercise, and why `.env.example` says so over that half of it.
    """
    stored = store.scope("")
    missing = {key: DEFAULT_SETTINGS[key]
               for key in SEEDED_FROM_ENV if key not in stored}
    if missing:
        store.write("", missing)
    return sorted(missing)


def usage_today(everyone: bool = False) -> dict:
    """How many of each kind were made since local midnight.

    One child's by default, because that is what a daily limit counts against.
    The parent dashboard asks for `everyone`: "what happened today" is a
    question about the afternoon, not about one person.

    The trash counts too. A daily limit that a delete gives back is not a
    limit - it just teaches them to delete the ones they like least.

    The family shelf does not count. `listing()` leaves other children's shared
    work out unless it is asked for it, which is exactly why that parameter
    defaults to off: a sister putting a video on the shelf must not spend this
    child's videos for the day.
    """
    lt = time.localtime()
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    counts = {"image": 0, "t2v": 0, "i2v": 0, "flf": 0, "upload": 0, "movie": 0,
              "panel": 0, "music": 0, "jingle": 0, "ambience": 0,
              "edit": 0, "outpaint": 0, "inpaint": 0, "restyle": 0}
    for item in listing(everyone) + trash_listing(everyone):
        if item["created"] >= midnight and item["kind"] in counts:
            counts[item["kind"]] += 1
    counts["videos"] = counts["t2v"] + counts["i2v"] + counts["flf"]
    # A comic panel is a picture. It costs the same GPU time and it came out of
    # the same button, so it comes out of the same daily allowance - without
    # this, a picture limit was a limit on the Picture tab only and they could
    # make comics all day. Stickers, grabbed frames, voice-overs and sound
    # effects are deliberately *not* here: they spend no GPU time at all.
    # The three Klein edits are pictures too, and for the same reason: a model
    # invents a whole picture from their words. Leaving them out would have made
    # "change this picture" the way round a daily limit.
    counts["pictures"] = (counts["image"] + counts["panel"] + counts["edit"]
                          + counts["outpaint"] + counts["inpaint"]
                          + counts["restyle"])
    # Songs have their own limit: they cost GPU time like a picture does, but
    # nobody thinks of a song as one of their pictures. A little tune and a
    # background hum count against it too - same model, same graph, same
    # seconds of GPU - and leaving them out would have made the kind chooser
    # the way round the song limit.
    counts["songs"] = counts["music"] + counts["jingle"] + counts["ambience"]
    return counts


def _today_key() -> str:
    return time.strftime("%Y-%m-%d")


# (settings key for the limit, settings key for today's top-up, usage_today key)
ALLOWANCE_KINDS = {
    "image": ("daily_image_limit", "bonus_image", "pictures"),
    "video": ("daily_video_limit", "bonus_video", "videos"),
    "music": ("daily_music_limit", "bonus_music", "songs"),
}


def allowance() -> dict:
    """How many pictures and videos are left today.

    `left` is None when no limit is set, which is the difference between "no
    countdown to show" and "none left" - the page must not confuse the two.
    """
    settings = get_settings()
    used = usage_today()
    today = _today_key()
    out = {}
    for kind, (limit_key, bonus_key, used_key) in ALLOWANCE_KINDS.items():
        limit = int(settings.get(limit_key) or 0)
        bonus = int(settings.get(bonus_key) or 0) if settings.get("bonus_day") == today else 0
        spent = int(used.get(used_key) or 0)
        out[kind] = {
            "limit": limit,
            "bonus": bonus,
            "used": spent,
            "left": max(0, limit + bonus - spent) if limit else None,
        }
    return out


def grant_bonus(kind: str, extra: int) -> dict:
    """Give them a few more of one kind, today only."""
    if kind not in ALLOWANCE_KINDS:
        raise GalleryError("unknown kind")
    _, bonus_key, _ = ALLOWANCE_KINDS[kind]
    settings = get_settings()
    today = _today_key()
    changes = {"bonus_day": today}
    if settings.get("bonus_day") != today:
        # Yesterday's top-up does not carry over.
        changes["bonus_video"] = 0
        changes["bonus_image"] = 0
        changes["bonus_music"] = 0
        current = 0
    else:
        current = int(settings.get(bonus_key) or 0)
    changes[bonus_key] = max(0, min(500, current + int(extra)))
    update_settings(**changes)
    return allowance()


# Counts worth a little confetti. No streaks and no daily goals: these are for
# something they have already done, never a nudge to do more.
MILESTONES = {
    "image": [1, 10, 25, 50, 100, 250, 500],
    "video": [1, 5, 10, 25, 50, 100],
    "comic": [1, 5, 10, 25],
    "movie": [1, 5, 10],
}
MILESTONE_WORDS = {
    "image": "pictures", "video": "videos", "comic": "comics", "movie": "movies",
}


def _totals() -> dict:
    counts = {"image": 0, "video": 0, "comic": 0, "movie": 0}
    for item in listing() + trash_listing():
        kind = item.get("kind") or ""
        if kind in ("image", "panel"):
            counts["image"] += 1
        elif kind in ("t2v", "i2v", "flf"):
            counts["video"] += 1
        elif kind in counts:
            counts[kind] += 1
    return counts


def milestone_reached() -> dict | None:
    """The newest milestone they have just crossed, once.

    Checked after a job rather than counted up as it goes, so it stays right
    even for anything made outside the app - and recorded, so it is a moment
    and not a banner that reappears on every reload.
    """
    seen = set(get_settings().get("milestones_seen") or [])
    hit = None
    for kind, totals in _totals().items():
        for mark in MILESTONES.get(kind, []):
            key = f"{kind}:{mark}"
            if totals >= mark and key not in seen:
                seen.add(key)
                hit = {"kind": kind, "count": mark, "word": MILESTONE_WORDS[kind]}
    if hit is None:
        return None
    try:
        update_settings(milestones_seen=sorted(seen))
    except OSError as exc:
        log.warning("could not record the milestone: %s", exc)
    return hit


def disk_used_bytes() -> int:
    return space()["total"]


def space() -> dict:
    """Where the gallery's bytes have gone, and how much room is left.

    Broken down rather than totalled: "5 GB used" says nothing you can act on,
    but "videos are 90% of it" says which button to reach for.
    """
    import shutil

    out = {"pictures": 0, "videos": 0, "trash": 0, "other": 0, "total": 0,
           "free": 0, "disk": 0}
    if not available():
        return out

    trash = _trash_dir().resolve()
    for path in GALLERY_DIR.rglob("*"):
        try:
            if not path.is_file():
                continue
            size = path.stat().st_size
        except OSError:
            continue
        out["total"] += size
        kind = MEDIA_SUFFIXES.get(path.suffix.lower())
        if trash in path.parents:
            out["trash"] += size
        elif kind is None:
            out["other"] += size          # sidecars, posters, thumbnails
        elif kind[0] == "video":
            out["videos"] += size
        else:
            out["pictures"] += size

    try:
        usage = shutil.disk_usage(GALLERY_DIR)
        out["free"], out["disk"] = usage.free, usage.total
    except OSError:
        pass
    return out


def older_than(days: float, keep_favourites: bool = True) -> list[dict]:
    """Gallery items older than `days`, favourites left out by default."""
    cutoff = time.time() - days * 86400
    return [
        item for item in listing(everyone=True)
        if item["created"] < cutoff and not (keep_favourites and item["favourite"])
    ]


def cleanup(days: float, keep_favourites: bool = True) -> dict:
    """Move everything older than `days` to the trash.

    To the trash, not gone: a tidy-up is exactly the operation you want to be
    able to take back, and the janitor empties it a week later anyway.
    """
    doomed = older_than(days, keep_favourites)
    deleted, failed = delete_many([item["id"] for item in doomed])
    return {"moved": len(deleted), "failed": len(failed),
            "bytes": sum(i["bytes"] for i in doomed)}
