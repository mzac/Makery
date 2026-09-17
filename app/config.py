"""Where a deployment value comes from: the parent page first, then `.env`.

Two earlier rounds moved every *behavioural* setting out of `.env` and onto the
parent page, where `.env` seeds a row once and the row owns it afterwards (see
`gallery.SEEDED_FROM_ENV`). That model is right for a daily limit and wrong for
the handful of values left here, for two reasons:

- **Seeding copies a credential into the database on the first start**, whether
  or not anybody asked for it - and every row in that table goes into the
  backup file a parent emails to themselves.
- **An upgrade must change nothing.** A value that is only in `.env` has to
  keep working exactly as it did, for ever, with no first-start moment where it
  is copied somewhere else and the file quietly stops mattering.

So this is an *override* layer rather than a seed. Three states per key:

    a row here            -> that value is what the app uses
    no row, `.env` set    -> `.env` is what the app uses
    neither               -> the built-in default below

"Clear" on the page deletes the row, which puts `.env` back. There is no
"stored as empty" state: one value in two places with a third value to say
which of them counts is the tri-state the settings table spent a whole round
getting rid of, and it is not being reinvented here.

**The rows live in their own scope**, `"deploy"`, not in the household's. That
is what keeps them out of `gallery.get_settings()`, out of `public_settings()`,
out of every `/api/*` answer that returns the settings whole, and - the reason
that matters most - out of `backup.build()`, which exports the settings table
by scope. See `backup.SKIP_SCOPES`.

**Secrets are never read back out to a browser.** `state()` says whether one is
set and where it came from; nothing in this module hands a secret's value to
anything but the code that has to use it, and `redactions()` exists so that
anything which does accidentally format one into a log line gets it removed on
the way out.
"""

import logging
import os
import re

from . import store

log = logging.getLogger("makery.config")

# Its own scope in the settings table. A profile id is a hex string (see
# app/profiles.py), so this cannot collide with a child's scope, and a word
# rather than a symbol so a human reading `state.db` can see what it is.
SCOPE = "deploy"

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class Bad(ValueError):
    """The value offered is not usable. The message is shown to a parent, and
    **never contains the value** - a rejected secret is still a secret."""


class Field:
    """One deployment value: where it comes from and what may be put in it."""

    def __init__(self, key, env, default="", secret=False, restart="",
                 what="", check=None, empty="", optional=False):
        self.key = key
        self.env = env
        self.default = default
        self.secret = secret
        # True when leaving it unset is an ordinary way to run: a relay that
        # wants no password, a bot nobody has set up. Those must not be
        # reported at startup as though something were missing.
        self.optional = optional
        # Empty when a change is live; otherwise the sentence the page shows
        # saying what has to happen before it takes effect.
        self.restart = restart
        self.what = what
        # What to say when somebody saves an empty box. Its own string because
        # the PIN has no Clear to point them at - see `_check_pin`.
        self.empty = empty or "That cannot be left empty. Use Clear instead."
        self._check = check

    def clean(self, raw: str) -> str:
        text = (raw or "").strip()
        if not text:
            raise Bad(self.empty)
        if self._check:
            self._check(text)
        return text


def _check_url(text: str) -> None:
    if not re.match(r"^https?://[^\s/]+", text):
        raise Bad("That needs to look like http://name:port.")


def _check_level(text: str) -> None:
    if text.upper() not in LOG_LEVELS:
        raise Bad("Pick one of " + ", ".join(LOG_LEVELS) + ".")


def _check_tz(text: str) -> None:
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    except ImportError:  # pragma: no cover - zoneinfo is in the standard library
        return
    try:
        ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise Bad("This machine has no timezone by that name. They look like "
                  "Europe/Paris or America/Toronto.") from exc


def _check_token(text: str) -> None:
    # Telegram's own shape: a numeric bot id, a colon, then the secret half.
    # Checked because the commonest way to get this wrong is to paste half of
    # it, and the symptom otherwise is a bot that silently never answers.
    if not re.match(r"^\d{5,}:[A-Za-z0-9_-]{20,}$", text):
        raise Bad("That does not look like a bot token. BotFather's look like "
                  "123456789 then a colon then about 35 letters and digits.")


