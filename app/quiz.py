"""Three sums before the factory opens, once a calendar day.

Whole numbers only, at one of three levels a parent picks per child, and only
the kinds of sum they have ticked: division always comes out exact, subtraction
never goes negative, and no answer is bigger than the box it is typed into.
This is a warm-up, not an exam - there is no lockout, no score kept, and
getting one wrong just means trying that one again.

The questions are made and marked on the server, so the answers are not sitting
in the page for them to read. Passing sets a signed cookie holding the local
date; the pass is recorded server-side too, so clearing the cookie or moving to
another device does not hand out a second go. The comparison is between date
strings, never elapsed hours - "tomorrow" means tomorrow's date, however late
they were up.
"""

import hashlib
import hmac
import logging
import random
import secrets
import time

from . import gallery, i18n

log = logging.getLogger("makery.quiz")

COOKIE = "warm-up"

# A grown-up standing at their iPad who needs the page for a minute, without
# spending their one go at the sums. Deliberately a *separate*, short-lived
# cookie and nothing written to the settings: a pass that a parent can hand out
# by typing a PIN would be a pass they could watch them type.
PARENT_COOKIE = "warm-up-grownup"


def parent_minutes() -> int:
    """How long "I'm a grown-up" lasts. A setting on the parent page; it was
    QUIZ_BYPASS_MINUTES in the environment until the settings moved."""
    return gallery.whole("quiz_bypass_minutes", 1, 1440)


def question_count() -> int:
    """How many sums. One value in one place - the parent page - per child."""
    return gallery.whole("quiz_questions", 1, 10)


# How hard, and which kinds. Both are settings, per child, on the parent page;
# QUIZ_LEVEL and QUIZ_OPS seed them on the first start and are not read again.
LEVELS = ("easy", "medium", "hard")
OPS = ("add", "sub", "mul", "div")


def clean_ops(text) -> list[str]:
    """"add, div" into ["add", "div"], in a fixed order, unknowns dropped.

    Returns empty for anything unrecognisable rather than guessing - the
    callers below each have their own answer for that, and they are different
    answers.
    """
    asked = {bit.strip().lower() for bit in str(text or "").replace(" ", ",").split(",")}
    return [op for op in OPS if op in asked]


def level() -> str:
    chosen = gallery.text("quiz_level").strip().lower()
    return chosen if chosen in LEVELS else "medium"


def operations() -> list[str]:
    """Which kinds of sum they are asked.

    A stored string with nothing recognisable in it means addition: the route
    that writes this will not save such a thing, but a hand-edited database
    could, and a quiz with no questions in it is one they can never pass.
    """
    return clean_ops(gallery.text("quiz_ops")) or ["add"]

# Open quizzes, by token. In memory on purpose: a restart mid-quiz costs them a
# fresh set of questions, which is a kinder failure than a token they can read
# the answers out of.
_open: dict[str, dict] = {}
_OPEN_TTL = 900
_OPEN_MAX = 64

_WORDS = {1: "One quick sum", 2: "Two quick sums", 3: "Three quick sums", 4: "Four quick sums",
          5: "Five quick sums", 6: "Six quick sums", 7: "Seven quick sums", 8: "Eight quick sums",
          9: "Nine quick sums", 10: "Ten quick sums"}


def friendly() -> str:
    return i18n.t("Let's warm up your brain first! {sums} and the factory opens.",
                  sums=i18n.t(_WORDS[question_count()]))


# Wrong guesses at the grown-up box on the sums used to be counted here. They
# are `pinbox.SHARED` now, next to the three other boxes that take the same PIN
# and need the same rule with their own copy of it - and, the reason that is a
# module rather than a list in `main.py`, where `app/telegram.py` can reach it
# too, so /unlock's promise to clear "any wrong-PIN lockout" is true of all
# four. `main` asks `pinbox` directly; there are no wrappers here, on purpose,
# because a `quiz.clear_pin_tries()` left lying about is an invitation to clear
# the wrong box from the wrong place, which is the bug that started all this.


def today() -> str:
    return time.strftime("%Y-%m-%d")


def enabled() -> bool:
    return gallery.flag("quiz_enabled", True)


# --- questions --------------------------------------------------------------
# One function per level rather than one function with a pile of ifs in it: the
# numbers *are* the design here, and a parent deciding whether a level suits
# their own child should be able to read the ranges at a glance.
#
# Three rules hold at every level, and they are why these are written out
# rather than drawn from one formula: no answer below zero, division that comes
# out exact, and nothing longer than the four digits the answer box fits.


