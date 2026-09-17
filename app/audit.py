"""What happened, written down in a way that shows if somebody edited it.

A parent asked for "a log file of everything done that is persistent and cannot
be deleted easily". This is that, and the first thing to be honest about is
what those last four words can mean on a box you own:

**A parent with a shell can delete `state.db`, and nothing here stops them.**
An app cannot keep a secret from the person who runs it. What it *can* do is
never delete the log itself, never offer a route that shortens it, and seal
every entry against the one before it so that a row edited, removed or
reordered afterwards shows up as a break at a named position. That is the
promise: not "you cannot", but "you cannot quietly".

### A table, not a file

The obvious alternative was hash-chained JSONL in `STATE_DIR`, and it loses on
three counts:

- **Appending is not atomic.** Two threads - a route, the janitor, the Telegram
  loop - appending to one file can interleave, and a crash mid-write leaves a
  half line that is indistinguishable from tampering. SQLite gives one
  transaction per entry, and `store.chain_append` reads the last hash and
  writes the new row *inside* it, so two writers can never seal against the
  same predecessor and fork the chain.
- **A second process.** The Telegram sandbox test proved two containers can
  share one state volume. `BEGIN IMMEDIATE` plus `busy_timeout` makes the
  second one wait; two file handles on one JSONL just corrupt it.
- **The database is already the thing that is backed up, checkpointed and
  copied.** One file to keep, not two.

The one thing a file would have won - "a human can read it with `cat`" - is
answered by the download: the Log tab hands out the whole thing as CSV or JSONL
whenever anybody wants it, and that copy is as readable as a file would have
been, with the hashes in it so it verifies away from this box.

### The chain

Each entry carries `prev_hash` and `hash`, where

    hash = sha256(prev_hash + US + id + US + at + US + actor + US + event + US + details)

with `US` a unit separator, `at` written to the millisecond so it round-trips
through JSON, and `details` the exact JSON text that is stored. The first entry
is sealed against `GENESIS` (sixty-four zeros). Verifying walks the log in id
order and recomputes; the first row whose recomputed hash differs, or whose
`prev_hash` is not its predecessor's `hash`, is the break, and `verify()` says
which one and why.

Three kinds of tampering and what each looks like:

- **an edited row** - that row's own hash no longer matches its contents
- **a removed row** - the next row's `prev_hash` points at a hash that is no
  longer there, and its id is not one past its predecessor's
- **a truncated tail** - nothing is *wrong*, so the last hash is what a parent
  writes down or takes away in a download; a shorter log with a different last
  hash is a log that was cut.

Re-sealing the whole chain after an edit would need the code, the database and
the intent - and would still show as a different final hash from the one in
last night's backup.

### Never fatal

Every call in here is wrapped: a logging failure must not break the app. If the
database is unwritable, the app keeps working and the Python log says why - the
alternative, a child unable to make a picture because an audit row would not
write, is worse than a gap.
"""

import contextvars
import hashlib
import json
import logging
import time

from . import store

log = logging.getLogger("makery.audit")

US = "\x1f"

# Who did it. A profile id for a child, or one of these.
PARENT = "parent"
SYSTEM = "system"
TELEGRAM = "telegram"

# The areas, which are also what the Log tab filters by: an event is
# "area.verb" and the filter is a prefix match.
AREAS = [
    {"id": "render", "label": "Making things"},
    {"id": "gallery", "label": "Deleting and restoring"},
    {"id": "upload", "label": "Photos and drawings"},
    {"id": "safety", "label": "The filter saying no"},
    {"id": "setting", "label": "Settings changed"},
    {"id": "profile", "label": "Who uses it"},
    {"id": "pin", "label": "PIN tries"},
    {"id": "parent", "label": "The parent page"},
    {"id": "telegram", "label": "The bot"},
    {"id": "factory", "label": "The factory closing"},
    {"id": "backup", "label": "Backups"},
    {"id": "log", "label": "The log itself"},
]

