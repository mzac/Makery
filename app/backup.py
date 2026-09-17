"""One file with everything a parent has decided in it.

Not the gallery. The pictures, videos and songs are the bulk of what this app
holds - gigabytes of it - and they are already files on a disk somebody can
copy. What is easy to lose and impossible to reconstruct is the small stuff
around them: the settings, who the children are, what their faces look like,
the characters they have invented and how each one is described, the prompt
overrides, and how long each kind of render has been taking. That is what this
file is, and it is a few hundred kilobytes.

The shape is a plain JSON object with a `version` and a `made_at`, so a human
can open one and read it. Pictures - the banner and the avatars - are base64 in
it rather than a zip beside it, because one file is the thing a parent can
actually email to themselves.

Restoring replaces every one of those. It is written to be all-or-nothing:
everything is decoded and checked first, a safety copy of what is there now is
taken, the state files are written to temporary names and `os.replace`d into
position, and the settings go in as one SQLite transaction. A half-restored
installation - new settings, old profiles - would have children whose ids no
longer match anything, and that is the outcome worth spending the code on.

**Profile ids are never renumbered.** A gallery sidecar records `who` as an id,
and the media is not in the backup, so a restore that invented new ids would
detach every child from everything they had made.

**And there is not one credential in it.** The settings section is the whole
settings table by scope, and the deployment values a parent sets on the page -
the relay password, the bot token, the notify URLs, the PIN - live in a scope
of their own for exactly this reason. `SKIP_SCOPES` leaves them out of what is
written and puts the live ones back over what is read, so a backup can neither
carry a secret out of this installation nor bring one into it. The rule is one
constant and both halves read it; see app/config.py for the other side of it.
"""

import base64
import json
import logging
import os
import time
from pathlib import Path

from . import audit, config, gallery, profiles, store

log = logging.getLogger("makery.backup")

# Bumped only for a change a reader has to know about. A file from an older
# version still restores: every section is optional on the way in.
VERSION = 1

# Where the copies live. How many of each kind are kept is a setting rather
# than a constant here - `backup_keep`, seeded once from `BACKUP_KEEP` like the
# rest, and defaulting to seven, which is a week: the span in which somebody
# notices "the parent page has gone funny". See `keep_count()` below.
DIR_NAME = "backups"

# The app's own name, in the two places a backup file carries it: the `app`
# key inside, and the filename. `APP_WAS` is what both said before the project
# was renamed to Makery. It is still accepted on the way in and still matched
# by the globs, because a parent's copies of their settings are exactly the
# thing that must survive a rename - the one from last month is the one they
# will reach for. Nothing is ever *written* under the old name.
APP_NAME = "makery"
APP_WAS = "easy-iv-gen"
NAME_GLOB = (f"{APP_NAME}-backup-*.json", f"{APP_WAS}-backup-*.json")


def _copies(folder: Path) -> list[Path]:
    """Every backup file in a directory, oldest name first, both spellings.

    Sorted on the date-and-time stamp rather than the whole name, so the two
    prefixes interleave by age instead of clumping.
    """
    found = {path for pattern in NAME_GLOB for path in folder.glob(pattern)}
    return sorted(found, key=lambda path: path.name.split("-backup-", 1)[-1])

# Settings scopes this file will not carry, in either direction.
#
# `config.SCOPE` holds the deployment values a parent has set on the page, and
# every one of them is a credential or the PIN. They are left out of `build()`
# so that the file a parent emails to themselves cannot be read for them, and
# they are left out of `apply()` - where the *live* ones are put back over the
# restore's `replace_all` - for two separate reasons: a backup taken before
# any of this existed has no value for them and must not be read as "clear the
# relay password", and a backup that somebody has edited by hand must not be
# able to set a PIN on the installation it is restored into.
SKIP_SCOPES = (config.SCOPE,)

# The state files that come along whole, as parsed JSON. The settings are not
# in here - they are rows now, and have a section of their own.
FILES = {
    "profiles": ".profiles.json",
    "characters": ".characters.json",
    "prompt_overrides": ".prompt-overrides.json",
    "timings": ".timings.json",
    "prompts": ".prompts.json",
    "chat": ".chat.json",
}
# A sibling's own typed ideas are `.prompts-<id>.json`, one per child, and are
# picked up by a glob in build() rather than being listed here.


class BackupError(RuntimeError):
    """The file is not one of ours, or cannot be applied."""


def directory() -> Path:
    return gallery.STATE_DIR / DIR_NAME