def _easy(kind: str) -> tuple[str, int]:
    """Single digits, adding to 20, tables to 5. For somebody six or seven."""
    if kind == "add":
        a, b = random.randint(2, 9), random.randint(2, 9)
        return f"{a} + {b}", a + b
    if kind == "sub":
        # The bigger number first and never all of it: the answer is at least 1
        # rather than a 0 that looks like a trick.
        a = random.randint(5, 18)
        b = random.randint(1, a - 1)
        return f"{a} − {b}", a - b
    if kind == "mul":
        a, b = random.randint(2, 5), random.randint(2, 5)
        return f"{a} × {b}", a * b
    b, answer = random.randint(2, 5), random.randint(2, 5)
    return f"{b * answer} ÷ {b}", answer


def _medium(kind: str) -> tuple[str, int]:
    """Roughly grade six, and the default: what this asked before there were
    levels at all, so an installation that upgrades sees no change."""
    if kind == "add":
        a, b = random.randint(120, 989), random.randint(120, 989)
        return f"{a} + {b}", a + b
    if kind == "sub":
        a = random.randint(320, 999)
        b = random.randint(110, a - 100)
        return f"{a} − {b}", a - b
    if kind == "mul":
        a, b = random.randint(12, 39), random.randint(3, 12)
        return f"{a} × {b}", a * b
    # exact division only - a remainder is a different lesson
    b, answer = random.randint(3, 12), random.randint(4, 20)
    return f"{b * answer} ÷ {b}", answer


def _hard(kind: str) -> tuple[str, int]:
    """Two- and three-digit numbers, tables to 12, and one sum in three with a
    second step in it. A two-step stays inside its own operation - a parent who
    ticked adding only should not be handed a subtraction to do."""
    two_step = random.random() < 0.34
    if kind == "add":
        if two_step:
            a, b, c = (random.randint(20, 199) for _ in range(3))
            return f"{a} + {b} + {c}", a + b + c
        a, b = random.randint(150, 999), random.randint(150, 999)
        return f"{a} + {b}", a + b
    if kind == "sub":
        if two_step:
            # Both bites out of a number big enough to take them: at most 480
            # comes off at least 500, so the answer cannot reach zero.
            a = random.randint(500, 999)
            b, c = random.randint(100, 240), random.randint(100, 240)
            return f"{a} − {b} − {c}", a - b - c
        a = random.randint(200, 999)
        b = random.randint(101, a - 50)
        return f"{a} − {b}", a - b
    if kind == "mul":
        a, b = random.randint(11, 99), random.randint(2, 12)
        return f"{a} × {b}", a * b
    b, answer = random.randint(3, 12), random.randint(11, 60)
    return f"{b * answer} ÷ {b}", answer


_MAKERS = {"easy": _easy, "medium": _medium, "hard": _hard}


def _question(kind: str, hardness: str = "") -> tuple[str, int]:
    return _MAKERS.get(hardness or level(), _medium)(kind)


def make() -> dict:
    """A fresh quiz. Returns the token and the questions, without the answers."""
    _sweep()
    wanted = question_count()
    hardness, ops = level(), operations()
    kinds = random.sample(ops, min(wanted, len(ops)))
    while len(kinds) < wanted:
        kinds.append(random.choice(ops))
    random.shuffle(kinds)

    asked: list[tuple[str, int]] = []
    seen: set[str] = set()
    for kind in kinds:
        # Never the same sum twice in one set. With one kind ticked and easy
        # numbers there are not many to draw from, and two identical rows read
        # as a mistake in the page rather than as a question worth answering.
        made = _question(kind, hardness)
        for _ in range(40):
            if made[0] not in seen:
                break
            made = _question(kind, hardness)
        seen.add(made[0])
        asked.append(made)

    token = secrets.token_urlsafe(16)
    _open[token] = {"answers": [a for _, a in asked], "made": time.time()}
    return {"token": token, "questions": [q for q, _ in asked]}


def _sweep() -> None:
    cutoff = time.time() - _OPEN_TTL
    for token in [t for t, v in _open.items() if v["made"] < cutoff]:
        _open.pop(token, None)
    while len(_open) > _OPEN_MAX:
        _open.pop(next(iter(_open)), None)


def mark(token: str, answers: list) -> tuple[bool, list[int]]:
    """(passed, indices of the wrong ones).

    The token is spent either way. All three right opens the factory; anything
    else means a new set of three, so the same sum is never asked twice and
    guessing at one of them gets them nowhere. An unknown token fails
    everything, which comes out as a fresh set too.
    """
    quiz = _open.pop(token, None)
    if quiz is None:
        return False, list(range(question_count()))

    wrong = []
    for i, correct in enumerate(quiz["answers"]):
        try:
            given = int(str(answers[i]).strip())
        except (IndexError, ValueError, TypeError, AttributeError):
            wrong.append(i)
            continue
        if given != correct:
            wrong.append(i)

    return not wrong, wrong


