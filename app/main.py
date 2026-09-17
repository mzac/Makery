"""FastAPI app: three generate routes, a job registry, and result streaming.

Every /api/generate/* route runs safety.check_prompt() before anything reaches
ComfyUI. That check is the real content filter - the negative prompts are inert
at CFG 1.0. Never add a route that skips it.
"""

import asyncio
import hmac
import json
import logging
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from . import (
    audit, backup, branding, chat, characters, comic, config, digest,
    gallery,
    i18n, notify, pinbox, prompts, quiz,
    lockdown, modules, music, naming, profiles, restyles, safety, schedule,
    scripts,
    sounds, stats, styles,
    telegram, themes, timings, uploads, workflows,
)
from .comfy import ComfyClient, ComfyError
from .jobs import JobRegistry
from .gallery import GalleryError
from .uploads import UploadError

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# And then again from the parent page, which wins over `.env` - plus the clock,
# which has to be set before anything asks what day it is, and the filter that
# keeps credentials out of every log line. All three are app/config.py's, and
# this is as early as they can run: `gallery` is imported above, which is what
# points the settings store at STATE_DIR.
config.apply_startup()
config.install_log_filter()
log = logging.getLogger("makery")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def parent_pin() -> str:
    """The PIN that gates the parent page, and the grown-up box on the quiz
    overlay. Empty means neither is offered - see `_parent()`.

    A box on the Settings tab now, with `PARENT_PIN` in `.env` behind it, so it
    is read at the call rather than held from import - see app/config.py, and
    `parent_pin_change()` for what it takes to move it.
    """
    return config.parent_pin()

# Where the picture maker is. Read once, here, because this client holds a
# WebSocket open for progress and cannot be re-pointed underneath it - which is
# why `comfy_url` is the one address on the parent page marked as needing a
# restart.
COMFY_URL = config.value("comfy_url")
client = ComfyClient(COMFY_URL)
registry = JobRegistry(client)

# Crops for the source thumbnail, keyed by (id, version, orientation). A miss
# costs ~50ms of Pillow, so a handful are worth keeping - but each one is a
# whole PNG of a video frame, a megabyte or two, so the number of them is
# capped. Everything that puts one in goes through `_remember_preview`: the
# upload route used to write straight into the dict, which meant the "small and
# bounded" promise held for exactly one of the two ways in and the cache grew by
# a picture for every photo uploaded until the container was restarted.
PREVIEW_CACHE_MAX = 32
_preview_cache: dict[tuple, bytes] = {}


def _remember_preview(key: tuple, png: bytes) -> None:
    """Keep one crop, dropping the oldest if that is one too many."""
    _preview_cache.pop(key, None)
    while len(_preview_cache) >= PREVIEW_CACHE_MAX:
        _preview_cache.pop(next(iter(_preview_cache)))
    _preview_cache[key] = png


# Tasks nobody is awaiting. A reference has to be held somewhere or the garbage
# collector is entitled to take them mid-run, which is the documented footgun
# of asyncio.create_task and not a theoretical one.
_background: set = set()


def _fire(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)

MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
    ".opus": "audio/ogg",
    ".m4a": "audio/mp4",
}


COMFY_INPUT_DIR = Path(os.getenv("COMFY_INPUT_DIR", "/comfy-input"))
JANITOR_EVERY = 3600


@contextmanager
def _janitor_step(what: str):
    """One job in the hourly pass, which cannot take the rest down with it.

    The pass used to be a single try: the first step to raise skipped every
    step after it for the whole hour, and the one that raised most reliably was
    the first one. That meant no backup, no input sweep and no log trim, with
    one line in the log to say so.
    """
    try:
        yield
    except Exception:
        log.exception("janitor: %s failed", what)


async def _janitor() -> None:
    """Hourly: empty old trash, and sweep the frames left in ComfyUI's input dir.

    Every "Animate this" uploads a PNG into ComfyUI's *input* directory, which
    ComfyUI never cleans and they never see. Small, but it was unbounded.
    """
    while True:
        try:
            with _janitor_step("recovering notes"):
                # Anything that lost its notes - a container restarted
                # mid-render, a file dropped in by hand - gets them back from
                # the file itself.
                healed = gallery.recover_missing()
                if healed:
                    log.info("janitor: recovered the notes for %d file(s)", healed)
            with _janitor_step("emptying the trash"):
                gone = gallery.purge_trash()
                if gone:
                    log.info("janitor: emptied %d old items from the trash", gone)
            with _janitor_step("tonight's backup"):
                # One copy of everything a parent has decided, once a calendar
                # day, keeping the last few. Cheap - a few hundred kilobytes -
                # and it is the only thing in the state directory that cannot
                # be made again from the media.
                made = backup.nightly()
                if made:
                    log.info("janitor: tonight's backup is %s", made.name)
            with _janitor_step("sweeping ComfyUI's input dir"):
                # 0 hours means "leave them alone", which is what the parent
                # page promises. Taken literally it is a cutoff of *now*,
                # which sweeps every frame there including the one the render
                # in flight is about to read - the one setting that was
                # supposed to turn the sweep off was the most destructive
                # value it could hold.
                sweep_hours = gallery.number("input_sweep_hours", 0.0, 8760.0)
                if sweep_hours > 0 and COMFY_INPUT_DIR.is_dir():
                    cutoff = time.time() - sweep_hours * 3600
                    swept = 0
                    # Any suffix, not only .png: "make it smooth" leaves an mp4
                    # there, and a glob that only knew about pictures would have
                    # left every one of those behind for ever.
                    # Two prefixes, not one. Everything this app uploads is
                    # named `makery-*`; every frame left behind before the
                    # rename is `easy-iv-gen-*`, and a sweep that stopped
                    # matching those would leave them in ComfyUI's input
                    # directory for ever. Both are ours - nothing else writes
                    # either - so the old one stays here until that directory
                    # has aged out.
                    for path in [*COMFY_INPUT_DIR.glob("makery-*"),
                                 *COMFY_INPUT_DIR.glob("easy-iv-gen-*")]:
                        try:
                            if path.stat().st_mtime < cutoff:
                                path.unlink()
                                swept += 1
                        except OSError as exc:
                            log.warning("janitor: could not remove %s: %s", path.name, exc)
                    if swept:
                        log.info("janitor: swept %d old frames from ComfyUI's input dir", swept)
            with _janitor_step("trimming the activity log"):
                # The activity log's own age limit, which is off by default.
                audit.trim()
        except Exception:  # the janitor must never die
            log.exception("janitor pass failed")
        await asyncio.sleep(JANITOR_EVERY)


def _busy_now() -> dict | None:
    """What is rendering right now, as plain numbers. Handed to telegram.py so
    a question asked mid-render can be answered without loading a model on top
    of one."""
    job = registry.active()
    if job is None:
        return None
    return {
        "kind": job.kind,
        "media": job.media,
        "percent": round(job.progress * 100),
    }


# Whether ComfyUI can see the music model. Read once at startup with everything
# else, and used to hide the Music tab rather than let them tap Go and get a
# ComfyUI error - the same way the Chat tab hides when its model is not pulled.
# None means "not asked yet", which reads as available: the check runs two
# seconds in and they should not lose a tab to a race with it.
_music_ready: bool | None = None


def music_ready() -> bool:
    return _music_ready is not False


async def _check_models() -> None:
    """Compare the model filenames in the workflows against what ComfyUI has.

    In the background: /object_info is about a megabyte and ComfyUI may still
    be starting. Nothing here can fail the app - a missing model is a line in
    the log, not a refusal to run, because the picture half may be fine while
    the video half is still downloading.
    """
    try:
        await asyncio.sleep(2)
        info = await client.object_info()
        missing = workflows.missing_models(info)
        if info:
            global _music_ready
            music_models = set(workflows.wanted_models(workflows.MUSIC_FILE))
            _music_ready = not (music_models & set(missing))
            if not _music_ready:
                log.warning("the music tab is hidden: ComfyUI cannot see %s",
                            ", ".join(sorted(music_models & set(missing))))
        if not info:
            log.info("could not read ComfyUI's model list; not checking")
        elif missing:
            log.warning(
                "ComfyUI cannot see %d model file(s) the workflows want: %s. "
                "Renders needing them will fail - see \"The models ComfyUI "
                "needs\" in the README.",
                len(missing), ", ".join(missing))
        else:
            log.info("every model the workflows want is there (%d file(s))",
                     len(workflows.wanted_models()))
    except Exception:
        log.debug("the model check did not run", exc_info=True)


async def _check_helpers() -> None:
    """Say at startup if a helper is pointed at a model Ollama has not got.

    A parent chooses these from a list of what is installed, so the usual way
    to get here is that somebody has since deleted the model - or typed a name
    into the database by hand. Either way the row goes back to what `.env`
    seeded it with, loudly, rather than being left to fail on their first tap.

    An Ollama that does not answer is not evidence of anything: it may still be
    starting. Nothing is changed unless it answered and the model was genuinely
    absent, and nothing here can fail the app.
    """
    try:
        await asyncio.sleep(2)
        wanted = {r["id"]: _ROLE_MODEL[r["id"]]() for r in ROLES}
        answered, have = await scripts.installed(set(wanted.values()))
        if not answered:
            log.info("could not ask Ollama which models it has; not checking")
            return
        back = {}
        for role in ROLES:
            name = wanted[role["id"]]
            if name in have:
                continue
            seed = _ROLE_SEED[role["id"]]() or scripts.SEED_MODEL
            log.warning(
                "%s is set to \"%s\", which Ollama has not got. Falling back "
                "to \"%s\" - pull the one you want (`ollama pull %s`) and "
                "choose it again on the parent page.",
                role["label"], name, seed, name)
            back[role["key"]] = _ROLE_SEED[role["id"]]()
        if back:
            gallery.update_settings(**back)
    except Exception:
        log.debug("the helper model check did not run", exc_info=True)


# The three paths, which are the only settings nothing but the environment can
# answer: compose has to know them before there is an app to ask, so they are
# read here and nowhere else. Everything else a parent can decide is either a
# row in state.db or one of app/config.py's deployment values, and both of
# those have a control on the parent page - see "Where settings live" in
# makery/CLAUDE.md. Each of these has a default that is right on the
# machine this was written for and a guess anywhere else, so a missing one is
# worth a line in the log rather than a mystery on their first tap.
DEPLOYMENT = (
    ("GALLERY_DIR", "where ComfyUI writes; the gallery is read straight out of it"),
    ("STATE_DIR", "where state.db, their characters and the backups live"),
    ("COMFY_INPUT_DIR", "ComfyUI's input directory, for the janitor's sweep"),
)