# One line of English per event, for the Log tab. A row whose event is not in
# here still shows - with its own name - because a log that hides what it does
# not recognise is not a log.
WORDS = {
    "render.started": "started making something",
    "render.finished": "finished making something",
    "render.cancelled": "stopped a render",
    "gallery.deleted": "moved something to the trash",
    "gallery.restored": "took something back out of the trash",
    "gallery.destroyed": "deleted something for good",
    "gallery.emptied": "emptied the trash",
    "upload.kept": "kept a photo or a drawing",
    "upload.refused": "had a photo refused by the picture checker",
    "safety.refused": "had something stopped by the filter",
    "setting.changed": "changed a setting",
    "setting.tidied": "tidied away settings an older version had",
    "profile.added": "added somebody",
    "profile.renamed": "changed somebody's details",
    "profile.removed": "removed somebody",
    "profile.switched": "signed in as somebody",
    "pin.failed": "got the parent PIN wrong",
    "pin.lockout": "locked the PIN out after too many tries",
    "parent.opened": "opened the parent page",
    "telegram.command": "sent the bot a command",
    "factory.closed": "closed the factory after a refusal",
    "backup.written": "wrote a backup",
    "backup.restored": "restored a backup",
    "log.trimmed": "trimmed the oldest entries",
    "log.kept": "kept the log a restore did not match",
}


# Settings written by the machinery rather than by a person. Logging these
# would bury the ones a parent actually changed under a hundred rows a day:
# the date they passed the sums, which limit email has gone out, the milestones
# already shown. They are visible on the parent page anyway.
#
# `quiz_secret` is in here for a second reason: it is a signing key, not a
# preference, and a log that quoted it would be a log that hands out a forged
# pass to anyone who downloads it.
QUIET_SETTINGS = frozenset({
    "quiz_passed_day", "quiz_passed_at", "quiz_bypassed_day", "quiz_secret",
    "limit_mail_image", "limit_mail_video", "limit_mail_music",
    "digest_last_sent", "milestones_seen", "bonus_day",
    "trash_emptied_at", "trash_emptied_count", "trash_emptied_by",
    "closed_at", "closed_reason",
})

# Whether this request came through `_parent()`. A parent editing the Rules tab
# is signed in as somebody in their browser, and without this every household
# setting they changed was written down as that child's doing. Set in main.py,
# in the one function every parent route starts with.
BY_PARENT: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "by_parent", default=False)


def _seal(row_id: int, prev_hash: str, at: float, actor: str,
          event: str, details: str) -> str:
    """The hash of one entry. The only place the recipe is written down - the
    verifier calls this same function, so the two cannot drift apart."""
    payload = US.join([prev_hash, str(row_id), f"{at:.3f}", actor, event, details])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _actor() -> str:
    """Whoever this request belongs to, or "system" for the janitor.

    Imported here rather than at the top: gallery imports this module, and a
    module-level import back the other way would be a cycle.
    """
    try:
        # The parent page first: whoever it is signed in as, the person who
        # typed the PIN is the one who did this.
        if BY_PARENT.get():
            return PARENT
        from . import gallery

        return (gallery.WHO.get() or {}).get("id") or SYSTEM
    except Exception:       # pragma: no cover - a broken profiles file
        return SYSTEM


def record(event: str, actor: str = "", **details) -> dict | None:
    """Write one entry. Never raises, never blocks anything important.

    `actor` defaults to whoever the request belongs to. Pass it explicitly for
    the three that are nobody in particular - the parent page, the bot, and the
    janitor - because those run with no profile in context and "system" would
    be the wrong answer for two of them.
    """
    try:
        text = json.dumps(_clean(details), sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        text = "{}"
    try:
        return store.chain_append(
            time.time(), actor or _actor(), str(event)[:64], text, _seal)
    except Exception as exc:
        # The whole point of this line. A log that can take the app down is a
        # log that gets taken out, and then there is no log at all.
        log.warning("could not write '%s' to the activity log: %s", event, exc)
        return None


def _clean(details: dict) -> dict:
    """Keep the entry small and free of anything that is a credential.

    Long strings are cut rather than dropped: "they typed a nine-hundred-word
    prompt" is worth recording and the middle of it is not.
    """
    out = {}
    for key, value in details.items():
        # None is "the caller had nothing to say"; "" is a real answer - a
        # setting cleared to empty is exactly the kind of change worth a row.
        if value is None:
            continue
        if isinstance(value, str) and len(value) > 300:
            value = value[:300] + "…"
        out[str(key)[:40]] = value
    return out


# --- settings ---------------------------------------------------------------

def settings_changed(scope: str, before: dict, after: dict) -> None:
    """One entry per key that actually moved, with which child it was for.

    Called from `gallery.update_settings`, which is the one place a setting is
    ever written - so there is no second path to remember to cover.
    """
    for key in sorted(after):
        if key in QUIET_SETTINGS:
            continue
        new = after[key]
        if key not in before:
            # Nothing stored yet. For the household that means the value
            # `.env` seeded on the first start; for a child it means they were
            # following the household's. Both are worth saying rather than
            # leaving a blank where the old value should be.
            was = "(the default)" if not scope else "(followed everyone else)"
        elif before[key] == new:
            continue
        else:
            was = _short(before[key])
        record("setting.changed", key=key, was=was, now=_short(new),
               # "" is the household, and saying so reads better than a blank.
               whose=scope or "everyone")


def _short(value):
    if isinstance(value, str) and len(value) > 120:
        return value[:120] + "…"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)[:120]
    return value


