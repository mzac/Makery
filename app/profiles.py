"""Who is using it - one household, several children, different rules.

Netflix's idea, for the same reason: one installation, one URL, one GPU, and a
nine-year-old who should not have the chat tab or fifteen-second videos while
their sister does. A profile carries a name, a face, an age, and its own copy of
every rule a parent can set.

**One profile means no sign-in screen at all.** A household with one child
never sees any of this: the picker only appears once there is a second person
to pick. That is deliberate - the cost of this feature to somebody who does not
want it should be zero, not one extra tap forever.

What a profile owns, and what it does not:

- **Its own rules.** Daily limits, which makers exist, the sums, the timetable,
  the colour scheme. Stored in `.settings-<id>.json`, laid over the household
  `.settings.json` rather than copied from it, so a setting nobody has touched
  for this child still follows the household default when that changes.
- **Its own gallery.** Every file records who made it, and each child sees
  their own. A parent sees everything, and can tick "everyone sees everything"
  for siblings who make things together.
- **Its own age**, which is the single thing most of the model instructions are
  really asking about. `KID_AGE` in `.env` fills in the *first* profile's and
  nothing else; after that the profile is the answer, and a second child may
  differ - the same helper writes for a nine-year-old and a twelve-year-old.
- **Not** the email, the phone messages, the PIN, the trash, or the pause
  switch. Those are the household's, and splitting them would mean a parent
  configuring the same thing three times.

Two things worth being straight about:

- **Adding a profile needs the parent PIN**, when one is set. Otherwise the
  way round a daily limit is to make a new profile, and a child who works that
  out in the first week has beaten the whole feature. With no PIN set, anyone
  can add one - which is how the rest of the app already behaves.
- **A new profile starts from the first one's rules**, not from the unlimited
  defaults, for the same reason.

Sealing, honestly: a sibling cannot *find* or *change* another child's work,
and cannot see it in any listing. A direct media URL is not blocked, because
the parent page shows those pictures in plain `<img>` tags that cannot carry a
PIN. That is a curtain, not a lock, and it is the right weight for siblings on
a home network.
"""

import json
import logging
import random
import re
import secrets
import time

from . import audit, branding, gallery

log = logging.getLogger("makery.profiles")

FILE = ".profiles.json"

# Avatars live beside the settings rather than in the gallery: a face is part
# of who they are, not one of the things they made, and it should not turn up in
# "everything I have drawn" or be deletable from there by accident.
AVATAR_DIR = ".avatars"

# The square a face is stored at. Big enough for the picker tile on a desktop
# at 2x and small enough that six of them are a rounding error on disk.
AVATAR_SIZE = 320

# What a new profile gets before anybody has made a picture for it. Colour and
# emoji alone make a perfectly good tile - Netflix has never done more - and it
# means a profile works the moment it is named, with the wizard as the treat
# rather than the toll.
FACES = ["\U0001f98a", "\U0001f431", "\U0001f436", "\U0001f984", "\U0001f427",
         "\U0001f438", "\U0001f419", "\U0001f99c", "\U0001f985", "\U0001f981",
         "\U0001f43c", "\U0001f420", "\U0001f680", "\U0001f916", "\U0001f409",
         "\U0001f9da", "\U0001f47b", "\U0001f3b8"]

COLOURS = ["#f7b32b", "#ef476f", "#06d6a0", "#4cc9f0", "#b388ff", "#ff8fab",
           "#7bd389", "#ffa94d"]

MAX_PROFILES = 8
MAX_NAME = 24

# Settings that belong to one child rather than to the household. Everything
# not listed here is read from - and written to - the household file, so a
# parent sets the email address once however many children there are.
PER_CHILD = frozenset({
    "daily_image_limit", "daily_video_limit", "daily_music_limit",
    "bonus_image", "bonus_video", "bonus_music", "bonus_day",
    "limit_mail_image", "limit_mail_video", "limit_mail_music",
    "quiz_enabled", "quiz_questions", "quiz_level", "quiz_ops",
    "quiz_passed_day", "quiz_passed_at",
    "quiz_bypassed_day", "quiz_secret",
    "module_picture", "module_video", "module_comic", "module_music",
    "module_chat",
    "schedule", "schedule_on", "schedule_override",
    "theme", "milestones_seen",
})

