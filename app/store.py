"""One SQLite file for everything a parent decides.

The settings used to be JSON files - `.settings.json` for the household and a
`.settings-<id>.json` laid over it per child. That worked, and it had two
problems worth fixing together:

- **Two writers, no lock.** A route, the janitor and the Telegram bot all write
  settings, from different threads, and the file was read-modify-written whole.
  Two of those landing at once lost one of them silently.
- **Half the controls were not in it at all.** A parent who wanted to change
  how long a video could be edited `.env` and rebuilt the container; one who
  wanted to change the daily limit used the parent page. Same kind of decision,
  two places, and no way to tell from either which one was in force.

So: one `state.db` in `STATE_DIR`, in WAL mode, with a `settings` table keyed
by `(scope, key)` - scope `""` for the household and a profile id for a child -
and the value stored as JSON text so a number stays a number and a list stays a
list. Everything above this file still goes through `gallery.get_settings()`
and `gallery.update_settings()`, which have not changed shape; only what is
underneath them has.

Three things this file is careful about:

- **Reads are on the request path.** Every route that asks whether the factory
  is paused asks this. So each thread keeps its own connection and its own
  cache of the whole table, and the cache is thrown away when anything is
  written - by this thread (a generation counter), or by another connection
  including one in another process (`PRAGMA data_version`, which is exactly
  what it is for). The table is a few hundred small rows; reading all of it is
  cheaper than working out which rows to read.
- **Writes take `BEGIN IMMEDIATE` under a process-wide lock.** The lock keeps
  this process' threads off each other, and `BEGIN IMMEDIATE` plus
  `busy_timeout` keeps a second *process* - the Telegram sandbox test proved
  two can share the state volume - waiting rather than failing. The atomicity
  that `os.replace` used to provide is now the transaction's job.
- **It raises `OSError`.** Every caller in the app already catches `OSError`
  around a settings write, because that is what a file write raised. A
  `sqlite3.Error` escaping into a route would have turned a full disk from a
  500 with a sentence into a 500 with a traceback, so it is translated here.

Two more tables share the file, for the same reason the settings are in it -
they need a transaction, and this is where transactions live:

- **`counters`**, the numbers that only ever go up, which `app/naming.py` uses
  to number a file. `bump()` reads and writes inside one transaction, so two
  renders finishing together cannot be handed the same number.
- **the activity log**, an append-only table with a hash chain over it. The
  rows and the hashing belong to `app/audit.py`; what is here is the half that
  has to be one transaction: reading the last row, sealing the new one against
  it and inserting, with nothing able to land in between. Splitting that across
  two calls would let two threads seal against the same predecessor and write a
  fork.
"""

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path

log = logging.getLogger("makery.store")

DB_NAME = "state.db"

# Set by gallery.py at import, so this module does not have to work out
# STATE_DIR for itself and there is no second copy of that rule to drift.
DIR: Path | None = None

# Per-thread connection and cache. A sqlite3 connection is not safe to share
# across threads and `check_same_thread=False` would only move the problem, so
# each thread opens its own; there are a handful of them.
_local = threading.local()

# One writer at a time inside this process. Cheap - a settings write is a few
# rows - and it means the only contention SQLite ever has to resolve is with
# another process.
_lock = threading.RLock()

# Bumped by every write this process makes, so every thread's cache notices.
# Another process' write is caught by PRAGMA data_version instead.
_generation = 0


def use(directory: Path) -> None:
    """Where the database lives. Called once, by gallery.py."""
    global DIR
    DIR = Path(directory)


