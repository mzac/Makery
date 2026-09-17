"""Messages to a parent's phone, through whatever they already use.

The nightly email is a good end-of-day summary and a bad way to be told
something right now. This is the right-now half: Telegram, WhatsApp, Signal,
ntfy, Discord, Matrix, Pushover and about 150 others, via Apprise, which is a
one-line-per-service URL scheme rather than 150 integrations to maintain.

    tgram://<bot token>/<chat id>

Where they go is a box on the parent page, under Alerts, with `NOTIFY_URLS` in
`.env` behind it for an installation that has always set it there - see
app/config.py for which of the two wins. Everything below is the same string
either way.

Five things can be sent, each switchable on the parent page:

- **every picture or video as it is made**, optionally with the file attached,
  which is the "send me a copy of everything" a parent actually wants
- **running out** of pictures or videos for the day
- **the daily summary**, as text - the email is where the thumbnails live
- **anything the word filter stopped**, in the chat or in a prompt
- **somebody getting the parent PIN wrong**

More than one place can be listed, and each can be told what it wants by
putting tags in front of it, the way Apprise's own config files do:

      made,file=tgram://<bot token>/<chat id>
      limit,flagged=ntfy://ntfy.sh/mytopic
      mailto://user:pass@smtp.example.net

That sends every picture, with the file, to Telegram; the two things worth
interrupting someone for to a phone; and, because it names no tags,
everything to the last one. `file` is a modifier rather than an event: it
means attach the picture or video for *this* place, whether or not the
attach switch on the parent page is on.

All of it is off until at least one URL is set, and sending happens in a thread:
nothing here may make a child wait on somebody's push service.
"""

import asyncio
import logging

from . import branding, config, gallery

log = logging.getLogger("makery.notify")

# The things it can say. A target with none of these named gets them all.
EVENTS = ("made", "limit", "digest", "flagged", "pin")

# Tag spellings a person might reasonably type for the attachment modifier,
# and for "send this one everything".
_FILE_WORDS = {"file", "files", "attach", "attachment", "copy", "copies"}
_ALL_WORDS = {"all", "any", "everything", "*"}


class Target:
    """One place to send to, and what it asked for."""

    __slots__ = ("url", "events", "file")

    def __init__(self, url: str, events: frozenset, file: bool):
        self.url = url
        self.events = events
        self.file = file

    @property
    def scheme(self) -> str:
        # The scheme only, never the token: this is what reaches the browser.
        return self.url.split("://", 1)[0]

    def wants(self, event: str) -> bool:
        return event in self.events


def _split(raw: str) -> list:
    """Whitespace separates targets. A comma separates tags - and, for the
    sake of anyone who set this up before tags existed, also separates bare
    URLs, which is why the comma split only happens when there is no tag."""
    out = []
    for chunk in raw.split():
        if "=" in chunk and "://" not in chunk.split("=", 1)[0]:
            out.append(chunk)
        else:
            out.extend(c for c in chunk.split(",") if c)
    return out


def _parse(raw: str) -> list:
    targets = []
    for token in _split(raw):
        head, sep, rest = token.partition("=")
        if sep and "://" not in head:
            words = {w.strip().lower() for w in head.split(",") if w.strip()}
            url = rest.strip()
        else:
            words, url = set(), token.strip()
        if not url:
            continue
        file = bool(words & _FILE_WORDS)
        events = {w for w in words if w in EVENTS}
        unknown = words - set(EVENTS) - _FILE_WORDS - _ALL_WORDS
        if unknown:
            log.warning("notify: %s does not name anything I can send; "
                        "it will get everything", ", ".join(sorted(unknown)))
        # No event named - or "all" - means everything, so that a typo is
        # noisy rather than silently muting a parent's only alert.
        if not events or words & _ALL_WORDS or unknown:
            events = set(EVENTS)
        targets.append(Target(url, frozenset(events), file))
    return targets


# Where messages go. A box on the parent page now, with NOTIFY_URLS in `.env`
# behind it - see app/config.py for which of the two wins. Parsed at the call
# rather than at import, so changing it takes effect on the next message and
# not at the next restart; the parse is a string split and is re-done only when
# the string itself has moved.
_PARSED_FROM: str | None = None
TARGETS: list = []
# Kept for anything that still reads it: every URL, in order.
URLS: list = []