def _check_deployment() -> None:
    """Say at startup what nobody has set, and where each address came from.

    Not fatal - every one of them has a default, and all three of the paths are
    set by the compose file rather than by `.env` - but an app talking to a
    ComfyUI at an address nobody chose should say so once, at the top of the
    log, rather than after the first render fails.
    """
    missing = [(name, what) for name, what in DEPLOYMENT
               if not (os.getenv(name) or "").strip()]
    for name, what in missing:
        log.warning("%s is not set (%s); using the built-in default", name, what)
    # The rest are app/config.py's: the page wins, then `.env`, then a default.
    # Said out loud at startup because "which of the two is in force" is the one
    # question an override layer makes it possible to get wrong. Never a value -
    # five of these nine are credentials.
    for row in config.public_state().values():
        unset = row["source"] == "default"
        built_in = row.get("default") or ""
        # Three ways of being unset, and only one of them is worth a warning.
        # An empty relay password or bot token is an ordinary way to run. A
        # key whose built-in default is already the right answer - the two
        # service addresses, the log level - does not need to be in `.env` at
        # all, and saying so invites somebody to add a line that changes
        # nothing. What is worth a warning is a key with nothing to fall back
        # on: no PIN means the parent page treats everyone as a grown-up.
        if not unset:
            where = ("set on the parent page" if row["source"] == "page"
                     else "from " + row["env"] + " in .env")
        elif row["optional"]:
            where = "not set, which is fine"
        elif built_in:
            where = "not set, so the built-in " + built_in
        else:
            where = "not set anywhere, and has no built-in default"
        say = log.warning if unset and not row["optional"] and not built_in else log.info
        say("%s (%s) is %s", row["env"], row["what"], where)
    # The one default that is a weaker answer than a value, rather than an
    # equally good one. Said last so it is the line left on the screen.
    if config.pin_is_default():
        log.warning(
            "the parent page is on the published default PIN - anybody who "
            "has read this project knows it. Change it on the parent page, "
            "under Settings, or set PARENT_PIN in .env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail at startup, not on their first tap, if a workflow file is unusable.
    workflows.preflight()
    # Their settings, characters and transcript belong to the app, not to
    # ComfyUI's output directory. Moves them across the first time STATE_DIR
    # is set, and does nothing at all when it is not.
    moved = gallery.prepare_state()
    if moved:
        log.info("moved %d thing(s) into %s", moved, gallery.STATE_DIR)
    # The settings live in state.db now. If the old JSON files are still there
    # and the database is empty, this is the first start after the change:
    # import them and rename the files to *.migrated, never delete them.
    try:
        imported = gallery.migrate_settings()
        for scope, count in sorted(imported.items()):
            log.info("settings: migrated %d value(s) for %s out of %s",
                     count, scope or "the household",
                     gallery.settings_file(scope))
        if imported:
            log.info("settings: the old files are kept beside the database "
                     "as *.json.migrated")
        # And fill in anything nobody has ever set, from .env. This is the one
        # moment those variables are read - see "Where settings live" in
        # makery/CLAUDE.md.
        seeded = gallery.seed_settings()
        if seeded:
            log.info("settings: seeded %d first-run default(s) from the "
                     "environment: %s", len(seeded), ", ".join(seeded))
        # And drop anything left in the table that this version has no setting
        # for. Last, so that neither the migration above nor `config`'s own
        # move out of the settings table can have a row taken from under it.
        dropped = gallery.drop_unknown_settings()
        if dropped:
            log.info("settings: tidied away %d row(s) this version has no "
                     "setting for", dropped)
            # Every other settings write goes in the log, and this one deletes
            # rows rather than changing them - so a parent reading the log
            # after an upgrade finds out where they went rather than finding
            # nothing at all. The names are not recorded: a key this version
            # does not know is one it cannot say anything useful about.
            audit.record("setting.tidied", audit.SYSTEM, rows=dropped)
    except OSError as exc:
        log.error("settings: could not prepare the database: %s", exc)
    _check_deployment()
    client.start()
    try:
        healed = gallery.recover_missing()
        if healed:
            log.info("recovered the notes for %d file(s) from their own metadata", healed)
    except Exception:
        log.exception("could not run the sidecar recovery")
    # Say up front if a model a workflow names is not one ComfyUI can see. The
    # alternative is that the first person to find out is a child tapping Go.
    _fire(_check_models())
    # And the same question of Ollama: a helper pointed at a model that is
    # not there falls back to the seed rather than failing on their first tap.
    _fire(_check_helpers())
    janitor = asyncio.create_task(_janitor(), name="janitor")
    sampler = asyncio.create_task(stats.sampler(), name="stats")
    mailer = asyncio.create_task(digest.scheduler(), name="digest")
    # Long-polls Telegram for a parent's questions. It is handed a callable
    # rather than importing the registry, which would be a circle.
    bot = asyncio.create_task(telegram.run(_busy_now), name="telegram")
    log.info("Makery up, ComfyUI at %s", COMFY_URL)
    if digest.settings()["configured"]:
        log.info("daily email to %s at %s", ", ".join(digest.recipients()),
                 digest.settings()["at"])
    log.info("the helpers: ideas %s, chat %s, telegram %s",
             scripts.model(), chat.model(), telegram.model())
    if telegram.possible():
        log.info("telegram questions %s",
                 "on" if telegram.enabled() else "off (the parent page)")
    yield
    bot.cancel()
    mailer.cancel()
    sampler.cancel()
    janitor.cancel()
    await client.aclose()


app = FastAPI(title="Makery", lifespan=lifespan, docs_url=None, redoc_url=None)

# Which child's page this is. A year, because a profile is not a session: the
# iPad in the kitchen is theirs and should still be theirs next month.
WHO_COOKIE = "who"
WHO_COOKIE_DAYS = 365


class WhoIsThis:
    """Put the signed-in profile where everything else can find it.

    A pure ASGI middleware and deliberately not `@app.middleware("http")`:
    that one runs `call_next` in its own task, and a ContextVar set outside it
    is not reliably visible inside. This wraps the app directly, so the
    variable is set in the very task the endpoint runs in.

    Everything per-child hangs off this - the settings, the gallery filter, the
    age the helper models are told about - which is what kept profiles from
    being an extra argument on sixty functions.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        try:
            pid = Request(scope).cookies.get(WHO_COOKIE, "")
            who = profiles.context(pid)
            person = profiles.get(who["id"]) or {}
        except Exception:   # pragma: no cover - a broken profiles file
            log.warning("could not work out whose page this is", exc_info=True)
            return await self.app(scope, receive, send)
        one = gallery.WHO.set(who)
        two = branding.CHILD.set({"name": person.get("name") or "",
                                  "age": person.get("age") or 0})
        # Which language they read. Whoever is at the screen chooses it in them
        # Settings tab and it lives in a cookie, not in a profile: two sisters
        # on one iPad may well not read the same one, and the person holding
        # it is the one who knows. Empty means nobody has said, and i18n falls
        # back to UI_LANG.
        three = i18n.LANG.set(i18n.from_cookie(Request(scope).cookies.get(i18n.COOKIE, "")))
        try:
            await self.app(scope, receive, send)
        finally:
            gallery.WHO.reset(one)
            branding.CHILD.reset(two)
            i18n.LANG.reset(three)


app.add_middleware(WhoIsThis)


class PromptIn(BaseModel):
    prompt: str = Field(default="", max_length=4000)
    # "Four at once": that many runs of the picture graph, one after another,
    # so each one can be shown the moment it lands.
    count: int = Field(default=1, ge=1, le=workflows.MAX_BATCH)
    # One of their saved characters, worked into the prompt by name and look.
    character: str = Field(default="", max_length=32)
    orientation: str = workflows.DEFAULT_ORIENTATION
    # {group id: choice id} from the style dropdowns; unknown ids are ignored.
    styles: dict[str, str] = Field(default_factory=dict)
    # "Make it again but..." hands back the seed the first one was drawn with,
    # so a changed word gives a variation on that picture rather than a new
    # one. Anything out of range is quietly replaced with a fresh seed.
    seed: int | None = Field(default=None, ge=0, le=workflows.MAX_SEED)
    # "A character" rather than "a picture": the same idea drawn alone on a
    # plain background, so the sticker cut-out actually works on it and the
    # vision model has nothing but the character to describe.
    cutout: bool = False


class VideoIn(PromptIn):
    # Clamped in workflows.clamp_duration; bounded here too so an absurd value
    # is rejected before it reaches the graph.
    # 0 means "the page did not say", which clamp_duration reads as the
    # default length. Not `default=workflows.DEFAULT_DURATION`: a Field
    # default is evaluated at import and that number is a setting now.
    duration: int = Field(default=0, ge=0, le=600)
    # What a character should say. LTX speaks dialogue that appears in double
    # quotes; this box exists so they do not have to know that trick.
    dialogue: str = Field(default="", max_length=300)
    # A sound effect to drop in once the video exists, and roughly where. They
    # used to have to go and find the video afterwards to add one.
    effect: str = Field(default="", max_length=32)
    effect_at: str = Field(default="start", max_length=8)
    # quick / normal / sharp - the ResolutionSelector's megapixel target. Sharp
    # caps the length server-side (workflows.QUALITY_MAX_SECONDS): more pixels
    # times more frames is what runs the card out of memory.
    quality: str = Field(default=workflows.DEFAULT_QUALITY, max_length=8)


class AnimateIn(VideoIn):
    source_job_id: str = ""
    source_gallery_id: str = ""
    # Which of "What kind of sound" the music card is set to, so Surprise me
    # does not spend an Ollama call writing lyrics for a background hum and
    # then throw them away. Only the music card ever sends it.
    sound_kind: str = Field(default=music.DEFAULT_KIND, max_length=20)   # anything in the gallery: a picture, a photo, a drawing, or a video's last frame


class ScriptIn(BaseModel):
    # "picture" wants a still described; "video" wants a shot with a line of
    # dialogue. Same button to them, different job.
    kind: str = "video"
    prompt: str = Field(default="", max_length=4000)
    # 0 means "the page did not say", which clamp_duration reads as the
    # default length. Not `default=workflows.DEFAULT_DURATION`: a Field
    # default is evaluated at import and that number is a setting now.
    duration: int = Field(default=0, ge=0, le=600)
    # If a picture is named, the helper looks at it and writes a prompt that
    # animates *that*, with their words (if any) as a steer.
    source_job_id: str = ""
    source_gallery_id: str = ""
    # Which of "What kind of sound" the music card is set to. "Surprise me" on
    # the Music tab reads it to decide whether there are words to invent at
    # all; the page has always sent it, and until it was declared here every
    # one of those taps was a 500.
    sound_kind: str = Field(default=music.DEFAULT_KIND, max_length=20)


async def _source_image_bytes(body) -> bytes | None:
    """The bytes of whichever picture the request names, or None if none."""
    if body.source_gallery_id:
        _require_mine(body.source_gallery_id)
        try:
            data, media = gallery.read_bytes(body.source_gallery_id)
            # "What happens next?": the helper looks at where the video ended.
            if media == "video":
                data = gallery.last_frame(body.source_gallery_id)
        except (GalleryError, OSError):
            raise HTTPException(status_code=400, detail=i18n.t("That one's gone. Pick another!"))
        return data
    if body.source_job_id:
        job = registry.get(body.source_job_id)
        if job is None or job.status != "done" or not job.result or job.is_video:
            raise HTTPException(status_code=400, detail=i18n.t("That picture isn't ready. Pick another!"))
        try:
            return await _result_bytes(job)
        except ComfyError:
            raise HTTPException(status_code=503, detail=i18n.t("Couldn't fetch that picture. Try again!"))
    return None


async def _result_bytes(job) -> bytes:
    """A finished job's file, from the gallery if it is there.

    It always is: the file is renamed to whatever the parent's pattern asks for
    the moment it lands (`jobs._name`), which means ComfyUI's `/view` no longer
    knows it by the name it wrote. The proxy is kept as the fallback for the
    one case that leaves the old name in place - a rename that could not
    happen.
    """
    try:
        return gallery.read_bytes(Path(job.result["filename"]).name)[0]
    except (GalleryError, OSError):
        return await client.fetch_view(job.result)


def _said(body) -> str:
    """Their spoken line, as it will be used.

    Its own function because the sidecar wants exactly what the prompt got: it
    is not in `idea` (that is only their description), and once it is in the
    prompt it is inside a sentence we wrote, so "make it again but..." could
    not get it back out again without guessing.
    """
    return getattr(body, "dialogue", "").strip().strip('"\u201c\u201d ')


async def _checked(body: PromptIn) -> str:
    """Safety-check their prompt, put it into English, and append the styles.

    The check runs on their own words, in whichever language they wrote them -
    the blocklist covers both. Translation happens *after* that and is checked
    again on the way out, because the translation is what reaches ComfyUI.
    The style phrases added last are a fixed list written in styles.py, so they
    cannot introduce anything the check would have caught.

    Their spoken line is deliberately **not** translated: if they want the
    character to say something in French, that is the point.
    """
    ok, message, category = safety.check_prompt(body.prompt)
    if not ok:
        log.info("prompt rejected (%s)", category)
        # "empty" and "length" are not somebody typing something they should
        # not - they left the box blank, or pasted a wall of text.
        if category not in ("empty", "length"):
            _fire(lockdown.refused("words", "the box they type their idea into",
                                   text=body.prompt))
        # In their language: `message` already came back from the filter in
        # whatever the switch in Settings says, so the only thing left to do
        # is honour what they *typed* when it disagrees - which is all there
        # was to go on before there was a switch.
        typed = scripts.detect(body.prompt)
        raise HTTPException(
            status_code=400,
            detail=safety.FRIENDLY_MESSAGES[typed]
            if typed and category not in ("empty", "length")
            else message,
        )

    text = body.prompt.strip()
    if scripts.looks_translatable(text):
        await _clear_card_for_ollama()
        try:
            text = await scripts.to_english(text)
        except scripts.ScriptError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    # Who is in it, before anything else: the rest of the sentence is about
    # them. The look was safety-checked when the character was saved.
    text = characters.in_prompt(text, getattr(body, "character", ""))
    dialogue = _said(body)
    if dialogue:
        ok, message, category = safety.check_prompt(dialogue)
        if not ok:
            log.info("dialogue rejected (%s)", category)
            # Reported like the idea box above it. It is the same filter, the
            # same child and the same typing; which of the two boxes it landed
            # in is a detail for the message, not a reason to tell nobody.
            if category not in ("empty", "length"):
                _fire(lockdown.refused("words", "the line the character says",
                                       text=dialogue))
            raise HTTPException(status_code=400, detail=message)
        if text.endswith("."):
            text = text[:-1]
        text = f'{text}. The main character says "{dialogue}".'
    if getattr(body, "cutout", False):
        return styles.compose_cutout(text, body.styles)
    if getattr(body, "banner", False):
        return styles.compose_banner(text, body.styles)
    return styles.compose(text, body.styles)


def _check_words(text: str, where: str) -> None:
    """The filter, and the report that goes with it, for a route with no
    `PromptIn` to hand to `_checked`.

    The comic and the film check their idea inside `comic.panels`/`comic.beats`
    instead, which raises a ScriptError the route cannot tell apart from the
    story helper being down - so those two refusals were answered to the child
    and reported to nobody: no audit row, no alert, and `close_on` never fired.
    This runs the same check up front and reports it exactly as `_checked`
    does. The check inside stays where it is as the second line of defence.

    "empty" and "length" are not somebody typing something they should not, so
    they are refused without an alert - same rule as everywhere else.
    """
    ok, message, category = safety.check_prompt(text)
    if ok:
        return
    log.info("prompt rejected (%s)", category)
    if category not in ("empty", "length"):
        _fire(lockdown.refused("words", where, text=text))
    raise HTTPException(status_code=400, detail=message)


UPLOAD_REFUSED = (
    "Let's use a different picture! That one isn't one we can animate here. "
    "Try a drawing, a toy, a pet, or a place."
)

# What the page may say an upload is. The badge, the shelf and the wording of a
# refusal come from it; the screening decision does not - see upload_photo().
UPLOAD_SOURCES = ("camera", "drawing", "card", "comic")

UPLOAD_WHERE = {
    "camera": "a photo from the camera roll",
    "drawing": "a picture from the drawing pad",
    "card": "a card made on the page",
    "comic": "a comic page made on the page",
}

BUSY_MESSAGE = (
    "One at a time! Wait for the one you're making now to finish, "
    "or tap Stop if you've changed your mind."
)


PAUSED_MESSAGE = "The factory is closed right now. Back soon!"

# How long before the timetable shuts it that they are warned. Long enough to
# finish a video (a 15s clip is about two minutes) and to start one more, short
# enough that it is not on the screen all afternoon.
CLOSING_SOON = 30
LIMIT_MESSAGE = {
    "image": "That's all the pictures for today - great work! Come back tomorrow.",
    "video": "That's all the videos for today - great work! Come back tomorrow.",
    "music": "That's all the songs for today - great work! Come back tomorrow.",
}


def _require_open() -> None:
    """Closed by the switch, or closed by the clock.

    Two different closures and two different signs. The switch means a grown-up
    shut it and only a grown-up opens it, so "back soon" is all that can
    honestly be said; the timetable knows exactly when it opens and says so.
    The switch is checked first because it is the exception: a parent who
    closes the factory at four o'clock on a Saturday means it.
    """
    if gallery.get_settings().get("paused"):
        raise HTTPException(status_code=503, detail=i18n.t(PAUSED_MESSAGE))
    when = schedule.state()
    if not when["open"]:
        raise HTTPException(status_code=503, detail=schedule.closed_message(when))


def _grownup(request: Request) -> bool:
    """Whether this request is a grown-up's rather than a child's.

    The same rule as the parent page itself: a correct PIN, or no PIN
    configured at all, which is how this app has always treated a LAN install.
    Used to let the parent page reach into any child's gallery - it sends the
    PIN with every call - without giving a sibling the same reach.

    Wrong guesses count towards the same lockout as `_parent()` and the
    grown-up box, for the same reason they do there: it is the same secret,
    and a check with no lockout beside checks that have one is simply the
    cheapest way to guess a four-digit PIN. A *missing* header is not a guess -
    the child's own page never sends one, and every call it makes about its own
    things would otherwise count - so only a wrong one does.

    **A correct one does not forgive**, which is the other half of the same
    thought and is new. This function is only ever reached through a header a
    browser holds and sends by itself; nobody types anything to get here, so
    there is nobody to say "they clearly know the PIN, forget the misses"
    about. See `_forgive()`.
    """
    if not parent_pin():
        return True
    given = request.headers.get("x-parent-pin", "")
    if not given:
        return False
    if pinbox.GATE.locked_for():
        # Locked out answers nothing, right or wrong: otherwise the lockout is
        # only a lockout for people who were going to fail anyway.
        return False
    if hmac.compare_digest(given, parent_pin()):
        return True
    _bad_pin(pinbox.GATE, "another child's gallery")
    return False


def _require_mine(item_id: str) -> None:
    """Theirs to build on. The make-something routes have no grown-up case -
    the parent page never renders - so this is the ownership half of
    `_may_change` without the PIN half.

    Without it a sibling who guesses a name (they are sequential) could animate
    another child's picture, grab a frame from their video or join their clips,
    and the result would be stamped as the sibling's own - a permanent copy
    behind the curtain.
    """
    if not gallery.belongs_to_me(item_id):
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone!"))


def _may_change(request: Request, item_id: str, trashed: bool = False) -> None:
    """Theirs to change, or a grown-up's.

    404 and not 403 on purpose: a sibling should not learn that a file exists
    by being told they may not touch it, and "that one's gone" is the wording
    every other missing item already uses.
    """
    if gallery.belongs_to_me(item_id, trashed) or _grownup(request):
        return
    raise HTTPException(status_code=404, detail=i18n.t("That one's gone!"))


def _gallery_item(item_id: str) -> dict:
    """The listing row for one id, or an empty dict.

    Everything that makes a new thing out of one of theirs copies the source's
    words onto it, so the viewer has something to show under the new file.
    """
    for item in gallery.listing():
        if item["id"] == item_id:
            return item
    return {}


def _require_module(name: str) -> None:
    """A maker a parent has switched off, or a machine cannot do.

    Checked on the route and not only in the page: hiding a tab is the
    friendly half, and this is the half that means reloading past it achieves
    nothing. Same split as the warm-up sums.
    """
    if not modules.enabled(name):
        raise HTTPException(
            status_code=403,
            detail=i18n.t(modules.OFF_MESSAGE.get(name, "That's switched off right now.")),
        )


def _require_warmed_up(request: Request) -> None:
    """Three sums first, once a calendar day.

    Checked here and not only in the page: the overlay is the friendly half,
    this is the half that means reloading past it does nothing.
    """
    if not _warmed_up(request):
        raise HTTPException(status_code=403, detail=quiz.friendly())


def _warmed_up(request: Request) -> bool:
    """Their own pass for today, or a grown-up who typed the PIN a moment ago."""
    return quiz.passed_today(
        request.cookies.get(quiz.COOKIE, ""),
        request.cookies.get(quiz.PARENT_COOKIE, ""),
    )


async def _require_budget(kind: str, want: int = 1) -> int:
    """A daily limit per kind, if the parent page has set one (0 = none).

    Returns how many they may actually have. Asking for four pictures with two
    left gets two, not a refusal: the limit is there to cap the day, not to
    punish them for tapping the wrong number.

    Running out also emails the grown-ups, once a day per kind, in the
    background - they must not wait on an SMTP handshake to be told no.
    """
    left = gallery.allowance()[kind]["left"]
    if left is None:
        return want
    if left <= 0:
        _fire(digest.limit_notice(kind))
        raise HTTPException(status_code=409, detail=i18n.t(LIMIT_MESSAGE[kind]))
    return min(want, left)


def _require_idle(request: Request) -> None:
    """One job at a time. A second would only queue behind the first anyway.

    The request is not optional: every caller is a make-something route, and an
    optional argument is an invitation to add one that quietly skips the sums.
    """
    _require_open()
    _require_warmed_up(request)
    running = registry.active()
    if running is not None:
        raise HTTPException(status_code=409, detail=i18n.t(BUSY_MESSAGE))


async def _started(
    kind: str,
    prompt: str,
    graph,
    duration: int | None = None,
    orientation: str = workflows.DEFAULT_ORIENTATION,
    chosen_styles: dict | None = None,
    idea: str = "",
    extra: dict | None = None,
    seed: int | None = None,
    seeds: list | None = None,
    character: str = "",
    cutout: bool = False,
    after=None,
    # Unset, so `jobs.after_share_for` decides it from the kind. A literal 1.0
    # here gave every finishing step a whole graph's slice of the bar and
    # stopped a jingle dead at 50%.
    after_share: float | None = None,
) -> dict:
    # Ollama and ComfyUI share one 16GB card and a video render peaks near
    # 15.5GB, so neither helper model may still be resident. Both, not just the
    # script one: the chat model is 7.6GB on its own.
    await scripts.release()
    await chat.release()
    # Their own words, so they can pick the idea up again later.
    gallery.remember_prompt(kind, idea)
    job = registry.create(
        kind, prompt, graph, duration, orientation, chosen_styles, idea, extra,
        seed=seed, seeds=seeds, character=character, cutout=cutout, after=after,
        after_share=after_share,
        # Whose it is, carried on the job: a video takes two minutes and the
        # request that asked for it is long gone by the time the file lands.
        who=(gallery.WHO.get() or {}).get("id") or "",
    )
    audit.record("render.started", id=job.id, kind=kind,
                 words=idea or prompt)
    return {"job_id": job.id}


@app.post("/api/generate/image")
async def generate_image(body: PromptIn, request: Request):
    # Gate first, *then* translate. _checked can spend an Ollama call and clear
    # ComfyUI's card off a French prompt, and doing that only to answer "one at
    # a time" made a busy tap cost twenty seconds of everyone's GPU.
    _require_idle(request)
    _require_module("picture")
    prompt = await _checked(body)
    count = await _require_budget("image", body.count)
    shape = body.orientation
    seed = workflows.pick_seed(body.seed)
    # Four at once is four graphs run in order, not one graph with a batch of
    # four: a batch comes out of the decoder all together, so there is nothing
    # to show until the whole thing is over. One at a time costs about four
    # times as long and they see each picture the moment it exists, which is
    # the trade they asked for.
    #
    # A seed each, one apart, so every one of the four is reproducible on its
    # own - "make it again, but..." on the third means the third.
    seeds = [(seed + i) % (workflows.MAX_SEED + 1) for i in range(count)]
    graphs = [workflows.build_image(prompt, shape, seed=s) for s in seeds]
    return await _started(
        "image", prompt, graphs,
        orientation=shape, chosen_styles=body.styles, idea=body.prompt.strip(),
        seed=seed, seeds=seeds, character=body.character, cutout=body.cutout,
    )


class BannerMakeIn(BaseModel):
    prompt: str = Field(default="", max_length=4000)
    styles: dict[str, str] = Field(default_factory=dict)
    # Read by _checked, which is where every prompt gets its final shape.
    banner: bool = True


@app.post("/api/generate/banner")
async def generate_banner(body: BannerMakeIn, request: Request):
    """A new strip for the top of their own page.

    An ordinary picture in every way that matters - same workflow, same word
    filter, same daily allowance, and it lands in their gallery like the rest.
    Only the shape is different, and the wording that keeps text out of it.
    They choose whether to use it once they have seen it.
    """
    _require_idle(request)
    _require_module("picture")
    prompt = await _checked(body)
    await _require_budget("image", 1)
    seed = workflows.pick_seed(None)
    return await _started(
        "image", prompt,
        workflows.build_image(prompt, seed=seed, size=workflows.BANNER_SIZE),
        chosen_styles=body.styles, idea=body.prompt.strip(), seed=seed,
        extra={"banner": True},
    )


class MusicIn(BaseModel):
    prompt: str = Field(default="", max_length=1000)
    # What is sung. Empty with singing on means they want a song but has not
    # written the words; the model is not asked to invent them at submit time,
    # because a surprise set of lyrics is not what Go is for - that is what
    # "Help me write it" is. It becomes an instrumental instead.
    lyrics: str = Field(default="", max_length=music.MAX_LYRIC_CHARS)
    singing: bool = True
    # Not `ge=`/`le=` off the module: those would be frozen at import, and
    # the bounds are a setting a parent can move. Clamped in the route instead.
    seconds: int = Field(default=0, ge=0, le=600)
    styles: dict[str, str] = Field(default_factory=dict)
    # Which of "What kind of sound" they chose. Not an enum off the module -
    # an unknown value is a page and a server that have drifted apart, and
    # `music.kind_of` answering "a song" is a better outcome than a 422 they
    # cannot do anything about.
    kind: str = Field(default=music.DEFAULT_KIND, max_length=20)


@app.post("/api/generate/music")
async def generate_music(body: MusicIn, request: Request):
    """One sound: what it sounds like, and - for a song - what is sung over it.

    Two boxes rather than one, so both go through the filter - the lyrics
    especially, because they are the half they will play to somebody.

    Three kinds share this route (`music.KINDS`): a song, a little tune and a
    background hum. They are one route and one daily allowance because they
    are one model, one graph and one cost; what differs is the tag line, the
    length and whether anything is sung. The *job* kind differs though, so
    their gallery can tell them apart - see `music.JOB_KIND`.
    """
    _require_idle(request)
    _require_module("music")
    if not music_ready():
        raise HTTPException(
            status_code=503,
            detail=i18n.t("The music maker isn't set up on this machine yet. "
                          "Everything else still works!"),
        )
    ok, message, category = safety.check_prompt(body.prompt)
    if not ok:
        log.info("song idea rejected (%s)", category)
        if category not in ("empty", "length"):
            _fire(lockdown.refused("words", "the box they type a song into",
                                   text=body.prompt))
        raise HTTPException(status_code=400, detail=message)

    kind = music.kind_of(body.kind)
    # The page hides the lyrics box for the two instrumental kinds; the server
    # does not take its word for it. A hum with a verse in it is not a hum.
    singing = bool(music.sings(kind) and body.singing and body.lyrics.strip())
    lyrics = music.tidy_lyrics(body.lyrics, singing)
    if singing:
        # The narrower list, not the picture one: "hanging" belongs to a sloth
        # in a tree as often as to anything else. See music.LYRIC_CATEGORIES.
        ok, category = music.check_lyrics(lyrics)
        if not ok:
            log.info("lyrics rejected (%s)", category)
            _fire(lockdown.refused("words", "the words to a song", text=lyrics))
            raise HTTPException(status_code=400, detail=safety.friendly_message())

    # One allowance for all three, and it stays keyed on "music": a hum and a
    # song cost the same GPU seconds, and a child who has used up their songs
    # has used up their sounds. The *job* kind below is the one that differs.
    await _require_budget("music", 1)
    seconds = music.clamp_for(kind, body.seconds)
    bpm = music.bpm_for(body.styles, kind)
    seed = workflows.pick_seed(None)
    tags = music.compose_tags(body.prompt, body.styles, singing, kind)
    graph = workflows.build_music(
        tags, lyrics, seconds, bpm, music.keyscale_for(body.styles),
        music.language_for(body.styles, lyrics) if singing else "en", seed,
    )
    return await _started(
        music.JOB_KIND[kind], tags, graph, duration=seconds,
        chosen_styles=body.styles, idea=body.prompt.strip(), seed=seed,
        after=_trim_after(kind),
        extra={"lyrics": lyrics, "singing": singing, "bpm": bpm,
               "sound_kind": kind},
    )


def _trim_after(kind: str):
    """Cut the silence off the end of an instrumental once it has landed.

    Only for the two instrumental kinds, and only when the tail is really
    silent - `gallery.trim_tail` measures before it cuts and does nothing when
    it is not sure. A song is left exactly as rendered: its tail is usually
    short, and a fade somebody wrote is not silence.

    Measured on this box over fourteen renders, the model stops playing a
    median of 3.0s before the file ends and once stopped 6.2s early. On a
    two-minute song that is nothing. On a ten-second jingle it is half of it.
    """
    if kind not in music.INSTRUMENTAL_KINDS:
        return None

    async def after(job, outputs: list) -> dict:
        name = Path(outputs[0]["filename"]).name
        try:
            seconds = await asyncio.to_thread(gallery.trim_tail, name)
        except Exception:
            log.exception("could not trim the end off %s", name)
            return {}
        # `duration` is what they asked for and what the timings are filed
        # under, so the measured length goes in beside it rather than over it.
        return {"played_seconds": seconds} if seconds else {}
    return after


class SongWordsIn(BaseModel):
    prompt: str = Field(default="", max_length=1000)
    styles: dict[str, str] = Field(default_factory=dict)


@app.post("/api/song-words")
async def song_words(body: SongWordsIn):
    """"Help me write it", for a song: the sound and the words in one answer."""
    await _clear_card_for_ollama()
    try:
        return await music.write(body.prompt, body.styles)
    except scripts.ScriptError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class ComicIn(BaseModel):
    prompt: str = Field(default="", max_length=1000)
    panels: int = Field(default=4, ge=comic.MIN_PANELS, le=comic.MAX_PANELS)
    character: str = Field(default="", max_length=32)
    styles: dict[str, str] = Field(default_factory=dict)


@app.post("/api/generate/comic")
async def generate_comic(body: ComicIn, request: Request):
    """A story in panels: the model writes them, ComfyUI draws them.

    Counted against the picture limit, because that is what they are - and
    trimmed to what is left rather than refused, so a four-panel comic with
    three pictures left becomes a three-panel comic.
    """
    _require_idle(request)
    _require_module("comic")
    _check_words(body.prompt, "the box the comic idea goes in")
    wanted = await _require_budget("image", body.panels)
    if wanted < comic.MIN_PANELS:
        # Not LIMIT_MESSAGE: they may well have one or two pictures left, and
        # "that's all the pictures for today" would be untrue.
        raise HTTPException(
            status_code=409,
            detail=i18n.t("A comic needs at least {min} pictures and you haven't "
                          "got that many left today. Try a single picture!",
                          min=comic.MIN_PANELS),
        )

    await _clear_card_for_ollama()
    try:
        story = await comic.panels(
            characters.in_prompt(body.prompt, body.character), wanted
        )
    except scripts.ScriptError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Their style choices go into every panel, which is the other half of why
    # the panels look like one strip rather than six unrelated pictures.
    graphs = [
        workflows.build_image(
            comic.panel_prompt(story["look"], panel["scene"], body.styles), "square"
        )
        for panel in story["panels"]
    ]
    log.info("comic: %d panels for %r", len(graphs), body.prompt.strip()[:60])
    return await _started(
        "comic",
        " / ".join(p["scene"] for p in story["panels"]),
        graphs,
        orientation="square",
        chosen_styles=body.styles,
        idea=body.prompt.strip(),
        extra={"panels": story["panels"], "look": story["look"],
               "title": body.prompt.strip()[:60]},
        character=body.character,
    )


class StoryIn(BaseModel):
    prompt: str = Field(default="", max_length=1000)
    parts: int = Field(default=3, ge=comic.MIN_BEATS, le=comic.MAX_BEATS)
    character: str = Field(default="", max_length=32)
    styles: dict[str, str] = Field(default_factory=dict)
    orientation: str = workflows.DEFAULT_ORIENTATION
    # 0 means "the page did not say", which clamp_duration reads as the
    # default length. Not `default=workflows.DEFAULT_DURATION`: a Field
    # default is evaluated at import and that number is a setting now.
    duration: int = Field(default=0, ge=0, le=600)
    quality: str = Field(default=workflows.DEFAULT_QUALITY, max_length=8)
    # The story maker films its first part from a picture they have already made
    # and looked at, rather than from words. Empty is the Video card's film,
    # which starts from words as it always has.
    source_gallery_id: str = Field(default="", max_length=200)
    # The title card the page draws on a canvas, as a data URL. The join has
    # always been able to open on one - the Video card's film simply never
    # sent one - and a story that has been named deserves its name on screen.
    title_card: str = Field(default="", max_length=4_000_000)


def _story_step(look: str, beat: dict, chosen: dict, seconds: int, shape: str,
                quality: str = workflows.DEFAULT_QUALITY):
    """The builder for one part after the first.

    Returned as a closure rather than a graph because it cannot be built yet:
    it starts from the last frame of the part before, which does not exist
    until that part has rendered. The job registry calls this when it does.
    """
    async def build(outputs: list) -> dict:
        name = Path(outputs[-1]["filename"]).name
        frame = await asyncio.to_thread(gallery.last_frame, name)
        frame = await asyncio.to_thread(uploads.prepare, frame, shape, quality)
        # LoadImage reads from ComfyUI's *input* directory, so the frame has to
        # make the round trip even though the video it came from is right there
        # in the output one.
        ref = await client.upload_image(frame, f"makery-story-{name}.png")
        return workflows.build_i2v(
            comic.beat_prompt(look, beat, chosen), ref, seconds, shape, None, quality
        )
    return build


async def _story_opening(body: "StoryIn", beat: dict, look: str, seconds: int,
                         shape: str, quality: str) -> dict:
    """Part one, filmed from a picture they already have.

    The same round trip the i2v route makes: their picture out of the gallery,
    cropped to the shape and quality chosen now, back into ComfyUI's *input*
    directory where `LoadImage` can read it.
    """
    _require_mine(body.source_gallery_id)
    try:
        data, media = gallery.read_bytes(body.source_gallery_id)
        if media == "video":
            data = gallery.last_frame(body.source_gallery_id)
        data = uploads.prepare(data, shape, quality)
    except (GalleryError, OSError, UploadError) as exc:
        log.warning("story source %s unusable: %s", body.source_gallery_id, exc)
        raise HTTPException(status_code=400, detail=i18n.t("That one's gone. Pick another!"))
    try:
        ref = await client.upload_image(
            data,
            f"makery-story-open-{Path(body.source_gallery_id).stem}-{shape}-{quality}.png",
        )
    except ComfyError as exc:
        log.error("story handoff failed: %s", exc)
        raise HTTPException(
            status_code=503, detail=i18n.t("Couldn't get that picture ready. Try again!")
        )
    return workflows.build_i2v(
        comic.beat_prompt(look, beat, body.styles), ref, seconds, shape, None, quality
    )


def _join_story(card_bytes: bytes | None = None):
    """The finishing step: stitch the parts into one film once they are done.

    A factory rather than the `after` itself, because the title card is drawn
    by the page at submit time and has to be carried into a callable the job
    registry will run minutes later. `None` is the Video card's film, which
    opens straight on its first frame the way it always has.
    """
    async def after(job, outputs: list) -> dict:
        names = [Path(o["filename"]).name for o in outputs]
        title = (job.idea or "").strip()[:60]
        movie = await asyncio.to_thread(gallery.join, names, card_bytes, 2.0, title)
        log.info("story %s joined %d clips into %s%s", job.id, len(names), movie,
                 " (on a title card)" if card_bytes else "")
        return {"movie": movie, "parts": names}
    return after


def _title_card(data_url: str) -> bytes | None:
    """The page's canvas, as bytes, or nothing.

    Run through `uploads.keep` like any other picture from the browser: it
    proves the bytes really are an image and re-encodes them, which is the same
    guard the join route puts on the card it is handed. A card that will not
    decode costs the card, never the film.
    """
    if not data_url:
        return None
    try:
        import base64

        raw = data_url.split(",", 1)[1] if "," in data_url else data_url
        return uploads.keep(base64.b64decode(raw))
    except Exception as exc:
        log.info("story title card unusable, filming without one: %s", exc)
        return None


@app.post("/api/generate/story")
async def generate_story(body: StoryIn, request: Request):
    """Several linked clips, joined into one little film.

    Each part starts from the last frame of the one before, which is the whole
    reason this is not just three videos: the clips actually continue from one
    another instead of being three separate takes on the same idea.

    It is slow - three renders and a stitch - and it spends three of their daily
    videos, because that is honestly what it costs.
    """
    _require_idle(request)
    _require_module("video")
    _check_words(body.prompt, "the box the film idea goes in")
    wanted = await _require_budget("video", body.parts)
    if wanted < comic.MIN_BEATS:
        raise HTTPException(
            status_code=409,
            detail=i18n.t("A film needs at least {min} videos and you haven't "
                          "got that many left today. Try a single video!",
                          min=comic.MIN_BEATS),
        )

    await _clear_card_for_ollama()
    try:
        story = await comic.beats(
            characters.in_prompt(body.prompt, body.character), wanted
        )
    except scripts.ScriptError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    quality = body.quality if body.quality in workflows.QUALITY else workflows.DEFAULT_QUALITY
    seconds = workflows.clamp_for_quality(body.duration, quality)
    shape = body.orientation
    seed = workflows.pick_seed(None)
    beats = story["beats"]

    # The story maker has already made the opening frame and they have already
    # said they like it, so part one animates *that* rather than inventing a
    # scene of its own - which is the whole reason the picture step exists.
    # Every part after it starts from the frame before either way.
    if body.source_gallery_id:
        first = await _story_opening(body, beats[0], story["look"], seconds,
                                     shape, quality)
    else:
        first = workflows.build_t2v(
            comic.beat_prompt(story["look"], beats[0], body.styles),
            seconds, shape, seed, quality,
        )
    steps = [first]
    steps += [
        _story_step(story["look"], beat, body.styles, seconds, shape, quality)
        for beat in beats[1:]
    ]

    log.info("story: %d parts for %r", len(steps), body.prompt.strip()[:60])
    return await _started(
        "story",
        " / ".join(b["scene"] for b in beats),
        steps,
        seconds,
        shape,
        body.styles,
        idea=body.prompt.strip(),
        extra={"beats": beats, "look": story["look"], "quality": quality,
               "said": _said(body)},
        seed=seed,
        character=body.character,
        after=_join_story(_title_card(body.title_card)),
    )


def _effect_after(effect: str, when: str):
    """The finishing step that puts a chosen sound into the rendered video.

    Written over the file itself rather than beside it: they asked for one
    video with a boing in it, not a video and a copy of it with a boing.
    Any failure here is logged and the video stands as rendered - a missing
    sound effect is not a reason to lose a three-minute render.
    """
    if not effect or effect not in sounds.IDS:
        return None
    when = when if when in ("start", "middle", "end") else "start"

    async def after(job, outputs: list) -> dict:
        name = Path(outputs[0]["filename"]).name
        try:
            await asyncio.to_thread(gallery.add_sound, name, effect, when, True)
        except Exception:
            log.exception("could not put the %r into %s", effect, name)
            return {}
        return {"effect": effect, "effect_at": when}
    return after


@app.post("/api/generate/t2v")
async def generate_t2v(body: VideoIn, request: Request):
    _require_idle(request)
    _require_module("video")
    prompt = await _checked(body)
    await _require_budget("video")
    quality = body.quality if body.quality in workflows.QUALITY else workflows.DEFAULT_QUALITY
    seconds = workflows.clamp_for_quality(body.duration, quality)
    seed = workflows.pick_seed(body.seed)
    graph = workflows.build_t2v(prompt, seconds, body.orientation, seed, quality)
    return await _started(
        "t2v", prompt, graph, seconds, body.orientation, body.styles,
        body.prompt.strip(), seed=seed, character=body.character,
        after=_effect_after(body.effect, body.effect_at),
        extra={"quality": quality, "said": _said(body)},
    )


@app.post("/api/generate/i2v")
async def generate_i2v(body: AnimateIn, request: Request):
    _require_idle(request)
    _require_module("video")
    prompt = await _checked(body)
    await _require_budget("video")
    quality = body.quality if body.quality in workflows.QUALITY else workflows.DEFAULT_QUALITY

    if body.source_gallery_id:
        # Something from the gallery: a generated picture, a photo or drawing
        # they uploaded, or a video (its last frame - "what happens next?").
        # Whatever it is, it is cropped to the shape chosen *now*, so an
        # uncropped photo becomes exactly what the video stage expects. A
        # picture already that size passes through untouched.
        _require_mine(body.source_gallery_id)
        try:
            data, media = gallery.read_bytes(body.source_gallery_id)
            if media == "video":
                data = gallery.last_frame(body.source_gallery_id)
            data = uploads.prepare(data, body.orientation, quality)
        except (GalleryError, OSError, UploadError) as exc:
            log.warning("gallery source %s unusable: %s", body.source_gallery_id, exc)
            raise HTTPException(status_code=400, detail=i18n.t("That one's gone. Pick another!"))
        try:
            image_ref = await client.upload_image(
                data,
                f"makery-gallery-{Path(body.source_gallery_id).stem}-{body.orientation}-{quality}.png",
            )
        except ComfyError as exc:
            log.error("gallery handoff failed: %s", exc)
            raise HTTPException(
                status_code=503, detail=i18n.t("Couldn't get that picture ready. Try again!")
            )
    else:
        source = registry.get(body.source_job_id)
        if source is None or source.status != "done" or not source.result:
            raise HTTPException(
                status_code=400,
                detail=i18n.t("Make or choose a picture first, then bring it here!"),
            )
        if source.is_video:
            raise HTTPException(
                status_code=400, detail=i18n.t("Pick a picture to animate, not a video!")
            )

        # The image is in ComfyUI's *output* dir but LoadImage reads from
        # *input*, so it has to make the round trip back through /upload/image.
        try:
            data = await client.fetch_view(source.result)
            # A fresh picture is 0.9MP-sized; at any other quality it needs the
            # same crop a gallery picture gets, or LTX resamples it.
            if quality != workflows.DEFAULT_QUALITY:
                data = uploads.prepare(data, body.orientation, quality)
            image_ref = await client.upload_image(data, f"makery-{source.id}-{quality}.png")
        except ComfyError as exc:
            log.error("animate handoff failed: %s", exc)
            raise HTTPException(
                status_code=503, detail=i18n.t("Couldn't get that picture ready. Try again!")
            )

    seconds = workflows.clamp_for_quality(body.duration, quality)
    seed = workflows.pick_seed(body.seed)
    graph = workflows.build_i2v(prompt, image_ref, seconds, body.orientation, seed, quality)
    return await _started(
        "i2v", prompt, graph, seconds, body.orientation, body.styles,
        body.prompt.strip(), seed=seed, character=body.character,
        after=_effect_after(body.effect, body.effect_at),
        extra={"quality": quality, "said": _said(body)},
    )


class BetweenIn(VideoIn):
    """A clip from one picture to another. Both are gallery items."""
    first_gallery_id: str = Field(default="", max_length=200)
    last_gallery_id: str = Field(default="", max_length=200)


async def _frame_for_slot(item_id: str, slot: str, orientation: str, quality: str) -> bytes:
    """The bytes for one end of the clip, cropped to the video's size.

    A picture is itself. A video means the frame nearest the slot: its last
    frame as a *first* picture (carry on from here), its first frame as a
    *last* picture (arrive at where this begins) - which is what makes a
    bridge between two of their clips possible.
    """
    try:
        data, media = gallery.read_bytes(item_id)
        if media == "video":
            data = gallery.last_frame(item_id) if slot == "first" else gallery.frame_at(item_id, 0.0)
        return uploads.prepare(data, orientation, quality)
    except (GalleryError, OSError, UploadError) as exc:
        log.warning("%s picture %s unusable: %s", slot, item_id, exc)
        raise HTTPException(status_code=400, detail=i18n.t("That picture's gone. Pick another!"))


@app.post("/api/generate/flf")
async def generate_between(body: BetweenIn, request: Request):
    """Start on one picture, end on another, and let the model do the middle.

    LTX's first-and-last-frame graph. Both ends are guides at 0.7 strength,
    so the clip really does open on the first and close on the last - which
    is also how a bridge between two of their videos works: the first slot
    takes a video's last frame, the last slot a video's first.
    """
    _require_idle(request)
    _require_module("video")
    prompt = await _checked(body)
    await _require_budget("video")
    for end in (body.first_gallery_id, body.last_gallery_id):
        if end:
            _require_mine(end)
    if not body.first_gallery_id or not body.last_gallery_id:
        raise HTTPException(status_code=400, detail=i18n.t("Pick a first picture and a last picture!"))
    quality = body.quality if body.quality in workflows.QUALITY else workflows.DEFAULT_QUALITY

    first = await _frame_for_slot(body.first_gallery_id, "first", body.orientation, quality)
    last = await _frame_for_slot(body.last_gallery_id, "last", body.orientation, quality)
    try:
        first_ref = await client.upload_image(
            first, f"makery-first-{Path(body.first_gallery_id).stem}-{body.orientation}-{quality}.png")
        last_ref = await client.upload_image(
            last, f"makery-last-{Path(body.last_gallery_id).stem}-{body.orientation}-{quality}.png")
    except ComfyError as exc:
        log.error("first/last handoff failed: %s", exc)
        raise HTTPException(status_code=503, detail=i18n.t("Couldn't get those pictures ready. Try again!"))

    seconds = workflows.clamp_for_quality(body.duration, quality)
    seed = workflows.pick_seed(body.seed)
    graph = workflows.build_flf2v(prompt, first_ref, last_ref, seconds, body.orientation, seed, quality)
    return await _started(
        "flf", prompt, graph, seconds, body.orientation, body.styles,
        body.prompt.strip(), seed=seed, character=body.character,
        after=_effect_after(body.effect, body.effect_at),
        extra={"quality": quality, "first": body.first_gallery_id, "last": body.last_gallery_id},
    )


@app.post("/api/upload")
async def upload_photo(
    request: Request,
    photo: UploadFile = File(...),
    source: str = Form("camera"),
    message: str = Form(""),
    orientation: str = "auto",
):
    """Accept a photo or a drawing and keep it in the gallery, ready to animate.

    The shape comes from the picture itself unless one is named explicitly: a
    portrait snap off the iPad should just animate as a portrait video.
    """
    _require_idle(request)
    raw = await photo.read()
    if orientation not in workflows.ORIENTATIONS:
        orientation = uploads.detect_orientation(raw)
    try:
        kept = uploads.keep(raw)
        preview = uploads.prepare(kept, orientation)
    except UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # What the page says this picture is. It decides which shelf the picture
    # lands on and how a refusal reads - and nothing else. It used to decide
    # whether the picture was looked at at all: "source=card" is a form field,
    # so any photo could be posted with that label and go straight into the
    # gallery with the checker skipped, no audit row, no alert to a grown-up
    # and no closure. The server cannot tell a card the page drew from a photo
    # off the camera roll - the bytes arrive from the browser either way - so
    # it no longer pretends it can. Everything that comes in here is screened,
    # exactly as the drawing pad's own pictures already were.
    if source not in UPLOAD_SOURCES:
        source = "camera"
    if source in ("card", "comic"):
        # A card is a gallery picture plus typed words, drawn by the page. The
        # picture is screened below like any other; the words are the half the
        # blocklist can read.
        ok, msg, category = safety.check_prompt(message)
        if not ok:
            log.info("card message rejected (%s)", category)
            if category not in ("empty", "length"):
                _fire(lockdown.refused("words", "the words on a card",
                                       text=message))
            raise HTTPException(status_code=400, detail=msg)
    if gallery.flag("screen_uploads", True):
        # The blocklist never sees a photo. The vision model does, with a
        # deliberately short list of things to say no to.
        await _clear_card_for_ollama()
        verdict = await scripts.screen(preview)
        if verdict is False:
            # Kept aside, small, so a parent can see what was refused and
            # let it through if the model was being silly.
            kept_as = None
            try:
                kept_as = gallery.save_refused(preview)
            except OSError as exc:
                log.warning("could not keep the refused upload: %s", exc)
            log.info("upload refused by the screen")
            audit.record("upload.refused", why="the picture checker said no",
                         kept_as=kept_as or "")
            # Tell the grown-ups now, with the picture, and close the factory
            # if they asked for that. Fired rather than awaited: they are being
            # answered either way and must not wait on a mail relay to hear no.
            _fire(lockdown.refused(
                "photo", UPLOAD_WHERE[source],
                image=gallery.refused_path(kept_as) if kept_as else None))
            raise HTTPException(status_code=400, detail=i18n.t(UPLOAD_REFUSED))
        if verdict is None:
            log.warning("upload screen unavailable; letting the photo through")

    # Into the gallery, whole and uncropped. It is cropped to whatever shape is
    # chosen at the moment it becomes a video, not now.
    try:
        gallery_id = gallery.save_upload(kept, source)
    except OSError as exc:
        log.error("could not keep the upload: %s", exc)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't save that picture. Try again!"))
    audit.record("upload.kept", id=gallery_id, source=source)
    version = int(gallery.path_for(gallery_id).stat().st_mtime)
    _remember_preview((gallery_id, version, orientation), preview)
    return {
        "gallery_id": gallery_id,
        "orientation": orientation,
        "source": source,
        "preview_url": f"/api/gallery/{gallery_id}/preview?orientation={orientation}&v={version}",
    }


@app.get("/api/gallery/{item_id}/preview")
async def gallery_preview(item_id: str, orientation: str = workflows.DEFAULT_ORIENTATION):
    """Any gallery item cropped to the chosen shape - the source thumbnail.

    For a video that is its last frame, so the thumbnail for "what happens
    next?" shows exactly what the new clip will start from.
    """
    try:
        path = gallery.path_for(item_id)
    except GalleryError:
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone."))
    if orientation not in workflows.ORIENTATIONS:
        orientation = workflows.DEFAULT_ORIENTATION

    key = (item_id, int(path.stat().st_mtime), orientation)
    png = _preview_cache.get(key)
    if png is None:
        try:
            data, media = gallery.read_bytes(item_id)
            if media == "video":
                data = gallery.last_frame(item_id)
            png = uploads.prepare(data, orientation)
        except (GalleryError, OSError, UploadError):
            raise HTTPException(status_code=404, detail=i18n.t("No picture for that one."))
        _remember_preview(key, png)

    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/gallery")
async def gallery_list():
    """Everything they have made, newest first."""
    if not gallery.available():
        return {"available": False, "items": []}
    try:
        # The one caller that asks "what may they see" rather than "what is
        # theirs": their own things, plus whatever anybody else has put on the
        # family shelf. Those arrive carrying `mine: false`, and the page shows
        # whose they are and offers none of the buttons that would change them.
        return {"available": True, "items": gallery.listing(family=True),
                "tags": gallery.all_tags()}
    except GalleryError as exc:
        log.error("gallery unreadable: %s", exc)
        return {"available": False, "items": []}


class GalleryIds(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=200)


@app.get("/api/gallery/zip")
async def gallery_zip(ids: str = "", what: str = ""):
    """Several items as one zip, so saving a batch is a single tap.

    Taken as a GET with comma-separated ids so a plain <a download> works -
    Safari will not start a download from a fetch POST. `what=today|favourites|all`
    names a set instead: the parent page's "save it all" buttons would otherwise
    put every id in the URL, and a few hundred of them exceeds what nginx will
    accept in a request line.
    """
    if what:
        # The parent page's "save it all" - the household's, whichever child
        # the browser happens to be signed in as. A plain <a download> cannot
        # carry the PIN, so this sits inside the stated media-URL curtain.
        items = gallery.listing(everyone=True)
        if what == "favourites":
            chosen = [i for i in items if i["favourite"]]
        elif what == "today":
            lt = time.localtime()
            midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
            chosen = [i for i in items if i["created"] >= midnight]
        elif what == "all":
            chosen = items
        else:
            raise HTTPException(status_code=400, detail=i18n.t("Don't know what to save."))
        wanted = [i["id"] for i in chosen]
    else:
        wanted = [i for i in ids.split(",") if i]
    if not wanted:
        raise HTTPException(status_code=400, detail=i18n.t("Pick some things to save first!"))

    handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    try:
        # In a thread: "save it all" can be several gigabytes of video, and
        # writing that on the event loop freezes their progress bar and every
        # other request until it finishes.
        written = await asyncio.to_thread(gallery.zip_into, wanted, handle)
        handle.close()
    except Exception:
        handle.close()
        os.unlink(handle.name)
        raise

    if not written:
        os.unlink(handle.name)
        raise HTTPException(status_code=404, detail=i18n.t("Those ones are gone!"))

    stamp = time.strftime("%Y-%m-%d")
    label = {"favourites": "favourites", "all": "everything"}.get(what, "my-stuff")
    return FileResponse(
        handle.name,
        media_type="application/zip",
        filename=f"{label}-{stamp}.zip",
        # The temp file is only needed until it has been sent.
        background=BackgroundTask(os.unlink, handle.name),
    )


@app.post("/api/gallery/delete")
async def gallery_delete_many(body: GalleryIds, request: Request):
    if not body.ids:
        raise HTTPException(status_code=400, detail=i18n.t("Pick some things first!"))
    for one in body.ids:
        _may_change(request, one)
    deleted, failed = gallery.delete_many(body.ids)
    return {"deleted": deleted, "failed": failed}


@app.get("/api/gallery/{item_id}/file")
async def gallery_file(item_id: str, download: int = 0):
    try:
        path = gallery.path_for(item_id)
    except GalleryError:
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone!"))

    headers = {"Cache-Control": "private, max-age=3600"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{path.name}"'
    return FileResponse(path, media_type=gallery.media_type(item_id), headers=headers)


@app.post("/api/gallery/join")
async def gallery_join(
    request: Request,
    ids: str = Form(...),
    title: str = Form(""),
    card: UploadFile | None = File(None),
):
    """Join clips into one film, optionally opening on a title card.

    The title card is rendered by the page (its own fonts, the banner
    behind), so the server needs no font files. Stitching is CPU-only and
    takes a few seconds per clip, so it runs in a thread.
    """
    _require_open()
    # Joining clips is the Video tab's work even though it starts from the
    # gallery, so it goes with it.
    _require_module("video")
    # A film is something they make, so it waits on the sums like the rest.
    _require_warmed_up(request)
    wanted = [i for i in ids.split(",") if i]
    if len(wanted) < 1:
        raise HTTPException(status_code=400, detail=i18n.t("Pick some videos first!"))
    if len(wanted) > 20:
        raise HTTPException(status_code=400, detail=i18n.t("That's a lot! Try twenty or fewer."))
    for one in wanted:
        _require_mine(one)
    title = title.strip()[:80]
    ok, message, _ = safety.check_prompt(title) if title else (True, "", "")
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    card_bytes = await card.read() if card is not None else None
    if card_bytes:
        try:
            card_bytes = uploads.keep(card_bytes)
        except UploadError:
            card_bytes = None

    try:
        new_id = await asyncio.to_thread(gallery.join, wanted, card_bytes, 2.0, title)
    except GalleryError as exc:
        log.warning("join refused: %s", exc)
        raise HTTPException(status_code=400, detail=i18n.t("Pick videos to join - pictures can't go in a film!"))
    except Exception:
        log.exception("join failed")
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't join those. Try again!"))
    return {"gallery_id": new_id}


class StoryFinishIn(BaseModel):
    film: str = Field(default="", max_length=200)
    song: str = Field(default="", max_length=200)
    picture: str = Field(default="", max_length=200)
    # The film's own sound - LTX writes music, effects and the line them
    # character says - kept under the song, or thrown away for it.
    keep_sound: bool = True


@app.post("/api/story/finish")
async def story_finish(body: StoryFinishIn, request: Request):
    """Put the song under the film: the last step of the story maker.

    No GPU and no model - the pictures are remuxed packet for packet and only
    the soundtrack is built - so it is not one of their daily videos and there is
    no job to watch. It is behind the warm-up and the open sign like everything
    else they make, and behind `_require_mine` on both halves: a story is made
    out of their own film and their own song.
    """
    _require_open()
    _require_module("story")
    # ...and the Video maker, for the same reason `/api/gallery/join` carries
    # it: what comes out of here is a film. A parent who turned videos off has
    # turned this off, and the page agrees - the Story tab hides itself when
    # the film step cannot run. Found by turning videos off and watching this
    # route cheerfully make one anyway.
    _require_module("video")
    _require_warmed_up(request)
    if not body.film or not body.song:
        raise HTTPException(status_code=400, detail=i18n.t("Make the film and the song first!"))
    _require_mine(body.film)
    _require_mine(body.song)

    # What the whole thing was made of, so the viewer can say so and a reload
    # can find all three again. The picture is optional: they may have skipped
    # that step and filmed from words.
    made_of = {"film": body.film, "song": body.song}
    if body.picture:
        made_of["picture"] = body.picture

    try:
        new_id = await asyncio.to_thread(
            gallery.add_song, body.film, body.song, body.keep_sound, made_of
        )
    except GalleryError as exc:
        log.warning("story finish refused: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=i18n.t("Couldn't put those together. Make sure it's a film and a song!"),
        )
    except Exception:
        log.exception("story finish failed")
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't put those together. Try again!"))
    return {"gallery_id": new_id}


MAX_VOICE_BYTES = 8 * 1024 * 1024


@app.post("/api/gallery/{item_id}/voice")
async def gallery_voice(
    item_id: str,
    request: Request,
    audio: UploadFile = File(...),
    keep: str = Form("1"),
):
    """Put their own recording over one of their videos, as a new video.

    Behind the warm-up gate like anything else that makes something, but not
    behind the daily video limit: no GPU time is spent, so it is not one of
    the videos the limit is counting.
    """
    _require_open()
    _require_warmed_up(request)
    _may_change(request, item_id)
    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail=i18n.t("That recording was empty. Try again!"))
    if len(raw) > MAX_VOICE_BYTES:
        raise HTTPException(status_code=400, detail=i18n.t("That recording is too long. Keep it short!"))

    try:
        keep_original = keep not in ("0", "false", "no")
        new_id = await asyncio.to_thread(gallery.add_voice, item_id, raw, keep_original)
    except GalleryError as exc:
        log.warning("voice refused for %s: %s", item_id, exc)
        raise HTTPException(status_code=400, detail=i18n.t("That one can't have a voice added."))
    except Exception:
        log.exception("voice-over failed")
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't add your voice. Try again!"))
    return {"gallery_id": new_id}


STICKER_TROUBLE = {
    "busy background": (
        "That one's background is too busy to cut out. Stickers work best on a "
        "picture where the thing you want sits on its own - try asking for "
        "\"on a plain white background\"!"
    ),
    "nothing left": (
        "That one went all see-through! Try a picture where the thing you want "
        "stands out from behind it."
    ),
    "only pictures can become stickers": "Only pictures can be stickers!",
}


@app.post("/api/gallery/{item_id}/sticker")
async def gallery_sticker(item_id: str, request: Request):
    """Cut the background out of a picture and keep it as a sticker.

    Behind the warm-up like everything else they make, but not behind the daily
    limit: no GPU time is spent, so it is not one of the pictures being counted.
    """
    _require_open()
    _require_warmed_up(request)
    _may_change(request, item_id)
    try:
        png = await asyncio.to_thread(gallery.sticker, item_id)
    except GalleryError as exc:
        reason = str(exc)
        if reason in ("bad id", "not found", "not media"):
            raise HTTPException(status_code=404, detail=i18n.t("That one's gone!"))
        raise HTTPException(
            status_code=400,
            detail=i18n.t(STICKER_TROUBLE.get(reason, "That one can't be a sticker.")),
        )
    except Exception:
        log.exception("sticker failed for %s", item_id)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't cut that one out. Try again!"))

    source = _gallery_item(item_id)
    try:
        new_id = gallery.save_derived(png, "sticker", {
            "prompt": source.get("prompt") or "",
            "idea": source.get("idea") or "",
            "character": source.get("character") or "",
            "sticker_of": item_id,
        })
    except OSError as exc:
        log.error("could not keep the sticker: %s", exc)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't save that. Try again!"))
    return {"gallery_id": new_id}


@app.get("/api/gallery/{item_id}/frame")
async def gallery_frame(item_id: str, at: float = 0.0):
    """One frame out of a video, as a picture. The preview for the frame grabber."""
    _require_mine(item_id)
    try:
        png = await asyncio.to_thread(gallery.frame_at, item_id, at)
    except (GalleryError, OSError):
        raise HTTPException(status_code=404, detail=i18n.t("No picture for that one."))
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=600"})


class FrameIn(BaseModel):
    at: float = Field(default=0.0, ge=0, le=3600)


@app.post("/api/gallery/{item_id}/frame")
async def gallery_keep_frame(item_id: str, body: FrameIn, request: Request):
    """Keep that frame as a picture of its own, ready to animate or print."""
    _require_open()
    _require_warmed_up(request)
    # Theirs to take a frame out of - the same check the GET above it makes, and
    # the one every other route that builds a new gallery item out of an old
    # one makes. Without it a guessed id from another child's gallery came back
    # stamped as this one's own picture.
    _require_mine(item_id)
    try:
        png = await asyncio.to_thread(gallery.frame_at, item_id, body.at)
    except (GalleryError, OSError):
        raise HTTPException(status_code=404, detail=i18n.t("No picture for that one."))

    source = _gallery_item(item_id)
    try:
        new_id = gallery.save_derived(png, "frame", {
            "prompt": source.get("prompt") or "",
            "idea": source.get("idea") or "",
            "orientation": source.get("orientation") or "",
            "character": source.get("character") or "",
            "frame_of": item_id,
            "frame_at": round(float(body.at), 2),
        })
    except OSError as exc:
        log.error("could not keep the frame: %s", exc)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't save that. Try again!"))
    return {"gallery_id": new_id}


# --- making something new out of one they already have -------------------------
#
# Three of these, and they share a shape. None of them counts against a daily
# limit - the sticker, the grabbed frame and the voice-over set that precedent
# and the reason is the same: a limit counts the things they *asked the machine
# to invent*, and none of these invents anything. Two of them do spend GPU
# time, which is why they go through the job registry and queue behind them
# video like any other render; the third spends none at all.

# A clip long enough to be worth smoothing and short enough that doubling
# every frame of it is a minute rather than a quarter of an hour. Their own
# videos are 5-15s at 24fps; the cap is on the frames as well as the seconds
# because a clip they have already smoothed once is 48fps and half the length
# would be twice the work.
SMOOTH_MAX_SECONDS = 30
SMOOTH_MAX_FRAMES = 800

SMOOTH_TOO_LONG = "That one's too long to do this to. Try it on a shorter video!"


class SmoothIn(BaseModel):
    slow: bool = False


@app.post("/api/gallery/{item_id}/smooth")
async def gallery_smooth(item_id: str, body: SmoothIn, request: Request):
    """Twice the frames of one of their videos: silkier, or half speed.

    One graph, two answers. Played at twice the original rate the clip is the
    same length and simply moves more smoothly; played at the original rate the
    same frames take twice as long, which is slow motion.

    **Slow motion comes out silent, on purpose.** The pictures can be stretched
    because RIFE invents the frames in between; the sound cannot, and the only
    cheap thing to do with it is play it at half speed - which drops it an
    octave and turns their character's line into a growl and the music into a
    drone. Nothing here can pitch-correct it, and a silent slow-motion clip is
    a better thing to hand a child than one that sounds broken. The page says
    so before they tap it.

    A render, so it queues like one - but not one of the videos their daily limit
    is counting: no model invents anything here, it is their own clip with more
    frames in it.
    """
    _require_idle(request)
    _require_mine(item_id)
    try:
        facts = gallery.video_facts(item_id)
    except GalleryError:
        raise HTTPException(status_code=400, detail=i18n.t("Only videos can be made smooth!"))
    except Exception:
        log.exception("could not read %s before smoothing it", item_id)
        raise HTTPException(status_code=400, detail=i18n.t("Couldn't read that video. Try another!"))
    if facts["seconds"] > SMOOTH_MAX_SECONDS or facts["frames"] > SMOOTH_MAX_FRAMES:
        raise HTTPException(status_code=400, detail=i18n.t(SMOOTH_TOO_LONG))

    # The file is in ComfyUI's *output* directory and LoadVideo reads from
    # *input*, so it makes the same round trip "Animate this" makes with a
    # picture. The janitor sweeps these back out again.
    try:
        data, _ = gallery.read_bytes(item_id)
        video_ref = await client.upload_image(
            data, f"makery-{Path(item_id).stem}-smooth.mp4"
        )
    except (GalleryError, OSError):
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone!"))
    except ComfyError as exc:
        log.error("smooth handoff failed: %s", exc)
        raise HTTPException(status_code=503, detail=i18n.t("Couldn't get that video ready. Try again!"))

    keep_sound = facts["sound"] and not body.slow
    graph = workflows.build_interpolated(
        video_ref, facts["fps"] * (1 if body.slow else 2), keep_sound
    )
    source = _gallery_item(item_id)
    return await _started(
        "slowmo" if body.slow else "smooth",
        source.get("prompt") or "", graph,
        duration=max(1, round(facts["seconds"] * (2 if body.slow else 1))),
        orientation=source.get("orientation") or workflows.DEFAULT_ORIENTATION,
        idea=source.get("idea") or "",
        character=source.get("character") or "",
        extra={
            "smooth_of": item_id,
            # One frame of *them* clip, for timings: the work here is the file
            # they already have, whatever size it came out at.
            "pixels": facts["width"] * facts["height"],
            # And in words, for the status sheet: a smoothed clip comes out
            # the size it went in.
            "size": f"{facts['width']}\u00d7{facts['height']}",
        },
    )


@app.post("/api/gallery/{item_id}/huge")
async def gallery_huge(item_id: str, request: Request):
    """One of their pictures, four times the size.

    An ESRGAN model read straight off the picture - one pass, no prompt, no
    sampler, six seconds - so the result is the picture they already have with
    the edges worked out rather than a new picture that merely resembles it.
    That is the whole reason this exists as its own button and not as "make it
    again, bigger".

    GPU time, so it queues; not a picture their daily limit counts, for the same
    reason the sticker is not.
    """
    _require_idle(request)
    _require_mine(item_id)
    try:
        data, media = gallery.read_bytes(item_id)
    except (GalleryError, OSError):
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone!"))
    if media != "image":
        raise HTTPException(status_code=400, detail=i18n.t("Only pictures can be made huge!"))
    try:
        png, width, height = await asyncio.to_thread(uploads.for_upscale, data)
        image_ref = await client.upload_image(
            png, f"makery-{Path(item_id).stem}-huge.png"
        )
    except UploadError:
        raise HTTPException(status_code=400, detail=i18n.t("Couldn't read that picture. Try another!"))
    except ComfyError as exc:
        log.error("huge handoff failed: %s", exc)
        raise HTTPException(status_code=503, detail=i18n.t("Couldn't get that picture ready. Try again!"))

    source = _gallery_item(item_id)
    return await _started(
        "huge", source.get("prompt") or "", workflows.build_huge(image_ref),
        orientation=source.get("orientation") or workflows.DEFAULT_ORIENTATION,
        idea=source.get("idea") or "",
        character=source.get("character") or "",
        # Four times each side is what the ESRGAN model does, so that is
        # what the status sheet says they are waiting for.
        extra={"huge_of": item_id, "pixels": width * height,
               "size": f"{width * 4}\u00d7{height * 4}"},
    )


class LoopIn(BaseModel):
    at: float = Field(default=0.0, ge=0, le=3600)
    seconds: float = Field(default=2.0, ge=0.2, le=2.0)


@app.post("/api/gallery/{item_id}/loop")
async def gallery_loop(item_id: str, body: LoopIn, request: Request):
    """A moment out of one of their videos, as a sticker that moves.

    No GPU at all - their own frames, fewer of them and smaller - so it is not
    behind the busy check either: it finishes while they are still looking at the
    sheet, and refusing it because a video is rendering would be a rule with
    nothing behind it.
    """
    _require_open()
    _require_warmed_up(request)
    _require_mine(item_id)
    try:
        webp = await asyncio.to_thread(
            gallery.moving_sticker, item_id, body.at, body.seconds
        )
    except GalleryError as exc:
        reason = str(exc)
        if reason in ("bad id", "not found", "not media"):
            raise HTTPException(status_code=404, detail=i18n.t("That one's gone!"))
        if reason == "not enough frames":
            raise HTTPException(
                status_code=400,
                detail=i18n.t("There isn't enough video there to loop. Try starting a bit earlier!"),
            )
        raise HTTPException(status_code=400, detail=i18n.t("Only videos can be moving stickers!"))
    except Exception:
        log.exception("moving sticker failed for %s", item_id)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't make that one move. Try again!"))

    source = _gallery_item(item_id)
    try:
        new_id = gallery.save_derived(webp, "loop", {
            "prompt": source.get("prompt") or "",
            "idea": source.get("idea") or "",
            "character": source.get("character") or "",
            "loop_of": item_id,
            "loop_at": round(float(body.at), 2),
            "duration": round(float(body.seconds), 1),
        }, suffix=".webp")
    except OSError as exc:
        log.error("could not keep the moving sticker: %s", exc)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't save that. Try again!"))
    return {"gallery_id": new_id}


# --- the three ways to change a picture they already have ----------------------
#
# Flux 2 Klein 9B, three ways, and unlike everything above them these *are*
# generation: a model invents pixels from their words. So all three spend one
# from the picture allowance, run `_checked` like every other prompt route, and
# queue behind whatever else is running. What makes them their own thing rather
# than another maker card is that they start from a picture they already have -
# so they live in the gallery viewer and answer through `watchDerived`, the
# same way "make it smooth" does.

# Both kinds of sticker are pictures with see-through bits, and all three of
# these graphs read RGB and hand back RGB - so an edit would quietly fill them
# cut-out back in with a background, and a moving one would come back as its
# first frame. "Make it huge" is hidden on them for the same reason.
UNEDITABLE_KINDS = ("sticker", "loop")

EDIT_NOT_A_PICTURE = "Only pictures can be changed. Pick one of your pictures!"
EDIT_NOT_A_STICKER = (
    "Stickers can't be changed - they'd lose their see-through bits. "
    "Try it on one of your pictures!"
)


class EditIn(BaseModel):
    prompt: str = Field(default="", max_length=4000)
    # Empty, and read by `_checked`, which is why it is here at all: an edit is
    # an *instruction*, not a description, and "in the style of a watercolour
    # painting, golden hour lighting" appended to "give the fox a scarf" asks
    # for a different picture rather than a changed one. The style dropdowns
    # are deliberately not on these sheets.
    styles: dict[str, str] = Field(default_factory=dict)
    # "Make it again, but..." on an edit: the same seed with a changed
    # instruction gives a variation on the picture they are looking at.
    seed: int | None = Field(default=None, ge=0, le=workflows.MAX_SEED)
    # Their own face as a second reference - "and put me in it". Only offered
    # when they have actually saved one.
    with_me: bool = False


class OutpaintIn(EditIn):
    side: str = workflows.DEFAULT_OUTPAINT_SIDE
    amount: str = workflows.DEFAULT_OUTPAINT_AMOUNT


async def _edit_source(item_id: str, budget: int = uploads.EDIT_MAX_PIXELS):
    """One of their pictures, sized for Klein and already in ComfyUI's input dir.

    Returns the filename ComfyUI knows it by, the bytes that went under that
    name, and the size they ended up. The size matters twice over, because the
    outpaint pads are worked out from it and `timings` measures this family in
    pixels; the bytes matter once, because the outpaint pastes them back into
    the render afterwards and has to paste exactly what the model was shown.
    """
    if _gallery_item(item_id).get("kind") in UNEDITABLE_KINDS:
        raise HTTPException(status_code=400, detail=i18n.t(EDIT_NOT_A_STICKER))
    try:
        data, media = gallery.read_bytes(item_id)
    except (GalleryError, OSError):
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone!"))
    if media != "image":
        raise HTTPException(status_code=400, detail=i18n.t(EDIT_NOT_A_PICTURE))
    try:
        png, width, height = await asyncio.to_thread(uploads.for_edit, data, budget)
        # The picture is in ComfyUI's *output* directory and LoadImage reads
        # from *input*, so it makes the same round trip "Animate this" makes.
        # The janitor sweeps these back out again.
        ref = await client.upload_image(png, f"makery-{Path(item_id).stem}-edit.png")
    except UploadError:
        raise HTTPException(status_code=400, detail=i18n.t("Couldn't read that picture. Try another!"))
    except ComfyError as exc:
        log.error("edit handoff failed: %s", exc)
        raise HTTPException(status_code=503, detail=i18n.t("Couldn't get that picture ready. Try again!"))
    return ref, png, width, height


async def _my_face_ref() -> str:
    """Their profile picture, uploaded as a second reference, or "" if they have none.

    A face that will not upload is not worth refusing the whole render over -
    they asked for a change to their picture and gets one, without themselves in it.
    """
    me = (gallery.WHO.get() or {}).get("id") or ""
    if not me or not profiles.has_avatar(me):
        return ""
    try:
        face = await asyncio.to_thread(profiles.avatar_path(me).read_bytes)
        png, _, _ = await asyncio.to_thread(uploads.for_edit, face)
        return await client.upload_image(png, f"makery-face-{me}.png")
    except (OSError, UploadError, ComfyError) as exc:
        log.warning("could not send their face as a second reference: %s", exc)
        return ""


@app.post("/api/gallery/{item_id}/edit")
async def gallery_edit(item_id: str, body: EditIn, request: Request):
    """Their picture, changed by what they typed.

    The picture is the reference and their words are the instruction, which is
    what Flux 2 Klein's edit template does and what makes "make it night-time"
    give back the same scene at night rather than a different night scene.
    Their words go through `_checked` like every other prompt in this app - the
    blocklist first, then French into English, because the model reads English.

    **This one costs a picture.** Smoothing a clip or making one huge does not,
    because neither invents anything; this invents a whole picture, and that is
    exactly what the daily limit counts.
    """
    _require_idle(request)
    _require_module("picture")
    _require_mine(item_id)
    prompt = await _checked(body)
    await _require_budget("image", 1)
    ref, _sized, width, height = await _edit_source(item_id)
    face = await _my_face_ref() if body.with_me else ""
    seed = workflows.pick_seed(body.seed)
    return await _started(
        "edit", prompt, workflows.build_edit(ref, prompt, seed, second_ref=face),
        orientation=workflows.nearest_orientation(width, height),
        idea=body.prompt.strip(), seed=seed,
        extra={"edit_of": item_id, "pixels": width * height,
               "size": f"{width}\u00d7{height}",
               **({"with_me": True} if face else {})},
    )


# The join is half a second against fourteen of rendering, so it gets a
# sliver of the bar rather than a graph's worth of it - at a whole slice the
# render would crawl to 50% and then jump.
OUTPAINT_JOIN_SHARE = 0.05


def _outpaint_after(source: bytes, pads: tuple[int, int, int, int]):
    """The finishing step that puts their own picture back into the render.

    Written over the rendered file rather than beside it, like the sound
    effects: they asked for their picture with more of the scene round it, not for
    that and a tidied copy of it. It happens before the sidecar is written, so
    what the gallery lists is one ordinary picture with nothing to explain.

    Any failure here is logged and the render stands as it came back - a join
    that could have been better is not a reason to lose the picture. What it
    cannot do is half-finish: `gallery.rewrite` replaces the file in one step.
    """
    async def after(job, outputs: list) -> dict:
        name = Path(outputs[0]["filename"]).name
        try:
            grown, _ = await asyncio.to_thread(gallery.read_bytes, name)
            joined = await asyncio.to_thread(uploads.rejoin_outpaint, grown, source, pads)
            await asyncio.to_thread(gallery.rewrite, name, joined)
        except Exception:
            log.exception("could not put their picture back into %s", name)
        return {}
    return after


@app.post("/api/gallery/{item_id}/outpaint")
async def gallery_outpaint(item_id: str, body: OutpaintIn, request: Request):
    """What is outside the frame of one of their pictures.

    Their picture is carried through the sampler untouched - the pad's own mask
    is the noise mask, so the only pixels that get invented are the new ones -
    and the words box is optional, because "show me more of it" is a complete
    request on its own.

    The finished canvas is capped (`workflows.OUTPAINT_MAX_PIXELS`), so asking
    for half again all round shrinks their picture a little to make room rather
    than running the card out of memory. "Make it huge" afterwards is the
    answer to wanting the pixels back.
    """
    _require_idle(request)
    _require_module("picture")
    _require_mine(item_id)
    # The only prompt box in the app that may be empty, so the filter runs on
    # their words only when there are any - `_checked` rightly refuses a blank
    # box everywhere else. What reaches the model when they say nothing is
    # styles.OUTPAINT, which is ours and needs no filtering, exactly like the
    # cut-out and banner wordings.
    typed = await _checked(body) if body.prompt.strip() else ""
    prompt = styles.compose_outpaint(typed)
    await _require_budget("image", 1)
    budget = min(uploads.EDIT_MAX_PIXELS,
                 workflows.outpaint_budget(body.side, body.amount))
    ref, sized, width, height = await _edit_source(item_id, budget)
    pads = workflows.outpaint_pads(width, height, body.side, body.amount)
    grown = (width + pads[0] + pads[2], height + pads[1] + pads[3])
    seed = workflows.pick_seed(body.seed)
    return await _started(
        "outpaint", prompt, workflows.build_outpaint(ref, prompt, pads, seed),
        orientation=workflows.nearest_orientation(*grown),
        # The one maker in the app whose words may be empty, and an empty idea
        # falls back to the composed prompt - which would show our own framing
        # sentence in the viewer as the thing they asked for.
        idea=body.prompt.strip() or "what's outside the frame", seed=seed,
        extra={"edit_of": item_id, "pixels": grown[0] * grown[1],
               "size": f"{grown[0]}\u00d7{grown[1]}",
               "side": body.side, "amount": body.amount},
        # Their own picture goes back into the middle of the render before the
        # sidecar is written. Without it the middle is a VAE round trip of them
        # picture rather than their picture, and it shows - see
        # uploads.rejoin_outpaint.
        after=_outpaint_after(sized, pads), after_share=OUTPAINT_JOIN_SHARE,
    )


@app.post("/api/gallery/{item_id}/inpaint")
async def gallery_inpaint(item_id: str, request: Request,
                          mask: UploadFile = File(...),
                          prompt: str = Form(default="")):
    """Just the bit they painted over, changed to what they typed.

    Multipart rather than JSON because the mask is a picture: the drawing pad
    they already know exports their strokes as white on black, and
    `VAEEncodeForInpaint`'s noise mask is what keeps the change inside them.
    Outside them the picture comes back through the VAE rather than untouched
    - measured at 2.8 of 255, which nobody can see, but it is a re-encode.
    """
    _require_idle(request)
    _require_module("picture")
    _require_mine(item_id)
    # Before `_checked`, which would answer "type something you'd like to make"
    # - true of a maker card and confusing under a picture they have just painted
    # a hole in.
    if not prompt.strip():
        raise HTTPException(
            status_code=400,
            detail=i18n.t("Tell me what should be there! Type it in the box and tap Go."),
        )
    words = await _checked(EditIn(prompt=prompt))
    await _require_budget("image", 1)
    ref, _sized, width, height = await _edit_source(item_id)
    try:
        painted = await mask.read()
        shaped = await asyncio.to_thread(uploads.mask_for_edit, painted, width, height)
        mask_ref = await client.upload_image(
            shaped, f"makery-{Path(item_id).stem}-mask.png")
    except UploadError:
        raise HTTPException(status_code=400, detail=i18n.t("Couldn't read what you painted. Try again!"))
    except ComfyError as exc:
        log.error("inpaint mask handoff failed: %s", exc)
        raise HTTPException(status_code=503, detail=i18n.t("Couldn't get that ready. Try again!"))
    seed = workflows.pick_seed(None)
    return await _started(
        "inpaint", words, workflows.build_inpaint(ref, mask_ref, words, seed),
        orientation=workflows.nearest_orientation(width, height),
        idea=prompt.strip(), seed=seed,
        extra={"edit_of": item_id, "pixels": width * height,
               "size": f"{width}\u00d7{height}"},
    )


# --- turn it into... --------------------------------------------------------
#
# The fourth thing to do with a picture they already have, and the one they
# reaches for without having to think of a sentence: a row of chips - a
# cartoon, a painting, a pencil drawing, a clay model - and the same picture
# comes back drawn that way. Their drawings are what this is really for: the
# house-and-cat they drew on the pad comes back as a clay model of itself, and
# that is a different feeling from making a picture of a house and a cat.
#
# Mechanically it is "change this picture" with the sentence written by us
# instead of by them, so everything it is made of is already above: the same
# graph, the same `_edit_source`, the same budget, the same `watchDerived` on
# the page. What is its own is `restyles.py`, which holds the eight sentences,
# and the fact that their words box is *optional* - the chip is a complete
# request, the way the outpaint's side and amount are.


class RestyleIn(BaseModel):
    # Which chip. An unknown one falls back to the first rather than 400ing -
    # see `restyles._chip`; the page can only send one of ours, so an unknown
    # id means a page left open across a rebuild.
    style: str = restyles.DEFAULT
    # Their own twist, and it may be empty: "turn it into a cartoon" is a whole
    # request. Shorter than the edit box on purpose - this is an extra clause
    # on a sentence we wrote, not a sentence of their own.
    prompt: str = Field(default="", max_length=300)
    # Read by `_checked`, and always empty here. The dropdowns describe a
    # picture to make from nothing; appending "golden hour lighting" to "redraw
    # this as a pencil sketch" asks for something else entirely.
    styles: dict[str, str] = Field(default_factory=dict)
    # "Make it again, but..." on a restyled picture: the same chip and the same
    # seed with a word changed gives a variation on this one.
    seed: int | None = Field(default=None, ge=0, le=workflows.MAX_SEED)


@app.post("/api/gallery/{item_id}/restyle")
async def gallery_restyle(item_id: str, body: RestyleIn, request: Request):
    """One of their pictures, drawn as a different kind of picture.

    **This costs a picture**, like the three edits above and unlike smooth and
    huge: the model draws a whole new picture: their scene, every pixel of it
    invented. `usage_today()` counts `restyle` into `pictures` for the same
    reason it counts the edits, or this would be the way round a daily limit.

    The chips are ours and need no filtering (`restyles.py` says why). Their own
    twist is a sentence they typed, so it goes through `_checked` exactly like
    every other prompt in this app - only when there is one, because the box is
    allowed to be empty.
    """
    _require_idle(request)
    _require_module("picture")
    _require_mine(item_id)
    twist = body.prompt.strip()
    # `_checked` rightly answers "type something you'd like to make" to an
    # empty box, which is the wrong thing to say about a box they were told they
    # did not have to fill in. Same shape as the outpaint's optional words.
    typed = await _checked(body) if twist else ""
    prompt = restyles.compose(body.style, typed)
    await _require_budget("image", 1)
    ref, _sized, width, height = await _edit_source(item_id)
    seed = workflows.pick_seed(body.seed)
    return await _started(
        "restyle", prompt, workflows.build_restyle(ref, prompt, seed),
        orientation=workflows.nearest_orientation(width, height),
        # What the viewer shows as the thing they asked for. Their twist alone
        # would lose which button made the picture, and our whole composed
        # sentence would read as forty words they never wrote.
        idea=restyles.asked_for(body.style, twist), seed=seed,
        extra={"restyle_of": item_id, "pixels": width * height,
               "size": f"{width}\u00d7{height}",
               # Both halves of the sheet, so "make it again, but..." can put
               # the chip back under their finger and their words back in the box.
               "turned_into": body.style, "twist": twist},
    )


# --- little sound effects ---------------------------------------------------

@app.get("/api/sounds")
async def sound_list():
    return {"sounds": sounds.catalogue()}


@app.get("/api/sounds/{effect_id}.wav")
async def sound_preview(effect_id: str):
    """The effect on its own, for the listen button."""
    try:
        data = await asyncio.to_thread(sounds.wav_bytes, effect_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=i18n.t("No such sound."))
    return Response(content=data, media_type="audio/wav",
                    headers={"Cache-Control": "private, max-age=86400"})


class SoundIn(BaseModel):
    effect: str = Field(default="", max_length=32)
    at: float = Field(default=0.0, ge=0, le=3600)


@app.post("/api/gallery/{item_id}/sound")
async def gallery_sound(item_id: str, body: SoundIn, request: Request):
    """Drop one of the sound effects into a video, as a new video."""
    _require_open()
    _require_warmed_up(request)
    _may_change(request, item_id)
    try:
        new_id = await asyncio.to_thread(gallery.add_sound, item_id, body.effect, body.at)
    except GalleryError as exc:
        log.warning("sound refused for %s: %s", item_id, exc)
        raise HTTPException(status_code=400, detail=i18n.t("That one can't have a sound added."))
    except Exception:
        log.exception("sound effect failed")
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't add that sound. Try again!"))
    return {"gallery_id": new_id}


@app.get("/api/gallery/{item_id}/thumb")
async def gallery_thumb(item_id: str):
    """A small cover-cropped tile for any item - what grids should ask for."""
    try:
        path = gallery.thumb(item_id)
    except GalleryError:
        path = None
    if path is None:
        raise HTTPException(status_code=404, detail=i18n.t("No picture for that one."))
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"}
    )


@app.get("/api/gallery/{item_id}/poster")
async def gallery_poster(item_id: str):
    """A still frame of a video, so thumbnails can be plain images."""
    try:
        path = gallery.poster(item_id)
    except GalleryError:
        path = None
    if path is None:
        raise HTTPException(status_code=404, detail=i18n.t("No picture for that one."))
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )


@app.get("/api/gallery/{item_id}/last-frame")
async def gallery_last_frame(item_id: str):
    """The final frame of a video, for the "what happens next?" thumbnail."""
    try:
        png = gallery.last_frame(item_id)
    except (GalleryError, OSError):
        raise HTTPException(status_code=404, detail=i18n.t("No picture for that one."))
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=3600"})


class FavouriteIn(BaseModel):
    on: bool = True


@app.put("/api/gallery/{item_id}/favourite")
async def gallery_favourite(item_id: str, body: FavouriteIn, request: Request):
    _may_change(request, item_id)
    try:
        meta = gallery.set_favourite(item_id, body.on)
    except GalleryError:
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone!"))
    except OSError as exc:
        log.error("could not star %s: %s", item_id, exc)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't save that. Try again!"))
    return {"id": item_id, "favourite": bool(meta.get("favourite"))}


class FamilyIn(BaseModel):
    on: bool = True


@app.put("/api/gallery/{item_id}/family")
async def gallery_family(item_id: str, body: FamilyIn, request: Request):
    """Put one of their own things where the whole family can see it.

    The middle ground between a gallery each and the parent switch that shows
    everybody everything: they share one picture, and it turns up on a Family
    shelf in every profile without the curtain coming down on the rest.

    `_may_change` and nothing beyond it, which is the whole gate: only the
    maker - or a grown-up with the PIN - can put something on the shelf, and
    only they can take it off again. A sibling who can see a family item cannot
    unshare it, and cannot star, rename, trash or build on it either; nothing
    here loosens `belongs_to_me`.
    """
    _may_change(request, item_id)
    try:
        meta = gallery.set_family(item_id, body.on)
    except GalleryError:
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone!"))
    except OSError as exc:
        log.error("could not share %s with the family: %s", item_id, exc)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't save that. Try again!"))
    return {"id": item_id, "family": bool(meta.get("family"))}


class NameIn(BaseModel):
    name: str = Field(default="", max_length=gallery.MAX_NAME)


@app.put("/api/gallery/{item_id}/name")
async def gallery_name(item_id: str, body: NameIn, request: Request):
    """Their own name for something, instead of image_00007_.png."""
    _may_change(request, item_id)
    name = body.name.strip()
    if name:
        ok, message, category = safety.check_prompt(name)
        if not ok:
            log.info("name rejected (%s)", category)
            raise HTTPException(status_code=400, detail=message)
    try:
        meta = gallery.set_name(item_id, name)
    except GalleryError:
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone!"))
    except OSError as exc:
        log.error("could not name %s: %s", item_id, exc)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't save that. Try again!"))
    return {"id": item_id, "name": meta.get("name") or ""}


class TagIn(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=200)
    tag: str = Field(default="", max_length=gallery.MAX_TAG)
    on: bool = True


@app.post("/api/gallery/tag")
async def gallery_tag(body: TagIn, request: Request):
    """Add or remove one tag, on one thing or on everything they have chosen."""
    for one in body.ids:
        _may_change(request, one)
    tag = body.tag.strip()
    if not tag:
        raise HTTPException(status_code=400, detail=i18n.t("Type a word for the tag first!"))
    ok, message, category = safety.check_prompt(tag)
    if not ok:
        log.info("tag rejected (%s)", category)
        raise HTTPException(status_code=400, detail=message)

    tagged = []
    for item_id in body.ids:
        try:
            gallery.set_tag(item_id, tag, body.on)
            tagged.append(item_id)
        except (GalleryError, OSError) as exc:
            log.warning("could not tag %s: %s", item_id, exc)
    return {"tagged": tagged, "tag": tag, "on": body.on, "tags": gallery.all_tags()}


@app.get("/api/gallery/trash")
async def gallery_trash():
    return {"items": gallery.trash_listing(), "days": gallery.trash_days()}


@app.get("/api/gallery/trash/{item_id}/file")
async def gallery_trash_file(item_id: str):
    try:
        path = gallery.trash_path_for(item_id)
    except GalleryError:
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone for good."))
    return FileResponse(path, media_type=gallery.media_type(item_id),
                        headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/gallery/trash/{item_id}/poster")
async def gallery_trash_poster(item_id: str):
    """Something showable for a trashed item: a video's first frame, or a
    song's waveform. Without it the parent page put an <img> in front of an
    mp3 and drew a row of broken-image icons."""
    try:
        path = gallery.still(item_id, trashed=True)
    except GalleryError:
        path = None
    if path is None:
        raise HTTPException(status_code=404, detail=i18n.t("No picture for that one."))
    return FileResponse(path, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=3600"})


@app.post("/api/gallery/trash/{item_id}/restore")
async def gallery_restore(item_id: str, request: Request):
    _may_change(request, item_id, trashed=True)
    try:
        gallery.restore(item_id)
    except GalleryError:
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone for good."))
    except OSError as exc:
        log.error("could not restore %s: %s", item_id, exc)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't put that back. Try again!"))
    return {"restored": item_id}


@app.delete("/api/gallery/trash/{item_id}")
async def gallery_destroy(item_id: str, request: Request):
    _may_change(request, item_id, trashed=True)
    try:
        gallery.destroy(item_id)
    except GalleryError:
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone already!"))
    except OSError as exc:
        log.error("could not destroy %s: %s", item_id, exc)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't delete that. Try again!"))
    return {"destroyed": item_id}


@app.delete("/api/gallery/{item_id}")
async def gallery_delete(item_id: str, request: Request):
    _may_change(request, item_id)
    try:
        gallery.delete(item_id)
    except GalleryError:
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone already!"))
    except OSError as exc:
        log.error("could not delete %s: %s", item_id, exc)
        raise HTTPException(
            status_code=500, detail=i18n.t("Couldn't delete that one. Try again!")
        )
    return {"deleted": item_id}


class CharacterIn(BaseModel):
    name: str = Field(default="", max_length=30)
    gallery_id: str = Field(default="", max_length=200)


@app.get("/api/characters")
async def character_list():
    """The cast, each with how much they are in - the managing page wants both
    and asking for a count per character would be one scan of the directory
    each."""
    cast = characters.listing()
    counts: dict[str, int] = {}
    for item in gallery.listing():
        who = item.get("character")
        if who:
            counts[who] = counts.get(who, 0) + 1
    for character in cast:
        character["works"] = counts.get(character["id"], 0)
    return {"characters": cast, "max": characters.limit()}


@app.post("/api/characters")
async def character_add(body: CharacterIn):
    """Turn a picture they have already made into someone they can use again.

    The vision model writes the one sentence that gets repeated in later
    prompts; the picture is kept too, so animating *that* gives an identical
    starting frame where a prompt only gives a family resemblance.
    """
    ok, message, category = safety.check_prompt(body.name)
    if not ok:
        log.info("character name rejected (%s)", category)
        raise HTTPException(status_code=400, detail=message)
    try:
        data, media = gallery.read_bytes(body.gallery_id)
        if media == "video":
            data = gallery.last_frame(body.gallery_id)
    except (GalleryError, OSError):
        raise HTTPException(status_code=400, detail=i18n.t("Pick a picture first!"))

    await _clear_card_for_ollama()
    try:
        look = await scripts.look(data)
    except scripts.ScriptError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        return characters.add(body.name, look, body.gallery_id)
    except characters.CharacterError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        log.error("could not save the character: %s", exc)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't save them. Try again!"))


class CharacterEditIn(BaseModel):
    name: str | None = Field(default=None, max_length=30)
    look: str | None = Field(default=None, max_length=300)


@app.put("/api/characters/{character_id}")
async def character_edit(body: CharacterEditIn, character_id: str):
    """Rename them, or reword how they look.

    The look is checked like anything else they type, because it goes straight
    into every prompt they appear in - it is the one field here that reaches
    ComfyUI verbatim.
    """
    for field in (body.name, body.look):
        if field is None:
            continue
        ok, message, category = safety.check_prompt(field)
        if not ok:
            log.info("character edit rejected (%s)", category)
            raise HTTPException(status_code=400, detail=message)
    try:
        return characters.update(character_id, name=body.name, look=body.look)
    except characters.CharacterError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        log.error("could not save the character: %s", exc)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't save them. Try again!"))


@app.delete("/api/characters/{character_id}")
async def character_remove(character_id: str):
    try:
        characters.remove(character_id)
    except OSError as exc:
        log.error("could not remove the character: %s", exc)
        raise HTTPException(status_code=500, detail=i18n.t("Couldn't do that. Try again!"))
    return {"removed": character_id}


@app.get("/api/characters/{character_id}/works")
async def character_works(character_id: str):
    """Everything this character is in.

    Only what was made *after* the character was picked on the card carries the
    tag, because that is when it started being written down - so their own
    picture is always included, even if nothing else is yet.
    """
    who = characters.get(character_id)
    if who is None:
        raise HTTPException(status_code=404, detail=i18n.t("Who's that?"))
    items = [i for i in gallery.listing() if i.get("character") == character_id]
    if who.get("picture_id") and not any(i["id"] == who["picture_id"] for i in items):
        for item in gallery.listing():
            if item["id"] == who["picture_id"]:
                items.append(item)
                break
    items.sort(key=lambda i: i["created"], reverse=True)
    return {"character": who, "items": items}


class RemixIn(BaseModel):
    kind: str = "image"


@app.post("/api/remix")
async def remix(body: RemixIn):
    """One of their old ideas, with a brand new set of looks on it.

    Instant when they have asked for something before, which is almost always;
    the first few times they tap it there is no history to draw on, so it falls
    through to the same inventor the Surprise me button uses.
    """
    bucket = {"image": "image", "video": "video", "t2v": "video", "i2v": "video",
              "comic": "comic", "story": "video"}.get(body.kind, "image")
    past = gallery.prompt_history().get(bucket) or []
    groups = list(styles.COMIC_GROUPS) if bucket == "comic" else None
    # The card that asked, so the draw covers the dropdowns it actually has.
    picked = styles.random_selection(groups, body.kind)

    if past:
        import random as _random

        idea = _random.choice(past)
        return {"prompt": idea, "styles": picked,
                "preview": styles.compose(idea, picked), "from_history": True}

    await _clear_card_for_ollama()
    try:
        idea = await scripts.surprise(None)
        if bucket == "comic":
            idea = await scripts.story(idea)
    except scripts.ScriptError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"prompt": idea, "styles": picked,
            "preview": styles.compose(idea, picked), "from_history": False}


@app.get("/api/history")
async def prompt_history():
    """Everything they have asked for, newest first, so they can use it again."""
    return gallery.prompt_history()


@app.delete("/api/history")
async def prompt_history_clear(kind: str = "", idea: str = ""):
    """Forget one thing they wrote, one whole list, or everything."""
    return gallery.forget_prompts(kind, idea[:300])


@app.get("/api/app")
async def app_branding():
    """What this instance is called. The page starts with neutral wording in
    the HTML and fills this in, so nobody's name is baked into the markup."""
    me = profiles.resolve((gallery.WHO.get() or {}).get("id") or "")
    return {
        **branding.public(),
        "banner_custom": gallery.banner_path() is not None,
        # The page guesses from localStorage before the first paint, exactly as
        # it does with the colours; this is the authority, so a language chosen
        # on another browser is corrected rather than flashing.
        "lang": i18n.lang(),
        "theme": gallery.get_settings().get("theme") or themes.DEFAULT,
        "themes": themes.public(),
        # Who is using it. A household with one child gets `pick: false` and
        # never sees a sign-in screen - the cost of this to somebody who does
        # not want it should be nothing, not one extra tap forever.
        "me": {"id": me["id"], "name": me["name"], "emoji": me.get("emoji"),
               "colour": me.get("colour"), "avatar": profiles.has_avatar(me["id"])},
        "pick": profiles.several(),
    }


# --- who is using it --------------------------------------------------------

@app.get("/api/profiles")
async def profiles_list():
    """The picker. Public on purpose: it is a list of first names on a LAN app
    with no login, and the thing it guards - changing the rules - has its own
    gate on every route that does it."""
    me = (gallery.WHO.get() or {}).get("id") or ""
    return {"who": profiles.public(me), "shared": profiles.shared(),
            "pick": profiles.several(), "locked": bool(parent_pin()),
            **profiles.faces()}


class PickIn(BaseModel):
    id: str = Field(default="", max_length=40)


@app.post("/api/profiles/pick")
async def profiles_pick(body: PickIn):
    """Sign in as somebody. The page reloads afterwards rather than repainting:
    the title, the colours, the gallery, the tabs and the daily counts all
    belong to whoever was picked, and putting them back one by one is a long
    list of things to forget."""
    who = profiles.get(body.id)
    if who is None:
        raise HTTPException(status_code=404, detail=i18n.t("I don't know who that is."))
    audit.record("profile.switched", actor=who["id"], name=who["name"])
    reply = JSONResponse({"id": who["id"], "name": who["name"]})
    reply.set_cookie(WHO_COOKIE, who["id"], max_age=WHO_COOKIE_DAYS * 86400,
                     httponly=True, samesite="lax", path="/")
    return reply


class ProfileIn(BaseModel):
    name: str = Field(default="", max_length=profiles.MAX_NAME)
    emoji: str = Field(default="", max_length=8)
    colour: str = Field(default="", max_length=9)
    age: int | None = Field(default=None, ge=0, le=19)


@app.post("/api/profiles")
async def profiles_add(body: ProfileIn, request: Request):
    """Add somebody. Behind the parent PIN when there is one.

    Not because a name is sensitive, but because a new profile starts with its
    own daily allowance: without this, the way round "three pictures a day" is
    to make a fourth child, and any eleven-year-old works that out in a week.
    """
    _parent(request)
    try:
        return profiles.add(body.name, body.emoji, body.colour, body.age or 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        log.error("could not add a profile: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save that")


# Above `/api/profiles/{pid}` on purpose. Routes are matched in the order
# they are declared, and with this one second "shared" was read as a
# profile id and answered "no such profile".
class SharedIn(BaseModel):
    shared: bool = False


@app.put("/api/profiles/shared")
async def profiles_shared(body: SharedIn, request: Request):
    """Whether everybody sees everybody's work. Off by default - the point of
    a profile is that it is yours - but siblings who make things together want
    one gallery, and nothing else about their rules has to be shared for it."""
    _parent(request)
    try:
        profiles.set_shared(body.shared)
    except OSError as exc:
        log.error("could not save that: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save that")
    return {"shared": profiles.shared()}


@app.put("/api/profiles/{pid}")
async def profiles_update(pid: str, body: ProfileIn, request: Request):
    """Rename, recolour, or say how old somebody is.

    The face and the colour are the child's own - they are picked in their
    Settings tab - so those two do not need the PIN. The name and the age do:
    the age is what every helper model is told to write for.
    """
    wants_grownup = body.name != "" or body.age is not None
    if wants_grownup or pid != ((gallery.WHO.get() or {}).get("id") or ""):
        _parent(request)
    try:
        return profiles.update(pid, name=body.name or None, emoji=body.emoji,
                               colour=body.colour, age=body.age)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        log.error("could not save a profile: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save that")


@app.delete("/api/profiles/{pid}")
async def profiles_remove(pid: str, request: Request):
    _parent(request)
    try:
        profiles.remove(pid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        log.error("could not remove a profile: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save that")
    return {"ok": True, "who": profiles.public()}


@app.get("/api/profiles/{pid}/avatar")
async def profiles_avatar(pid: str):
    who = profiles.get(pid)
    if who is None or not profiles.has_avatar(pid):
        raise HTTPException(status_code=404, detail=i18n.t("No picture for that one."))
    return FileResponse(profiles.avatar_path(pid), media_type="image/png",
                        headers={"Cache-Control": "no-cache"})


class FaceIn(BaseModel):
    # Something already in their gallery. Making the picture is the ordinary
    # picture route with a square shape - there is no separate avatar
    # generator, and there should not be one.
    gallery_id: str = Field(default="", max_length=200)


@app.post("/api/profiles/{pid}/avatar")
async def profiles_set_avatar(pid: str, body: FaceIn, request: Request):
    """Use one of their own pictures as their face.

    Only their own, and only for themselves: a sibling should not be able to change
    somebody else's face, and that is the one thing about a profile that is
    visible to the whole household.
    """
    mine = (gallery.WHO.get() or {}).get("id") or ""
    if pid != mine:
        _parent(request)
    if profiles.get(pid) is None:
        raise HTTPException(status_code=404, detail=i18n.t("I don't know who that is."))
    _may_change(request, body.gallery_id)
    try:
        path = gallery.path_for(body.gallery_id)
        data = path.read_bytes()
    except (GalleryError, OSError):
        raise HTTPException(status_code=404, detail=i18n.t("I can't find that picture."))
    try:
        await asyncio.to_thread(profiles.save_avatar, pid, data)
    except Exception as exc:
        log.warning("could not make an avatar out of %s: %s", body.gallery_id, exc)
        raise HTTPException(status_code=400, detail=i18n.t("That one won't work as a picture of you."))
    return {"ok": True}


@app.delete("/api/profiles/{pid}/avatar")
async def profiles_clear_avatar(pid: str, request: Request):
    mine = (gallery.WHO.get() or {}).get("id") or ""
    if pid != mine:
        _parent(request)
    try:
        profiles.clear_avatar(pid)
    except (ValueError, OSError):
        pass
    return {"ok": True}


@app.get("/api/estimate")
async def estimate(kind: str = "image", duration: int = 0, orientation: str = "landscape",
                   quality: str = workflows.DEFAULT_QUALITY, count: int = 1,
                   parts: int = 1):
    """How long this will probably take, from what this machine has done.

    Nothing is assumed: with no history it says so, and the page says so too.
    The alternative was a table of seconds measured on one graphics card, which
    would be wrong on everybody else's.
    """
    # MAX_BATCH is the "four at once" limit on the Picture tab; a comic asks
    # about its panels, and there can be six of those. Clamping to 4 here told
    # them a six-panel comic would take a four-panel comic's time.
    most = max(workflows.MAX_BATCH, comic.MAX_PANELS)
    return await asyncio.to_thread(
        timings.estimate, kind, duration or None, orientation,
        quality if quality in workflows.QUALITY else workflows.DEFAULT_QUALITY,
        max(1, min(most, count)), max(1, min(10, parts)),
    )


@app.get("/api/styles")
async def style_options():
    """The dropdowns for each card, for the page to build itself from."""
    return {
        "music": music.options(),
        # [min, default, max] for each slider. The page used to carry these as
        # literals in the HTML, which meant two places to change and one of
        # them silently wrong when the environment moved.
        "music_seconds": [music.MIN_SECONDS, music.DEFAULT_SECONDS, music.MAX_SECONDS],
        # The "What kind of sound" chips, each carrying its own [min, default,
        # max] - the slider has to move when they change the chip, because a
        # ninety-second jingle is not a jingle.
        "music_kinds": music.kind_options(),
        "video_seconds": [workflows.MIN_DURATION, workflows.DEFAULT_DURATION,
                          workflows.MAX_DURATION],
        "quality_max": workflows.QUALITY_MAX_SECONDS,
        # The page reveals the Music tab on this rather than on a second call:
        # it already waits for these dropdowns before the card is usable.
        "music_ready": music_ready(),
        # And which makers exist at all - a parent's switches crossed with what
        # this machine can actually do. The page hides a tab on this; the
        # routes refuse regardless, which is the half that counts.
        "modules": modules.states({"music": music_ready()}),
        # The Story tab borrows the other three makers, so it needs to know
        # which of its steps can run - one switched off is a step it skips,
        # not a tab that disappears. The film is the exception; the page hides
        # the tab on that one, and `_require_module` refuses regardless.
        "story_steps": modules.story_steps({"music": music_ready()}),
        "image": styles.options("image"),
        "video": styles.options("video"),
        "comic": styles.options("comic"),
        # The "Turn it into..." chips. Here rather than on a route of their
        # own because the page already waits for this one before anything is
        # usable, and a second fetch for a row of eight buttons would be a
        # request per load to save nothing.
        "restyles": restyles.choices(),
    }


async def _clear_card_for_ollama() -> None:
    """Hand the GPU to Ollama before asking it anything.

    Ollama silently falls back to CPU if a model will not fit in VRAM, and with
    ComfyUI's models resident there is not enough room. The symptom is just
    "the idea helper got slow", which is nearly impossible to guess at, so the
    card is cleared first rather than hoped about.
    """
    await client.free()


@app.post("/api/surprise")
async def surprise(body: ScriptIn):
    """An idea out of thin air, plus a random look to go with it."""
    seconds = workflows.clamp_duration(body.duration) if body.duration else None
    await _clear_card_for_ollama()
    try:
        idea = await scripts.surprise(seconds)
        # A comic needs something to happen, so the invented idea gets turned
        # into a little story rather than staying a single scene.
        if body.kind in ("comic", "story"):
            idea = await scripts.story(idea)
    except scripts.ScriptError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if body.kind == "music":
        # A song's dropdowns are its own vocabulary, not the picture one - and
        # a surprise song with no words is half a surprise, so the words come
        # back in the same answer rather than leaving them to tap a second
        # button before anything is singable.
        sound = music.kind_of(body.sound_kind)
        picked = music.random_selection(sound)
        words = {}
        # Nothing is sung on a tune or a hum, so there is nothing to invent
        # and no call to spend waiting for it.
        if music.sings(sound):
            try:
                words = await music.write(idea, picked)
            except scripts.ScriptError as exc:
                # The idea is still good on its own; they can write their own
                # words, or tap the helper. Better than losing the whole
                # surprise.
                log.info("surprise song words unavailable: %s", exc)
        return {"prompt": idea, "styles": picked,
                "lyrics": words.get("lyrics", ""),
                "preview": music.compose_tags(idea, picked,
                                              music.sings(sound), sound)}
    groups = list(styles.COMIC_GROUPS) if body.kind == "comic" else None
    # The card that asked, so the draw covers the dropdowns it actually has.
    picked = styles.random_selection(groups, body.kind)
    return {"prompt": idea, "styles": picked, "preview": styles.compose(idea, picked)}


@app.post("/api/script")
async def write_script(body: ScriptIn):
    """Expand a one-line idea into a video prompt with a spoken line.

    With a picture named, the model looks at the picture instead and writes a
    prompt that animates what is actually in it - so a drawing they upload
    comes back with a script about *their* drawing.
    """
    seconds = workflows.clamp_duration(body.duration)
    image = await _source_image_bytes(body)
    await _clear_card_for_ollama()
    try:
        if image is not None:
            # A picture made here has its own words on file. The model sees
            # the picture either way, but the words name what it might only
            # guess at - the character, the style they chose - so they go in
            # as context. A photo they uploaded has none, and that is fine.
            made_from = ""
            if body.source_gallery_id:
                for item in gallery.listing():
                    if item["id"] == body.source_gallery_id:
                        made_from = item.get("idea") or item.get("prompt") or ""
                        break
            return await scripts.describe(image, body.prompt, seconds, made_from)
        if body.kind == "picture":
            return {"prompt": await scripts.picture(body.prompt)}
        if body.kind in ("comic", "story"):
            # The same helper: a comic and a story both need something to
            # *happen*, and "a hedgehog in a pond" is a picture, not a story.
            return {"prompt": await scripts.story(body.prompt)}
        return {"prompt": await scripts.generate(body.prompt, seconds)}
    except scripts.ScriptError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --- someone to talk to -----------------------------------------------------

class ChatIn(BaseModel):
    message: str = Field(default="", max_length=chat.MAX_MESSAGE_CHARS)
    # The page holds the conversation and sends it back each turn. Trusted only
    # as far as chat.reply trims and re-checks it - it comes from the browser.
    history: list[dict] = Field(default_factory=list, max_length=60)


@app.get("/api/chat")
async def chat_ready():
    """Whether the chat tab should offer anything, and what to open with."""
    return {
        # Both halves of "can they use this": a parent's switch, and whether
        # Ollama has the model at all.
        "ready": modules.enabled("chat") and await chat.available(),
        "name": chat.helper_name(),
        "greeting": chat.greeting(),
        "model": chat.model(),
    }


@app.post("/api/chat")
async def chat_say(body: ChatIn, request: Request):
    """One turn with the helper.

    Refused while something is rendering, and that is not politeness: the chat
    model is 7.6GB and a video render peaks near 15.5GB of a 16.3GB card, so
    the two genuinely cannot both be resident. Asking anyway would push Ollama
    onto the CPU and make them wait minutes for a sentence.
    """
    _require_open()
    _require_module("chat")
    _require_warmed_up(request)
    if registry.active() is not None:
        raise HTTPException(
            status_code=409,
            detail=i18n.t("The factory is busy making your video! Chat to me when it's done."),
        )
    # Chat and ComfyUI want the same card. ComfyUI is not using it right now -
    # that was just checked - so it can let go of it.
    await _clear_card_for_ollama()
    try:
        return await chat.reply(body.message, body.history)
    except chat.ChatError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/job/{job_id}/cancel")
async def cancel_job(job_id: str):
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone already."))
    await registry.cancel(job_id)
    audit.record("render.cancelled", id=job.id, kind=job.kind, words=job.idea)
    return job.public()


class QuizIn(BaseModel):
    token: str = Field(default="", max_length=64)
    answers: list[str] = Field(default_factory=list, max_length=10)


@app.get("/api/quiz")
async def quiz_get(request: Request):
    """Whether they still owe the factory three sums today, and if so, which.

    A closed factory means no sums. Warming up for a door that will not open is
    a mean trick, and the "back soon" sign should be the only thing they see.
    They will be asked when it reopens - the pass is per calendar day, so being
    closed this morning costs them nothing later.
    """
    settings = gallery.get_settings()
    paused = bool(settings.get("paused")) or not schedule.state(settings)["open"]
    if paused or _warmed_up(request):
        return {"needed": False, "paused": paused, **quiz.status()}
    return {
        "needed": True,
        "message": quiz.friendly(),
        # Only offer the grown-up box when there is a PIN to check it against;
        # without one it would be a "skip" button with their name on it.
        "grownup": bool(parent_pin()),
        **quiz.make(),
        **quiz.status(),
    }


@app.post("/api/quiz")
async def quiz_post(body: QuizIn, response: Response):
    """Mark them. All three right sets the cookie and opens the factory."""
    passed, wrong = quiz.mark(body.token, body.answers)
    if not passed:
        # Any wrong answer means three new sums, not another go at the same
        # one: retrying a single question is a guessing game, and the point is
        # the arithmetic.
        return {"passed": False, "wrong": wrong, **quiz.make()}

    quiz.record_pass()
    response.set_cookie(
        quiz.COOKIE,
        quiz.cookie_for(quiz.today()),
        max_age=quiz.seconds_left_today(),
        httponly=True,
        samesite="lax",
        path="/",
    )
    log.info("they passed today's sums")
    return {"passed": True, "wrong": []}


class GrownupIn(BaseModel):
    pin: str = Field(default="", max_length=64)


@app.post("/api/quiz/grownup")
async def quiz_grownup(body: GrownupIn, response: Response):
    """A grown-up past the sums for an hour, without spending their go at them.

    Nothing is written down: this sets a short, clock-limited cookie and leaves
    `quiz_passed_day` alone, so they still owe the factory three sums today.
    The parent page's "let them skip them today" is the other thing, and it is
    deliberately a different button in a different place.
    """
    if not parent_pin():
        raise HTTPException(status_code=404, detail="No grown-up PIN is set.")
    # Bolted shut from Telegram. /lock says in so many words that it closes
    # this box too, and the whole point of it is that knowing the PIN is not
    # enough - so it is checked before the PIN is, exactly as in _parent().
    if gallery.get_settings().get("parent_locked"):
        raise HTTPException(
            status_code=403,
            detail="This is locked. Unlock it from Telegram with /unlock.",
        )
    # This is the box `pinbox.SHARED` is named for, and the only one of the
    # three a child can reach without finding an open parent page. Nothing
    # clears it on the way in any more: a correct *header* stopped forgiving
    # when it turned out a parent's open tab was handing these guesses back
    # every thirty seconds. See `_forgive()`.
    _refuse_if_locked(pinbox.SHARED)
    if not hmac.compare_digest(body.pin, parent_pin()):
        _bad_pin(pinbox.SHARED)
        raise HTTPException(status_code=403, detail="That's not the right PIN.")

    # Typed, and right: this one does forgive.
    pinbox.SHARED.clear()
    minutes = quiz.parent_minutes()
    seconds = minutes * 60
    response.set_cookie(
        quiz.PARENT_COOKIE,
        quiz.grownup_cookie(int(time.time()) + seconds),
        max_age=seconds,
        httponly=True,
        samesite="lax",
        path="/",
    )
    log.info("a grown-up skipped the sums for %d minutes", minutes)
    return {"ok": True, "minutes": minutes}


@app.get("/api/allowance")
async def allowance(request: Request):
    """What is left today, and whether the factory is open.

    Deliberately cheap - the page polls it every minute and after every job,
    so unlike /api/health it talks to nothing but the gallery directory.
    """
    settings = gallery.get_settings()
    switched_off = bool(settings.get("paused"))
    when = schedule.state(settings)
    shut = switched_off or not when["open"]
    return {
        # `paused` stays the "they cannot make anything" flag the page has
        # always keyed off, so the timetable needed no new branch there - it
        # only needed somewhere to put the sentence.
        "paused": shut,
        "by_hand": switched_off,
        # The overlay already says it is closed, in large letters over a
        # sleeping factory, so it gets the when on its own; a 503 body has no
        # such heading and gets the whole sentence.
        "closed_sub": (i18n.t("Back soon!") if switched_off
                       else schedule.reopen_line(when) if shut else ""),
        "opens_at": None if switched_off or when["open"] else when["opens"],
        # Only while it really is about to shut. "Closes at six" on a page
        # opened at ten in the morning is nagging, not a warning.
        "closes_in": (when["left"] if not shut and when["left"] is not None
                      and when["left"] <= CLOSING_SOON else None),
        "closes_at": None if shut or when["until"] is None else schedule.friendly(when["until"]),
        "allowance": gallery.allowance(),
        # Never while closed: the "back soon" sign is the whole message then.
        "quiz_needed": not shut and not _warmed_up(request),
    }


@app.get("/api/now")
async def now():
    """The live numbers, and nothing else.

    The status sheet ticks its GPU strip every two seconds, and it stays open
    for a moment after a job has finished - when nothing is polling
    `/api/job/{id}` any more. It cannot use `/api/health` for that: health
    pings ComfyUI *and* Ollama on every call, and asking those two every two
    seconds to draw a percentage would be a poll of two other services for the
    sake of a line of text. This one touches nothing off the box: `snapshot()`
    is filled in by the sampler task once a second, and `ahead` is what the
    job's own loop last read off ComfyUI's /queue.
    """
    job = registry.active()
    return {
        "system": stats.snapshot(),
        "busy": job is not None,
        "job": job.id if job else None,
        # How many jobs ComfyUI has in front of theirs. Almost always nothing:
        # this app runs one at a time, so anything here is somebody using
        # ComfyUI directly.
        "ahead": job.ahead if job else None,
    }


@app.get("/api/active")
async def active_job():
    """The job currently running, if any.

    Generation happens server-side, so reloading the page does not stop
    anything - but without this the page would forget the job id and show
    nothing while the render carried on. The page asks on load and reattaches.
    """
    job = registry.active()
    return {"job": job.public() if job else None}


@app.get("/api/job/{job_id}")
async def job_status(job_id: str):
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=i18n.t("That one's gone. Make a new one!"))
    payload = job.public()
    # Live machine numbers ride along with every poll, so the page can show
    # "GPU 98%" next to the bar without a second request.
    payload["system"] = stats.snapshot()
    # And, on the poll that sees a job finish, whether that just took their past
    # a round number. Checked here rather than in the job so it also catches
    # a comic page or a drawing, which are uploads, not jobs.
    if job.status == "done":
        payload["milestone"] = gallery.milestone_reached()
    return payload


@app.get("/api/result/{job_id}")
async def job_result(job_id: str, download: int = 0):
    job = registry.get(job_id)
    if job is None or job.status != "done" or not job.result:
        raise HTTPException(status_code=404, detail=i18n.t("That one isn't ready yet."))

    filename = job.result["filename"]
    suffix = Path(filename).suffix.lower()
    media_type = MEDIA_TYPES.get(suffix, "application/octet-stream")

    label = "song" if job.is_audio else "video" if job.is_video else "picture"
    headers = {"Cache-Control": "private, max-age=3600"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="my-{label}-{job.id}{suffix}"'

    # From the gallery, where the file has been under its own name since the
    # second it landed - ComfyUI's `/view` knows it by the name it wrote, and
    # that is no longer the name it has. A FileResponse also answers a Range
    # request, which a proxied stream cannot and iOS will not play without.
    try:
        return FileResponse(gallery.path_for(Path(filename).name),
                            media_type=media_type, headers=headers)
    except (GalleryError, OSError):
        return StreamingResponse(
            client.stream_view(job.result), media_type=media_type, headers=headers
        )


# One alert per ten minutes, however many guesses there are - except the one
# that trips the lockout, which always goes. A child at the keypad should not
# be able to fill a mailbox.
PIN_ALERT_EVERY = 600.0
_last_pin_alert = 0.0


def _bad_pin(box, where: str = "") -> None:
    """Count a wrong PIN against the box it was typed into, and, if the
    grown-ups asked to be told, tell them.

    **The box is the caller's to choose**, and it is the only place a wrong
    guess is counted. Four boxes count separately - see `app/pinbox.py` - so
    that no box can be used to lock another; passing the wrong one here would
    quietly undo that. `where` overrides the box's own wording for the alert
    where one box is reached two ways: a wrong header is "parent page" from the
    gate and "another child's gallery" from `_grownup()`, which is the same
    box and two different things for a parent to be told.

    The rate limit is here rather than in the two senders, so that one limit
    covers the email and the phone message together.
    """
    global _last_pin_alert
    where = where or box.where
    tries = box.note()
    locked = box.locked_for() > 0
    now = time.time()
    # Every wrong guess is written down, not only the ones that send an alert:
    # the rate limit below is there so a child at the keypad cannot fill a
    # mailbox, and it has nothing to do with what the log should contain.
    audit.record("pin.failed", actor=audit.PARENT, where=where, tries=tries)
    if locked:
        audit.record("pin.lockout", actor=audit.PARENT, where=where, tries=tries)
    if not locked and now - _last_pin_alert < PIN_ALERT_EVERY:
        return
    _last_pin_alert = now
    _fire(notify.bad_pin(where, tries, locked))
    _fire(digest.pin_notice(where, tries, locked))


# The parent page calls a dozen routes on load and then polls every thirty
# seconds, so one entry per request would be a log of nothing but itself. One
# entry per session-ish window is the useful fact: somebody opened it.
PARENT_OPEN_EVERY = 600
_last_parent_open = 0.0


def _parent_did_this() -> None:
    """Past the gate: note whose request this is, and that the page was opened.

    Everything the request writes from here on is the parent's doing, not the
    doing of whichever child their browser happens to be signed in as - which
    is what stops every household setting saved on the Rules tab going into
    the log against a nine-year-old's name.
    """
    audit.BY_PARENT.set(True)
    global _last_parent_open
    now = time.time()
    if now - _last_parent_open < PARENT_OPEN_EVERY:
        return
    _last_parent_open = now
    audit.record("parent.opened", actor=audit.PARENT)


# The page sends this beside the PIN on the requests that follow somebody
# actually typing it into the gate box, and on no others. It is the difference
# between "a person is here and knows the PIN" and "a tab is open", which is
# the difference `_forgive()` needs and a header alone cannot express.
TYPED_HEADER = "x-parent-pin-typed"


def _forgive(request: Request) -> None:
    """A correct PIN that somebody just typed: forget the wrong guesses.

    "A correct PIN forgives the misses" is a rule worth keeping - a parent who
    fumbles their own PIN four times and then gets it right should not spend
    ten minutes locked out of their own page - but it was being applied to the
    wrong thing. `_parent()` runs on every request the parent page makes, and
    the parent page holds the PIN in sessionStorage and sends it as a header
    from then on: it polls every thirty seconds, unattended, with nobody at the
    keyboard. Every one of those polls was forgiving the misses.

    That mattered most somewhere else entirely. The lockout being cleared is
    the *shared* one, and the box it protects is the grown-up box on the sums -
    which is on the child's own page. So a parent's tab left open on a laptop
    was quietly handing back the guesses a child was spending on the iPad, five
    at a time, for as long as it stayed open. Neither person could have known.

    So only a deliberate entry forgives. The page marks those requests, and
    nothing else carries the marker. A child who can set the header by hand has
    devtools open on a tab whose sessionStorage already holds the PIN, and is
    past this either way; what this stops is the app undoing its own lockout
    while nobody is looking.

    **Two boxes, not four.** The gate, because that is what was just typed
    into, and the sums overlay, because a grown-up standing at the parent page
    is the person that box exists to let through and it is unkind to make them
    wait out a child's guesses. The PIN-change and grown-up-mode boxes forgive
    on their own typed PINs and not on this one: each of those is a second
    deliberate act, and signing in should not silently hand back tries at the
    two things inside the page that are worth guessing at.
    """
    if request.headers.get(TYPED_HEADER):
        pinbox.GATE.clear()
        pinbox.SHARED.clear()


def _parent(request: Request) -> None:
    """Gate for the parent page. No PIN configured means no gate - it is a LAN
    app - but a PIN in compose keeps them from wandering into it.

    Wrong headers get five tries and ten minutes like every other way of
    offering this PIN - `pinbox.GATE`, which this shares with `_grownup()`
    because it is the same credential presented the same way. A *missing*
    header is not a guess - the page asks without one on first load and then
    prompts - so only a wrong one counts.

    **It is deliberately not the sums overlay's counter**, which it used to be.
    That box is on the child's own page, and once its count stopped being wiped
    by this page's own polling, sharing the refusal would have meant a child
    could lock their parent out of the parent page - and out of the typed PIN
    that is the way back - with five wrong guesses at their own screen. See
    `app/pinbox.py`.

    A correct header clears a lockout only when the page says somebody typed
    the PIN - see `_forgive()`, which is the whole of that story.
    """
    # Bolted shut from Telegram, on top of the PIN. Checked before the PIN is
    # even looked at: the point of it is that knowing the PIN is not enough.
    if gallery.get_settings().get("parent_locked"):
        raise HTTPException(
            status_code=403,
            detail="This page is locked. Unlock it from Telegram with /unlock.",
        )
    if not parent_pin():
        _parent_did_this()
        return
    given = request.headers.get("x-parent-pin", "")
    if not given:
        raise HTTPException(status_code=401, detail="PIN please")
    _refuse_if_locked(pinbox.GATE)
    if not hmac.compare_digest(given, parent_pin()):
        _bad_pin(pinbox.GATE, "parent page")
        raise HTTPException(status_code=401, detail="PIN please")
    _forgive(request)
    _parent_did_this()


def _as_child(who: str) -> dict:
    """Run the rest of this parent route as one child.

    Everything that reads the request context then answers about them: the
    settings, the daily limits, which makers exist, the timetable, the sums.
    That is the whole reason the Rules tab needed no per-child plumbing of its
    own - it asks the same routes with `?who=` on the end.

    No reset: the middleware holds a token from before this ran and puts back
    what was there when the request ends, whatever happened in between.
    """
    chosen = profiles.resolve(who)
    gallery.WHO.set(profiles.context(chosen["id"]))
    branding.CHILD.set({"name": chosen.get("name") or "",
                        "age": chosen.get("age") or 0})
    return chosen


@app.get("/api/parent/summary")
async def parent_summary(request: Request, who: str = ""):
    _parent(request)
    # The dashboard is the household's - one day, every child - and the rules
    # are one child's. A parent looking at "Right now" wants to see the
    # afternoon, not to have to pick somebody first.
    chosen = _as_child(who)
    active = registry.active()
    items = gallery.listing(everyone=True)
    lt = time.localtime()
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    space = gallery.space()
    return {
        "today": gallery.usage_today(everyone=True),
        # What they actually made, not just how many - a glance at the day
        # without having to go into their gallery.
        "today_items": [i for i in items if i["created"] >= midnight],
        "favourites": [i["id"] for i in items if i["favourite"]],
        "all_ids": [i["id"] for i in items],
        "space": space,
        "total_items": len(items),
        "disk_mb": round(space["total"] / 1e6),
        "trash_count": len(gallery.trash_listing(everyone=True)),
        "refused": gallery.refused_listing(),
        "trash": gallery.trash_listing(everyone=True),
        "trash_days": gallery.trash_days(),
        "backups": backup.listing(),
        # Whose rules the rest of this answer is about, and everybody there is.
        "who": profiles.public(chosen["id"], grownup=True),
        "whose": chosen["id"],
        "shared": profiles.shared(),
        "profiles_max": profiles.MAX_PROFILES,
        "faces": profiles.faces(),
        "settings": gallery.public_settings(),
        # What the app would be called with the title box left empty, for that
        # box's placeholder. Worked out here rather than in the page, which
        # would need its own copy of the apostrophe rule to say it.
        "default_title": branding.default_title(),
        # Each maker with both of its states: whether a parent has it on, and
        # whether this machine can do it at all. They want different sentences.
        "modules": modules.listing({
            "music": music_ready(),
            "chat": await chat.available(),
        }),
        # Open by the clock: the week as rows the page can draw, plus what it
        # adds up to right now, so the verdict line does not have to work it
        # out a second time.
        "schedule": schedule.state(),
        "days": [{"id": d, "name": n} for d, n in
                 zip(schedule.DAYS, schedule.DAY_NAMES)],
        "close_choices": lockdown.CHOICES,
        # What a new file will be called, one pattern per kind. The page draws
        # its rows and its token list from this rather than carrying either as
        # HTML, so app/naming.py stays the only copy of both.
        "naming": naming.public(),
        # What is actually in force, which is not always what is stored: "-"
        # in the settings means "whatever CLOSE_ON_REFUSAL says".
        "close_on": lockdown.setting(),
        "allowance": gallery.allowance(),
        "digest": digest.settings(),
        "notify": notify.settings(),
        "telegram": telegram.settings(),
        "quiz": quiz.status(),
        # Enough of the log for the tab's heading; the entries come from
        # /api/parent/log, which is paged.
        "log": {"entries": audit.count(),
                "keep_days": audit.keep_days(),
                "keep_words": audit.keep_words()},
        # So the parent page can hide the song limit on a machine with no
        # music model rather than offer a control over nothing.
        "music": music_ready(),
        "chat": {"today": chat.today_count(), "name": chat.helper_name(),
                 "total": len(chat.transcript())},
        "busy": active.public() if active else None,
        "comfy_reachable": await client.reachable(),
        "ollama": await scripts.placement(),
        "ollama_last_run": scripts.last_run or None,
        "pin_required": bool(parent_pin()),
        # The deployment values: which of the parent page and `.env` is in
        # force for each, and whether a change needs a restart. **Never a
        # value for any of the five that are credentials** - see
        # app/config.py, and `parent_config()` below.
        "deployment": config.public_state(),
    }


@app.get("/api/parent/stats")
async def parent_stats(request: Request):
    """The machine, right now and for the last few minutes.

    Its own route rather than part of the summary: the graph wants it every
    couple of seconds and the summary is a listing of their whole gallery.
    """
    _parent(request)
    return {
        "now": stats.snapshot(),
        "history": stats.history(),
        "seconds": stats.HISTORY,
        "busy": (lambda j: j.public() if j else None)(registry.active()),
    }


# "0", "90", "60s", "5m", "1h", "-1" for "hold it for ever". Ollama takes a
# number of seconds or a Go duration; anything else it ignores silently, which
# on a settings page reads as the box doing nothing at all.
_KEEP_ALIVE = re.compile(r"^-?\d+(\.\d+)?(ns|us|ms|s|m|h)?$")


def _keep_alive(asked: str, safe: str) -> str:
    text = (asked or "").strip()
    if not text:
        return safe
    return text if _KEEP_ALIVE.match(text) else safe


class SettingsIn(BaseModel):
    """Everything the Rules tab can set. Every field is optional: the page
    sends the whole card it just saved, not the whole tab.

    There is no tri-state left here. A switch is 0 or 1 and means it; the
    environment seeded the row on the first start and is not consulted again.
    """
    paused: bool | None = None
    quiz_enabled: int | None = Field(default=None, ge=0, le=1)
    quiz_questions: int | None = Field(default=None, ge=1, le=10)
    quiz_bypass_minutes: int | None = Field(default=None, ge=1, le=1440)
    # How hard the sums are: "easy", "medium" or "hard". Anything else is read
    # as "medium" rather than refused - a level nobody has heard of should fall
    # back rather than lose the rest of the save.
    quiz_level: str | None = Field(default=None, max_length=16)
    # Which kinds of sum: "add,sub,mul,div" in any order.
    quiz_ops: str | None = Field(default=None, max_length=64)
    daily_video_limit: int | None = Field(default=None, ge=0, le=500)
    daily_image_limit: int | None = Field(default=None, ge=0, le=500)
    daily_music_limit: int | None = Field(default=None, ge=0, le=500)
    # "" | "photo" | "words" - what a refusal closes the factory for.
    close_on: str | None = Field(default=None, max_length=16)
    screen_uploads: int | None = Field(default=None, ge=0, le=1)
    # The janitor's two numbers. 0 days keeps nothing; 0 hours sweeps nothing.
    trash_days: float | None = Field(default=None, ge=0, le=3650)
    input_sweep_hours: float | None = Field(default=None, ge=0, le=8760)
    # How many of each kind of backup the nightly sweep keeps. Bounded at one
    # rather than zero: keeping none is not a tidier installation, it is an
    # installation with no backups, and there is already a "do not make them"
    # question one level up if that is ever wanted.
    backup_keep: int | None = Field(default=None, ge=1, le=365)
    # How long a video and a song may be. The ceiling is the one number here
    # that can make a render fail rather than look different - see the note on
    # the card, and app/workflows.py.
    video_min_seconds: int | None = Field(default=None, ge=1, le=600)
    video_max_seconds: int | None = Field(default=None, ge=1, le=600)
    video_default_seconds: int | None = Field(default=None, ge=1, le=600)
    video_max_seconds_sharp: int | None = Field(default=None, ge=1, le=600)
    music_min_seconds: int | None = Field(default=None, ge=1, le=600)
    music_max_seconds: int | None = Field(default=None, ge=1, le=600)
    music_default_seconds: int | None = Field(default=None, ge=1, le=600)
    chat_strict: int | None = Field(default=None, ge=0, le=1)
    music_strict: int | None = Field(default=None, ge=0, le=1)
    prompt_editing: int | None = Field(default=None, ge=0, le=1)
    max_characters: int | None = Field(default=None, ge=1, le=100)
    # en | fr, and they | he | they. Neither is a fact about the machine.
    ui_lang: str | None = Field(default=None, max_length=2)
    kid_pronoun: str | None = Field(default=None, max_length=8)
    # What the whole thing is called. Empty builds it from whose page it is.
    app_title: str | None = Field(default=None, max_length=60)
    # How the helper models are held on the card, and what the chat helper is
    # called. Ollama's keep_alive is a duration string - "0", "60s", "5m" -
    # so it is checked as one rather than taken as written.
    script_keep_alive: str | None = Field(default=None, max_length=16)
    chat_keep_alive: str | None = Field(default=None, max_length=16)
    comfy_free_after_job: int | None = Field(default=None, ge=0, le=1)
    chat_name: str | None = Field(default=None, max_length=24)
    chat_keep_messages: int | None = Field(default=None, ge=20, le=20000)


@app.put("/api/parent/settings")
async def parent_settings(body: SettingsIn, request: Request, who: str = ""):
    _parent(request)
    _as_child(who)
    try:
        changes = {k: v for k, v in body.model_dump().items() if v is not None}
        # The ones that are a choice from a list rather than a number: an
        # unknown value is the safe one, not a 400, because a stale page
        # sending a since-removed option should not lose the rest of the save.
        if body.close_on is not None:
            changes["close_on"] = (body.close_on if body.close_on in
                                   {c["id"] for c in lockdown.CHOICES} else "")
        if body.ui_lang is not None:
            changes["ui_lang"] = body.ui_lang if body.ui_lang in i18n.LANGS else "en"
        if body.kid_pronoun is not None:
            changes["kid_pronoun"] = (body.kid_pronoun if body.kid_pronoun in
                                      ("she", "he", "they") else "they")
        if body.quiz_level is not None:
            changes["quiz_level"] = (body.quiz_level if body.quiz_level in
                                     quiz.LEVELS else "medium")
        # Written back cleaned, so the database never holds a combination the
        # generator would have to guess at. A string with nothing usable in it
        # is a mistake, and addition is the kindest thing to do with one.
        if body.quiz_ops is not None:
            changes["quiz_ops"] = ",".join(quiz.clean_ops(body.quiz_ops)) or "add"
        # Ollama reads keep_alive as a number of seconds or a duration like
        # "5m"; anything else makes it fall back to its own default silently,
        # which would look like the setting doing nothing. Read as the safe
        # value rather than refused, like the choices above.
        for field_name, safe in (("script_keep_alive", "0"),
                                 ("chat_keep_alive", "5m")):
            asked = getattr(body, field_name)
            if asked is not None:
                changes[field_name] = _keep_alive(asked, safe)
        return gallery.public_settings(gallery.update_settings(
            **changes,
            # Opening it again by hand clears why it shut, so the reason on the
            # page is always about the closure they are looking at.
            **({"closed_reason": "", "closed_at": 0}
               if body.paused is False else {}),
        ))
    except OSError as exc:
        log.error("could not save settings: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save settings")


class NamingIn(BaseModel):
    """The eight name patterns. Every field optional, like the settings card:
    the page sends the row it just edited."""

    picture: str | None = Field(default=None, max_length=naming.MAX_PATTERN)
    video: str | None = Field(default=None, max_length=naming.MAX_PATTERN)
    song: str | None = Field(default=None, max_length=naming.MAX_PATTERN)
    comic: str | None = Field(default=None, max_length=naming.MAX_PATTERN)
    film: str | None = Field(default=None, max_length=naming.MAX_PATTERN)
    photo: str | None = Field(default=None, max_length=naming.MAX_PATTERN)
    sticker: str | None = Field(default=None, max_length=naming.MAX_PATTERN)
    other: str | None = Field(default=None, max_length=naming.MAX_PATTERN)


@app.put("/api/parent/naming")
async def parent_naming(body: NamingIn, request: Request):
    """What new files are called.

    Its own route rather than a handful of fields on `/api/parent/settings`,
    because that one quietly falls back on a value it does not recognise -
    which is right for a dropdown with a stale option in it and wrong here. A
    pattern that would not make a usable filename comes back as a 400 with the
    sentence to show, and **nothing is saved**: half-applying eight patterns
    would leave a parent guessing which of them took.
    """
    _parent(request)
    changes = {}
    try:
        for bucket, asked in body.model_dump().items():
            if asked is not None:
                changes[naming.setting_key(bucket)] = naming.check(asked)
    except naming.NamingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not changes:
        return naming.public()
    try:
        # The household's, always. A filename is a fact about the disk, not
        # about whose gallery it lands in - and two children whose files are
        # named differently is a directory nobody can read.
        gallery.update_settings("", **changes)
    except OSError as exc:
        log.error("could not save the name patterns: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save settings")
    return naming.public()


class ScheduleIn(BaseModel):
    """A whole week at once.

    Not a day at a time: the page edits seven rows and one Save, and a
    per-day route would mean seven requests and a half-saved week if one of
    them failed.
    """
    # "mon=16:00-18:30;tue=...". Parsed leniently - see app/schedule.py.
    text: str | None = Field(default=None, max_length=400)
    # -1 leaves it to "on if there is a timetable"; 0 and 1 are a choice.
    on: int | None = Field(default=None, ge=-1, le=1)


@app.put("/api/parent/schedule")
async def parent_schedule(body: ScheduleIn, request: Request, who: str = ""):
    _parent(request)
    _as_child(who)
    try:
        if body.text is not None:
            schedule.save(body.text)
        if body.on is not None:
            gallery.update_settings(schedule_on=body.on)
    except OSError as exc:
        log.error("could not save the timetable: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save settings")
    return schedule.state()


class OpenAnywayIn(BaseModel):
    on: bool = True


@app.post("/api/parent/schedule/override")
async def parent_schedule_override(body: OpenAnywayIn, request: Request, who: str = ""):
    """Ignore the timetable for the rest of today.

    A timetable with no way round it is a trap - the one evening it matters,
    the fix would be editing rows and remembering to put them back. This
    expires at midnight on its own, which is the part that makes it safe to
    reach for.
    """
    _parent(request)
    _as_child(who)
    try:
        schedule.open_anyway(body.on)
    except OSError as exc:
        log.error("could not save the timetable: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save settings")
    return schedule.state()


class BonusIn(BaseModel):
    kind: str = "video"
    # Negative takes a top-up back, so a mis-tap on "+5" is not final.
    extra: int = Field(default=1, ge=-50, le=50)


@app.post("/api/parent/bonus")
async def parent_bonus(body: BonusIn, request: Request, who: str = ""):
    """"Just one more" - a top-up that only counts for today."""
    _parent(request)
    _as_child(who)
    try:
        return gallery.grant_bonus(body.kind, body.extra)
    except GalleryError:
        raise HTTPException(status_code=400, detail="Unknown kind")
    except OSError as exc:
        log.error("could not grant a top-up: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save settings")


class DigestIn(BaseModel):
    """The Daily email card, both halves of it.

    The top half is whether it goes and when; the bottom half is the relay it
    goes through, which used to be `DIGEST_*` in `.env`. Every field is
    optional, so the page can send the section it just saved.
    """

    enabled: int | None = Field(default=None, ge=0, le=1)
    at: str | None = Field(default=None, max_length=5)
    # The "they have run out" email, which some households want and some do not.
    limit_mail: int | None = Field(default=None, ge=0, le=1)
    # How much of a day goes in one mail. A hundred thumbnails is still a mail
    # nobody wants.
    max_items: int | None = Field(default=None, ge=1, le=200)
    # The email server. Deliberately neither the password nor the one-Apprise-
    # URL box here: both are credentials, both live in app/config.py's own
    # scope and are set through `/api/parent/config`, because a row in the
    # settings table is a row in every backup file - see app/digest.py.
    to: str | None = Field(default=None, max_length=500)
    smtp_host: str | None = Field(default=None, max_length=200)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_starttls: int | None = Field(default=None, ge=0, le=1)
    smtp_user: str | None = Field(default=None, max_length=200)
    sender: str | None = Field(default=None, max_length=200)
    sender_name: str | None = Field(default=None, max_length=80)
    subject: str | None = Field(default=None, max_length=200)
    limit_subject: str | None = Field(default=None, max_length=200)


@app.put("/api/parent/digest")
async def parent_digest(body: DigestIn, request: Request):
    _parent(request)
    if body.at is not None and body.at != "" and not digest.valid_time(body.at):
        raise HTTPException(status_code=400, detail="Use a time like 19:30")
    try:
        gallery.update_settings(
            digest_enabled=body.enabled,
            digest_at=body.at,
            limit_mail_enabled=body.limit_mail,
            digest_max_items=body.max_items,
            digest_to=body.to,
            digest_smtp_host=body.smtp_host,
            digest_smtp_port=body.smtp_port,
            digest_smtp_starttls=body.smtp_starttls,
            digest_smtp_user=body.smtp_user,
            digest_from=body.sender,
            digest_from_name=body.sender_name,
            digest_subject=body.subject,
            digest_limit_subject=body.limit_subject,
        )
    except OSError as exc:
        log.error("could not save the email settings: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save settings")
    return digest.settings()


class NotifyIn(BaseModel):
    made: int | None = Field(default=None, ge=0, le=1)
    attach: int | None = Field(default=None, ge=0, le=1)
    limit: int | None = Field(default=None, ge=0, le=1)
    digest: int | None = Field(default=None, ge=0, le=1)
    flagged: int | None = Field(default=None, ge=0, le=1)
    # Somebody getting the parent PIN wrong. One switch, both channels.
    pin: int | None = Field(default=None, ge=0, le=1)
    # Answering questions back on Telegram.
    telegram: int | None = Field(default=None, ge=0, le=1)
    # The biggest file worth attaching, which is a property of whichever
    # service the URLs point at.
    max_mb: float | None = Field(default=None, ge=0, le=2000)
    # Who may talk to the bot, and how long a question may take. The bot
    # *token* is not here and stays in `.env`.
    telegram_chat_ids: str | None = Field(default=None, max_length=500)
    telegram_timeout: float | None = Field(default=None, ge=5, le=900)


@app.put("/api/parent/notify")
async def parent_notify(body: NotifyIn, request: Request):
    _parent(request)
    try:
        gallery.update_settings(
            notify_made=body.made, notify_attach=body.attach,
            notify_limit=body.limit, notify_digest=body.digest,
            notify_flagged=body.flagged, notify_pin=body.pin,
            notify_max_mb=body.max_mb,
            telegram_ask=body.telegram,
            telegram_chat_ids=body.telegram_chat_ids,
            telegram_timeout=body.telegram_timeout,
        )
    except OSError as exc:
        log.error("could not save the alert settings: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save settings")
    return {**notify.settings(), "telegram": telegram.settings()}


@app.post("/api/parent/notify/test")
async def parent_notify_test(request: Request):
    """The "does my Telegram bot actually work" button."""
    _parent(request)
    if not notify.configured():
        raise HTTPException(
            status_code=400,
            detail="No NOTIFY_URLS set in .env, so there is nowhere to send it.",
        )
    ok = await notify.send(
        branding.TITLE,
        "This is the test message from the parent page. If you can read it, "
        "alerts are working.",
    )
    if not ok:
        raise HTTPException(
            status_code=502,
            detail="Apprise could not deliver it. Check the URL in NOTIFY_URLS "
                   "and the container log.",
        )
    return {"sent": True, "targets": notify.settings()["targets"]}


# --- which model does which job --------------------------------------------

# The three jobs a language model does here, and what each one needs. Written
# out once: the GET, the PUT and the Test button all read this rather than
# each carrying its own idea of what a role is.
ROLES = (
    {
        "id": "script",
        "key": "script_model",
        "label": "The idea helper",
        "what": "\u201cHelp me write it\u201d, Surprise me, the comic and film "
                "beats, the song words, the French, and looking at a picture.",
        # Not a preference: describe(), look() and screen() all send an image.
        "needs_vision": True,
    },
    {
        "id": "chat",
        "key": "chat_model",
        "label": "The Chat tab",
        "what": "Who they are talking to on the Chat tab.",
        "needs_vision": False,
    },
    {
        "id": "telegram",
        "key": "telegram_model",
        "label": "Answering on Telegram",
        "what": "Your own questions to the bot, answered from today's numbers. "
                "It never sees a picture, so a text-only model is fine here.",
        "needs_vision": False,
        # Empty means "whatever the idea helper is", which is what an empty
        # TELEGRAM_MODEL always meant.
        "follows": "script",
    },
)

_ROLE_MODEL = {"script": scripts.model, "chat": chat.model,
               "telegram": telegram.model}
_ROLE_SEED = {"script": lambda: scripts.SEED_MODEL,
              "chat": lambda: chat.SEED_MODEL,
              "telegram": lambda: telegram.SEED_MODEL}


@app.get("/api/parent/models")
async def parent_models(request: Request):
    """What Ollama has, and which of it is doing what.

    The app does not download models and this route does not load one either:
    `/api/tags` reads the manifests on disk and `/api/ps` reads what is already
    resident. Choosing from a list of what is really there is the whole point -
    a typed name that has never been pulled is a helper that fails on their first
    tap rather than on this page.
    """
    _parent(request)
    listing = await scripts.catalogue()
    loaded = {m["name"]: m for m in (await scripts.placement()).get("loaded", [])}
    chosen = {r["id"]: gallery.text(r["key"]) for r in ROLES}
    in_use = {r["id"]: _ROLE_MODEL[r["id"]]() for r in ROLES}
    have = {m["name"] for m in listing["models"]}
    return {
        "reachable": listing["reachable"],
        "models": [
            {
                **m,
                "loaded": m["name"] in loaded,
                "vram_mb": (loaded.get(m["name"]) or {}).get("vram_mb"),
                # Which of the three this one is doing right now, so the page
                # can say so beside the name rather than in three places.
                "roles": [r["id"] for r in ROLES if in_use[r["id"]] == m["name"]],
            }
            for m in listing["models"]
        ],
        "roles": [
            {
                **{k: v for k, v in r.items() if k != "key"},
                "chosen": chosen[r["id"]],
                "in_use": in_use[r["id"]],
                "seed": _ROLE_SEED[r["id"]](),
                # Only meaningful when Ollama answered - an unreachable one
                # must not be read as "nothing is installed".
                "missing": listing["reachable"] and in_use[r["id"]] not in have,
            }
            for r in ROLES
        ],
        # Trying a model out loads it, so the page says so rather than letting
        # a parent evict a render's VRAM with a button.
        "busy": registry.active() is not None,
    }


class ModelsIn(BaseModel):
    """A name per role. Absent means "leave that one alone"; empty is only
    meaningful for Telegram, where it means "follow the idea helper"."""
    script: str | None = Field(default=None, max_length=128)
    chat: str | None = Field(default=None, max_length=128)
    telegram: str | None = Field(default=None, max_length=128)


def _model_name(value: str) -> str:
    """One Ollama tag, or "". Whitespace is the only thing worth refusing: a
    name that is not pulled is caught by the page, by the Test button and by
    the startup check, and refusing it here would stop a parent choosing a
    model they are part-way through pulling."""
    name = " ".join(value.split())
    if " " in name:
        raise HTTPException(status_code=400, detail="A model name has no spaces in it.")
    return name


@app.put("/api/parent/models")
async def parent_models_save(body: ModelsIn, request: Request):
    _parent(request)
    changes = {}
    for role in ROLES:
        value = getattr(body, role["id"])
        if value is None:
            continue
        name = _model_name(value)
        if not name and not role.get("follows"):
            raise HTTPException(status_code=400,
                                detail=f"{role['label']} needs a model.")
        changes[role["key"]] = name
    was = {r["id"]: _ROLE_MODEL[r["id"]]() for r in ROLES}
    try:
        gallery.update_settings(**changes)
    except OSError as exc:
        log.error("could not save the model choices: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save settings")
    now = {r["id"]: _ROLE_MODEL[r["id"]]() for r in ROLES}
    for role in ROLES:
        if was[role["id"]] != now[role["id"]]:
            log.info("%s: %s -> %s", role["label"], was[role["id"]], now[role["id"]])
    # A model nobody uses any more must not go on holding the card until its
    # own keep-alive runs out - the chat one is 7.6GB and five minutes.
    for name in set(was.values()) - set(now.values()):
        await scripts.unload(name)
    return await parent_models(request)


class ModelTestIn(BaseModel):
    role: str = Field(default="script", max_length=16)


@app.post("/api/parent/models/test")
async def parent_models_test(body: ModelTestIn, request: Request):
    """One short question through whichever model a role is on.

    Refused while something is rendering, for the same reason the Chat tab is:
    loading a model here would take VRAM out from under a job that is already
    using it. `keep_alive: 0` hands it straight back afterwards.
    """
    _parent(request)
    if body.role not in _ROLE_MODEL:
        raise HTTPException(status_code=404, detail="No such helper.")
    if registry.active() is not None:
        raise HTTPException(
            status_code=409,
            detail="Something is rendering. Trying a model now would take the "
                   "graphics card out from under it.",
        )
    name = _ROLE_MODEL[body.role]()
    await _clear_card_for_ollama()
    try:
        return await scripts.try_out(name)
    except scripts.ScriptError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/api/parent/digest/test")
async def parent_digest_test(request: Request):
    """Two lines through the relay - the "are these settings right?" button.

    Its own route beside the one below, which builds the whole day with its
    thumbnails. A parent who has just typed an address wants to know whether
    the address works, and an empty day answers that as well as a busy one.
    """
    _parent(request)
    try:
        return await digest.send_test()
    except digest.DigestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log.exception("test email failed")
        raise HTTPException(status_code=502, detail=f"Could not send it: {exc}")


@app.post("/api/parent/digest/send")
async def parent_digest_send(request: Request):
    """Send today's email right now - the "does this actually work?" button."""
    _parent(request)
    try:
        return await digest.send_now(note="Sent by hand from the parent page.")
    except digest.DigestError as exc:
        log.warning("test digest failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Could not send: {exc}")
    except Exception as exc:
        log.exception("test digest failed")
        raise HTTPException(status_code=500, detail=f"Could not send: {exc}")


class CleanupIn(BaseModel):
    days: int = Field(default=180, ge=1, le=3650)
    keep_favourites: bool = True
    # Ask first, then do: "this would move 24 things" before anything moves.
    preview: bool = True


@app.post("/api/parent/cleanup")
async def parent_cleanup(body: CleanupIn, request: Request):
    """Move everything older than `days` to the trash, favourites spared."""
    _parent(request)
    if body.preview:
        doomed = gallery.older_than(body.days, body.keep_favourites)
        return {
            "preview": True,
            "count": len(doomed),
            "bytes": sum(i["bytes"] for i in doomed),
        }
    try:
        result = await asyncio.to_thread(
            gallery.cleanup, body.days, body.keep_favourites
        )
    except OSError as exc:
        log.error("cleanup failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not tidy up")
    log.info("parent tidy-up moved %d items older than %d days", result["moved"], body.days)
    return {"preview": False, **result}


@app.post("/api/parent/quiz/bypass")
async def parent_quiz_bypass(request: Request, who: str = ""):
    """Wave them through today's sums. Today only - it expires with the date."""
    _parent(request)
    _as_child(who)
    quiz.bypass()
    log.info("parent let them skip today's sums")
    return quiz.status()


@app.post("/api/parent/quiz/reset")
async def parent_quiz_reset(request: Request, who: str = ""):
    """Ask them to do the sums again - they get a new set next time they look."""
    _parent(request)
    _as_child(who)
    quiz.reset()
    return quiz.status()


@app.post("/api/parent/trash/empty")
async def parent_trash_empty(request: Request):
    """Delete everything in the trash now, rather than waiting out the days."""
    _parent(request)
    gone = 0
    for item in gallery.trash_listing(everyone=True):
        try:
            gallery.destroy(item["id"])
            gone += 1
        except (GalleryError, OSError) as exc:
            log.warning("could not empty %s: %s", item["id"], exc)
    if gone:
        gallery.note_trash_emptied(gone, "the parent page")
    log.info("parent emptied the trash: %d item(s) gone for good", gone)
    return {"destroyed": gone}


# --- backup and restore -----------------------------------------------------
# Everything a parent has decided, in one file. Not the gallery: that is the
# media, it is gigabytes, and it is already files on a disk. See app/backup.py.

@app.get("/api/parent/backup")
async def parent_backup(request: Request):
    """Download one file with every setting, profile, character and face in it."""
    _parent(request)
    try:
        raw = backup.as_bytes()
    except OSError as exc:
        log.error("could not build a backup: %s", exc)
        raise HTTPException(status_code=500, detail="Could not build the backup")
    return Response(
        content=raw,
        media_type="application/json",
        headers={"Content-Disposition":
                 f'attachment; filename="{backup.filename()}"'},
    )


@app.get("/api/parent/backups")
async def parent_backups(request: Request):
    """The copies the app has kept on the server, newest first."""
    _parent(request)
    return {"backups": backup.listing(), "keep": backup.keep_count(),
            "where": str(backup.directory())}


@app.post("/api/parent/backup")
async def parent_backup_now(request: Request):
    """Make one of those copies now, without downloading anything."""
    _parent(request)
    try:
        path = backup.write_one()
    except OSError as exc:
        log.error("could not write a backup: %s", exc)
        raise HTTPException(status_code=500, detail="Could not write the backup")
    return {"name": path.name, "backups": backup.listing()}


@app.post("/api/parent/restore")
async def parent_restore(request: Request, file: UploadFile = File(...)):
    """Put a backup file back.

    Two taps on the page, because this replaces the settings, the profiles, the
    characters, the prompt overrides, the timings and the faces. A safety copy
    of what is there now is taken first, into the same backups directory, so
    the tap is undoable.
    """
    _parent(request)
    raw = await file.read()
    if len(raw) > 64 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="That file is far too big to be one of ours.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="That is not a backup file.")
    try:
        return await asyncio.to_thread(backup.apply, data)
    except backup.BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        log.error("could not restore a backup: %s", exc)
        raise HTTPException(status_code=500, detail="Could not write the restored settings")


class RestoreNamedIn(BaseModel):
    name: str = Field(default="", max_length=120)


@app.post("/api/parent/restore/saved")
async def parent_restore_saved(body: RestoreNamedIn, request: Request):
    """The same, from one of the copies already on the server."""
    _parent(request)
    try:
        return await asyncio.to_thread(backup.apply_file, body.name)
    except backup.BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        log.error("could not restore %s: %s", body.name, exc)
        raise HTTPException(status_code=500, detail="Could not write the restored settings")


# --- the activity log -------------------------------------------------------
# Read-only, all of it. There is deliberately **no route that deletes or
# shortens the log** - the only thing that can is the age setting, and it puts
# a sealed entry in the log saying that it ran. See app/audit.py.

@app.get("/api/parent/log")
async def parent_log(request: Request, day: str = "", who: str = "",
                     kind: str = "", page: int = 0, limit: int = 50):
    """Newest first, filtered by day, by child and by kind, and paged."""
    _parent(request)
    size = max(1, min(int(limit or 50), 200))
    return audit.page(day=day, actor=who, area=kind,
                      limit=size, offset=max(0, int(page)) * size)


@app.get("/api/parent/log/verify")
async def parent_log_verify(request: Request):
    """Recompute every seal and say "intact", or where it breaks."""
    _parent(request)
    return await asyncio.to_thread(audit.verify)


@app.get("/api/parent/log/export")
async def parent_log_export(request: Request, kind: str = "csv"):
    """The whole log, as a file to keep somewhere this app cannot reach.

    Streamed rather than built in memory: the point of it is that the copy can
    be big, and the hashes go with it so it verifies away from this box.
    """
    _parent(request)
    as_csv = kind != "jsonl"
    stamp = time.strftime("%Y-%m-%d")
    name = f"makery-log-{stamp}." + ("csv" if as_csv else "jsonl")
    return StreamingResponse(
        audit.export_lines(as_csv),
        media_type="text/csv" if as_csv else "application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


class LogSettingsIn(BaseModel):
    # 0 is for ever, and is the default. See app/audit.py.
    keep_days: float | None = Field(default=None, ge=0, le=3650)
    keep_words: int | None = Field(default=None, ge=0, le=1)


@app.put("/api/parent/log/settings")
async def parent_log_settings(body: LogSettingsIn, request: Request):
    """The two choices a parent has about the log: how long, and whether it
    records the words a refusal stopped."""
    _parent(request)
    changes = {}
    if body.keep_days is not None:
        changes["audit_keep_days"] = body.keep_days
    if body.keep_words is not None:
        changes["audit_words"] = body.keep_words
    try:
        gallery.update_settings(who="", **changes)
    except OSError as exc:
        log.error("could not save the log settings: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save that")
    return {"keep_days": audit.keep_days(), "keep_words": audit.keep_words()}


# --- the deployment values --------------------------------------------------
# The last handful of things that were only ever in `.env`: where the picture
# maker and the helper models are, how much the log says, which clock "today"
# is measured against, and five credentials. app/config.py holds them, the page
# wins over `.env`, and Clear puts `.env` back. Two rules the routes below
# enforce rather than the module:
#
# - **A secret is never read back.** `config.state()` says set or not set and
#   where from; there is no route that returns one, and no route that puts one
#   in an error message either.
# - **The PIN is not one of these.** It gates the page these routes are on, so
#   moving it takes the current PIN typed in again, and it has no Clear at all
#   - see `parent_pin_change()`.

class ConfigIn(BaseModel):
    key: str = Field(default="", max_length=32)
    value: str = Field(default="", max_length=2000)


def _config_field(key: str):
    """The field this route may touch, or a 400 naming the ones it may.

    `parent_pin` is deliberately refused here: it is the lock on this page and
    it has a route of its own that asks for the current one.
    """
    if key == "parent_pin":
        raise HTTPException(
            status_code=400,
            detail="The PIN is changed on its own, with the current one.")
    if key not in config.FIELDS:
        raise HTTPException(status_code=404, detail="There is no such setting.")
    return config.FIELDS[key]


@app.put("/api/parent/config")
async def parent_config(body: ConfigIn, request: Request):
    """Set one of them from the page. It wins over `.env` from here on."""
    _parent(request)
    field = _config_field(body.key)
    try:
        state = config.put(body.key, body.value)
    except config.Bad as exc:
        # `Bad` carries a sentence about the *shape* and never the value.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "restart": bool(field.restart), **state}


@app.delete("/api/parent/config/{key}")
async def parent_config_clear(key: str, request: Request):
    """Drop the page's value, so whatever `.env` says applies again - which may
    be nothing at all, and the page says so before the tap."""
    _parent(request)
    field = _config_field(key)
    try:
        state = config.clear(key)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "restart": bool(field.restart), **state}


class PinIn(BaseModel):
    current: str = Field(default="", max_length=64)
    new: str = Field(default="", max_length=64)


# --- the three PIN boxes ----------------------------------------------------
# The counting is `app/pinbox.py`'s: three boxes, five tries each, ten minutes
# each, counted separately so that failing at one does not lock a parent out of
# another - and in a module of their own so that `/unlock` on the bot can reach
# all three. See that file for why they cannot be one counter. What is here is
# only the HTTP half: what a locked box answers, and what a wrong guess costs
# besides a try.


def _refuse_if_locked(box) -> None:
    """Called *before* the comparison, so a locked box answers nothing, right
    or wrong - otherwise the lockout only stops the people who were going to
    fail anyway."""
    locked = box.locked_for()
    if locked:
        raise HTTPException(
            status_code=429,
            detail=f"Too many tries. Have another go in {max(1, locked // 60)} minutes.")


def _typed_pin_ok(box) -> None:
    """A PIN somebody just typed into this box, and it was right.

    **Forgiving is what this is for.** A parent who mistypes their own PIN four
    times and then gets it right should not be carrying those four misses
    around for ten minutes. It clears that box and no other: the boxes count
    separately so that none of them can be used to lock another, and forgiving
    across them would be the same collapse by a friendlier route. What must
    never forgive anything is a correct *header*, which a browser sends by
    itself - see `_forgive()`.
    """
    box.clear()


@app.post("/api/parent/pin")
async def parent_pin_change(body: PinIn, request: Request):
    """Change the PIN on the page this route is on.

    Three things this is careful about, and each of them is a way to lose the
    parent page:

    - **The current PIN is typed again**, into this box, rather than taken from
      the header the browser already holds. A wrong one counts against this
      box's own five tries, and is written down and alerted on with every
      other wrong PIN, so this is not a way round the limit - see
      `app/pinbox.py` for why the shared list could not be the one that counts
      here.
    - **The new one is checked before anything is written**, and an empty or
      too-short value is a 400. `config.put` refuses an empty value outright,
      so there is no path here that ends with no PIN configured - which the
      rest of this file reads as "everyone is a grown-up".
    - **There is no Clear.** Taking the PIN off is turning the lock off from
      behind it; it is done by clearing `PARENT_PIN` in `.env` *and* the stored
      one, which needs a shell on the host. The README says how.
    """
    _parent(request)
    have = parent_pin()
    if have:
        _refuse_if_locked(pinbox.PIN_CHANGE)
        if not hmac.compare_digest(body.current, have):
            _bad_pin(pinbox.PIN_CHANGE)
            raise HTTPException(status_code=403, detail="That's not the right PIN.")
        _typed_pin_ok(pinbox.PIN_CHANGE)
    try:
        config.put("parent_pin", body.new)
    except config.Bad as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    # Said in the log as well as the activity log: a PIN changing is the one
    # configuration change somebody might need to find months later. Never the
    # value, on either side.
    log.warning("the parent PIN was changed from the parent page")
    return {"ok": True, "was_set": bool(have)}


@app.get("/api/parent/chat")
async def parent_chat(request: Request):
    """The whole chat transcript. Nothing they say to the helper is private
    from the grown-ups, and the helper tells them so if they ask."""
    _parent(request)
    return {"messages": chat.transcript(), "name": chat.helper_name(),
            "today": chat.today_count()}


@app.delete("/api/parent/chat")
async def parent_chat_clear(request: Request):
    _parent(request)
    chat.forget()
    return {"cleared": True}


@app.get("/api/parent/prompts")
async def parent_prompts(request: Request):
    """Every instruction this app gives a model, with its built-in text.

    Sixteen strings decide the tone of the helpers, what the chat will talk
    about, and what the upload screen refuses. They were readable only by
    opening the source.
    """
    _parent(request)
    return prompts.listing()


class PromptIn2(BaseModel):
    text: str = Field(default="", max_length=prompts.MAX_CHARS)


@app.put("/api/parent/prompts/{prompt_id}")
async def parent_prompt_set(prompt_id: str, body: PromptIn2, request: Request):
    """Replace one, or send an empty string to go back to the built-in.

    Off unless PROMPT_EDITING is set: these are the only thing between a child
    and whatever the model feels like saying, and a page that invites editing
    them without the person having decided to is worse than no page.
    """
    _parent(request)
    if not prompts.editable():
        raise HTTPException(
            status_code=403,
            detail="Editing the prompts is switched off. Set PROMPT_EDITING=1 in .env.",
        )
    try:
        return await asyncio.to_thread(prompts.set_override, prompt_id, body.text)
    except KeyError:
        raise HTTPException(status_code=404, detail="No such prompt.")
    except OSError as exc:
        log.error("could not save the prompt override: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save that.")


@app.get("/api/parent/refused/{item_id}")
async def parent_refused_file(item_id: str, request: Request):
    _parent(request)
    try:
        path = gallery.refused_path(item_id)
    except GalleryError:
        raise HTTPException(status_code=404, detail="Gone")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, no-store"})


@app.post("/api/parent/refused/{item_id}/allow")
async def parent_refused_allow(item_id: str, request: Request):
    _parent(request)
    try:
        return {"gallery_id": gallery.allow_refused(item_id)}
    except (GalleryError, OSError):
        raise HTTPException(status_code=404, detail="Gone")


@app.delete("/api/parent/refused/{item_id}")
async def parent_refused_drop(item_id: str, request: Request):
    _parent(request)
    try:
        gallery.drop_refused(item_id)
    except (GalleryError, OSError):
        raise HTTPException(status_code=404, detail="Gone")
    return {"dropped": item_id}


class ClientLogIn(BaseModel):
    where: str = Field(default="", max_length=60)
    detail: str = Field(default="", max_length=400)


@app.post("/api/client-log")
async def client_log(body: ClientLogIn):
    """Let the page say what happened on a device I cannot open the console on.

    An iPad on the other side of the house is the only witness to half the
    bugs in here, and "it didn't work" is not enough to fix anything. Nothing
    identifying, nothing kept - it goes to the container log and no further.
    """
    log.info("client [%s] %s", body.where[:60], body.detail[:400])
    return {"ok": True}


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "comfy_url": COMFY_URL,
        "comfy_reachable": await client.reachable(),
        "websocket": client.ws_connected,
        "jobs": len(registry.jobs),
        "duration_range": [workflows.MIN_DURATION, workflows.MAX_DURATION],
        "orientations": list(workflows.ORIENTATIONS),
        "busy": registry.active() is not None,
        "gallery": gallery.available(),
        "paused": bool(gallery.get_settings().get("paused")),
        "schedule": schedule.state(),
        "quiz": quiz.status(),
        "system": stats.snapshot(),
        "ollama": await scripts.placement(),
        "ollama_last_run": scripts.last_run or None,
        # The Music tab hides itself when ComfyUI has no ACE-Step model, the
        # way the Chat tab does without its own.
        "music": music_ready(),
        "modules": modules.states({"music": music_ready()}),
    }


@app.exception_handler(HTTPException)
async def friendly_errors(request, exc: HTTPException):
    """Keep every error body shaped the same so the frontend never guesses."""
    detail = exc.detail if isinstance(exc.detail, str) else "Something went wrong."
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.get("/parent")
async def parent_page():
    """/parent reads better than /parent.html on a phone's address bar."""
    return FileResponse(STATIC_DIR / "parent.html", headers={"Cache-Control": "no-store"})


# --- their banner -------------------------------------------------------------

@app.get("/banner.png")
async def banner():
    """The strip across the top of their page.

    Theirs if they have made one, otherwise the one that ships. Before the static
    mount on purpose, so `<img src="banner.png">` in the page needs no special
    case and no cache-buster - it is the same URL either way, and no-store is
    what makes a change appear the moment they tap "Use this one".
    """
    own = gallery.banner_path()
    return FileResponse(own or (STATIC_DIR / "banner.png"),
                        media_type="image/png",
                        headers={"Cache-Control": "no-store"})


class BannerIn(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)


@app.post("/api/settings/banner")
async def set_banner(body: BannerIn):
    """Use something they have already made as the banner."""
    try:
        await asyncio.to_thread(gallery.set_banner, body.item_id)
    except GalleryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("could not set the banner")
        raise HTTPException(
            status_code=500,
            detail=i18n.t("That picture wouldn't go in the banner, sorry. Try another one!"),
        ) from exc
    return {"custom": True}



@app.delete("/api/settings/banner")
async def reset_banner():
    return {"custom": False, "removed": await asyncio.to_thread(gallery.clear_banner)}


class ModulesIn(BaseModel):
    # -1 on each leaves it to the ENABLE_* environment; 0 and 1 are a choice
    # made on the parent page.
    picture: int | None = Field(default=None, ge=-1, le=1)
    video: int | None = Field(default=None, ge=-1, le=1)
    comic: int | None = Field(default=None, ge=-1, le=1)
    music: int | None = Field(default=None, ge=-1, le=1)
    chat: int | None = Field(default=None, ge=-1, le=1)
    story: int | None = Field(default=None, ge=-1, le=1)


@app.put("/api/parent/modules")
async def parent_modules(body: ModulesIn, request: Request, who: str = ""):
    """Which makers exist. Off means the tab goes and the routes refuse."""
    _parent(request)
    _as_child(who)
    try:
        gallery.update_settings(**{
            f"module_{mid}": getattr(body, mid) for mid in modules.IDS
        })
    except OSError as exc:
        log.error("could not save the module switches: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save settings")
    return {"modules": modules.listing({
        "music": music_ready(), "chat": await chat.available(),
    })}


class ThemeIn(BaseModel):
    theme: str = Field(default="", max_length=40)


# POST, not PUT, because the page sends it with the same postJSON() helper as
# every other setting - and /api/settings/banner next door is a POST too.
@app.post("/api/settings/theme")
async def set_theme(body: ThemeIn):
    """Their colours. Stored beside the media rather than in the browser, so the
    page looks the same on the tablet and on the laptop."""
    name = themes.clean(body.theme)
    try:
        await asyncio.to_thread(gallery.update_settings, theme=name)
    except OSError as exc:
        log.error("could not save the colours: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save that") from exc
    return {"theme": name}


@app.middleware("http")
async def always_revalidate_the_page(request: Request, call_next):
    """Scripts and styles must be checked with the server on every load.

    StaticFiles sends an ETag and no Cache-Control, so Safari applied its own
    freshness rule and kept a parent.js for hours after a rebuild - the
    parent page rendered with new HTML and an old script, and looked half
    done. no-cache is not "never cache": the browser keeps the file and asks
    "still this one?", and an unchanged file is a 304 and a few bytes. Images
    are left alone; they are addressed by ?v= already where it matters.
    """
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-cache"
    return response


# Mounted last: the API routes above must win over the static catch-all.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
