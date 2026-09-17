"""When the factory is open, by the clock rather than by a switch.

The pause switch answers "is it open *now*", which means a parent has to
remember to flip it twice a day. A timetable answers it for the week: half an
hour before bed, four till six on school days, all Saturday morning. The
switch still exists and still wins - a timetable is the normal case and the
switch is the exception to it.

Three things this deliberately does:

- **It says when, not just no.** "Back soon" is the right sign for a parent
  who shut the factory by hand and the wrong one for a timetable, where the
  answer is known: "opens at 4:00pm". A closed sign that tells them when to come
  back is the difference between a rule and a broken app.
- **It can be overridden.** `open_anyway()` opens it for the rest of the day
  without touching the timetable, from the parent page or from Telegram. A
  timetable with no override is a trap: the one evening it matters, the fix
  would be editing seven rows and remembering to put them back.
- **It never stops a render that is already going.** Like the pause switch, it
  is checked when something starts. Taking a video away at 5:59 because it
  would finish at 6:01 would teach them to not start anything after half past.

The format in `.settings.json` is one line, readable and editable by hand:

    mon=16:00-18:30;tue=16:00-18:30;...;sat=09:00-12:00,14:00-20:00;sun=

A day with no windows is shut. A missing day is shut. `OPEN_HOURS` in the
environment is the default for a household that would rather set it there, and
`"-"` in the settings means "whatever that says" - the same sentinel the other
string settings use.
"""

import logging
import time

from . import gallery, i18n

log = logging.getLogger("makery.schedule")

# Monday first, matching time.localtime().tm_wday.
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday", "Sunday")

# Midnight to midnight, in minutes. 24:00 is allowed as an end so "open until
# bedtime, whenever that is" can be written without an off-by-a-minute.
DAY_END = 24 * 60

# More than this many windows on one day is somebody fighting the parser.
MAX_WINDOWS = 4


def _env_default() -> str:
    """What a timetable falls back to when nothing is stored. Only a broken
    database gets here now: `OPEN_HOURS` seeds the setting on the first start
    and the stored line is the answer from then on."""
    return str(gallery.DEFAULT_SETTINGS.get("schedule") or "")


def _minutes(text: str) -> int | None:
    """"16:30" -> 990. None if it is not a time."""
    text = text.strip()
    if not text:
        return None
    hh, _, mm = text.partition(":")
    try:
        hours, mins = int(hh), int(mm or 0)
    except ValueError:
        return None
    if not (0 <= hours <= 24 and 0 <= mins <= 59):
        return None
    total = hours * 60 + mins
    return total if total <= DAY_END else None


def clock(minutes: int) -> str:
    """990 -> "16:30". The wire format and the <input type="time"> value."""
    minutes = max(0, min(DAY_END, int(minutes)))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# How each language writes half past four in the afternoon. The closed sign is
# the one place in the app a time is read by somebody who is not setting it,
# so it is said the way it is said out loud - and the twelve-hour clock with
# am or pm on the end is an English habit and nobody else's. The other six all
# count to twenty-four; what differs is the separator and whether a zero-minute
# time says the minutes at all.
#
#   fr  16h30 / 16h        the hour carries the h
#   es  16:30              "a las 16:30"
#   pt  16:30
#   it  16:30
#   de  16:30 Uhr / 16 Uhr the unit goes on the end
#   nl  16.30 / 16 uur     a full stop, which is the Dutch convention
_CLOCK = {
    "fr": ("{h}h{m:02d}", "{h}h"),
    "es": ("{h}:{m:02d}", "{h}:00"),
    "pt": ("{h}:{m:02d}", "{h}:00"),
    "it": ("{h}:{m:02d}", "{h}:00"),
    "de": ("{h}:{m:02d} Uhr", "{h} Uhr"),
    "nl": ("{h}.{m:02d} uur", "{h} uur"),
}


def friendly(minutes: int) -> str:
    """990 -> "4:30pm", or "16h30" for a French reader, "16:30 Uhr" in German.

    Midnight and midday are words rather than numbers in every one of them,
    which is why they go through `i18n.t` instead of through the format above:
    "It opens again at 0:00" is a correct sentence nobody says.
    """
    minutes = max(0, min(DAY_END, int(minutes)))
    shape = _CLOCK.get(i18n.lang())
    if shape is None:
        return _friendly_en(minutes)
    if minutes >= DAY_END or minutes == 0:
        return i18n.t("midnight")
    hours, mins = divmod(minutes, 60)
    if hours == 12 and mins == 0:
        return i18n.t("midday")
    return (shape[0] if mins else shape[1]).format(h=hours, m=mins)


