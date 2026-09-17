"""A nightly email of what they made today, with thumbnails.

**All of it is on the parent page now**, under Alerts - whether it goes and
when, and also where it goes: the address, the relay, the port, the sender and
the two subject lines. Those used to be `DIGEST_*` in the environment on the
argument that a mail server belongs to the house rather than to the app, which
was true and was not the question: an address is exactly the kind of thing a
parent changes, and editing a file and rebuilding a container to do it was the
same mistake the daily limit used to make. The `DIGEST_*` variables seed these
rows on the first start and are not read again - see "Where settings live" in
makery/CLAUDE.md.

**Two of those boxes are handled differently from every other one**: the relay
password, and the "one Apprise URL, used as it is" that a parent gives instead
of the relay boxes - the shape that box exists for is
`mailtos://user:apppassword@gmail.com`, which is a mail password with a
hostname in front of it. Every row in the *settings* table goes into the backup
file, and the backup file is the thing a parent emails to themselves; neither
of those belongs in it. So neither is a row in that table: app/config.py keeps
both in a scope of its own that the backup skips, with `DIGEST_SMTP_PASS` and
`DIGEST_URL` in `.env` still applying to an installation that has always set
them there. The page shows whether each is set, offers to replace or clear it,
and never reads one back. An installation that already had a `digest_url` row
has it moved on the next start - see `config.migrate_from_settings`.

Nothing here is read at import, for the reason everything else in this app
stopped being: a value a parent can change while the app is running has to be
read when it is used. `mail_url()` is rebuilt per send, so a corrected relay
reaches tonight's email without a restart.

The scheduler is a plain minute loop rather than cron: the container is the
only thing that needs to know, a missed minute is not worth a second process,
and "have I already sent today's?" is one date string in the settings, so a
restart at 19:31 does not send a second copy.
"""

import asyncio
import contextlib
import io
import logging
import tempfile
import time
import urllib.parse
from pathlib import Path

from . import branding, config, gallery, notify

log = logging.getLogger("makery.digest")


# The relay, as a parent has it on the page. Every one of these is read at the
# call; none of them is a module constant any more.
DEFAULT_FROM = "makery@localhost"


def smtp_host() -> str:
    return gallery.text("digest_smtp_host").strip()


def smtp_port() -> int:
    return gallery.whole("digest_smtp_port", 1, 65535)


def smtp_user() -> str:
    return gallery.text("digest_smtp_user").strip()


def smtp_pass() -> str:
    """The relay password, right now. Read at the call like every other field
    on that card, so a corrected one reaches tonight's email; kept out of the
    settings table for the reason at the top of this file."""
    return config.value("smtp_pass")


def direct_url() -> str:
    """The one Apprise URL a parent may give instead of the boxes above.

    A credential too, and for the same reason as the password: the shape it
    exists for is `mailtos://user:apppassword@gmail.com`, so it is a mail
    password with a hostname in front of it. Kept where the password is - see
    the top of this file - rather than in a settings row that the backup
    exports."""
    return config.value("digest_url").strip()


def smtp_starttls() -> bool:
    return gallery.flag("digest_smtp_starttls")


def from_address() -> str:
    return gallery.text("digest_from").strip() or DEFAULT_FROM


def from_name() -> str:
    """The display name on the sender. Empty means the app's own title."""
    return gallery.text("digest_from_name").strip() or branding.TITLE


def subject() -> str:
    """{date}, {count} and {name} are filled in; anything else is left alone."""
    chosen = gallery.text("digest_subject").strip()
    if chosen:
        return chosen
    name = branding.KID_NAME
    return (f"What {name} made today - {{date}}" if name
            else "What was made today - {date}")


def limit_subject() -> str:
    """The separate "they have just run out for today" mail. {things}, {count}
    and {name} are filled in."""
    return gallery.text("digest_limit_subject").strip() or (
        f"{branding.WHO} has used all {branding.THEIR} {{things}} for today"
    )