# --- making one -------------------------------------------------------------

def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _b64(path: Path) -> str | None:
    try:
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None


def build() -> dict:
    """Everything, as one dict ready to be written out."""
    state = gallery.STATE_DIR
    out = {
        "app": APP_NAME,
        "version": VERSION,
        "made_at": time.time(),
        "made_at_text": time.strftime("%Y-%m-%d %H:%M:%S"),
        # {scope: {key: value}} - "" is the household, the rest are profile
        # ids. Never SKIP_SCOPES: see the constant, and the top of this file.
        "settings": {scope: values
                     for scope, values in store.everything().items()
                     if scope not in SKIP_SCOPES},
        # The filename counters. Not a setting - they only ever go up, and a
        # restore that rewound one would let a number be used a second time,
        # which is the single promise app/naming.py makes about `{n}`.
        "counters": store.counters(),
        # The activity log, seals and all, so a restored one verifies exactly
        # as the original did. Append-only in the same spirit as the counters:
        # putting a backup back never shortens the live log - see
        # audit.from_backup().
        "log": audit.for_backup(),
        "files": {},
        "avatars": {},
    }
    for name, filename in FILES.items():
        data = _read_json(state / filename)
        if data is not None:
            out["files"][name] = data
    # A sibling's own typed ideas live in their own file, named after their id.
    for path in sorted(state.glob(".prompts-*.json")):
        data = _read_json(path)
        if data is not None:
            out["files"].setdefault("prompts_by_child", {})[
                path.name[len(".prompts-"):-len(".json")]] = data
    # Their banner, only when they have chosen one: the shipped one is in the image.
    banner = state / gallery.CUSTOM_DIR_NAME / gallery.BANNER_NAME
    if banner.is_file():
        out["banner"] = _b64(banner)
    for path in sorted((state / ".avatars").glob("*.png")):
        encoded = _b64(path)
        if encoded:
            out["avatars"][path.stem] = encoded
    return out


def filename(when: float | None = None) -> str:
    stamp = time.strftime("%Y-%m-%d", time.localtime(when or time.time()))
    return f"{APP_NAME}-backup-{stamp}.json"


def as_bytes() -> bytes:
    return json.dumps(build(), indent=1).encode("utf-8")


def write_one(note: str = "") -> Path:
    """Put a copy in STATE_DIR/backups and trim the old ones.

    The name carries the date *and* the time, so two on one day do not collide
    - the nightly one and the safety copy a restore takes are exactly that.
    """
    store.checkpoint()
    folder = directory()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d-%H%M%S")
    tag = f"-{note}" if note else ""
    path = folder / f"{APP_NAME}-backup-{stamp}{tag}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(build(), indent=1))
    os.replace(tmp, path)
    log.info("backup: wrote %s (%d bytes)", path.name, path.stat().st_size)
    # Here rather than only in `nightly()`, which is what this docstring has
    # always claimed and what the by-hand ones never got: "back it up now"
    # tapped once a week for a year is fifty-two files nobody deletes, on the
    # disk the parent page reports on. A rotation that fails is a warning, not
    # a failed backup - the copy is already safely on disk.
    try:
        rotate()
    except OSError as exc:
        log.warning("backup: could not trim the old copies: %s", exc)
    audit.record("backup.written",
                 actor=audit.SYSTEM if note == "nightly" else audit.PARENT,
                 file=path.name, why=note or "by hand",
                 bytes=path.stat().st_size)
    return path


def keep_count() -> int:
    """How many of each kind to keep. A setting, like the trash's days."""
    return gallery.whole("backup_keep", 1, 365)


def _why(path: Path) -> str:
    """Which kind of copy this is: "nightly", "before-restore", or "" for one
    made by hand from the parent page."""
    return ("nightly" if path.stem.endswith("-nightly")
            else "before-restore" if path.stem.endswith("-before-restore")
            else "")


def rotate(keep: int | None = None) -> int:
    """Keep the newest `keep` of each kind, and drop the rest.

    Each kind separately, on purpose. The safety copies are the ones taken
    before a restore, and a restore is exactly when somebody wants the one from
    five minutes ago - a single pool would let a run of nightlies push them all
    out. The ones made by hand from the parent page are a kind too, and were
    the ones nothing trimmed at all.

    The names carry the date and time, so sorting them is sorting by age.
    """
    most = max(1, keep_count() if keep is None else keep)
    try:
        paths = _copies(directory())
    except OSError as exc:
        log.warning("backup: could not list the old copies: %s", exc)
        return 0
    kinds: dict[str, list[Path]] = {}
    for path in paths:
        kinds.setdefault(_why(path), []).append(path)
    gone = 0
    for files in kinds.values():
        for path in files[:-most] if len(files) > most else []:
            try:
                path.unlink()
                gone += 1
            except OSError as exc:
                log.warning("backup: could not remove %s: %s", path.name, exc)
    if gone:
        log.info("backup: trimmed %d old copies, keeping %d of each kind",
                 gone, most)
    return gone