# --- the age trim -----------------------------------------------------------

def keep_days() -> float:
    """How long the log is kept. 0 - the default - is for ever."""
    from . import gallery

    return gallery.number("audit_keep_days", 0.0, 3650.0)


def keep_words() -> bool:
    """Whether a refusal records the words that were refused.

    Off by default. A parent who wants to see what was typed can turn it on,
    and that is a decision worth making deliberately rather than one this file
    makes for every household.
    """
    from . import gallery

    return gallery.flag("audit_words", False)


def trim() -> int:
    """Drop anything older than the setting, and say so in the log.

    Nothing by default. When it does run, the entry it writes afterwards is
    what turns the gap at the front of the chain from "somebody has been in
    here" into "the app trimmed it on Tuesday, and here is the sealed row that
    says so".
    """
    days = keep_days()
    if days <= 0:
        return 0
    try:
        gone, highest = store.chain_trim(time.time() - days * 86400)
    except Exception as exc:
        log.warning("could not trim the activity log: %s", exc)
        return 0
    if gone:
        record("log.trimmed", actor=SYSTEM, entries=gone, up_to_id=highest,
               older_than_days=days)
        log.info("activity log: trimmed %d entries older than %s days",
                 gone, days)
    return gone


# --- reading it back --------------------------------------------------------

def _row(entry: dict) -> dict:
    try:
        details = json.loads(entry["details"])
    except (TypeError, ValueError):
        details = {}
    return {
        "id": entry["id"],
        "at": entry["at"],
        "actor": entry["actor"],
        "event": entry["event"],
        "says": WORDS.get(entry["event"], entry["event"]),
        "area": entry["event"].split(".", 1)[0],
        "details": details,
        "hash": entry["hash"],
    }


def page(day: str = "", actor: str = "", area: str = "",
         limit: int = 50, offset: int = 0) -> dict:
    """Newest first, filtered and paged, for the Log tab.

    `day` is a local calendar date, because "what happened on Tuesday" is the
    question a parent asks and an epoch range is not.
    """
    since, until = _day_range(day)
    limit = max(1, min(int(limit or 50), 500))
    rows = store.chain_page(since, until, actor, area, limit, max(0, int(offset)))
    return {
        "entries": [_row(r) for r in rows],
        "total": store.chain_count(since, until, actor, area),
        "offset": max(0, int(offset)),
        "limit": limit,
        "actors": store.chain_actors(),
        "areas": AREAS,
        "keep_days": keep_days(),
        "keep_words": keep_words(),
    }


def count() -> int:
    """How many entries there are, for the heading on the tab."""
    try:
        return store.chain_count()
    except Exception:
        return 0


def _day_range(day: str):
    if not day:
        return None, None
    try:
        start = time.mktime(time.strptime(day.strip()[:10], "%Y-%m-%d"))
    except (ValueError, OverflowError):
        return None, None
    # Through the calendar, not by adding 86400: the day a clock changes is 23
    # or 25 hours long and both ends of it are still that day.
    lt = time.localtime(start)
    end = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday + 1,
                       0, 0, 0, 0, 0, -1))
    return start, end


