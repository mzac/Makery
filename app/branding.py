"""What this instance is called, in one place.

This was written for one particular eleven-year-old, and that child's name
ended up spelled into the page title, the email subjects, the movie title
cards and the parent page. None of that is in the code any more, so the same
code runs for anybody's child - or for nobody's, with neutral wording.

**Nothing here is read from the environment at import.** A name and an age
belong to a *profile* now, and the title is a setting; `KID_NAME` and
`KID_AGE` in `.env` make the first profile on an empty installation and are
never looked at again. So `KID_NAME`, `AGE` and `TITLE` keep their spelling at
every call site and are read when they are asked for, through the module's
`__getattr__` - a parent renaming a child on the parent page must reach
tonight's email subject, and before this it did not.

Nothing here is a secret and nothing here changes behaviour. It exists so that
no other module has to think about apostrophes or pronouns.
"""

import contextvars
import os


def _clean(name: str) -> str:
    return " ".join((name or "").split())[:40]


# What app/profiles.py calls the first child when nobody has named one. It is a
# placeholder in the picker rather than a name, so it reads back here as
# "nobody said": otherwise the title is "Me's AI Factory" and the emails say
# "Me has used all their pictures for today".
UNNAMED = "Me"

# The two that make the first profile, and only that. Read here so there is one
# copy of the rule; `profiles._first()` is the one moment either is used.
SEED_NAME = _clean(os.getenv("KID_NAME", ""))
try:
    SEED_AGE = max(0, min(19, int(os.getenv("KID_AGE", "0") or 0)))
except ValueError:
    SEED_AGE = 0


def _named(name: str) -> str:
    """A profile's name, or "" when it is only the placeholder."""
    name = _clean(name)
    return "" if name == UNNAMED else name


def household() -> dict:
    """The name and age the parent-facing sentences use.

    Whichever profile `adopts` - the one that owns everything made before there
    were profiles - is the household, exactly as it is for the settings. Its
    name is what the emails, the Telegram bot and the janitor mean by "the
    child".

    Imported late and never allowed to fail: `profiles` imports this module, and
    an unreadable profiles file must not take the nightly email with it.
    """
    try:
        from . import profiles

        every = profiles.all()
        who = next((p for p in every if p.get("adopts")), None) or every[0]
        return {"name": _named(who.get("name")), "age": int(who.get("age") or 0)}
    except Exception:
        return {"name": SEED_NAME, "age": SEED_AGE}


# she / he / they. Only ever used in the *parent-facing* text - the emails and
# the parent page - where the sentences are about the child rather than
# addressed to them. Everything the child reads is already second person.
#
# Singular "they" is the default and is what every sentence in this app is
# written against; the other two are here because a parent who has said which
# words fit their own child should get them.
_PRONOUNS = {
    "she": ("she", "her", "her", "hers", False),
    "he": ("he", "him", "his", "his", False),
    "they": ("they", "them", "their", "theirs", True),
}
# Which one is a setting on the parent page - it is wording about the child
# rather than a fact about the machine - and `KID_PRONOUN` in `.env` only seeds
# it on the first start. A profile owns the name and the age; this stays the
# household's, because the sentences it appears in are the emails and the
# parent page, and both of those are the household's too.
#
# Read through the module's `__getattr__` so that `branding.THEIR` keeps its
# spelling at all twenty-odd call sites and stops being frozen at import.


def pronouns() -> tuple:
    from . import gallery

    return _PRONOUNS.get(gallery.text("kid_pronoun"), _PRONOUNS["they"])


_DYNAMIC = {"THEY": 0, "THEM": 1, "THEIR": 2, "THEIRS": 3, "PLURAL": 4,
            "WHO_PRONOUN": 0}

# The four that used to be frozen at import. Spelled the same at every call
# site and worked out when they are asked for, so that renaming a child or
# retitling the app on the parent page reaches the next sentence rather than
# the next rebuild.
_LIVE = {
    "KID_NAME": lambda: household()["name"],
    "AGE": lambda: household()["age"],
    "WHO": lambda: household()["name"] or "Your child",
    "TITLE": lambda: _title(),
}


def __getattr__(name: str):
    if name in _DYNAMIC:
        return pronouns()[_DYNAMIC[name]]
    if name in _LIVE:
        return _LIVE[name]()
    raise AttributeError(name)


def possessive(name: str) -> str:
    """Ada -> Ada's; Charles -> Charles'."""
    if not name:
        return ""
    return name + ("'" if name[-1:].lower() == "s" else "'s")


def app_title() -> str:
    """Whatever a parent has typed under "Words and wording", or "".

    Set, it wins everywhere and in every language: somebody who has named the
    whole thing did not mean it to change per child or per language.
    """
    from . import gallery

    return _clean(gallery.text("app_title"))


def default_title() -> str:
    """"Ada's AI Factory", or "My AI Factory" when nobody is named.

    What the app would be called with the title box left empty, which is what
    that box shows as its placeholder - so the page does not have to carry a
    second copy of the apostrophe rule to say it.
    """
    name = household()["name"]
    return f"{possessive(name)} AI Factory" if name else "My AI Factory"


def _title() -> str:
    return app_title() or default_title()


# `TITLE`, `WHO`, `KID_NAME` and `AGE` are read through `__getattr__` above:
#
#   TITLE      the app's name, from the setting or built from the child's
#   WHO        the subject of a parent-facing sentence: "Ada made 3 pictures
#              today", or "Your child made 3 pictures today" with no name set
#   KID_NAME   the household child's name, or "" when nobody is named
#   AGE        how old that child is, which is what most of the model
#              instructions are really asking about: "nearly twelve" was
#              spelled into fourteen of them, and it is the single thing that
#              decides whether what comes back is written for a capable reader
#              or for a toddler. 0 means it was not said.
#
# `WHO` mid-sentence, where a pronoun reads better than repeating the name, is
# `WHO_PRONOUN` - see the pronoun block above.