def nightly() -> Path | None:
    """One a day, from the janitor. Skipped if today's is already there."""
    today = time.strftime("%Y-%m-%d")
    if any(path.name.endswith("-nightly.json")
           and f"-backup-{today}-" in path.name
           for path in _copies(directory())):
        return None
    try:
        path = write_one("nightly")
    except OSError as exc:
        log.warning("backup: could not write tonight's copy: %s", exc)
        return None
    return path


def listing() -> list[dict]:
    """What is in the backups directory, newest first, for the parent page."""
    out = []
    try:
        paths = _copies(directory())
    except OSError:
        return out
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        out.append({
            "name": path.name,
            "bytes": stat.st_size,
            "made_at": stat.st_mtime,
            # "nightly", "before-restore", or "" for one made by hand.
            "why": _why(path),
        })
    out.sort(key=lambda row: row["made_at"], reverse=True)
    return out


def _safe_name(name: str) -> Path:
    """One of ours, in the backups directory, and nowhere else.

    The name arrives from the browser, so it is checked the way a gallery id is
    - no separators, no leading dot, and it has to resolve to a direct child of
    that one directory.
    """
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise BackupError("No such backup.")
    path = (directory() / name).resolve()
    try:
        if path.parent != directory().resolve() or not path.is_file():
            raise BackupError("No such backup.")
    except OSError as exc:
        raise BackupError("No such backup.") from exc
    return path


# --- putting one back -------------------------------------------------------

def check(data) -> dict:
    """Is this one of ours, and what is in it?

    Raises `BackupError` with a sentence a parent can act on. Every section is
    optional - a file from an older version is still worth restoring - but the
    shape of each one that is there has to be right, because the alternative is
    a half-written state directory.
    """
    if not isinstance(data, dict):
        raise BackupError("That is not a backup file.")
    if data.get("app") not in (APP_NAME, APP_WAS):
        raise BackupError("That file was not made by this app.")
    try:
        version = int(data.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    if version < 1 or version > VERSION:
        raise BackupError(
            f"That backup says version {data.get('version')}; this app "
            f"understands up to {VERSION}.")
    settings = data.get("settings")
    if settings is not None and not isinstance(settings, dict):
        raise BackupError("The settings in that file are not readable.")
    for scope, values in (settings or {}).items():
        if not isinstance(scope, str) or not isinstance(values, dict):
            raise BackupError("The settings in that file are not readable.")
    # Counted without SKIP_SCOPES, so the number the page shows is the number
    # that will actually be restored.
    settings = {scope: values for scope, values in (settings or {}).items()
                if scope not in SKIP_SCOPES}
    files = data.get("files") or {}
    if not isinstance(files, dict):
        raise BackupError("The saved files in that backup are not readable.")
    if not isinstance(data.get("log") or [], list):
        raise BackupError("The activity log in that backup is not readable.")
    if not isinstance(data.get("avatars") or {}, dict):
        raise BackupError("The faces in that backup are not readable.")
    who = (files.get("profiles") or {}).get("who") or []
    return {
        "version": version,
        "made_at": data.get("made_at") or 0,
        "made_at_text": data.get("made_at_text") or "",
        "settings_scopes": len(settings or {}),
        "settings_values": sum(len(v) for v in (settings or {}).values()),
        "profiles": len(who) if isinstance(who, list) else 0,
        # The characters file is a bare list.
        "characters": len(files.get("characters") or []),
        "avatars": len(data.get("avatars") or {}),
        "banner": bool(data.get("banner")),
        "log": len(data.get("log") or []),
        "files": sorted(k for k in files if k != "prompts_by_child"),
    }


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".restoring")
    tmp.write_text(text)
    os.replace(tmp, path)


def _write_bytes_atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".restoring")
    tmp.write_bytes(raw)
    os.replace(tmp, path)