def _friendly_en(minutes: int) -> str:
    """The English shape, kept on its own: the parent page's status line is
    English whatever the child's page is set to."""
    minutes = max(0, min(DAY_END, int(minutes)))
    if minutes >= DAY_END:
        return "midnight"
    hours, mins = divmod(minutes, 60)
    if hours == 0 and mins == 0:
        return "midnight"
    if hours == 12 and mins == 0:
        return "midday"
    suffix = "am" if hours < 12 else "pm"
    show = hours % 12 or 12
    return f"{show}:{mins:02d}{suffix}" if mins else f"{show}{suffix}"


def parse(text: str) -> dict[str, list[list[int]]]:
    """The one-line format into {day: [[from, to], ...]}, in minutes.

    Anything it cannot read is dropped rather than raising: this string can be
    hand-edited in `.settings.json`, and a typo in Wednesday should cost
    Wednesday, not the whole week.
    """
    week: dict[str, list[list[int]]] = {day: [] for day in DAYS}
    for chunk in (text or "").replace("\n", ";").split(";"):
        day, _, windows = chunk.partition("=")
        day = day.strip().lower()[:3]
        if day not in week:
            continue
        for window in windows.split(","):
            start, _, end = window.partition("-")
            a, b = _minutes(start), _minutes(end)
            if a is None or b is None or b <= a:
                continue
            week[day].append([a, b])
        week[day] = _tidy(week[day])
    return week


def _tidy(windows: list[list[int]]) -> list[list[int]]:
    """Sorted, merged where they touch, and capped.

    Overlapping windows are not wrong, they are just two ways of writing one -
    and a parent dragging a second row over the first should see one row back,
    not two that argue.
    """
    out: list[list[int]] = []
    for start, end in sorted(windows):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out[:MAX_WINDOWS]


def unparse(week: dict[str, list[list[int]]]) -> str:
    """Back to the one line. Days with nothing are written out as empty rather
    than left out, so the string says what it means without being read against
    this file."""
    return ";".join(
        f"{day}=" + ",".join(f"{clock(a)}-{clock(b)}" for a, b in _tidy(week.get(day) or []))
        for day in DAYS
    )


def raw(settings: dict | None = None) -> str:
    """The timetable as written, before it is parsed. "-" means the
    environment's, which is how every other string setting works."""
    current = gallery.get_settings() if settings is None else settings
    chosen = current.get("schedule", "-")
    if not isinstance(chosen, str) or chosen == "-":
        return _env_default()
    return chosen


def week(settings: dict | None = None) -> dict[str, list[list[int]]]:
    return parse(raw(settings))


def has_times(model: dict[str, list[list[int]]]) -> bool:
    return any(model.get(day) for day in DAYS)


def is_on(settings: dict | None = None) -> bool:
    """Whether the timetable is being applied at all.

    -1, the default, means "on if there is one to apply". A parent who sets
    times expects them to start working; a parent who has never set any should
    not have the app behave as though they set none deliberately.
    """
    current = gallery.get_settings() if settings is None else settings
    try:
        chosen = int(current.get("schedule_on", -1))
    except (TypeError, ValueError):
        chosen = -1
    if chosen < 0:
        return has_times(week(current))
    return bool(chosen)


def _now() -> tuple[int, int, float]:
    """(weekday 0-6, minutes past midnight, the epoch second)."""
    lt = time.localtime()
    return lt.tm_wday, lt.tm_hour * 60 + lt.tm_min, time.time()


def _override_until(settings: dict) -> float:
    """"Open anyway" runs out at the end of the day it was granted, so a
    forgotten override cannot quietly become the timetable."""
    try:
        until = float(settings.get("schedule_override", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    return until if until > time.time() else 0.0


def end_of_day() -> float:
    lt = time.localtime()
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 23, 59, 59, 0, 0, -1))


def open_anyway(on: bool = True, who: str | None = None) -> dict:
    """Ignore the timetable for the rest of today. Not a change to it."""
    return gallery.update_settings(who=who, schedule_override=(end_of_day() if on else 0))


def open_anyway_for_everyone(on: bool = True) -> None:
    """The same, for the household and every child at once.

    The Telegram bot runs with nobody signed in, and a waiver written only
    into the household file never reaches a child whose own file carries a
    `schedule_override` - which every added profile's does. A parent typing
    /open at nine in the evening means "let them in", all of them.
    """
    from . import profiles

    open_anyway(on, who="")
    for who in profiles.all():
        open_anyway(on, who=who["id"])