_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven",
          "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
          "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")

# Ages are spelled out rather than given as "11": a model reading "eleven years
# old" writes for a person, and reading "11" is one token away from writing a
# spec sheet. `age_words()` below is the one that does it - there used to be
# three module constants here as well, frozen at import against one age, and
# nothing outside this file ever read them.


# Whose page this is, for the length of one request: {"name": ..., "age": ...}.
# Set by the same middleware that sets gallery.WHO. None means the household's
# own name and age - the profile that adopts - which is what the emails and the
# janitor see.
#
# The age is here rather than passed down because it reaches the models through
# prompts.text(), which is called from nine modules and knows nothing about who
# is asking. A nine-year-old and a twelve-year-old should not get the same
# helper, and that is a one-line difference in the instruction.
CHILD = contextvars.ContextVar("child", default=None)


def age_words(age: int) -> tuple[str, str]:
    """("eleven years old", "eleven-year-old"), or the wording for no age."""
    word = _WORDS[age] if 0 < age < len(_WORDS) else ""
    return (f"{word} years old" if word else "a child",
            f"{word}-year-old" if word else "child")


def about(text: str, age: int | None = None) -> str:
    """Fill the age tokens in a model instruction.

    A plain replace and not str.format: several of these instructions contain
    literal braces - the comic one shows the model the JSON it must return -
    and formatting them would either break or need every brace doubled.
    """
    if age is None:
        age = (CHILD.get() or {}).get("age") or household()["age"]
    phrase, noun = age_words(int(age or 0))
    return text.replace("{age}", phrase).replace("{age_old}", noun)


def name_now() -> str:
    """The child this request belongs to, or the household's one child."""
    return _named((CHILD.get() or {}).get("name")) or household()["name"]


def who_now() -> str:
    """The same, as the subject of a parent-facing sentence."""
    return name_now() or household()["name"] or "Your child"


# The possessive is the part that does not translate, and the seven fall into
# three shapes.
#
# **English and German** hang the name off the front: English adds 's, German
# adds a bare s - "Adas KI-Fabrik" - and an apostrophe alone after a name that
# already hisses, "Max' KI-Fabrik". **French, Spanish, Italian and
# Portuguese** put the name last after "de" / "di", and French alone elides
# before a vowel or a mute h, "d'Ada". **Dutch** sidesteps the question with
# "De AI-fabriek van Ada", which is right whatever the name ends in - so it
# needs no rule here at all, and that is a translation decision rather than an
# omission.
#
# So there are two entries per language and not four: the ordinary one, and
# the one the name's own shape asks for where a language has one. Both are
# whole sentences in the dictionary, because the elision happens *inside* the
# words rather than in front of them.
_SIBILANT = ("s", "ß", "x", "z")
_VOWEL_FR = "aeiouàâäéèêëïîôöùûüh"


def _title_key(code: str, name: str) -> str:
    """Which of the two dictionary entries this name wants."""
    if code == "fr" and name[0].lower() in _VOWEL_FR:
        return "factory-of-elided"
    if code == "de" and name[-1].lower() in _SIBILANT:
        return "factory-of-elided"
    return "{name}'s AI Factory"


def title_for(name: str = "") -> str:
    """"Ada's AI Factory", "La fabrique IA d'Ada", "Adas KI-Fabrik".

    The possessive is the part that does not translate - see `_title_key`.

    The title set under "Words and wording" still wins in every language,
    because somebody who has named the whole thing did not mean it to change
    per child, or per language.
    """
    from . import i18n

    if app_title():
        return app_title()
    name = _named(name) or household()["name"]
    if not name:
        return i18n.t("My AI Factory")
    code = i18n.lang()
    if code == "en":
        return f"{possessive(name)} AI Factory"
    return i18n.t(_title_key(code, name), name=name)


def title_pieces(name: str = "") -> list[str]:
    """The title split into the two lines the header prints it on.

    The big white line is whichever half carries the *name*, and the gold one
    under it is the rest. Which half that is follows the language - English
    and German put the name first, the Romance ones put it last - and the page
    used to work it out again with a regular expression per language. It is
    decided here instead, where the sentence is built and the name is already
    known, and handed over on /api/app.
    """
    title = title_for(name)
    who = _named(name) or household()["name"]
    if not who or who not in title:
        return [title, ""]
    at = title.index(who)
    # The name and whatever is glued to it - "Adas", "d'Ada" - belong to the
    # line that carries the name.
    end = at + len(who)
    while end < len(title) and title[end] not in " ":
        end += 1
    head, tail = title[:at].strip(), title[end:].strip()
    if at == 0:
        return [title[:end], tail]
    return [title[at:end], head]


# There is deliberately no verb-agreement helper. Every sentence in the
# parent-facing text has WHO as its subject - a name, or "Your child" - and
# both are singular noun phrases, so the verb is "has" whatever KID_PRONOUN
# says. The places where the *pronoun* is the subject are all past tense
# ("she made" / "they made", "he deleted" / "they deleted"), and English
# does not inflect those. An earlier version had a helper here and it wrote
# "Your child have used all their pictures".


def public() -> dict:
    """What the page needs to brand itself, for whoever is looking."""
    child = CHILD.get() or {}
    home = household()
    name = _named(child.get("name")) or home["name"]
    age = child.get("age") or home["age"]
    return {"title": title_for(name), "title_parts": title_pieces(name),
            "kid": name, "who": name or "Your child", "age": age}