def _check_notify(text: str) -> None:
    # One URL per line or per comma, each optionally with `made,file=` in
    # front of it. Only the shape is checked here; app/notify.py does the rest
    # and says so in the log.
    for token in text.replace(",", " ").replace("\n", " ").split():
        if "=" in token and "://" not in token.split("=", 1)[0]:
            token = token.split("=", 1)[1]
        if "://" not in token:
            raise Bad("Each one has to be a URL with :// in it, like "
                      "ntfy://ntfy.sh/mytopic.")


def _check_mail_url(text: str) -> None:
    # One Apprise URL, and only its shape is checked here - app/digest.py hands
    # it to Apprise, which is the thing that knows what schemes exist.
    if "://" not in text or not text.split("://", 1)[0].strip():
        raise Bad("That has to be one URL with :// in it, like "
                  "mailtos://you:apppassword@gmail.com.")


def _check_pin(text: str) -> None:
    if len(text) < 4:
        raise Bad("A PIN needs at least four characters.")
    if len(text) > 64:
        raise Bad("That is too long for a PIN.")


# The keys, in the order the parent page shows them. `what` is for the log and
# for `.env.example`; the page carries its own wording next to the box.
# Public knowledge by design - see the parent_pin field below.
DEFAULT_PIN = "1234"

FIELDS = {
    f.key: f for f in (
        Field("notify_urls", "NOTIFY_URLS", secret=True, check=_check_notify,
              what="where messages to a phone go"),
        Field("telegram_token", "TELEGRAM_BOT_TOKEN", secret=True,
              check=_check_token, optional=True,
              # Also read out of a tgram:// notify URL, so an empty box here
              # does not mean there is no bot.
              what="the Telegram bot's own token"),
        Field("smtp_pass", "DIGEST_SMTP_PASS", secret=True, optional=True,
              what="the password for the mail relay"),
        Field("digest_url", "DIGEST_URL", secret=True, optional=True,
              check=_check_mail_url,
              # An ordinary settings row until this round, which put the app
              # password out of `mailtos://user:apppassword@gmail.com` into
              # every backup file. See `migrate_from_settings`.
              what="one Apprise URL for the nightly email, used as it is"),
        Field("parent_pin", "PARENT_PIN", secret=True, check=_check_pin,
              # A default rather than an empty string, so that "nobody has set
              # a PIN" cannot happen. It used to, and it meant the parent page
              # let everybody through - the one setting whose unset state was
              # the insecure one. This is a published default and so is public
              # knowledge: it exists to make the gate present on a fresh
              # install, not to be relied on. The app says so loudly at
              # startup until it is changed.
              default=DEFAULT_PIN,
              # There is no Clear for this one: taking the lock off from behind
              # it is how a page like this is left open by accident.
              empty="A PIN cannot be empty - that would leave this page open "
                    "to anybody who can reach the app.",
              what="the PIN on the parent page"),
        Field("log_level", "LOG_LEVEL", default="INFO", check=_check_level,
              what="how much the container log says"),
        Field("comfy_url", "COMFY_URL", default="http://comfyui-comfyui:8188",
              check=_check_url,
              restart="The picture maker holds one WebSocket open for progress, "
                      "so a new address is picked up when the container restarts.",
              what="where the picture maker is"),
        Field("ollama_url", "OLLAMA_URL", default="http://ollama:11434",
              check=_check_url, what="where the helper models are"),
        Field("tz", "TZ", check=_check_tz,
              restart="The clock is set once, as the app starts, so that "
                      "“today” cannot move under a day that is "
                      "already half over.",
              what="which clock “today” is measured against"),
    )
}

# What a browser may be shown. Everything else about a secret - set or not, and
# where it came from - is fine; the value is not.
PUBLIC = tuple(k for k, f in FIELDS.items() if not f.secret)


# --- reading ----------------------------------------------------------------

def _rows() -> dict:
    """The stored overrides. Never raises: an unreadable database has to mean
    "nobody has overridden anything", or a broken disk would take the PIN off
    the parent page."""
    try:
        return store.scope(SCOPE) if store.DIR is not None else {}
    except Exception as exc:  # pragma: no cover - store already swallows its own
        log.error("could not read the deployment settings: %s", exc)
        return {}


def stored(key: str) -> str | None:
    """What the page has set, or None for "the page has not set this"."""
    value_ = _rows().get(key)
    return value_ if isinstance(value_, str) and value_ else None


def from_env(key: str) -> str:
    field = FIELDS[key]
    return (os.getenv(field.env) or "").strip()


def value(key: str) -> str:
    """What the app should use for this key, right now."""
    field = FIELDS[key]
    return stored(key) or from_env(key) or field.default