def path() -> Path:
    if DIR is None:  # pragma: no cover - gallery sets it at import
        raise RuntimeError("store.use() was never called")
    return DIR / DB_NAME


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    scope TEXT NOT NULL,
    key   TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (scope, key)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS counters (
    name  TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

-- The activity log. Append-only by construction: nothing in this file updates
-- a row, and the only DELETE is the age trim, which says so in the log itself.
-- AUTOINCREMENT, not a plain rowid, so an id is never handed out twice after a
-- trim - a gap in the numbers stays a gap and can be read as one.
CREATE TABLE IF NOT EXISTS audit (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    at        REAL NOT NULL,
    actor     TEXT NOT NULL,
    event     TEXT NOT NULL,
    details   TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_at ON audit (at);
"""


def _connect() -> sqlite3.Connection:
    DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path()), timeout=20, isolation_level=None)
    # WAL so a reader never blocks the writer and vice versa - which is the
    # whole reason a second process can watch this file without either of them
    # seeing "database is locked".
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=20000")
    conn.executescript(SCHEMA)
    return conn


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    return conn


def _fail(what: str, exc: Exception) -> OSError:
    log.error("settings store: could not %s: %s", what, exc)
    return OSError(f"could not {what}: {exc}")


def _stamp(conn: sqlite3.Connection) -> tuple:
    """What the cache is valid for: this process' own write count, and
    SQLite's own counter of commits made by *other* connections."""
    try:
        other = conn.execute("PRAGMA data_version").fetchone()[0]
    except sqlite3.Error:
        other = time.time()
    return (_generation, other)


def everything() -> dict[str, dict]:
    """`{scope: {key: value}}` for the whole table, cached per thread.

    The returned dict is the cache itself, not a copy: callers read it and
    build their own answer on top. Nothing mutates it.
    """
    try:
        conn = _conn()
        stamp = _stamp(conn)
        cached = getattr(_local, "cache", None)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        out: dict[str, dict] = {}
        for scope, key, value in conn.execute(
                "SELECT scope, key, value FROM settings"):
            try:
                out.setdefault(scope, {})[key] = json.loads(value)
            except ValueError:
                continue
        _local.cache = (stamp, out)
        return out
    except sqlite3.Error as exc:
        # A read must never take a route down: the app behaved sensibly with an
        # unreadable settings file before and it behaves sensibly here, by
        # falling back to the defaults.
        log.error("settings store: could not read: %s", exc)
        return {}


def scope(name: str = "") -> dict:
    """One scope's stored keys. `""` is the household."""
    return everything().get(name, {})


def scopes() -> list[str]:
    return sorted(everything())


def write(name: str, values: dict) -> None:
    """Set some keys in one scope. Nothing else in that scope is touched."""
    if not values:
        return
    write_many({name: values})


def write_many(by_scope: dict[str, dict]) -> None:
    """One transaction across several scopes.

    `update_settings` splits a single save between the household and one child;
    doing both halves in one transaction is what stops a crash in the middle
    leaving half a save behind.
    """
    global _generation
    rows = [(s, k, json.dumps(v))
            for s, values in by_scope.items() for k, v in values.items()]
    if not rows:
        return
    with _lock:
        conn = _conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(
                "INSERT INTO settings (scope, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(scope, key) DO UPDATE SET value = excluded.value",
                rows)
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise _fail("save the settings", exc) from exc
        _generation += 1


def forget(name: str, keys=None) -> None:
    """Drop keys from a scope, or the whole scope when `keys` is None.

    Used when a profile is removed and when a restore replaces everything.
    """
    global _generation
    with _lock:
        conn = _conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if keys is None:
                conn.execute("DELETE FROM settings WHERE scope = ?", (name,))
            else:
                conn.executemany(
                    "DELETE FROM settings WHERE scope = ? AND key = ?",
                    [(name, k) for k in keys])
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise _fail("forget those settings", exc) from exc
        _generation += 1


def replace_all(by_scope: dict[str, dict]) -> None:
    """Every setting, for every scope, in one transaction.

    What a restore does. All of it or none of it: a half-applied restore is the
    one outcome worse than a failed one.
    """
    global _generation
    with _lock:
        conn = _conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM settings")
            conn.executemany(
                "INSERT INTO settings (scope, key, value) VALUES (?, ?, ?)",
                [(s, k, json.dumps(v))
                 for s, values in by_scope.items()
                 for k, v in (values or {}).items()])
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise _fail("restore the settings", exc) from exc
        _generation += 1


# --- the meta table: small facts about the database itself ------------------

def note(key: str, value) -> None:
    global _generation
    with _lock:
        conn = _conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)))
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise _fail("write a note", exc) from exc
        _generation += 1