def recipients() -> list[str]:
    """Who it goes to. Comma- or semicolon-separated, and newlines are fine so
    the box on the parent page can be typed one address to a line."""
    raw = gallery.text("digest_to").replace(";", ",").replace("\n", ",")
    return [part.strip() for part in raw.split(",") if part.strip()]


# How much of a day's work to put in one email. Thumbnails are small, but a
# hundred of them is still a mail nobody wants.
def max_thumbs() -> int:
    return gallery.whole("digest_max_items", 1, 200)


# The fallback time, for a stored one that will not parse.
TIME_DEFAULT = "19:30"
# Every thumbnail is letterboxed into the same box. Email clients cannot be
# relied on for object-fit, and a column of tiles that are each a different
# height - a portrait picture next to a 16:9 clip - looks broken rather than
# varied.
THUMB_WIDTH = 320
THUMB_HEIGHT = 200
THUMB_MAT = (238, 238, 240)

# One item, and several of them. Both spellings are written out because half
# of these are phrases rather than nouns: an "s" on the end of "Film joined
# from clips" or "Picture with a bit fixed" is not a plural, and the
# summary line at the top of the email said so every night.
KIND_LABEL = {
    "image": ("Picture", "Pictures"),
    "panel": ("Comic picture", "Comic pictures"),
    "comic": ("Comic", "Comics"),
    "t2v": ("Video", "Videos"),
    "i2v": ("Video from a picture", "Videos from a picture"),
    "flf": ("Video from one picture to another",
            "Videos from one picture to another"),
    "story": ("Film", "Films"),
    "movie": ("Film joined from clips", "Films joined from clips"),
    "storyfilm": ("Story film, with its own song",
                  "Story films, each with its own song"),
    "upload": ("Photo or drawing", "Photos and drawings"),
    "voice": ("Video with a voice over it", "Videos with a voice over them"),
    "sound": ("Video with a sound effect", "Videos with a sound effect"),
    "music": ("Song", "Songs"),
    "jingle": ("Little tune", "Little tunes"),
    "ambience": ("Background hum", "Background hums"),
    "sticker": ("Sticker", "Stickers"),
    "frame": ("Frame out of a video", "Frames out of a video"),
    "smooth": ("Video made smooth", "Videos made smooth"),
    "slowmo": ("Video in slow motion", "Videos in slow motion"),
    "huge": ("Picture made four times bigger",
             "Pictures made four times bigger"),
    "loop": ("Moving sticker", "Moving stickers"),
    "edit": ("Picture they changed", "Pictures they changed"),
    "outpaint": ("Picture with more around it", "Pictures with more around them"),
    "inpaint": ("Picture with a bit fixed", "Pictures with a bit fixed"),
    "restyle": ("Picture turned into another kind of picture",
                "Pictures turned into another kind of picture"),
}

# The same pair for an item whose sidecar never recorded a kind.
MEDIA_LABEL = {
    "video": ("Video", "Videos"),
    "audio": ("Song", "Songs"),
    "image": ("Picture", "Pictures"),
}


def _maker(item: dict) -> str:
    """Whose it is, for the line under a thumbnail - but only once there is
    more than one child, because "Ada" on every one of Ada's pictures says
    nothing. Imported late: profiles imports gallery imports nothing of this,
    but keeping the email free of a profile dependency at import time means a
    broken profiles file cannot stop the mail going out."""
    try:
        from . import profiles

        if not profiles.several():
            return ""
        return profiles.name_of(item.get("who") or "")
    except Exception:
        return ""


def _label_pair(item: dict) -> tuple[str, str]:
    """(one of these, several of these). Anything made before the sidecar
    recorded a kind - or straight from ComfyUI - has none, so fall back to what
    it actually is rather than calling a video a picture."""
    return (KIND_LABEL.get(item.get("kind") or "")
            or MEDIA_LABEL.get(item.get("media") or "")
            or MEDIA_LABEL["image"])


def _label(item: dict) -> str:
    """What to call one item, on its own thumbnail."""
    return _label_pair(item)[0]