def apply(data: dict) -> dict:
    """Put a checked backup back. Takes a safety copy of what is there first.

    Everything is decoded before anything is written, so a corrupt avatar means
    a refusal rather than a state directory half from one backup and half from
    another. The settings go in as one SQLite transaction, and each file lands
    with `os.replace`, which is atomic for anything reading it.
    """
    summary = check(data)
    state = gallery.STATE_DIR

    # Decode first. Anything that will not decode stops the whole thing here,
    # where nothing has been touched yet.
    pictures: list[tuple[Path, bytes]] = []
    if data.get("banner"):
        try:
            pictures.append((state / gallery.CUSTOM_DIR_NAME / gallery.BANNER_NAME,
                             base64.b64decode(data["banner"])))
        except (ValueError, TypeError) as exc:
            raise BackupError("The banner in that backup is damaged.") from exc
    for pid, encoded in (data.get("avatars") or {}).items():
        if not isinstance(pid, str) or "/" in pid or pid.startswith("."):
            raise BackupError("A face in that backup has an odd name.")
        try:
            pictures.append((state / ".avatars" / f"{pid}.png",
                             base64.b64decode(encoded)))
        except (ValueError, TypeError) as exc:
            raise BackupError(f"The face for {pid} is damaged.") from exc

    files = data.get("files") or {}
    texts: list[tuple[Path, str]] = []
    for name, filename_ in FILES.items():
        if name in files:
            texts.append((state / filename_, json.dumps(files[name], indent=1)))
    for pid, contents in (files.get("prompts_by_child") or {}).items():
        if not isinstance(pid, str) or "/" in pid or pid.startswith("."):
            raise BackupError("A child's saved ideas have an odd name.")
        texts.append((state / f".prompts-{pid}.json", json.dumps(contents, indent=1)))

    # The log, **before anything else** - including the safety copy, which
    # writes an entry of its own. A live log with entries in it is kept and the
    # backup's is left alone, because merging two chains would mean re-sealing
    # one of them, which is the exact operation the chain exists to make
    # visible. Checking after the safety copy would have meant the check never
    # once found an empty log.
    log_result = audit.from_backup(data.get("log") or [])

    before = None
    try:
        before = write_one("before-restore")
    except OSError as exc:
        log.warning("backup: could not take a safety copy first: %s", exc)

    # Settings first, because it is the one that can refuse: a failed SQLite
    # transaction changes nothing, and stopping here leaves the files alone.
    if data.get("settings") is not None:
        # Read what the deployment scope holds *now*, before the wipe, and
        # write it back in the same transaction. `replace_all` empties the
        # whole table, so without this a restore would take the relay password
        # and the bot token off a working installation - and the backup has no
        # value to put back, because it never carried one. Anything the file
        # itself claims for that scope is dropped on the way in: a hand-edited
        # backup is not a way to set a PIN on somebody else's install.
        keep = {scope: dict(store.scope(scope)) for scope in SKIP_SCOPES}
        store.replace_all({
            **{scope: {k: v for k, v in values.items()
                       if k in gallery.DEFAULT_SETTINGS}
               for scope, values in data["settings"].items()
               if scope not in SKIP_SCOPES},
            **{scope: values for scope, values in keep.items() if values},
        })
        # The redaction list is built from those values and the table has just
        # been rewritten underneath it.
        config.refresh_redactions()
    if isinstance(data.get("counters"), dict):
        # Never downwards: `set_counters` keeps whichever is higher, so putting
        # last week's file back cannot hand out this week's numbers again.
        store.set_counters(data["counters"])
    for path, text in texts:
        _write_atomic(path, text)
    for path, raw in pictures:
        _write_bytes_atomic(path, raw)

    # The profile list is read through an mtime cache; an `os.replace` can land
    # inside the same second as the read that filled it.
    profiles._CACHE = (-1.0, {})
    log.warning("restored a backup made %s: %d settings across %d scope(s), "
                "%d profile(s), %d face(s)",
                summary["made_at_text"] or "at an unknown time",
                summary["settings_values"], summary["settings_scopes"],
                summary["profiles"], summary["avatars"])
    audit.record("backup.restored", actor=audit.PARENT,
                 made_at=summary["made_at_text"],
                 settings=summary["settings_values"],
                 profiles=summary["profiles"],
                 log_entries_added=log_result["restored"],
                 log_entries_kept=log_result["kept"])
    return {**summary, "log": log_result,
            "safety_copy": before.name if before else ""}


def apply_file(name: str) -> dict:
    """Restore one of the copies in STATE_DIR/backups, by name."""
    path = _safe_name(name)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise BackupError("That backup cannot be read.") from exc
    return apply(data)