def noted(key: str, default=None):
    try:
        row = _conn().execute(
            "SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    except sqlite3.Error:
        return default
    if not row:
        return default
    try:
        return json.loads(row[0])
    except ValueError:
        return default


# --- the counters table: numbers that only ever go up -----------------------
#
# A file's name may carry `{n}` (see app/naming.py), and the promise there is
# that a number is never handed out twice. That cannot be a setting: a setting
# is read-modify-written from a cache, and two renders landing together would
# be given the same number. It is its own table, read and written inside one
# `BEGIN IMMEDIATE`, and it deliberately does **not** bump `_generation` - the
# settings cache knows nothing about it and throwing that away once per file
# would be work for nothing.

def bump(name: str, by: int = 1) -> int:
    """Add `by` to one counter and return what it now says. Starts at 1."""
    with _lock:
        conn = _conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT value FROM counters WHERE name = ?",
                               (name,)).fetchone()
            value = int(row[0] if row else 0) + int(by)
            conn.execute(
                "INSERT INTO counters (name, value) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                (name, value))
            conn.execute("COMMIT")
            return value
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise _fail("take the next number", exc) from exc


def counters() -> dict[str, int]:
    """Every counter, for the backup. Losing these to a restore would let a
    number be used a second time, which is the one thing they promise not."""
    try:
        return {name: int(value) for name, value in
                _conn().execute("SELECT name, value FROM counters")}
    except sqlite3.Error:
        return {}


def set_counters(values: dict) -> None:
    """Put a backup's counters back, never below what is already there: a
    restore of last week's file must not rewind next week's numbering."""
    if not values:
        return
    with _lock:
        conn = _conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            for name, value in values.items():
                try:
                    wanted = int(value)
                except (TypeError, ValueError):
                    continue
                conn.execute(
                    "INSERT INTO counters (name, value) VALUES (?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET "
                    "value = MAX(value, excluded.value)", (str(name), wanted))
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise _fail("restore the counters", exc) from exc


def empty() -> bool:
    """Whether anything has ever been stored. What the migration asks."""
    try:
        return not _conn().execute(
            "SELECT 1 FROM settings LIMIT 1").fetchone()
    except sqlite3.Error:
        return False


def checkpoint() -> None:
    """Fold the WAL back into the main file.

    Called before a backup copies the database, so what is copied is the whole
    truth rather than a main file with the last few writes still in a sidecar.
    """
    with _lock:
        try:
            _conn().execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error as exc:
            log.warning("could not checkpoint the settings database: %s", exc)



# --- the activity log -------------------------------------------------------
# A table rather than a file, and `app/audit.py` says why. What lives here is
# the part that must not be split: seal-against-the-last-row and insert happen
# inside one `BEGIN IMMEDIATE`, under the same process-wide lock every other
# write here takes, so two threads can never seal against the same predecessor.

# What the first entry is sealed against. A constant rather than an empty
# string, so a row with no predecessor still looks like every other row.
GENESIS = "0" * 64

_AUDIT_COLUMNS = "id, at, actor, event, details, prev_hash, hash"


def _audit_row(row: tuple) -> dict:
    return {"id": row[0], "at": row[1], "actor": row[2], "event": row[3],
            "details": row[4], "prev_hash": row[5], "hash": row[6]}


def chain_last() -> dict | None:
    """The newest entry, or None for a log nothing has been written to yet."""
    try:
        row = _conn().execute(
            f"SELECT {_AUDIT_COLUMNS} FROM audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.Error as exc:
        log.error("activity log: could not read the last entry: %s", exc)
        return None
    return _audit_row(row) if row else None


def chain_append(at: float, actor: str, event: str, details: str, seal) -> dict:
    """Add one entry, sealed against whatever is currently last.

    `seal(row_id, prev_hash, at, actor, event, details)` returns the hash. The
    hashing is audit.py's; all this file knows about the chain is that a row is
    sealed against the row before it and that both steps are one transaction.
    """
    with _lock:
        conn = _conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            last = conn.execute(
                "SELECT id, hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
            # `seq` rather than max(id): AUTOINCREMENT keeps its own high-water
            # mark, so an id is not handed out twice after the age trim has
            # removed the row that had it.
            seq = conn.execute(
                "SELECT seq FROM sqlite_sequence WHERE name = 'audit'").fetchone()
            row_id = int(seq[0]) + 1 if seq else (int(last[0]) + 1 if last else 1)
            prev_hash = last[1] if last else GENESIS
            digest = seal(row_id, prev_hash, at, actor, event, details)
            conn.execute(
                "INSERT INTO audit (id, at, actor, event, details, prev_hash, hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (row_id, at, actor, event, details, prev_hash, digest))
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise _fail("write to the activity log", exc) from exc
    return {"id": row_id, "at": at, "actor": actor, "event": event,
            "details": details, "prev_hash": prev_hash, "hash": digest}


def _audit_where(since=None, until=None, actor="", area="") -> tuple[str, list]:
    clauses, args = [], []
    if since is not None:
        clauses.append("at >= ?")
        args.append(float(since))
    if until is not None:
        clauses.append("at < ?")
        args.append(float(until))
    if actor:
        clauses.append("actor = ?")
        args.append(actor)
    if area:
        # An event is "area.verb", so a prefix match is the filter by kind.
        clauses.append("event LIKE ?")
        args.append(f"{area}.%")
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", args


def chain_page(since=None, until=None, actor="", area="",
               limit: int = 50, offset: int = 0) -> list[dict]:
    """Newest first, for the page. The filters are the ones the Log tab offers."""
    where, args = _audit_where(since, until, actor, area)
    try:
        rows = _conn().execute(
            f"SELECT {_AUDIT_COLUMNS} FROM audit{where} "
            "ORDER BY id DESC LIMIT ? OFFSET ?", (*args, int(limit), int(offset))
        ).fetchall()
    except sqlite3.Error as exc:
        log.error("activity log: could not read it: %s", exc)
        return []
    return [_audit_row(r) for r in rows]


def chain_count(since=None, until=None, actor="", area="") -> int:
    where, args = _audit_where(since, until, actor, area)
    try:
        return int(_conn().execute(
            f"SELECT count(*) FROM audit{where}", args).fetchone()[0])
    except sqlite3.Error:
        return 0


def chain_after(row_id: int = 0, limit: int = 1000) -> list[dict]:
    """A page of the log in *written* order, for verifying and for exporting.

    Oldest first and by id, so a caller can walk the whole thing in bounded
    memory - a log kept for a year is not something to load into a list.
    """
    try:
        rows = _conn().execute(
            f"SELECT {_AUDIT_COLUMNS} FROM audit WHERE id > ? "
            "ORDER BY id LIMIT ?", (int(row_id), int(limit))).fetchall()
    except sqlite3.Error as exc:
        log.error("activity log: could not read it: %s", exc)
        return []
    return [_audit_row(r) for r in rows]


def chain_actors() -> list[str]:
    try:
        return [r[0] for r in _conn().execute(
            "SELECT DISTINCT actor FROM audit ORDER BY actor")]
    except sqlite3.Error:
        return []


def chain_trim(before: float) -> tuple[int, int]:
    """Drop entries older than `before`. Returns (how many, the newest id gone).

    The only DELETE in this file, and the only thing that can shorten the log.
    It does nothing unless a parent has set a number of days, and `audit.trim()`
    writes an entry saying it ran - so the gap at the front of the chain has a
    sealed explanation at the back of it.
    """
    with _lock:
        conn = _conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT count(*), max(id) FROM audit WHERE at < ?",
                (float(before),)).fetchone()
            count, highest = int(row[0] or 0), int(row[1] or 0)
            if count:
                conn.execute("DELETE FROM audit WHERE at < ?", (float(before),))
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise _fail("trim the activity log", exc) from exc
    return count, highest


def chain_empty() -> bool:
    try:
        return not _conn().execute("SELECT 1 FROM audit LIMIT 1").fetchone()
    except sqlite3.Error:
        return True


def chain_restore(rows: list[dict]) -> int:
    """Put a backup's log into an empty table, ids, hashes and all.

    Only ever called when there is nothing to lose - `audit.from_backup()`
    refuses otherwise - because the alternative to keeping the ids is a chain
    whose seals match nothing.
    """
    global _generation
    if not rows:
        return 0
    with _lock:
        conn = _conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM audit LIMIT 1").fetchone():
                conn.execute("ROLLBACK")
                return 0
            conn.executemany(
                "INSERT INTO audit (id, at, actor, event, details, prev_hash, hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(int(r["id"]), float(r["at"]), str(r["actor"]), str(r["event"]),
                  str(r["details"]), str(r["prev_hash"]), str(r["hash"]))
                 for r in rows])
            conn.execute("COMMIT")
        except (sqlite3.Error, KeyError, TypeError, ValueError) as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise _fail("restore the activity log", exc) from exc
        _generation += 1
    return len(rows)