def _tally(items: list[dict]) -> str:
    """"3 pictures, 1 video and a song" - the line the email opens with and
    the one the phone summary repeats. One function, because two copies of it
    drifted into two different sentences about the same day."""
    counts: dict = {}
    for item in items:
        pair = _label_pair(item)
        counts[pair] = counts.get(pair, 0) + 1
    return ", ".join(f"{n} {(one if n == 1 else many).lower()}"
                     for (one, many), n in counts.items()) or "nothing yet"


def _chat_today() -> int:
    """How much they used the chat tab today. Imported late and never allowed to
    fail: an email that did not go out because the transcript was unreadable
    would be a silly way to lose the day's summary."""
    try:
        from . import chat

        return chat.today_count()
    except Exception:  # pragma: no cover
        log.debug("could not count today's chat", exc_info=True)
        return 0


class DigestError(RuntimeError):
    """Something about sending the mail went wrong, with a sayable reason."""


def mail_url() -> str:
    """An Apprise `mailto://` built from the DIGEST_SMTP_* settings.

    The email goes out through Apprise like everything else now, rather than
    through a second hand-rolled smtplib path. The settings did not change: a
    relay, a port, optional credentials, a from address and a list of
    recipients are still what a person configures. This turns them into the
    one URL Apprise wants.

    The "Apprise URL" box on the page uses something Apprise supports that this
    shape cannot express - Gmail with an app password, SendGrid, SES - and wins
    over the rest of the card when it is filled in.
    """
    direct = direct_url()
    if direct:
        return direct
    host, to = smtp_host(), recipients()
    if not host or not to:
        return ""
    user, name = smtp_user(), from_name()
    auth = ""
    if user:
        auth = (urllib.parse.quote(user, safe="") + ":" +
                urllib.parse.quote(smtp_pass(), safe="") + "@")

    def build(with_name: bool) -> str:
        fields = {
            "to": ",".join(to),
            "from": from_address(),
            # "insecure" is Apprise's word for plain SMTP, which is what an
            # unauthenticated relay on port 25 inside a house is.
            "mode": "starttls" if smtp_starttls() else "insecure",
            "format": "html",
            # Apprise appends its own <img> for any image attachment the body
            # does not already reference. Every thumbnail here is referenced by
            # name, so this only catches one that failed to render.
            "inline": "yes",
        }
        if with_name and name:
            # Apprise's From validator refuses a straight apostrophe outright -
            # "Ada's AI Factory" is rejected and no mail goes at all - while
            # the typographic one is accepted and RFC 2047-encoded properly.
            # Swapping it is both the workaround and the better typography.
            fields["name"] = name.replace("'", "\u2019")
        # quote_via, or a space becomes "+" and Apprise puts the plus in the
        # display name rather than reading it as a space.
        return "mailto://%s%s:%s/?%s" % (
            auth, host, smtp_port(),
            urllib.parse.urlencode(fields, quote_via=urllib.parse.quote),
        )

    url = build(True)
    if name and not _apprise_accepts(url):
        # Something else in the name it will not take. Losing the display name
        # is a great deal better than losing the email.
        log.warning("apprise would not take the sender name %r; sending without it",
                    name)
        url = build(False)
    return url


def _apprise_accepts(url: str) -> bool:
    try:
        import apprise

        return bool(apprise.Apprise().add(url))
    except Exception:
        return True   # let the real send report the real problem


# --- configuration, with the parent page's overrides on top -----------------

def settings() -> dict:
    """What the digest will actually do. One place now: the parent page."""
    stored = gallery.get_settings()
    at = str(stored.get("digest_at") or "").strip() or TIME_DEFAULT
    host = smtp_host()
    return {
        "enabled": bool(_int(stored.get("digest_enabled"))),
        "at": at if valid_time(at) else TIME_DEFAULT,
        "to": recipients(),
        "smtp": f"{host}:{smtp_port()}" if host else "",
        "from": from_address(),
        "from_name": from_name(),
        "subject": subject(),
        "configured": bool(mail_url()),
        "last_sent": str(stored.get("digest_last_sent") or ""),
        "limit_mail": bool(_int(stored.get("limit_mail_enabled"))),
        "max_items": max_thumbs(),
        # What the boxes on the page hold, as stored, so an empty one shows as
        # empty and its placeholder can say what it falls back to.
        "fields": {key: stored.get(key, "") for key in (
            "digest_to", "digest_smtp_host", "digest_smtp_port",
            "digest_smtp_starttls", "digest_smtp_user", "digest_from",
            "digest_from_name", "digest_subject", "digest_limit_subject")},
        # Never the password itself, and never the Apprise URL either - only
        # whether there is one and where it came from. See app/config.py:
        # neither of them is a settings row, deliberately.
        "has_password": bool(smtp_pass()),
        "password": config.state("smtp_pass"),
        "url": config.state("digest_url"),
    }