# A new profile starts from the first child's rules by *falling through* to
# them: the first child's settings are the household file, and a child's own
# file holds only what a parent has set for them specifically. Nothing is
# copied, so a limit changed for the first child later still reaches everyone
# who has not been given their own. Only the sums key is seeded, below.


def _path():
    return gallery.STATE_DIR / FILE


# Read on every request, so it is cached against the file's own mtime. Tiny,
# but this is the one state file on the hot path for *every* route rather than
# for the few that ask about settings.
_CACHE: tuple[float, dict] = (-1.0, {})


def _read() -> dict:
    global _CACHE
    try:
        stamp = _path().stat().st_mtime
    except OSError:
        return {}
    if _CACHE[0] == stamp:
        return _CACHE[1]
    try:
        data = json.loads(_path().read_text())
    except (OSError, ValueError):
        return {}
    data = data if isinstance(data, dict) else {}
    _CACHE = (stamp, data)
    return data


def _write(data: dict) -> None:
    """Atomic. The middleware reads this file on every request, and a plain
    write_text truncates before it writes: a read landing in that gap would
    see an empty file, and the fallback for an empty file is to invent the
    first profile - over the top of the real list.

    The temp-file dance itself is `gallery.write_json`, which the other small
    state files share. It used to be here, with one fixed temporary name that
    two concurrent saves would write into together."""
    global _CACHE
    gallery.write_json(_path(), data)
    _CACHE = (-1.0, {})


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:16]
    return (base or "kid") + "-" + f"{random.randrange(16 ** 4):04x}"


def _clean_name(name) -> str:
    return " ".join(str(name or "").split())[:MAX_NAME]


def all() -> list[dict]:
    """Every profile, in the order they were made.

    Creation order, not alphabetical: the picker should not rearrange itself
    when a third child is added, because the tile positions are how a
    six-year-old finds their own face.
    """
    data = _read()
    out = [p for p in (data.get("who") or []) if isinstance(p, dict) and p.get("id")]
    return out or [_first()]


def _first() -> dict:
    """The one profile every installation has, invented on demand.

    This is the migration. An installation that predates profiles has a
    gallery full of files with nobody's name on them, and they belong to the
    child who made them - so the first profile carries `adopts`, and anything
    with no owner recorded is theirs.
    """
    made = {
        "id": "one",
        # The one moment KID_NAME and KID_AGE in `.env` are read for anything.
        # From here on this profile *is* the household's name and age - the
        # emails, the title and the bot all ask this file, not the environment
        # - and a parent changes them under "Who uses it".
        "name": branding.SEED_NAME or branding.UNNAMED,
        "emoji": FACES[0],
        "colour": COLOURS[0],
        "age": branding.SEED_AGE,
        "avatar": False,
        "adopts": True,
        "created": time.time(),
    }
    # Written only when there is no file at all. A file that exists but will
    # not parse is not "no profiles", it is a write in progress or a broken
    # file, and either way the right move is to answer with this one in
    # memory and leave the disk alone.
    try:
        if not _path().exists():
            _write({"who": [made]})
            log.info("profiles: made the first one for %s", made["name"])
    except OSError as exc:
        log.warning("could not write the profiles file: %s", exc)
    return made


def get(pid: str) -> dict | None:
    return next((p for p in all() if p["id"] == pid), None)


def default() -> dict:
    """Whose page it is when nobody has said. The adopting profile, which is
    also the first, which is also the only one on most installations."""
    every = all()
    return next((p for p in every if p.get("adopts")), every[0])


def resolve(pid: str) -> dict:
    """A cookie value into a real profile. An unknown one is not an error - a
    profile can be removed while a browser still holds its name - so it falls
    back to the default rather than showing an empty page."""
    return get(pid or "") or default()


def several() -> bool:
    """Whether the sign-in screen exists at all."""
    return len(all()) > 1