def state(settings: dict | None = None) -> dict:
    """Everything the pages and the bot need to say when it is open.

    One call, because "is it open", "until when" and "when does it open next"
    are always wanted together - the closed sign needs the third, the open page
    needs the second, and the parent page needs all three.
    """
    current = gallery.get_settings() if settings is None else settings
    model = week(current)
    on = is_on(current)
    wday, minute, _ = _now()
    override = _override_until(current)

    today = [list(w) for w in model.get(DAYS[wday]) or []]
    within = next((w for w in today if w[0] <= minute < w[1]), None)

    out = {
        "on": on,
        "week": {day: [list(w) for w in model.get(day) or []] for day in DAYS},
        "text": unparse(model),
        "today": today,
        "open": True,
        "until": None,
        # Minutes until it shuts, so a warning can be shown before it happens
        # rather than the page going quiet mid-sentence.
        "left": None,
        "opens": None,
        "opens_day": None,
        "opens_in": None,
        "override": bool(override),
        "override_until": override or None,
        "says": "",
    }
    if not on:
        return out
    if override:
        out["says"] = "Open anyway until midnight - the timetable is off for today."
        return out

    if within is not None:
        out["until"] = within[1]
        out["left"] = within[1] - minute
        out["says"] = f"Open until {friendly(within[1])}."
        return out

    out["open"] = False
    nxt = _next_opening(model, wday, minute)
    if nxt is None:
        out["says"] = "Closed - the timetable has no open times in it."
        return out
    days_ahead, start = nxt
    out["opens"] = start
    out["opens_in"] = days_ahead
    out["opens_day"] = (
        "today" if days_ahead == 0 else
        "tomorrow" if days_ahead == 1 else
        # A week out lands on the same weekday it is now, and "on Tuesday" on
        # a Tuesday reads as "later today". Only one day of the week is open
        # for that to happen at all, but that is exactly the timetable where
        # getting it wrong matters most.
        "next " + DAY_NAMES[(wday + days_ahead) % 7] if days_ahead >= 7 else
        DAY_NAMES[(wday + days_ahead) % 7]
    )
    out["says"] = f"Closed until {_friendly_en(start)} {out['opens_day']}."
    return out


def _next_opening(model, wday: int, minute: int) -> tuple[int, int] | None:
    """(how many days ahead, what minute). Walks a week and then gives up -
    a timetable with nothing in it has no next opening, and pretending
    otherwise would show a child a day that never comes."""
    for ahead in range(8):
        for start, _end in model.get(DAYS[(wday + ahead) % 7]) or []:
            if ahead > 0 or start > minute:
                return ahead, start
    return None


def reopen_line(st: dict | None = None) -> str:
    """Just the when, with no "the factory is closed" in front of it.

    The closed sign already says it is closed - in large letters, with a
    sleeping factory over the top - so repeating it underneath reads as a
    stutter. The 503 body has no such heading and wants the whole sentence,
    which is what `closed_message` is for.
    """
    st = state() if st is None else st
    if st["open"]:
        return ""
    if st["opens"] is None:
        return i18n.t("Back soon!")
    when = friendly(st["opens"])
    if st["opens_day"] == "today":
        return i18n.t("It opens at {when}. See you then!", when=when)
    if st["opens_day"] == "tomorrow":
        return i18n.t("It opens again tomorrow at {when}. See you then!", when=when)
    day = st["opens_day"] or ""
    # "next Tuesday" and "Tuesday" are two entries rather than one plus a
    # prefix: French puts the "prochain" after the day, not in front of it.
    return i18n.t("closed-until-next-day" if day.startswith("next ")
                  else "closed-until-day", day=i18n.t(day), when=when)


def closed_message(st: dict | None = None) -> str:
    """The sign they are shown, which is the whole reason for this module."""
    st = state() if st is None else st
    if st["open"]:
        return ""
    return i18n.t("The factory is closed right now. ") + reopen_line(st)


def save(text: str) -> dict:
    """Store a timetable, canonicalised. Returns the settings.

    Written back through `parse`/`unparse` rather than as typed, so what comes
    out of the settings file is always something this module can read - and
    what the parent page redraws is what the engine will actually use.
    """
    return gallery.update_settings(schedule=unparse(parse(text)))