def _int(value, default: bool = False) -> bool:
    """A stored 0/1. There is no third state any more - see app/gallery.py."""
    try:
        chosen = int(value)
    except (TypeError, ValueError):
        return default
    return default if chosen < 0 else bool(chosen)


def valid_time(text: str) -> bool:
    try:
        hour, _, minute = text.partition(":")
        return 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59
    except ValueError:
        return False


# --- building the mail ------------------------------------------------------

def _thumbnail(item: dict) -> bytes | None:
    """A small JPEG for one item, wherever it is now.

    gallery.still() hands back the picture itself, or a video's cached poster
    frame, from either the gallery or the trash - so something they made and
    then deleted still has a thumbnail to show.
    """
    from PIL import Image

    item_id = item["id"]
    try:
        source = gallery.still(item_id, item.get("trashed", False))
        if source is None:
            return None
        with Image.open(source) as image:
            image.load()
            image = image.convert("RGB")
            scale = min(THUMB_WIDTH / image.width, THUMB_HEIGHT / image.height)
            if scale < 1:
                image = image.resize(
                    (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                    Image.LANCZOS,
                )
            canvas = Image.new("RGB", (THUMB_WIDTH, THUMB_HEIGHT), THUMB_MAT)
            canvas.paste(image, ((THUMB_WIDTH - image.width) // 2,
                                 (THUMB_HEIGHT - image.height) // 2))
            out = io.BytesIO()
            canvas.save(out, "JPEG", quality=80, optimize=True)
            return out.getvalue()
    except Exception as exc:  # a broken file must not lose the whole email
        log.warning("no thumbnail for %s: %s", item_id, exc)
        return None


def _todays_items() -> list[dict]:
    """Everything made since local midnight, oldest first so it reads as a day.

    The trash counts. Something they made and then deleted is still something
    they made, and it is sitting recoverable in the trash for a week - so it
    belongs in the email, marked as deleted, where a parent can see it and
    decide. This also keeps the email agreeing with the daily limits, which
    have counted the trash from the start.
    """
    lt = time.localtime()
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    items = [
        {**i, "trashed": False}
        # The household's, not one child's: this can be sent by hand from the
        # parent page, where somebody's profile cookie is in play, and an email
        # that silently covered one of three children would be worse than none.
        for i in gallery.listing(everyone=True) if i["created"] >= midnight
    ] + [
        {**i, "trashed": True, "favourite": False}
        for i in gallery.trash_listing(everyone=True) if i["created"] >= midnight
    ]
    items.sort(key=lambda i: i["created"])
    return items


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@contextlib.contextmanager
def built(items: list[dict], note: str = ""):
    """Yields (subject, html, text, [attachment paths]) for one day's email.

    A context manager because the thumbnails have to exist as *files* for the
    length of the send: Apprise matches a `cid:` in the HTML against an
    attachment's **filename** and embeds that one inline as multipart/related.
    So each thumbnail is written as `shot-01.jpg` and the HTML says
    `cid:shot-01.jpg`. The directory goes when the block exits.
    """
    summary = _tally(items)

    date = time.strftime("%A %d %B")
    template = subject()
    try:
        heading = template.format(date=date, count=len(items),
                                  name=branding.KID_NAME)
    except (KeyError, IndexError, ValueError):
        heading = template

    shown = items[:max_thumbs()]
    extra = len(items) - len(shown)
    binned = [i for i in items if i.get("trashed")]
    said = _chat_today()
    refused = len(gallery.refused_listing())

    with tempfile.TemporaryDirectory(prefix="makery-digest-") as folder:
        cards, attachments = [], []
        for index, item in enumerate(shown):
            thumb = _thumbnail(item)
            if thumb is None:
                continue
            name = f"shot-{index:02d}.jpg"
            path = Path(folder) / name
            path.write_bytes(thumb)
            attachments.append(str(path))

            label = _label(item)
            when = time.strftime("%H:%M", time.localtime(item["created"]))
            badge = "&#9654; " if item["media"] == "video" else ""
            star = " &#11088;" if item.get("favourite") else ""
            gone = item.get("trashed")
            # A deleted one is dimmed rather than hidden: it is still theirs,
            # still recoverable, and a parent should be able to see it went.
            tag = ('<span style="background:#ffe0e0;color:#a12b2b;border-radius:4px;'
                   'padding:1px 5px;font-size:11px;margin-left:4px">deleted</span>') if gone else ""
            cards.append(
                f'<td style="padding:0 14px 22px 0;vertical-align:top;width:{THUMB_WIDTH}px">'
                f'<img src="cid:{name}" width="{THUMB_WIDTH}" height="{THUMB_HEIGHT}" '
                f'style="width:100%;max-width:{THUMB_WIDTH}px;height:auto;'
                f'border-radius:10px;display:block{";opacity:0.55" if gone else ""}">'
                f'<div style="font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:#444;'
                f'padding-top:6px;min-height:40px">'
                f'<b>{badge}{label}</b>{star}{tag} &middot; '
                f'{(_escape(_maker(item)) + ", ") if _maker(item) else ""}{when}<br>'
                f'{_escape(item["idea"] or "(no words)")}</div></td>'
            )

        rows = []
        for at in range(0, len(cards), 2):
            rows.append("<tr>" + "".join(cards[at:at + 2]) + "</tr>")

        html = f"""<div style="font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;color:#222;max-width:720px;margin:0 auto;padding:18px">
<h2 style="margin:0 0 4px;font-size:21px">{_escape(branding.TITLE)}</h2>
<p style="margin:0 0 16px;color:#666">{_escape(date)} &mdash; {_escape(branding.THEY)} made {_escape(summary)}.</p>
{f'<p style="margin:0 0 16px;padding:10px 12px;background:#fff6d6;border-radius:8px">{_escape(note)}</p>' if note else ''}
{f'<p style="margin:0 0 16px;color:#a12b2b">{_escape(branding.WHO)} deleted {len(binned)} of them. They are in the trash for {int(gallery.trash_days())} days &mdash; the parent page can put any of them back.</p>' if binned else ''}
<table cellpadding="0" cellspacing="0" border="0" style="width:100%">{''.join(rows)}</table>
{f'<p style="color:#666">&hellip;and {extra} more.</p>' if extra else ''}
{f'<p style="margin-top:18px;padding:10px 12px;background:#eef6ff;border-radius:8px">{_escape(branding.WHO)} said {said} thing(s) to the helper in the chat tab today. Every word of it is on the parent page.</p>' if said else ''}
{f'<p style="margin-top:18px;padding:10px 12px;background:#ffe9e9;border-radius:8px">{refused} upload(s) the screen refused are waiting on the parent page.</p>' if refused else ''}
<p style="margin-top:22px;color:#999;font-size:13px">Sent by {_escape(branding.TITLE)}. Change the time or turn this off on the parent page.</p>
</div>"""

        lines = [f"{branding.WHO} made {summary} today."]
        if binned:
            lines.append(
                f"{len(binned)} of them {branding.THEY} deleted - marked below, and still in the "
                f"trash for {int(gallery.trash_days())} days if you want any of them back."
            )
        if note:
            lines.append(note)
        for item in shown:
            when = time.strftime("%H:%M", time.localtime(item["created"]))
            mark = " (deleted)" if item.get("trashed") else ""
            maker = _maker(item)
            lines.append(f"  {when}  {_label(item)}{mark}"
                         f"{' (' + maker + ')' if maker else ''}: "
                         f"{item['idea'] or '(no words)'}")
        if extra:
            lines.append(f"  ...and {extra} more.")
        if said:
            lines.append(
                f"\n{branding.WHO} said {said} thing(s) to the helper in the chat tab "
                "today. Every word of it is on the parent page."
            )
        if refused:
            lines.append(f"\n{refused} upload(s) are waiting for you on the parent page.")

        yield heading, html, "\n".join(lines), attachments


# --- sending ----------------------------------------------------------------

def _send_blocking(subject: str, html: str, text: str, attachments: list) -> None:
    """Hand one email to Apprise. Raises DigestError with something sayable."""
    url = mail_url()
    if not url:
        raise DigestError(
            "No mail server is set up yet - fill in the email server on the "
            "parent page, under Alerts."
        )
    try:
        import apprise
    except ImportError as exc:  # pragma: no cover - it is in requirements.txt
        raise DigestError("apprise is not installed") from exc

    box = apprise.Apprise()
    if not box.add(url):
        raise DigestError(f"Apprise did not understand {url.split('://', 1)[0]}://…")
    try:
        ok = box.notify(
            title=subject,
            body=html,
            body_format=apprise.NotifyFormat.HTML,
            attach=attachments or None,
        )
    except Exception as exc:
        raise DigestError(str(exc)) from exc
    if not ok:
        raise DigestError(
            f"{smtp_host() or 'the mail server'} would not take it - check the "
            "container log for what Apprise said."
        )


async def send_now(note: str = "") -> dict:
    """Build and send today's email right now. Raises DigestError with a reason."""
    items = await asyncio.to_thread(_todays_items)
    to = recipients()
    with built(items, note) as (heading, html, text, attachments):
        await asyncio.to_thread(_send_blocking, heading, html, text, attachments)
    log.info("digest sent to %s (%d items, %d thumbnails)",
             ", ".join(to) or "the configured URL", len(items), len(attachments))
    return {"sent_to": to, "items": len(items), "subject": heading}


# --- "they have run out" ------------------------------------------------------

THINGS = {"image": "pictures", "video": "videos", "music": "songs"}

# Which sidecar kinds each daily allowance actually counts, mirroring
# gallery.usage_today(). The email used to ask "is this a video?" and treat
# everything else as belonging to whichever limit ran out, which put pictures
# under "Today's songs" the moment songs got a limit of their own. There are
# more than two kinds of thing now, so the test has to name them.
LIMIT_KINDS = {
    "image": ("image", "panel", "edit", "outpaint", "inpaint", "restyle"),
    "video": ("t2v", "i2v", "flf"),
    "music": ("music", "jingle", "ambience"),
}

# Anything made before the sidecar recorded a kind has none, so it falls back
# to what the file is - which is the old two-way test, kept for exactly the
# case it is still right for.
FALLBACK_MEDIA = {"image": "image", "video": "video", "music": "audio"}


def _counts_towards(item: dict, kind: str) -> bool:
    """Whether one gallery item is one of the things this limit counts."""
    its_kind = item.get("kind") or ""
    if its_kind:
        return its_kind in LIMIT_KINDS.get(kind, ())
    return item.get("media") == FALLBACK_MEDIA.get(kind)


async def limit_notice(kind: str) -> None:
    """Tell the grown-ups the first time they run out of `kind` today.

    Fire-and-forget: called from the route that has just refused them, and it
    must not make anybody wait on an SMTP handshake to see the friendly message.
    Once a day per kind - they will tap the button again, and a mailbox full of
    the same note is worse than no note.
    """
    if kind not in THINGS:
        return
    config = settings()
    # The phone message and the email are separate wants: somebody may have a
    # Telegram bot and no mail relay at all.
    from . import notify as _notify

    wants_mail = config["limit_mail"] and config["configured"]
    if not wants_mail and not _notify.configured():
        return

    today = time.strftime("%Y-%m-%d")
    key = f"limit_mail_{kind}"
    if str(gallery.get_settings().get(key) or "") == today:
        return
    # Written before the send, not after: a relay that hangs must not turn into
    # one note per tap.
    await asyncio.to_thread(gallery.update_settings, **{key: today})

    allowance = gallery.allowance()[kind]
    notify.fire(notify.ran_out(kind, allowance["limit"] + allowance["bonus"]))
    if not wants_mail:
        return
    try:
        items = await asyncio.to_thread(_todays_items)
        await asyncio.to_thread(_send_limit_mail, kind, allowance, items)
        log.info("told %s that the %s ran out",
                 ", ".join(recipients()) or "the configured URL", THINGS[kind])
    except DigestError as exc:
        log.error("could not send the ran-out note: %s", exc)
    except Exception:
        log.exception("could not send the ran-out note")


def _send_limit_mail(kind: str, allowance: dict, items: list[dict]) -> None:
    things = THINGS[kind]
    allowed = allowance["limit"] + allowance["bonus"]
    template = limit_subject()
    try:
        subject = template.format(things=things, count=allowed,
                                  name=branding.KID_NAME)
    except (KeyError, IndexError, ValueError):
        subject = template

    mine = [i for i in items if _counts_towards(i, kind)]
    when = time.strftime("%H:%M")
    html = f"""<div style="font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;color:#222;max-width:560px;margin:0 auto;padding:18px">
<h2 style="margin:0 0 10px;font-size:20px">{_escape(branding.WHO)} has used all {branding.THEIR} {things} for today</h2>
<p style="margin:0 0 14px">That is all {allowed} of them, the last at {when}. {_escape(branding.WHO)} has been
told to come back tomorrow.</p>
<p style="margin:0 0 14px;padding:10px 12px;background:#eef6ff;border-radius:8px">If you would rather
{_escape(branding.THEY)} had a few more, the parent page has a one-tap top-up that only counts for today.</p>
{('<p style="margin:0 0 6px;color:#666">Today&rsquo;s ' + things + ':</p><ul style="margin:0;padding-left:20px;color:#444">' + ''.join('<li>' + time.strftime('%H:%M', time.localtime(i['created'])) + ' &mdash; ' + _escape(i['idea'] or '(no words)') + '</li>' for i in mine[-10:]) + '</ul>') if mine else ''}
</div>"""
    lines = [
        f"{branding.WHO} has used all {allowed} of {branding.THEIR} {things} "
        f"for today (the last one at {when}).",
        "",
        f"{branding.WHO} has been told to come back tomorrow. "
        f"If you would rather {branding.THEY} had a few more, "
        "the parent page has a one-tap top-up that only counts for today.",
    ]
    if mine:
        lines += ["", f"Today's {things}:"]
        lines += [
            "  " + time.strftime("%H:%M", time.localtime(i["created"])) + "  " +
            (i["idea"] or "(no words)")
            for i in mine[-10:]
        ]
    _send_blocking(subject, html, "\n".join(lines), [])


# --- "does this relay actually work" ----------------------------------------

async def send_test() -> dict:
    """Two lines through the relay, and nothing else.

    Its own button beside "Send a report now", which builds the whole day with
    its thumbnails: the question here is only whether the address, the host and
    the port are right, and an empty day answers it as well as a busy one. It
    refuses with a sentence rather than a traceback when nothing is set up,
    which is the state a parent is most likely to press it in.
    """
    to = recipients()
    head = f"Test email from {branding.TITLE}"
    body = ("If you are reading this, the email settings on the parent page "
            "are right and the nightly summary will arrive.")
    html = f"""<div style="font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;color:#222;max-width:560px;margin:0 auto;padding:18px">
<h2 style="margin:0 0 10px;font-size:20px">{_escape(head)}</h2>
<p style="margin:0">{_escape(body)}</p>
</div>"""
    await asyncio.to_thread(_send_blocking, head, html, body, [])
    log.info("sent a test email to %s", ", ".join(to) or "the configured URL")
    return {"sent_to": to}


# --- somebody guessing the PIN ----------------------------------------------

async def pin_notice(where: str, tries: int, locked: bool) -> None:
    """Somebody got the parent PIN wrong. Fire-and-forget, like the one above.

    The rate limit is the caller's - this is called once per alert, not once
    per keystroke - because the same limit has to cover the phone message and
    this, or a child at the keypad sends two streams of notes instead of one.
    """
    config = settings()
    if not (config["configured"] and gallery.flag("notify_pin", True)):
        return
    when = time.strftime("%H:%M")
    head = ("Someone tried the parent page PIN and got it wrong"
            if not locked else "The parent page has locked itself")
    body = (f"{tries} wrong {'try' if tries == 1 else 'tries'} at {when}, "
            f"on the {where}.")
    tail = ("It will not answer again for a few minutes. Nothing is open to "
            "them - this is the lock working."
            if locked else
            "Probably nothing. It is worth knowing if it keeps happening.")
    html = f"""<div style="font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;color:#222;max-width:560px;margin:0 auto;padding:18px">
<h2 style="margin:0 0 10px;font-size:20px">{_escape(head)}</h2>
<p style="margin:0 0 14px">{_escape(body)}</p>
<p style="margin:0;color:#666">{_escape(tail)}</p>
</div>"""
    try:
        await asyncio.to_thread(
            _send_blocking, f"{head} - {branding.TITLE}", html,
            f"{head}\n\n{body}\n\n{tail}", [])
        log.info("told %s about a wrong PIN", ", ".join(recipients()))
    except Exception:
        log.exception("could not send the wrong-PIN note")


# --- the filter stopped something -------------------------------------------

async def refusal_notice(subject: str, body: str, image=None) -> None:
    """The email half of lockdown.refused(). Sent whatever the switches say.

    No switch of its own on purpose: if the factory has just closed itself, the
    grown-ups are the only people who can open it, so this is the one message
    that is not a preference.
    """
    if not settings()["configured"]:
        return
    shot = []
    if image is not None:
        try:
            shot = [str(image)]
        except Exception:
            shot = []
    html = ("<div style=\"font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;"
            "color:#222;max-width:560px;margin:0 auto;padding:18px\">"
            f"<h2 style=\"margin:0 0 10px;font-size:20px\">{_escape(subject)}</h2>"
            + "".join(f"<p style=\"margin:0 0 10px\">{_escape(line)}</p>"
                      for line in body.split("\n") if line.strip())
            + ("".join(f"<img src=\"cid:{Path(p).name}\" "
                       "style=\"max-width:100%;border-radius:8px\">" for p in shot))
            + "</div>")
    try:
        await asyncio.to_thread(_send_blocking, subject, html, body, shot)
        log.info("told %s that the filter stopped something",
                 ", ".join(recipients()) or "the configured URL")
    except Exception:
        log.exception("could not send the refusal note")


async def scheduler() -> None:
    """Send once a day at the configured local time, if they made anything."""
    while True:
        try:
            config = settings()
            if config["enabled"] and config["configured"]:
                now = time.localtime()
                today = time.strftime("%Y-%m-%d", now)
                due_h, _, due_m = config["at"].partition(":")
                due = int(due_h) * 60 + int(due_m)
                minutes = now.tm_hour * 60 + now.tm_min
                already = str(gallery.get_settings().get("digest_last_sent") or "")
                # A window, not an instant: a restart at the wrong second must
                # not skip the day, and a late wake-up must not send at 3am.
                if already != today and due <= minutes < due + 10:
                    items = await asyncio.to_thread(_todays_items)
                    if items:
                        await send_now()
                        notify.fire(notify.summary(_tally(items), len(items)))
                    else:
                        log.info("nothing made today, no digest sent")
                    # Marked either way: an empty day is a day dealt with.
                    await asyncio.to_thread(gallery.update_settings, digest_last_sent=today)
        except DigestError as exc:
            log.error("digest failed: %s", exc)
            # Do not mark it sent - the next minute in the window tries again.
        except Exception:
            log.exception("digest scheduler pass failed")
        await asyncio.sleep(60)