def targets() -> list:
    """The places to send to, right now."""
    global _PARSED_FROM, TARGETS, URLS
    raw = config.value("notify_urls")
    if raw != _PARSED_FROM:
        _PARSED_FROM = raw
        TARGETS = _parse(raw)
        URLS = [t.url for t in TARGETS]
    return TARGETS


def max_attach_mb() -> float:
    """The biggest file worth attaching. Telegram takes 50MB, most others
    less; anything bigger is mentioned rather than sent, because a parent would
    rather have the note than nothing.

    A setting rather than a constant - it is a property of whichever service
    the URLs point at, and the person holding the phone is the one who knows
    which. `NOTIFY_MAX_MB` seeds it once and is not read again."""
    return gallery.number("notify_max_mb", 0.0, 2000.0)

# Tasks nobody awaits. Held, or the garbage collector may take them mid-send.
_running: set = set()


def configured() -> bool:
    return bool(targets()) and _apprise() is not None


def _apprise():
    try:
        import apprise

        return apprise
    except ImportError:  # pragma: no cover - it is in requirements.txt
        log.warning("apprise is not installed; notifications are off")
        return None


# The parent-page switches. Which events are worth sending, and how big a
# file may ride along, are a parent's choice and live in the settings; **where**
# they go is a box on the same card, kept out of the settings table - and so
# out of the backup file - by app/config.py. The NOTIFY_* variables seed the
# rows on the first start and are not read again - see app/gallery.py.
_flag = gallery.flag


def settings() -> dict:
    here = targets()
    return {
        "configured": configured(),
        # The scheme only, never the token: this goes to the browser.
        "targets": [t.scheme for t in here],
        "routes": [
            {"scheme": t.scheme,
             "events": [e for e in EVENTS if e in t.events],
             "all": len(t.events) == len(EVENTS),
             "file": t.file}
            for t in here
        ],
        "count": len(here),
        # Whether the URLs came from the page or from `.env`, and never the
        # URLs themselves - each one has a token in it.
        "urls": config.state("notify_urls"),
        "made": _flag("notify_made"),
        "attach": _flag("notify_attach"),
        "limit": _flag("notify_limit", True),
        "digest": _flag("notify_digest"),
        "flagged": _flag("notify_flagged", True),
        "pin": _flag("notify_pin", True),
        "max_mb": max_attach_mb(),
    }


# --- sending ----------------------------------------------------------------

def _send_blocking(title: str, body: str, urls: list, attach=None) -> bool:
    apprise = _apprise()
    if apprise is None or not urls:
        return False
    box = apprise.Apprise()
    for url in urls:
        if not box.add(url):
            log.warning("notify: %s is not a URL apprise understands",
                        url.split("://", 1)[0])
    if not len(box):
        return False
    try:
        return bool(box.notify(title=title, body=body, attach=attach or None))
    except Exception:
        log.exception("notify failed")
        return False


async def send(title: str, body: str, attach=None, event: str = "") -> bool:
    """One message to everywhere that asked for this event. Never raises - a
    push service being down is not a reason for anything else here to fail."""
    if not configured():
        return False
    urls = [t.url for t in targets() if not event or t.wants(event)]
    if not urls:
        return False
    try:
        return await asyncio.to_thread(_send_blocking, title, body, urls, attach)
    except Exception:
        log.exception("notify failed")
        return False


async def _send_split(title: str, body: str, path, event: str) -> bool:
    """The same message twice: once to the places that want the file, once to
    the places that only want to be told. Apprise attaches per send, not per
    target, so this is two sends or none."""
    if not configured():
        return False
    everyone = _flag("notify_attach")
    wanted = [t for t in targets() if t.wants(event)]
    with_file = [t.url for t in wanted if path and (everyone or t.file)]
    without = [t.url for t in wanted if t.url not in with_file]
    sent = False
    if with_file:
        sent = await asyncio.to_thread(
            _send_blocking, title, body, with_file, path) or sent
    if without:
        sent = await asyncio.to_thread(
            _send_blocking, title, body, without, None) or sent
    return sent


def fire(coro) -> None:
    """Send without waiting, holding the task so it is not collected mid-flight."""
    if not configured():
        coro.close()
        return
    task = asyncio.create_task(coro)
    _running.add(task)
    task.add_done_callback(_running.discard)