def shared() -> bool:
    """Everyone sees everyone's work. Off unless a parent says otherwise: the
    whole point of a profile is that it is yours."""
    return bool(_read().get("shared"))


def set_shared(on: bool) -> None:
    data = _read()
    data.setdefault("who", all())
    data["shared"] = bool(on)
    _write(data)


def owns(meta_who: str, pid: str) -> bool:
    """Whether a file with that owner recorded belongs to this profile.

    An empty owner is the pre-profiles case and belongs to whoever adopts.
    """
    if shared():
        return True
    if meta_who:
        return meta_who == pid
    who = get(pid)
    return bool(who and who.get("adopts"))


def add(name: str, emoji: str = "", colour: str = "", age: int = 0) -> dict:
    data = _read()
    every = [p for p in (data.get("who") or []) if isinstance(p, dict) and p.get("id")]
    if not every:
        every = [_first()]
        data = _read()
        every = data.get("who") or every
    if len(every) >= MAX_PROFILES:
        raise ValueError(f"That is as many as it holds ({MAX_PROFILES}).")
    name = _clean_name(name)
    if not name:
        raise ValueError("A profile needs a name.")
    if any(p["name"].lower() == name.lower() for p in every):
        raise ValueError(f"There is already a {name}.")
    taken = {p.get("colour") for p in every}
    made = {
        "id": _slug(name),
        "name": name,
        "emoji": emoji if emoji in FACES else random.choice(
            [f for f in FACES if f not in {p.get("emoji") for p in every}] or FACES),
        "colour": colour if colour in COLOURS else next(
            (c for c in COLOURS if c not in taken), random.choice(COLOURS)),
        "age": max(0, min(19, int(age or 0))) or branding.AGE,
        "avatar": False,
        "adopts": False,
        "created": time.time(),
    }
    every.append(made)
    data["who"] = every
    _write(data)
    try:
        # Their own key for the sums cookie. Without it a new profile falls
        # back to the household's, and two children sharing one iPad share a
        # pass: whoever does the sums first does them for both.
        gallery.update_settings(who=made["id"], quiz_secret=secrets.token_urlsafe(32))
    except OSError as exc:
        log.warning("could not seed the sums key for %s: %s", made["id"], exc)
    log.info("profiles: added %s", name)
    audit.record("profile.added", actor=audit.PARENT, id=made["id"],
                 name=name, age=made["age"])
    return made


def update(pid: str, **fields) -> dict:
    data = _read()
    every = data.get("who") or all()
    for who in every:
        if who.get("id") != pid:
            continue
        if "name" in fields and fields["name"] is not None:
            name = _clean_name(fields["name"])
            if not name:
                raise ValueError("A profile needs a name.")
            if any(p["name"].lower() == name.lower() and p["id"] != pid for p in every):
                raise ValueError(f"There is already a {name}.")
            who["name"] = name
        if fields.get("emoji") in FACES:
            who["emoji"] = fields["emoji"]
        if fields.get("colour") in COLOURS:
            who["colour"] = fields["colour"]
        if fields.get("age") is not None:
            who["age"] = max(0, min(19, int(fields["age"] or 0)))
        if fields.get("avatar") is not None:
            who["avatar"] = bool(fields["avatar"])
        data["who"] = every
        _write(data)
        # One entry, whichever of the four moved. The name and the age are the
        # two that need the parent PIN, so they are the two worth naming.
        audit.record("profile.renamed", id=pid, name=who["name"],
                     age=who.get("age") or 0)
        return who
    raise ValueError("No such profile.")


