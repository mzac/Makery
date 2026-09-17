"""What happens after the filter says no.

The blocklist and the photo screen already refuse the thing itself, and the
child sees a friendly message. This is the other half, for the households that
want it: tell the grown-ups *now*, with the picture or the words attached, and
optionally shut the factory until one of them opens it again.

Shutting it is deliberately not the default. A word filter that closes the
whole app is a word filter that punishes a child for typing "gun" in a sentence
about a water pistol, and the cost of that landing wrongly is a day they cannot
use the thing they were looking forward to. So there are three settings and the
middle one is the one to recommend:

    ""       never close, only tell (the default)
    "photo"  close when the picture checker says no to a photo they uploaded
    "words"  that, and when the word filter stops something they typed

A photo the vision model calls unsuitable is a much stronger signal than a word
on a list: it looked at an actual image and said no. That is why it is the
level worth turning on first.

**A closure is always reported**, whatever the notification switches say: if
the factory has just shut itself, the grown-ups are the only people who can
open it and they need to know why. A refusal that did *not* close anything is
an ordinary filter alert and respects the "anything the word filter stops"
switch like everything else.
"""

import asyncio
import logging
import time

from . import audit, branding, gallery, notify

log = logging.getLogger("makery.lockdown")

# In the order they appear in the dropdown, with what the parent page says.
CHOICES = [
    {"id": "", "label": "Just tell me - leave the factory open"},
    {"id": "photo", "label": "Close it if the picture checker says no to a photo"},
    {"id": "words", "label": "Close it for that, or for anything the word filter stops"},
]
_IDS = {c["id"] for c in CHOICES}

# What each setting will act on.
_CLOSES_ON = {"": (), "photo": ("photo",), "words": ("photo", "words")}


# Tasks nobody awaits. Its own rather than notify.fire(), which does nothing
# when no phone is configured - this has to run regardless, because closing the
# factory and emailing about it do not depend on there being a Telegram bot.
_running: set = set()


def fire(coro) -> None:
    task = asyncio.create_task(coro)
    _running.add(task)
    task.add_done_callback(_running.discard)


def setting() -> str:
    """Which of the three, straight off the parent page.

    It used to be a stored "-" meaning "whatever CLOSE_ON_REFUSAL says", with
    "" a parent deliberately choosing "just tell me" and having to be able to
    win over the environment. CLOSE_ON_REFUSAL now only seeds this on the first
    start, so there is one value and nothing to arbitrate.
    """
    stored = gallery.text("close_on")
    return stored if stored in _IDS else ""


def would_close(trigger: str) -> bool:
    return trigger in _CLOSES_ON.get(setting(), ())


WHERE_WORD = {
    "photo": "a photo they tried to upload",
    "words": "something they typed",
}


async def refused(trigger: str, where: str, text: str = "", image=None) -> bool:
    """Tell the grown-ups, and close the factory if they asked for that.

    `trigger` is "photo" or "words" - what kind of refusal this was, which is
    what the setting is about. `where` is for the message: "the picture box",
    "the chat". Returns whether it closed anything.

    Never raises. It is called from a route that has already refused the child
    and is about to answer them; nothing here may turn that into a 500.
    """
    closed = False
    # Every refusal, whichever half of the filter made it: the words box, the
    # photo screen and the chat all come through here. What is written down is
    # the *category* - which answers "is the filter working" - and the words
    # themselves only when a parent has asked for them on the Log tab.
    audit.record("safety.refused", trigger=trigger, where=where,
                 words=(text[:300] if text and audit.keep_words() else None))
    try:
        if would_close(trigger):
            gallery.update_settings(
                paused=True,
                closed_reason=f"{WHERE_WORD.get(trigger, 'something')} "
                              f"({where}) was stopped by the filter",
                closed_at=time.time(),
            )
            closed = True
            log.warning("closed the factory: %s refused in %s", trigger, where)
            audit.record("factory.closed", actor=audit.SYSTEM,
                         trigger=trigger, where=where)
    except Exception:
        log.exception("could not close the factory")

    try:
        await _tell(trigger, where, text, image, closed)
    except Exception:
        log.exception("could not tell anyone about the refusal")
    return closed


async def _tell(trigger: str, where: str, text: str, image, closed: bool) -> None:
    what = WHERE_WORD.get(trigger, "something")
    head = (f"The factory is closed - {what} was stopped"
            if closed else f"The filter stopped {what}")
    lines = [f"In {where}, at {time.strftime('%H:%M')}."]
    if text:
        lines.append("")
        lines.append(f"{branding.WHO} typed: {text[:300]}")
    if image is not None:
        lines.append("")
        lines.append("The picture is attached. It was not saved to "
                     f"{branding.THEIR} gallery.")
    lines.append("")
    lines.append(
        "The factory is closed until you open it on the parent page."
        if closed else
        f"{branding.WHO} was shown the friendly refusal. Nothing was made.")
    body = "\n".join(lines)

    # A closure always goes. Anything short of one is an ordinary filter alert
    # and obeys the switch, or turning that off would stop meaning anything.
    if not closed and not notify.settings()["flagged"]:
        return
    await notify.send(head, body, attach=str(image) if image else None,
                      event="flagged")
    from . import digest

    await digest.refusal_notice(head, body, image)