# --- the four things it says ------------------------------------------------

# Every kind a finished file can be filed as, in the words a parent would
# use. The generate routes in `app/main.py` are the list that has to be
# covered: whatever they hand `jobs.create()` is what arrives here.
KIND_WORD = {
    "image": "picture", "panel": "comic picture", "comic": "comic",
    "t2v": "video", "i2v": "video", "flf": "video", "movie": "film",
    "story": "film", "storyfilm": "film with its own song",
    "upload": "photo", "voice": "video", "sound": "video",
    "sticker": "sticker", "frame": "picture", "music": "song",
    "jingle": "little tune", "ambience": "background hum",
    "smooth": "video", "slowmo": "slow-motion video", "huge": "big picture",
    "loop": "moving sticker",
    "edit": "changed picture", "outpaint": "picture", "inpaint": "picture",
    "restyle": "picture in a new style",
}

# What an unknown kind is called. Not "picture": a kind nobody added here is
# precisely the case where guessing is wrong, and "made a new thing" with the
# file attached says less but says nothing false. The log line is how the
# missing entry gets noticed at all.
UNKNOWN_WORD = "new thing"


def word_for(kind: str) -> str:
    word = KIND_WORD.get(kind or "")
    if word:
        return word
    log.warning("notify: nothing to call a %r, saying \"a %s\" instead",
                kind, UNKNOWN_WORD)
    return UNKNOWN_WORD


def _attachable(item_id: str):
    """The file's path, if it is small enough to send. None otherwise."""
    try:
        path = gallery.path_for(item_id)
        if path.stat().st_size > max_attach_mb() * 1_000_000:
            log.info("notify: %s is over %sMB, sending the note without it",
                     item_id, max_attach_mb())
            return None
        return str(path)
    except Exception:
        return None


async def made(item_id: str, kind: str, idea: str, who: str = "") -> None:
    """One picture or video, as it lands.

    `who` is the profile that made it. With one child it is left out and the
    message reads as it always did; with several, "Max made a video" is the
    whole point of the message - "Your child made a video" answers nothing.
    """
    if not settings()["made"]:
        return
    from . import profiles

    word = word_for(kind)
    body = (idea or "").strip() or "(no words)"
    name = profiles.name_of(who) if who and profiles.several() else branding.WHO
    await _send_split(f"{name} made a {word}", body,
                      _attachable(item_id), "made")


# One per daily allowance - the same three gallery.ALLOWANCE_KINDS counts.
LIMIT_WORD = {"image": "pictures", "video": "videos", "music": "songs"}


async def ran_out(kind: str, allowed: int) -> None:
    if not settings()["limit"]:
        return
    # Three allowances, not two: songs have had their own since the Music
    # card arrived, and "all their videos" is the wrong sentence for a song.
    things = LIMIT_WORD.get(kind, "things")
    await send(
        f"{branding.WHO} has used all {branding.THEIR} {things} for today",
        f"That is all {allowed} of them. The parent page has a one-tap top-up "
        "that only counts for today.",
        event="limit",
    )


async def summary(counts: str, total: int) -> None:
    if not settings()["digest"]:
        return
    await send(f"Today at {branding.TITLE}",
               f"{branding.WHO} made {counts}. The email has the pictures.",
               event="digest")


async def bad_pin(where: str, tries: int, locked: bool) -> None:
    """Somebody getting the parent PIN wrong.

    The rate limit lives in the caller, not here, so that one limit covers this
    and the email - otherwise a child at the keypad sends two streams of notes.
    """
    if not settings()["pin"]:
        return
    head = ("The parent page has locked itself" if locked
            else f"Someone got the parent PIN wrong ({where})")
    tail = ("It will not answer again for a few minutes. Nothing is open to "
            "them - this is the lock working."
            if locked else
            "Probably nothing. Worth knowing if it keeps happening.")
    await send(head,
               f"{tries} wrong {'try' if tries == 1 else 'tries'}, on the "
               f"{where}.\n\n{tail}",
               event="pin")


# There used to be a flagged() here. `lockdown.refused()` does that job now -
# it carries the refused picture as an attachment and knows whether the factory
# was closed - and two code paths for the same event would have drifted.