# --- remembering that they passed --------------------------------------------

def _secret() -> bytes:
    """A signing key kept beside the settings, made once.

    Without it the cookie would be a date they could type themselves; with a key
    that changes every restart they would be re-quizzed every rebuild.
    """
    stored = str(gallery.get_settings().get("quiz_secret") or "")
    if len(stored) < 32:
        stored = secrets.token_urlsafe(32)
        try:
            gallery.update_settings(quiz_secret=stored)
        except OSError as exc:
            log.warning("could not keep the quiz key: %s", exc)
    return stored.encode()


def cookie_for(day: str) -> str:
    mac = hmac.new(_secret(), day.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{day}.{mac}"


def cookie_ok(value: str) -> bool:
    if not value or "." not in value:
        return False
    day, _, mac = value.partition(".")
    if day != today():
        return False
    return hmac.compare_digest(mac, cookie_for(day).partition(".")[2])


def grownup_cookie(until: int) -> str:
    mac = hmac.new(_secret(), str(until).encode(), hashlib.sha256).hexdigest()[:32]
    return f"{until}.{mac}"


def grownup_ok(value: str) -> bool:
    """A grown-up let through recently. Time-limited, not date-limited: it is
    for the next few minutes at the iPad, not for the rest of their day."""
    if not value or "." not in value:
        return False
    until, _, mac = value.partition(".")
    try:
        if int(until) < time.time():
            return False
    except ValueError:
        return False
    return hmac.compare_digest(mac, grownup_cookie(int(until)).partition(".")[2])


def seconds_left_today() -> int:
    """Until local midnight, so the cookie clears itself rather than lingering."""
    now = time.localtime()
    return max(60, 86400 - (now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec))


def record_pass() -> None:
    try:
        gallery.update_settings(quiz_passed_day=today(), quiz_passed_at=time.strftime("%H:%M"))
    except OSError as exc:
        log.warning("could not record the quiz pass: %s", exc)


def passed_today(cookie: str = "", grownup: str = "") -> bool:
    """Whether this browser may use the factory without doing the sums.

    Three ways through: the server's record of a pass (or a parent's day-long
    bypass), their own signed day cookie, or a grown-up who typed the PIN in the
    last `PARENT_MINUTES`. The record is what stops a cleared cookie - or them
    sister's laptop - from being a second go; the day cookie is what lets the
    page know without waiting; the grown-up one expires on the clock and is
    never written down, so it does not use up their go at the sums.
    """
    if not enabled():
        return True
    if str(gallery.get_settings().get("quiz_passed_day") or "") == today():
        return True
    return cookie_ok(cookie) or grownup_ok(grownup)


def bypass() -> None:
    """A parent waving them through, today only.

    The same record a real pass writes, so it expires with the date like
    everything else here - there is no way to leave the quiz accidentally off
    tomorrow. Marked as a bypass purely so the parent page can say so.
    """
    try:
        gallery.update_settings(
            quiz_passed_day=today(), quiz_passed_at=time.strftime("%H:%M"),
            quiz_bypassed_day=today(),
        )
    except OSError as exc:
        log.warning("could not let them skip the quiz: %s", exc)


def reset() -> None:
    """A parent asking them to do it again - undoes a pass or a bypass.

    The signing key is rotated too, or this would do nothing on the one device
    that matters: passed_today() falls back to the cookie once the server's
    record is cleared, and the cookie they were handed this morning is still a
    valid signature over today's date. A new key makes it stop verifying.
    """
    try:
        gallery.update_settings(
            quiz_passed_day="", quiz_passed_at="", quiz_bypassed_day="",
            quiz_secret=secrets.token_urlsafe(32),
        )
    except OSError as exc:
        log.warning("could not reset the quiz: %s", exc)


def status() -> dict:
    settings = gallery.get_settings()
    day = str(settings.get("quiz_passed_day") or "")
    return {
        "enabled": enabled(),
        # Not "questions": the quiz responses spread status() over make(), and
        # a count here would overwrite the actual list of sums.
        "question_count": question_count(),
        # What is in force. There is no "default" to report beside it any
        # more: the environment seeded these once and the stored value is the
        # answer, and the page's own options are the list of choices.
        "level": level(),
        "ops": operations(),
        "passed_today": day == today(),
        "passed_at": str(settings.get("quiz_passed_at") or "") if day == today() else "",
        "bypassed_today": str(settings.get("quiz_bypassed_day") or "") == today(),
    }