def source(key: str) -> str:
    """"page", "env" or "default" - which of the three is in force."""
    if stored(key) is not None:
        return "page"
    return "env" if from_env(key) else "default"


def pin_is_default() -> bool:
    """True while the parent page is still on the published default PIN."""
    return parent_pin() == DEFAULT_PIN


def parent_pin() -> str:
    """The PIN that gates the parent page, right now.

    Its own name because it is asked for on every parent request and reads
    better than `value("parent_pin")` at ten call sites in app/main.py.
    """
    return value("parent_pin")


def state(key: str) -> dict:
    """One field, for the page. **A secret's value is never in here.**"""
    field = FIELDS[key]
    row = {
        "key": key,
        "secret": field.secret,
        "set": bool(value(key)),
        "source": source(key),
        "env": field.env,
        "env_set": bool(from_env(key)),
        "restart": field.restart,
        "optional": field.optional,
        "what": field.what,
    }
    if not field.secret:
        row["value"] = value(key)
        row["default"] = field.default
    return row


def public_state() -> dict:
    """Every field the Settings tab draws, keyed by name."""
    return {key: state(key) for key in FIELDS}


# --- writing ----------------------------------------------------------------

def put(key: str, raw: str) -> dict:
    """Put a value on the page's side of the fence. Raises `Bad` on a value
    this app will not take, and `OSError` if the database will not have it."""
    field = FIELDS[key]
    text = field.clean(raw)
    was = source(key)
    store.write(SCOPE, {key: text})
    _after_change(key, "set", was)
    return state(key)


def clear(key: str) -> dict:
    """Drop the page's value, so whatever `.env` says applies again."""
    was = source(key)
    store.forget(SCOPE, [key])
    _after_change(key, "cleared", was)
    return state(key)


def _after_change(key: str, what: str, was: str) -> None:
    """Log it, tell anything holding the old value, and refresh the redactions.

    **The value is not in the entry.** What a parent needs from the log is that
    somebody changed the bot token on Tuesday, and the audit log is exported
    from the parent page - a credential in it is a credential in that export.
    """
    refresh_redactions()
    apply(key)
    try:
        from . import audit

        audit.record("config.changed", actor=audit.PARENT, key=key,
                     what=what, was=was, now=source(key))
    except Exception as exc:  # pragma: no cover - audit.record swallows its own
        log.warning("could not log the change to %s: %s", key, exc)
    log.info("%s was %s from the parent page (%s -> %s)",
             FIELDS[key].env, what, was, source(key))


def apply(key: str) -> None:
    """Make a changed value take effect, for the ones where that is possible.

    The rest are `Field.restart` and say so on the page. Nothing here reaches
    into another module's state: `notify` and `telegram` re-read their own on
    the next call, and the two clients that cannot are the two that restart.
    """
    if key == "log_level":
        apply_log_level()


def apply_log_level() -> None:
    level = value("log_level").upper()
    if level not in LOG_LEVELS:
        level = "INFO"
    logging.getLogger().setLevel(level)


def apply_timezone() -> None:
    """Put the app's clock where the parent page says, once, at startup.

    Every "today" in this app - the daily limits, the sums, whether tonight's
    email has gone, the date in a filename - is `time.localtime()`, which is
    the process' own timezone. Setting it here rather than only in the
    container's environment means one answer inside the process rather than
    two; doing it *once* rather than on every save is why this key is marked
    as needing a restart. Moving the clock under a day that is already half
    over would reset or freeze that day's allowance, which is not something a
    settings page should be able to do by accident.
    """
    import time

    wanted = value("tz")
    if not wanted:
        return
    os.environ["TZ"] = wanted
    if hasattr(time, "tzset"):
        time.tzset()


# --- taking a credential out of the settings table --------------------------
#
# Keys that used to be ordinary settings rows and are fields here now. A row in
# that table is a row in `backup.build()`, so a credential in one is a
# credential in every backup file a parent has ever emailed to themselves -
# which is the whole reason this module exists.
MOVED_FROM_SETTINGS = ("digest_url",)