def remove(pid: str) -> None:
    """Take a profile away. Nothing they made is deleted.

    Their pictures keep their name on them and stop showing in anybody's
    gallery, which is not the same as being gone: they are still on disk, still
    in the nightly email, and a parent can still see and save every one of
    them. Deleting a child's work because a tile was removed would be the
    wrong default by a long way.
    """
    data = _read()
    every = data.get("who") or all()
    if len(every) <= 1:
        raise ValueError("There has to be somebody.")
    going = next((p for p in every if p["id"] == pid), None)
    if going is None:
        raise ValueError("No such profile.")
    left = [p for p in every if p["id"] != pid]
    # Somebody has to own the files that predate profiles.
    if going.get("adopts"):
        left[0]["adopts"] = True
    data["who"] = left
    _write(data)
    audit.record("profile.removed", actor=audit.PARENT, id=pid,
                 name=going.get("name") or "",
                 # Nothing they made is deleted, and the log should say so
                 # rather than leave "removed" to be read as "erased".
                 kept_their_work=True)
    try:
        gallery.forget_settings(pid)
    except OSError as exc:
        log.warning("could not drop the settings for %s: %s", pid, exc)
    for stray in (gallery.STATE_DIR / f".settings-{pid}.json",
                  gallery.STATE_DIR / f".settings-{pid}.json.migrated",
                  gallery.STATE_DIR / f".prompts-{pid}.json",
                  avatar_path(pid)):
        try:
            stray.unlink()
        except OSError:
            pass
    log.info("profiles: removed %s", going.get("name") or pid)


# --- their face -------------------------------------------------------------

def avatar_dir():
    return gallery.STATE_DIR / AVATAR_DIR


def avatar_path(pid: str):
    """Deliberately not built from anything the browser sent: `pid` is looked
    up in the profile list before this is called, so the name on disk can only
    ever be one that is already in that file."""
    return avatar_dir() / f"{pid}.png"


def has_avatar(pid: str) -> bool:
    try:
        return avatar_path(pid).is_file()
    except OSError:
        return False


def save_avatar(pid: str, data: bytes) -> None:
    """Store a square PNG as this profile's face."""
    from PIL import Image
    import io

    directory = avatar_dir()
    directory.mkdir(parents=True, exist_ok=True)
    image = Image.open(io.BytesIO(data))
    image.load()
    image = image.convert("RGB")
    side = min(image.width, image.height)
    left, top = (image.width - side) // 2, (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = image.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
    image.save(avatar_path(pid), "PNG")
    update(pid, avatar=True)


def clear_avatar(pid: str) -> None:
    if get(pid) is None:
        raise ValueError("No such profile.")
    try:
        avatar_path(pid).unlink()
    except OSError:
        pass
    update(pid, avatar=False)


def public(pid: str = "", grownup: bool = False) -> list[dict]:
    """The picker's data. `pid` marks which one is signed in.

    Without `grownup` this is what the unauthenticated picker gets: names,
    faces, colours. Ages are for the parent page, which sends the PIN.
    """
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "emoji": p.get("emoji") or FACES[0],
            "colour": p.get("colour") or COLOURS[0],
            **({"age": p.get("age") or 0} if grownup else {}),
            "avatar": has_avatar(p["id"]),
            "is_me": p["id"] == pid,
            # Which one owns the files made before profiles existed - those
            # carry no `who`, and the parent page needs to know whose they are
            # rather than marking them "nobody in particular".
            "adopts": bool(p.get("adopts")),
        }
        for p in all()
    ]


def name_of(pid: str) -> str:
    """For a parent-facing sentence about one child. Falls back to the
    household wording rather than to an id, which means nothing to anybody."""
    who = get(pid or "")
    return (who or {}).get("name") or branding.WHO


def age_of(pid: str) -> int:
    who = get(pid or "")
    return (who or {}).get("age") or branding.AGE


def faces() -> dict:
    return {"emoji": FACES, "colours": COLOURS, "max": MAX_PROFILES}


def context(pid: str) -> dict:
    """What gallery.WHO holds for one request: an id, whether this profile
    owns the files that predate profiles, and whether the household shares."""
    who = get(pid or "") or default()
    return {"id": who["id"], "adopts": bool(who.get("adopts")), "shared": shared()}


# gallery.py cannot import this module - this one imports it - so the list of
# settings that belong to one child is handed over rather than looked up. Until
# it is, gallery treats every setting as the household's, which is exactly how
# the app behaved before profiles existed.
gallery.PER_CHILD = PER_CHILD
gallery.IS_ADOPTER = lambda pid: bool((get(pid) or {}).get("adopts"))