def verify() -> dict:
    """Walk the whole chain and recompute every seal.

    Returns "intact", or the first entry that does not add up and what is wrong
    with it. Reads in pages, so a log with a year in it does not have to fit in
    memory.
    """
    checked = 0
    first_id = 0
    last_id = 0
    last_hash = store.GENESIS
    expect_prev = store.GENESIS
    expect_id = 0
    cursor = 0
    while True:
        rows = store.chain_after(cursor, 500)
        if not rows:
            break
        for entry in rows:
            cursor = entry["id"]
            if not checked:
                first_id = entry["id"]
                # A trim leaves the oldest surviving row sealed against a hash
                # that is no longer here, and that is not a break. What would
                # be a break is the *next* row disagreeing with this one.
                expect_prev = entry["prev_hash"]
                expect_id = entry["id"]
            if entry["prev_hash"] != expect_prev:
                return _broken(entry, checked, first_id,
                               "it does not follow on from the entry before it")
            if entry["id"] != expect_id:
                return _broken(entry, checked, first_id,
                               f"entry {expect_id} is missing")
            recomputed = _seal(entry["id"], entry["prev_hash"], entry["at"],
                               entry["actor"], entry["event"], entry["details"])
            if recomputed != entry["hash"]:
                return _broken(entry, checked, first_id,
                               "its contents do not match its seal - it has been edited")
            checked += 1
            last_id = entry["id"]
            last_hash = entry["hash"]
            expect_prev = entry["hash"]
            expect_id = entry["id"] + 1
    trimmed = first_id > 1
    return {
        "ok": True,
        "checked": checked,
        "first_id": first_id,
        "last_id": last_id,
        # What to write down, or to compare against last night's backup. A
        # shorter log with a different last hash is a log that was cut.
        "last_hash": last_hash,
        "trimmed": trimmed,
        "says": (
            "Nothing has been written to the log yet." if not checked else
            f"Intact: all {checked} entries check out."
            + (f" The oldest kept is #{first_id}; anything before it was trimmed"
               " by the age setting, which says so in the log itself."
               if trimmed else "")
        ),
    }


def _broken(entry: dict, checked: int, first_id: int, why: str) -> dict:
    when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry["at"]))
    return {
        "ok": False,
        "checked": checked,
        "first_id": first_id,
        "broken_at": entry["id"],
        "broken_when": when,
        "why": why,
        "says": (f"The chain breaks at entry #{entry['id']} ({when}): {why}. "
                 f"The {checked} entries before it are intact."),
    }


# --- handing it out ---------------------------------------------------------

def export_lines(as_csv: bool):
    """The whole log, oldest first, a line at a time.

    A generator because this is streamed: the point of the download is that a
    parent can keep a copy somewhere this app cannot reach, and that copy has
    to be able to be big. The hashes go with it, so it verifies elsewhere.
    """
    if as_csv:
        yield "id,when,actor,event,details,prev_hash,hash\n"
    cursor = 0
    while True:
        rows = store.chain_after(cursor, 500)
        if not rows:
            return
        for entry in rows:
            cursor = entry["id"]
            when = time.strftime("%Y-%m-%d %H:%M:%S",
                                 time.localtime(entry["at"]))
            if as_csv:
                yield ",".join([
                    str(entry["id"]), when, _csv(entry["actor"]),
                    _csv(entry["event"]), _csv(entry["details"]),
                    entry["prev_hash"], entry["hash"]]) + "\n"
            else:
                yield json.dumps({**entry, "when": when},
                                 sort_keys=True) + "\n"


def _csv(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


# --- the backup -------------------------------------------------------------

def for_backup() -> list[dict]:
    """Every entry, for `backup.build()`. The raw rows, seals included, so a
    restored log verifies exactly as the original did."""
    out: list[dict] = []
    cursor = 0
    while True:
        rows = store.chain_after(cursor, 1000)
        if not rows:
            return out
        out.extend(rows)
        cursor = rows[-1]["id"]


def from_backup(rows) -> dict:
    """Put a backup's log back - but **only into an empty one**.

    A restore never shortens the log. If this installation already has entries,
    the backup's are left where they are and an entry is written saying so:
    merging two chains would mean re-sealing one of them, which is precisely
    the operation this whole file exists to make visible.

    "Empty" is meant literally, and `backup.apply` therefore calls this first,
    before it takes its own safety copy - which writes an entry, and would
    otherwise have made the empty case unreachable. The practical shape of it:
    a restore onto a fresh installation brings the history back whole, and a
    restore onto a running one leaves the history alone. Both are what somebody
    doing it would want, and neither loses an entry.
    """
    if not isinstance(rows, list) or not rows:
        return {"restored": 0, "kept": 0}
    try:
        live = store.chain_count()
    except Exception:
        live = 0
    if live:
        record("log.kept", actor=PARENT, in_backup=len(rows), already_here=live)
        log.warning("restore: kept this installation's %d log entries and left "
                    "the backup's %d alone", live, len(rows))
        return {"restored": 0, "kept": live}
    try:
        put = store.chain_restore(rows)
    except Exception as exc:
        log.warning("restore: could not put the log back: %s", exc)
        return {"restored": 0, "kept": 0}
    log.info("restore: put %d log entries back", put)
    return {"restored": put, "kept": 0}