def migrate_from_settings() -> None:
    """Move any of `MOVED_FROM_SETTINGS` out of the household's scope.

    `digest_url` - the "Apprise URL, used as it is" box on the Daily email
    card - was a plain settings row, and its own documented example is
    `mailtos://user:apppassword@gmail.com`. An installation that took that
    advice has a mail password in the settings table and in every backup it
    has made since.

    So on every start: if the old row is still there, its value comes here -
    unless the page has already set one, in which case the page's wins and the
    old one is simply dropped - and **the old row goes either way**. Leaving it
    behind would leave the credential exactly where it should not be, which is
    the thing being fixed rather than a detail of it.

    Runs before `refresh_redactions()` so the moved value is redacted from the
    first log line onwards, and never raises: a database that will not take the
    write must not stop the app starting.
    """
    if store.DIR is None:
        return
    try:
        old = store.scope()
    except Exception as exc:  # pragma: no cover - store swallows its own
        log.error("could not read the settings table: %s", exc)
        return
    for key in MOVED_FROM_SETTINGS:
        if key not in old:
            continue
        was = old[key]
        text = was.strip() if isinstance(was, str) else ""
        try:
            if text and stored(key) is None:
                store.write(SCOPE, {key: text})
                log.warning(
                    "%s was a setting and is a deployment value now; the "
                    "stored one has been moved out of the settings table, "
                    "where the backup could reach it", FIELDS[key].env)
            store.forget("", [key])
        except OSError as exc:
            log.error("could not move %s out of the settings table: %s",
                      FIELDS[key].env, exc)


def apply_startup() -> None:
    """Everything that has to happen before the app serves anything."""
    migrate_from_settings()
    apply_timezone()
    apply_log_level()
    refresh_redactions()


# --- keeping secrets out of the log -----------------------------------------
#
# A logging filter runs on every record in the process, including httpx's
# request lines, so it cannot ask the database what the secrets are - that
# would be a SQLite call per log line. It reads this tuple instead, which is
# rebuilt at startup and after every change, which are the only two moments it
# can move.

_REDACT: tuple[str, ...] = ()

# Below this length a "secret" is more likely to be a word that appears in
# ordinary log lines than the credential itself, and redacting it would make
# the log unreadable while protecting nothing. A four-digit PIN is the case
# this is here for - and nothing logs the PIN.
MIN_REDACT = 8


def refresh_redactions() -> None:
    """Rebuild the list of strings that must never appear in a log line."""
    global _REDACT
    found = set()
    for key, field in FIELDS.items():
        if not field.secret:
            continue
        # The one in force *and* the one in `.env`, which are different as
        # soon as somebody replaces a credential from the page. The old one is
        # still a credential sitting in this process' environment, and a log
        # line is no better a place for it for having been superseded.
        for current in (value(key), from_env(key)):
            if len(current) >= MIN_REDACT:
                found.add(current)
    # The bot token hidden inside a `tgram://` URL is the same secret again,
    # and it is the one httpx puts in a URL. Asked of notify rather than
    # re-parsed here, so there is one parser for that format.
    try:
        from . import notify

        for target in notify.targets():
            if target.scheme in ("tgram", "telegram"):
                rest = target.url.split("://", 1)[1].split("?", 1)[0]
                for part in rest.split("/"):
                    if len(part) >= MIN_REDACT and ":" in part:
                        found.add(part)
    except Exception as exc:  # pragma: no cover - notify logs its own trouble
        log.debug("could not read the notify URLs for redaction: %s", exc)
    # Longest first, so a token that contains another string is replaced whole.
    _REDACT = tuple(sorted(found, key=len, reverse=True))


def redactions() -> tuple[str, ...]:
    return _REDACT


class HideSecrets(logging.Filter):
    """Take every credential back out of a log record.

    httpx logs each request at INFO with the whole URL, and for the Telegram
    bot the token *is* the URL - one long-poll every fifty seconds would write
    it into the container log for ever, where `docker logs` hands it to anyone
    who can read it. The relay password and the notify URLs are here for the
    same reason: an exception's text carries whatever was in the request.

    Installed on the **root handlers** rather than on a logger. A filter on a
    logger only sees records logged through that logger, never a child's; a
    handler sees everything that reaches it, which is every record in the
    process.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        secrets = _REDACT
        if not secrets:
            return True
        try:
            text = record.getMessage()
        except Exception:  # pragma: no cover - a broken format string
            return True
        hit = False
        for secret in secrets:
            if secret in text:
                text, hit = text.replace(secret, "<secret>"), True
        if hit:
            record.msg, record.args = text, ()
        return True


def install_log_filter() -> None:
    """Put the filter on every root handler, once."""
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, HideSecrets) for f in handler.filters):
            handler.addFilter(HideSecrets())
