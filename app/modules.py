"""Which halves of the app exist at all.

Not every household wants every tab. A six-year-old sibling should probably not
have the chat; a metered connection or a smaller card might not want video;
somebody may simply decide that comics are a distraction this week. So each
maker is a switch on the parent page - per child - and turning one off takes
its tab away rather than greying it out. `ENABLE_PICTURE` and its four
neighbours in `.env` seed those switches on the first start and are not looked
at again.

**The server enforces it, not the page.** Hiding a tab is the friendly half;
`_require_module()` on every route it owns is the half that means reloading
past it achieves nothing - the same split the warm-up sums and the pause use.

A module can also be *unavailable* rather than switched off: the music tab has
no ACE-Step model on some machines, and the chat tab no chat model. That is a
different thing from a parent turning it off, and `available()` reports both so
the parent page can say which it is - "you turned this off" and "this machine
cannot do it" want different sentences.
"""

import logging

from . import gallery

log = logging.getLogger("makery.modules")

# id, what a parent sees, what the .env switch is called, and the one line that
# says what turning it off actually costs.
MODULES = [
    {"id": "picture", "label": "Pictures", "emoji": "\U0001f3a8",
     "env": "ENABLE_PICTURE",   # what seeded it, for the docs
     "note": "The Picture tab, and the banner maker in Settings."},
    {"id": "video", "label": "Videos", "emoji": "\U0001f3ac",
     "env": "ENABLE_VIDEO",
     "note": "The Video tab, all four of its modes, and joining clips into a film."},
    {"id": "comic", "label": "Comics", "emoji": "\U0001f4d6",
     "env": "ENABLE_COMIC",
     "note": "The Comic tab. Comics count against the picture limit."},
    {"id": "music", "label": "Songs", "emoji": "\U0001f3b5",
     "env": "ENABLE_MUSIC",
     "note": "The Music tab. Needs an ACE-Step model in ComfyUI."},
    {"id": "chat", "label": "Chat", "emoji": "\U0001f4ac",
     "env": "ENABLE_CHAT",
     "note": "The Chat tab. Needs a chat model in Ollama. Every turn is on this page."},
    # The Story tab spends the picture, video and song allowances rather than
    # having one of its own, so turning it off takes away a *way of working*
    # and not a thing they can make. It also needs the three makers underneath
    # it: `story_steps()` says which of its steps can run at all.
    {"id": "story", "label": "Story maker", "emoji": "\U0001f3ad",
     "env": "ENABLE_STORY",
     "note": "The Story tab: one idea taken all the way to a little film with "
             "its own song. Needs Videos on; uses the picture, video and song "
             "limits as it goes."},
]

IDS = [m["id"] for m in MODULES]
_BY_ID = {m["id"]: m for m in MODULES}

# What each one is called when it is refused, in a sentence a child reads.
OFF_MESSAGE = {
    "picture": "Making pictures is switched off right now. Ask a grown-up!",
    "video": "Making videos is switched off right now. Ask a grown-up!",
    "comic": "Making comics is switched off right now. Ask a grown-up!",
    "music": "Making songs is switched off right now. Ask a grown-up!",
    "chat": "The chat is switched off right now. Ask a grown-up!",
    "story": "The story maker is switched off right now. Ask a grown-up!",
}


def story_steps(ready: dict | None = None) -> dict:
    """Which steps of the story flow this installation can actually do.

    The Story tab borrows the other makers rather than owning a graph of its
    own, so a parent who turns pictures off has not turned the story maker off
    - they have taken one step out of it. The card says which step it cannot
    do and carries on; **the film is the exception**, because a story with no
    film is not a shorter story, it is the picture and the song they could have
    made on their own cards. `firstTab`/`applyModules` hide the tab on that
    one alone.
    """
    ready = ready or {}
    return {step: available(step, ready.get(step, True))
            for step in ("picture", "video", "music")}


def enabled(module: str) -> bool:
    """Whether a parent has it on. Says nothing about whether it can work."""
    if module not in _BY_ID:
        return True
    return gallery.flag(f"module_{module}", True)


def available(module: str, ready: bool = True) -> bool:
    """On *and* able to run. `ready` is the module's own prerequisite - a model
    ComfyUI or Ollama may not have."""
    return enabled(module) and ready


def listing(ready: dict | None = None) -> list[dict]:
    """Every module with its two states, for the parent page.

    `ready` maps ids to whether the machine can do them at all, so the page can
    tell "you turned this off" apart from "this machine cannot do it" - which
    want different sentences and different remedies.
    """
    ready = ready or {}
    return [
        {**entry,
         "enabled": enabled(entry["id"]),
         "ready": bool(ready.get(entry["id"], True)),
         "on": available(entry["id"], ready.get(entry["id"], True))}
        for entry in MODULES
    ]


def states(ready: dict | None = None) -> dict:
    """Just {id: is it usable}, which is all the child's page needs."""
    ready = ready or {}
    return {mid: available(mid, ready.get(mid, True)) for mid in IDS}
