"""Songs, through ACE-Step.

The picture and video cards ask for a sentence and add style phrases to it.
Music is the same shape with two differences that matter:

1. **A song has words.** The model takes `tags` (what it should sound like) and
   `lyrics` (what is sung) as two separate fields, so the card has two boxes
   rather than one. "Help me write it" fills both from one idea, which is the
   whole point of it - writing a verse and a chorus is the part a child gets
   stuck on.
2. **Some choices are numbers, not phrases.** A lullaby is not a pop song with
   the word "lullaby" added; it is slower. So the kind of music carries a BPM
   and the mood carries a key, and both go into their own fields on the node.
   That is the difference between "sounds a bit like" and "is".

The tag vocabulary is deliberately short and concrete. ACE-Step responds to
plain descriptions - "acoustic guitar, warm, gentle" - far better than to a
paragraph, and a long tag list from a dozen dropdowns pulls it in every
direction at once.
"""

import logging
import re

from . import i18n, prompts, safety, scripts

log = logging.getLogger("makery.music")


# Section headers ACE-Step understands. Anything else in the lyrics is sung.
#
# ACE-Step 1.0's lyric tokenizer carries twelve of them as tokens of their own
# - [intro], [verse], [chorus], [pre-chorus], [bridge], [outro], [hook],
# [solo], [break], [inst], [start], [end] - and **1.5 does not use that
# tokenizer at all**: it hands the lyrics to a small language model as plain
# text. So the list is not a closed one, and an *annotated* header like
# "[Chorus - everyone]" reads as well as a bare one. ComfyUI's own 1.5
# templates are written that way, which is where `LYRIC_PLAN` gets it from.
SECTION_NAMES = ("intro", "verse", "chorus", "pre-chorus", "bridge", "outro",
                 "hook", "solo", "break", "inst", "instrumental")

# What goes in the lyrics box when they want no singing at all. The model
# treats this as "play, do not sing" rather than as a word to pronounce.
INSTRUMENTAL = "[inst]"

# What they can have it sung in. The codes are ACE-Step's own `language`
# field, and each one is here because `safety.py` has a blocklist for it:
# lyrics in a language the filter does not know would be checked against a
# word list that does not know its words, and that check is the only thing
# between them and whatever the helper feels like writing. **Adding one here
# means adding that language to BLOCKLIST first** - the rule that kept this
# list at two is the same rule that let it grow to seven.
#
# Built from `i18n.LANGS` rather than written out again, so the dropdown and
# the Settings chips cannot come to disagree about what they may have. Each
# name is in its own language, because that is what they are looking for.
LANGUAGES = [(code, i18n.NAMES[code]) for code in i18n.LANGS]

# (group id, label above the dropdown, [(choice id, label, tag phrase)])
GROUPS = [
    (
        "genre",
        "Kind of music",
        [
            ("pop", "Pop", "upbeat pop song, catchy melody, bright production"),
            ("rock", "Rock", "rock band, electric guitars, live drums, energetic"),
            ("dance", "Dance", "electronic dance music, four on the floor, big synths"),
            ("hiphop", "Hip hop", "hip hop beat, punchy drums, clean bassline"),
            ("folk", "Folk", "acoustic folk, fingerpicked guitar, warm and homely"),
            ("orchestra", "Orchestra", "cinematic orchestra, strings and brass, sweeping"),
            ("jazz", "Jazz", "jazz trio, brushed drums, walking bass, piano"),
            ("lullaby", "Lullaby", "gentle lullaby, soft music box, very quiet"),
            ("marching", "Marching band", "marching band, snare drums, bold brass"),
            ("chiptune", "Video game", "8-bit chiptune, retro video game music"),
            ("country", "Country", "country song, acoustic guitar, fiddle, easy swing"),
            ("reggae", "Reggae", "reggae groove, offbeat guitar, deep relaxed bass"),
        ],
    ),
    (
        "mood",
        "Mood",
        [
            ("happy", "Happy", "cheerful and sunny"),
            ("dreamy", "Dreamy", "dreamy and floating, lots of reverb"),
            ("exciting", "Exciting", "fast and exciting, driving rhythm"),
            ("spooky", "Spooky", "spooky and mysterious, minor key"),
            ("calm", "Calm", "calm and peaceful, unhurried"),
            ("silly", "Silly", "silly and playful, bouncy"),
            ("epic", "Epic", "epic and heroic, huge drums"),
            ("sad", "Thoughtful", "thoughtful and a little sad, tender"),
        ],
    ),
    (
        "instrument",
        "Main instrument",
        [
            ("piano", "Piano", "piano leads the tune"),
            ("guitar", "Guitar", "guitar leads the tune"),
            ("drums", "Drums", "drums out in front"),
            ("violin", "Violin", "violin leads the tune"),
            ("flute", "Flute", "flute leads the tune"),
            ("synth", "Synth", "synthesiser leads the tune"),
            ("ukulele", "Ukulele", "ukulele leads the tune"),
            ("trumpet", "Trumpet", "trumpet leads the tune"),
            ("steeldrum", "Steel drums", "steel drums lead the tune"),
            ("harp", "Harp", "harp leads the tune"),
        ],
    ),
    (
        "language",
        "Sung in",
        # No tag phrase: this one is a field on the encoder, not a word in the
        # tag line. See NOT_TAGS.
        [(code, label, "") for code, label in LANGUAGES],
    ),
    (
        "voice",
        "Who sings it",
        [
            ("girl", "A girl", "young female vocals, clear and bright"),
            ("boy", "A boy", "young male vocals, clear and bright"),
            ("woman", "A woman", "female vocals"),
            ("man", "A man", "male vocals"),
            ("choir", "A whole choir", "choir, many voices together"),
            ("robot", "A robot", "vocoder robot vocals"),
        ],
    ),
    (
        "singers",
        "How many singers",
        # `{who}` is filled in from the voice dropdown - see VOICE_WORD. Each
        # phrase has to read properly with it empty too, because nothing
        # chosen there is a perfectly ordinary answer.
        [
            ("duet", "Two taking turns",
             "{who} duet, two singers taking turns, "
             "a verse each and the chorus together"),
            ("group", "A group joins in",
             "lead {who} vocals with backing vocals, "
             "the group joins in on the chorus, harmonies"),
            ("everyone", "Everyone together",
             "{who} group vocals all the way through, "
             "everyone singing together, harmonies"),
            ("call", "Call and answer",
             "call and response vocals, "
             "one {who} voice answered by the rest"),
        ],
    ),
]

# How the two vocal dropdowns are combined.
#
# "Who sings it" says what one singer sounds like; "How many singers" says how
# many there are and what they do. Written side by side they argue - "female
# vocals" followed by "duet" leaves the model to guess whether the second
# singer is female too - so the arrangement phrase takes the voice as a word
# in front of it, and "a girl" plus "two taking turns" comes out as a **female
# duet**. The voice's own phrase still follows it, describing the lead.
#
# A whole choir is already a group of people, so it contributes no word:
# "choir duet" is a contradiction, and the arrangement phrase reads perfectly
# well on its own. With no voice chosen at all `{who}` is empty and each
# phrase means what the word means by itself - a plain "duet" is understood to
# be two different singers.
VOICE_WORD = {
    "girl": "young female",
    "boy": "young male",
    "woman": "female",
    "man": "male",
    "robot": "robot",
    "choir": "",
}

# What the *lyric writer* is told to do about the same choice. The tags above
# ask the music model for the arrangement; these ask the word model for words
# that fit it, because a duet is nothing but a tag unless the verses actually
# alternate. One dropdown, both halves - the same argument `write()` makes for
# doing the tags and the lyrics in a single call.
#
# The bracketed headers are the convention ComfyUI's own ACE-Step 1.5
# templates use ("[Verse 1 - Trap Rap]", "[Intro - Synth Rise & Vocal Chop]"):
# a section marker with a note after it, in plain words.
LYRIC_PLAN = {
    "duet": (
        "Two singers take turns. Head the verses [Verse 1 - Singer 1] and "
        "[Verse 2 - Singer 2] so they alternate, and head every chorus "
        "[Chorus - both together]."
    ),
    "group": (
        "One lead singer, and everybody joins in on the chorus. Head the "
        "verses [Verse 1] and [Verse 2], head every chorus "
        "[Chorus - everyone], and make the chorus short and easy to shout."
    ),
    "everyone": (
        "Everybody sings all of it together. Write the usual verses and "
        "choruses and put \"- everyone\" inside each header, like "
        "[Verse 1 - everyone] and [Chorus - everyone]. Short lines with "
        "plenty of repeating, so a crowd can sing them."
    ),
    "call": (
        "Call and answer: one singer sings a line and the rest answer it. "
        "Write the verses as call-and-answer lines, with the answer in round "
        "brackets at the end of the line, like: Where are we going? "
        "(Anywhere!). Head them [Verse 1 - call and answer] and "
        "[Verse 2 - call and answer]."
    ),
}

# Not a tag. It is its own field on the encoder, so `compose_tags` skips it and
# `language_for` reads it; a "language" written into the tag line would only
# confuse the thing that decides what the song sounds like.
NOT_TAGS = ("language",)

# Groups that mean nothing with nobody singing, so they are dropped from the
# tag line and hidden on the page when they pick "Just music". One list rather
# than a test in each place, because the two disagreeing would either hide a
# dropdown that still worked or show one that did not.
VOICE_ONLY = ("voice", "language", "singers")

# The order tags are written in. Genre first: it is the thing the model leans
# on hardest, and what comes first carries the most weight. The arrangement
# goes last, after the voice it is written around.
ORDER = ["genre", "mood", "instrument", "voice", "singers"]

DEFAULTS = {"genre": "pop", "mood": "happy"}

# What the empty option says, where "Any" would be wrong. See options().
BLANK = {"language": "Match my words", "singers": "Just one singer"}

# Beats per minute per kind of music. A lullaby is not a pop song with the word
# "lullaby" bolted on - it is slower, and this is the field that makes it so.
BPM = {
    "pop": 120, "rock": 132, "dance": 128, "hiphop": 92, "folk": 96,
    "orchestra": 90, "jazz": 110, "lullaby": 68, "marching": 120,
    "chiptune": 140, "country": 104, "reggae": 78,
}
DEFAULT_BPM = 110

# The key each mood is written in. Major sounds bright, minor sounds dark; this
# is the one musical decision that is really about feeling rather than style.
KEYSCALE = {
    "happy": "C major", "dreamy": "D major", "exciting": "E major",
    "spooky": "D minor", "calm": "F major", "silly": "G major",
    "epic": "A minor", "sad": "A minor",
}
DEFAULT_KEYSCALE = "C major"

# --- what kind of sound this is ---------------------------------------------
#
# ACE-Step is a *music* model, and the honest summary of fourteen test renders
# is that it makes music whatever it is asked for. What that leaves room for
# is two things either side of a song, and one thing it cannot do at all.
# Measurements are in CLAUDE.md; the short version:
#
# - **A little tune** is a song with nobody singing and a short clock. Every
#   jingle rendered came out on the grid of the bpm it was given (median gap
#   between onsets 0.853s at 140bpm - exactly two beats - and 0.427s at the
#   same tempo: one beat), strongly pitched, and repeating. It is the kind
#   that works best, because it is the thing the model already is.
# - **A background hum** is the far end: continuous, no beat, nothing to sing
#   along to. It is a real and *measurable* difference rather than a wish -
#   against a song's 2.7-4.4 onsets a second on a regular grid, the hums came
#   out at 0.2-2.7 with the spacing three to twelve times as ragged, an
#   average brightness of 141-405Hz against 499-510, and a tenth to a fiftieth
#   of the energy above 2kHz.
# - **A sound effect is deliberately not here.** Asked for one door creak it
#   produced 1.2 seconds of sound in a 4-second file, once, and there is no
#   way to tell from this side whether it was a door. `app/sounds.py` already
#   has twelve effects synthesised in numpy: exact, instant, free, and the
#   same every time. A diffusion model that spends GPU seconds to maybe
#   produce a creak is strictly worse than one that always does.
#
# What it also cannot do is **noise**. Rain was asked for twice, the second
# time in as many words as exist for it ("white noise, rain hiss, heavy static
# texture, pure noise"), and both came back as a quiet low rumble with 0.6%
# and 0.1% of their energy above 2kHz - rain is almost nothing *but* energy
# above 2kHz. A crowded market was indistinguishable from a song on every
# measure but one. So the hum's tag line steers hard towards a drone and the
# label says "hum" rather than "soundscape": it promises what it can keep.
#
# Fields: the tags prepended to theirs, whether anything is sung, and the
# window of seconds this kind belongs in, which is then clamped into whatever
# bounds a parent set for songs. See seconds_for(). `None` means "whatever a
# song may be", which is what a song is.
KINDS = [
    (
        "song", "A song", {
            # No tags of its own: a song is what the dropdowns already build.
            "tags": "",
            "sings": True,
            "window": None,
        },
    ),
    (
        "jingle", "A little tune", {
            "tags": "short instrumental jingle, one clear tune, "
                    "tight and tidy, no singing",
            "sings": False,
            # Short, and the default is at the short end rather than the
            # middle. Measured: the model stops playing a median of three
            # seconds before the file ends and once stopped six early, so
            # asking for twenty seconds of jingle is asking for twelve
            # seconds of jingle and eight of nothing. `gallery.trim_tail`
            # cuts what is left over; not asking for it in the first place
            # is the better half of the fix.
            #
            # The numbers sit on the slider's own five-second step, because
            # anything between two notches snaps to one and the default would
            # quietly not be the default. 15 asked for is about ten seconds
            # of tune after the trim, which is what a title sting wants; the
            # notches either side are 10 and 20.
            "window": (10, 20, 15),
        },
    ),
    (
        "ambience", "A background hum", {
            "tags": "continuous ambient drone, steady room tone, "
                    "slow and unchanging, no drums, no beat, no melody, "
                    "nothing to sing along to",
            "sings": False,
            # Long: a hum is something to leave playing behind something
            # else. This is the one kind that reliably fills its clock - the
            # spaceship hum was still sounding at 14.95s of 15.
            "window": (15, 60, 30),
        },
    ),
]

DEFAULT_KIND = "song"

# Dropdowns that make no sense for a kind, hidden on the page and skipped in
# the tag line. Only one entry, and it earns itself: "marching band, snare
# drums, bold brass" in front of a hum is a contradiction the model resolves
# by making a march, and the kind's own phrase is written to be the loudest
# thing in the line. Mood and main instrument are kept - a spooky hum and a
# harp drone are both perfectly good things to want.
#
# The bpm goes with it: with no genre there is nothing to look one up from,
# and a drone wants the slowest clock there is anyway.
HIDDEN_FOR = {"ambience": ("genre",)}
AMBIENCE_BPM = 60

_KINDS = {kid: spec for kid, _, spec in KINDS}

# The kinds with nobody singing. The lyrics box and all three vocal dropdowns
# are hidden for these on the page, and the route forces [inst] whatever the
# page sent - one list, so the two cannot disagree the way a test in each
# place would.
INSTRUMENTAL_KINDS = tuple(kid for kid, _, spec in KINDS if not spec["sings"])

# What each kind is called once it is a job and a file on disk.
#
# A song keeps the name it has always had, so nothing already in their gallery
# moves and no sidecar has to be rewritten; the other two get their own, so
# the shelf, the badge, the "it's ready" line and the log can say which it is.
# **One source of truth**: half a dozen modules key off these three strings
# (`jobs.Job.is_audio`, `timings.FAMILY`, `gallery.usage_today`,
# `naming.KIND_WORD`, the digest and the bot), and three literal tuples that
# had to agree is how one of them ends up quietly not counting.
JOB_KIND = {"song": "music", "jingle": "jingle", "ambience": "ambience"}
JOB_KINDS = tuple(JOB_KIND.values())


def kind_of(value) -> str:
    """Whichever of KINDS they asked for, or a song."""
    value = (value or "").strip().lower()
    return value if value in _KINDS else DEFAULT_KIND


def sings(kind: str) -> bool:
    """Whether this kind has words at all."""
    return bool(_KINDS[kind_of(kind)]["sings"])


def kind_tags(kind: str) -> str:
    return _KINDS[kind_of(kind)]["tags"]


def kind_options() -> list[dict]:
    """The "What kind of sound" chips, for the page to draw.

    Each carries its own seconds, because the length slider has to move when
    they change the chip - a ninety-second jingle is not a jingle.
    """
    out = []
    for kid, label, spec in KINDS:
        low, high, mid = seconds_for(kid)
        out.append({
            "id": kid,
            "label": i18n.label("kind", kid, label),
            "hint": i18n.t(HINTS[kid]),
            "sings": spec["sings"],
            "seconds": [low, mid, high],
            # Which dropdowns to show for it. The same list options() puts on
            # each group, from the other end, so the page can hide a row the
            # moment they tap a chip without asking the server again.
            "hides": list(HIDDEN_FOR.get(kid, ())),
        })
    return out


# One line under the chips saying what they will get. Worth the words: "a
# background hum" is not a thing an eleven-year-old has a word for yet, and a
# chip whose result surprises them is a chip they stop tapping.
HINTS = {
    "song": "Words, a tune and somebody singing them.",
    "jingle": "A short tune with nobody singing - good for the start of a video.",
    "ambience": "A long, quiet sound to put behind something else. No tune, no beat.",
}


def seconds_for(kind: str) -> tuple[int, int, int]:
    """(shortest, longest, default) for one kind, in seconds.

    Each kind has a window that suits it, **clamped into the song bounds a
    parent set** rather than ignoring them: a parent who shortens the longest
    song on the Rules tab expects everything to get shorter, and a second set
    of rows on that page for "but how long can a hum be" is a control nobody
    asked for.

    A window that falls entirely outside what a parent allows - a jingle's
    8-20s when songs must be at least 30 - gives the parent's bounds back
    whole. The alternative is a slider with one position on it, and a parent
    who set a floor of thirty seconds meant it.
    """
    kind = kind_of(kind)
    low, high = min_seconds(), max_seconds()
    window = _KINDS[kind]["window"]
    if not window:
        return low, high, default_seconds()
    want_low, want_high, want_mid = window
    kind_low, kind_high = max(low, want_low), min(high, want_high)
    if kind_low > kind_high:
        return low, high, default_seconds()
    return kind_low, kind_high, max(kind_low, min(kind_high, want_mid))


def clamp_for(kind: str, seconds) -> int:
    """Their length into the bounds of the kind they chose. 0 means "the page did
    not say", exactly as clamp_seconds reads it."""
    low, high, middle = seconds_for(kind)
    try:
        value = int(float(seconds))
    except (TypeError, ValueError):
        return middle
    if value <= 0:
        return middle
    return max(low, min(high, value))


# How long a song can be. The short end is what they will use most - a jingle
# they can play to somebody - and the long end is a whole song with two verses.
#
# In the environment because the ceiling is a property of the machine rather
# than of this app, and a cheap one: ACE-Step turbo runs at about 1.1 seconds
# of wall clock per second of audio here, so two minutes is about two minutes.
# Nothing like video, where the limit is VRAM rather than patience.
# Settings rather than constants, and read through functions so a change on the
# parent page reaches the next song without a restart. MUSIC_MIN_SECONDS and
# its two neighbours seed them on the first start - see app/gallery.py.


def min_seconds() -> int:
    from . import gallery

    return gallery.whole("music_min_seconds", 1, 600)


def max_seconds() -> int:
    from . import gallery

    return max(min_seconds(), gallery.whole("music_max_seconds", 1, 600))


def default_seconds() -> int:
    from . import gallery

    return max(min_seconds(), min(max_seconds(),
                                  gallery.whole("music_default_seconds", 1, 600)))


def __getattr__(name: str):
    """The three names this module used to export as constants."""
    if name == "MIN_SECONDS":
        return min_seconds()
    if name == "MAX_SECONDS":
        return max_seconds()
    if name == "DEFAULT_SECONDS":
        return default_seconds()
    raise AttributeError(name)

# A verse, a chorus and a bridge, with room to spare. Longer than this is not
# a song they are going to hear all of in ninety seconds.
MAX_LYRIC_CHARS = 1500

_PHRASES = {gid: {cid: phrase for cid, _, phrase in choices}
            for gid, _, choices in GROUPS}


def options() -> list[dict]:
    """The dropdowns, for the page to render."""
    return [
        {
            "id": gid,
            "label": i18n.t(label),
            # Translated on the way out, not in the tuples: see styles.options.
            "choices": [{"id": cid, "label": i18n.label(gid, cid, clabel)}
                        for cid, clabel, _ in choices],
            "default": DEFAULTS.get(gid, ""),
            # The vocal ones hide with the instrumental toggle.
            "voice_only": gid in VOICE_ONLY,
            # Which of the "What kind of sound" chips this dropdown belongs
            # to. A list rather than the kinds it is *not* for, so a kind
            # added later has to say what it wants rather than inheriting
            # everything by silence.
            "kinds": [kid for kid, _, _ in KINDS
                      if gid not in HIDDEN_FOR.get(kid, ())],
            # What the empty option should say. "Any" is right for a mood and
            # wrong for a language: there is no such thing as a song in no
            # language, only one in whichever they wrote. It is wrong for the
            # arrangement too - leaving that alone is not "surprise me", it is
            # one singer, the way every song came out before this existed.
            "blank": i18n.t(BLANK.get(gid, "Any")),
        }
        for gid, label, choices in GROUPS
    ]


def random_selection(kind: str = DEFAULT_KIND) -> dict:
    """One random choice per group, for Surprise me. Every choice is safe on
    its own and in combination - that is the point of a fixed list.

    "One singer" is the empty option rather than a row in the list, so it is
    thrown into the hat by hand: a draw that could never pick it would make
    every surprise song a duet or a choir, which is the one arrangement they
    gets most of the time by choice.

    A kind with nobody singing draws nothing from the three vocal groups and
    nothing from whatever it hides, so a surprise hum comes back with the same
    dropdowns set that the card is actually showing them - a choice they can see
    and change, rather than one written into the tags behind a hidden control.
    """
    import random

    kind = kind_of(kind)
    hidden = set(HIDDEN_FOR.get(kind, ()))
    if not sings(kind):
        hidden.update(VOICE_ONLY)

    picked = {}
    for gid, _, choices in GROUPS:
        if gid in hidden:
            continue
        ids = [cid for cid, _, _ in choices]
        if gid == "singers":
            ids.append("")
        chosen = random.choice(ids) if ids else ""
        if chosen:
            picked[gid] = chosen
    return picked


def clamp_seconds(seconds) -> int:
    """Into the bounds a parent set. 0 - what the route sends when the page
    said nothing - means the default length rather than the shortest."""
    try:
        value = int(float(seconds))
    except (TypeError, ValueError):
        return default_seconds()
    if value <= 0:
        return default_seconds()
    return max(min_seconds(), min(max_seconds(), value))


def bpm_for(selections: dict | None, kind: str = DEFAULT_KIND) -> int:
    # A hum has no genre to read a tempo off and wants the slowest clock there
    # is; everything else is the kind of music they picked. The bpm field is
    # obeyed - measured, a jingle asked for at 140 put its onsets 0.427s apart,
    # which is one beat at 140 to within a hundredth of a second.
    if kind_of(kind) == "ambience":
        return AMBIENCE_BPM
    return BPM.get((selections or {}).get("genre") or "", DEFAULT_BPM)


def keyscale_for(selections: dict | None) -> str:
    return KEYSCALE.get((selections or {}).get("mood") or "", DEFAULT_KEYSCALE)


def compose_tags(idea: str, selections: dict | None, singing: bool = True,
                 kind: str = DEFAULT_KIND) -> str:
    """Their words plus the chosen phrases, as one comma-separated tag line.

    Commas rather than sentences: this field is a list of things the song is,
    and ACE-Step reads it that way.

    Their words come first and the kind's phrase comes *second*, in front of the
    dropdowns. Order carries weight in this field - the node map says genre
    leads for that reason - and "continuous ambient drone, no drums" has to
    outrank "marching band, snare drums" or the hum comes out as a march.
    """
    parts = []
    text = " ".join((idea or "").split()).strip().strip(".")
    if text:
        parts.append(text)
    kind_phrase = kind_tags(kind)
    if kind_phrase:
        parts.append(kind_phrase)
    hidden = HIDDEN_FOR.get(kind_of(kind), ())
    for gid in ORDER:
        if gid in NOT_TAGS or gid in hidden:
            continue
        if gid in VOICE_ONLY and not singing:
            continue
        phrase = _PHRASES.get(gid, {}).get((selections or {}).get(gid) or "")
        if phrase:
            parts.append(_with_voice(phrase, selections) if gid == "singers"
                         else phrase)
    if not singing:
        parts.append("instrumental, no vocals")
    return ", ".join(parts)


def _with_voice(phrase: str, selections: dict | None) -> str:
    """An arrangement phrase with the chosen voice folded into it - see
    VOICE_WORD. The whitespace is collapsed afterwards because the word is
    often nothing, and "lead  vocals" is not a phrase anybody writes."""
    word = VOICE_WORD.get((selections or {}).get("voice") or "", "")
    return " ".join(phrase.format(who=word).split())


def tidy_lyrics(text: str, singing: bool = True) -> str:
    """What actually goes in the lyrics field.

    Left almost alone on purpose - they are their words, and a song is allowed to
    be nonsense. Only two things are done: the blank lines a model likes to put
    between sections are collapsed, because they read as silence, and a section
    header on its own is given something to sing after it.
    """
    if not singing:
        return INSTRUMENTAL
    lines = [line.strip() for line in (text or "").replace("\r", "").split("\n")]
    kept = [line for line in lines if line]
    if not kept:
        return INSTRUMENTAL
    # A header with nothing under it is a promise the model cannot keep.
    while kept and _is_header(kept[-1]):
        kept.pop()
    return "\n".join(kept) if kept else INSTRUMENTAL


def _is_header(line: str) -> bool:
    """Is this line a section marker rather than something to sing?

    Anything that is one pair of square brackets and nothing else. It used to
    be an exact match against SECTIONS, which stopped being enough once the
    helper started annotating them: "[Chorus - both together]" is how the
    arrangement is written down, and it is as much a header as "[Chorus]".
    """
    line = line.strip()
    return len(line) > 2 and line.startswith("[") and line.endswith("]")


def language_for(selections: dict | None, lyrics: str) -> str:
    """Which language to tell the model it is singing in.

    Their choice wins; "Match my words" falls back to reading the finished
    lyrics, which is what happened before there was a dropdown at all.
    """
    chosen = (selections or {}).get("language") or ""
    if chosen in {code for code, _ in LANGUAGES}:
        return chosen
    return language_of(lyrics)


def language_of(lyrics: str) -> str:
    """Which language to tell the model it is singing in.

    This kept a French word list of its own, on the argument that `scripts`
    was tuned for a different question - whether to spend a translation call.
    With six to tell apart that argument stops paying for itself: a second set
    of stop-word lists is a second thing to get wrong, and what is at stake
    here is only the singer's accent, where there it decides whether the
    prompt is rewritten. So it is the same detector now, and "too short to
    tell" sings in English.
    """
    return scripts.detect(lyrics) or "en"


# --- what the model is told, when it writes the song ------------------------

SYSTEM = """You write short songs for {age} to make with a music model. You are
given an idea in one line. Answer with JSON and nothing else:

{"tags": "...", "lyrics": "..."}

TAGS
- A comma-separated list of what the song should *sound* like: the kind of
  music, the instruments, the feel. Six to ten short items. No sentences.
- Never name a real artist, band or song.

LYRICS
- A short song, 8 to 16 lines in total, with section headers on their own
  lines: [Verse], [Chorus], [Verse], [Chorus]. Use a [Bridge] only if there
  is room. A header may carry a note about who sings that part -
  "[Chorus - everyone]" - and does whenever you are asked below for one.
- Lines of four to eight words. They are sung, so they have to be sayable.
- Rhyme the ends of lines in pairs. A child should be able to sing along by
  the second chorus.
- Completely safe for a child: no violence, no romance beyond friendship,
  nothing frightening, nothing rude. Not babyish either - write for a capable
  {age_old}, so aim for funny and vivid rather than cute.
- Write the lyrics in the language the idea ASKS FOR, if it asks for one -
  "a song in French about a cat" is a French song written from an English
  sentence. Otherwise write them in the language the idea is written in.
- No emoji, no stage directions, no explanation.

Output only the JSON object."""


# Which parts of the blocklist apply to *lyrics*, the same argument the chat
# tab makes in CHAT_CATEGORIES and for the same reason.
#
# The full list exists to keep things out of a picture. Applied to a song it
# refuses the ordinary: "hanging" (from a tree), "wound" (round a spool),
# "blood" (in "blood brothers"), "killing it", "brutal". The first surprise
# song this app ever wrote was about a sloth stuck upside-down in a tree and
# was refused for violence - almost certainly on the word "hanging".
#
# So lyrics are checked against the categories where a match is essentially
# never innocent, with two added that chat leaves out: a child's song has no
# business naming a drug or a firearm, and neither word turns up by accident
# the way "wound" does. `scary` is left out on purpose too - the card offers a
# **Spooky** mood, and a filter that then refuses "terrifying" is a feature
# fighting itself.
#
# The rest is left to the instruction above, which says it plainly, and to the
# fact that they read and edit every line before anything is made. "Check song
# words against the whole picture list" on the parent page uses the whole
# blocklist instead; MUSIC_STRICT seeds that switch on the first start.
# Named by family, not one by one - see CHAT_CATEGORIES.
LYRIC_CATEGORIES = safety.in_every_language(
    "sexual", "minors_sexual", "hate", "real_people", "drugs", "weapons",
)
def strict() -> bool:
    """Whether the whole picture blocklist applies to lyrics too. A switch on
    the parent page; MUSIC_STRICT only seeds it."""
    from . import gallery

    return gallery.flag("music_strict", False)


def check_lyrics(text: str) -> tuple[bool, str]:
    """(ok, category) for words that will be sung, not drawn."""
    if not text or not text.strip():
        return True, ""     # no words is an instrumental, not a refusal
    if len(text) > MAX_LYRIC_CHARS:
        return False, "length"
    if strict():
        ok, _, category = safety.check_prompt(text)
        return ok, category
    # `safety` runs the loop, not this file - see the same call in `chat.py`.
    # The glued-together evasion check still runs whatever the categories are,
    # and so now do the short terms that are only matched in their own
    # language; neither of them reached the copy of the loop that was here.
    return safety.check_categories(text, LYRIC_CATEGORIES)


FRIENDLY_UNAVAILABLE = (
    "I couldn't think of a song just then. Try tapping it again, or write your "
    "own words - they don't have to rhyme!"
)
FRIENDLY_REJECTED = (
    "Let's try a different idea for the song! That one came back with words we "
    "can't sing here."
)


async def write(idea: str, selections: dict | None = None) -> dict:
    """Their one line into {tags, lyrics}. Raises scripts.ScriptError.

    Both halves in one call rather than two: the words and the sound have to
    agree - a lullaby with a stomping chorus is neither - and asking twice gets
    two models' worth of disagreement for twice the wait.
    """
    ok, message, _ = safety.check_prompt(idea)
    if not ok:
        raise scripts.ScriptError(message)

    payload = {
        "model": scripts.model(),
        "system": prompts.text("song", SYSTEM),
        "prompt": (
            f"Idea: {idea.strip()}\n"
            + (f"It should sound like: {compose_tags('', selections)}.\n"
               if selections else "")
            + singing_plan(selections)
            + _reply_language(idea, selections)
        ),
        "stream": False,
        "think": False,
        "keep_alive": scripts.keep_alive(),
        "format": "json",
        "options": {"temperature": 0.9, "num_predict": 600},
    }

    data = scripts.extract_json(await scripts._ask(payload))
    if not data or not str(data.get("lyrics") or "").strip():
        log.info("song helper gave nothing usable; retrying once")
        data = scripts.extract_json(await scripts._ask(payload))
    if not data or not str(data.get("lyrics") or "").strip():
        raise scripts.ScriptError(FRIENDLY_UNAVAILABLE)

    # Both fields come back as a list about a third of the time, however
    # firmly the instruction says otherwise - lyrics as a list of lines, tags
    # as a list of words. `str()` on that gives ACE-Step a Python repr to sing,
    # brackets and quotes included, which is exactly as bad as it sounds.
    tags = " ".join(_as_text(data.get("tags"), ", ").split())[:400]
    lyrics = _as_text(data.get("lyrics"), "\n").strip()[:MAX_LYRIC_CHARS]

    # The tags describe the song, so they get the same check a picture prompt
    # does. The lyrics get the narrower one - see LYRIC_CATEGORIES.
    if tags:
        ok, _, category = safety.check_prompt(tags)
        if not ok:
            log.warning("song tags rejected (%s)", category)
            raise scripts.ScriptError(FRIENDLY_REJECTED)
    ok, category = check_lyrics(lyrics)
    if not ok:
        log.warning("song lyrics rejected (%s)", category)
        raise scripts.ScriptError(FRIENDLY_REJECTED)

    return {"tags": tags, "lyrics": tidy_lyrics(_bracket_headers(lyrics))}


def singing_plan(selections: dict | None) -> str:
    """How the helper should lay the words out for the chosen arrangement.

    Only "Help me write it" ever sees this. Words they typed themselves are never
    restructured - the arrangement puts the tags on the song either way, and
    rewriting their verses to fit a dropdown would be the app arguing with them.
    """
    plan = LYRIC_PLAN.get((selections or {}).get("singers") or "", "")
    return f"{plan}\n" if plan else ""


# A section header the model wrote without its brackets. It drops them every
# few answers - "Verse 1 - Singer 1" rather than "[Verse 1 - Singer 1]" - and a
# header without brackets is not a header at all: ACE-Step sings the words
# "verse one singer one" in the middle of the song.
#
# Tight on purpose. The line has to be a section name, optionally a number,
# optionally a note after a dash, and nothing else, so a sung line that happens
# to start with the word "Chorus" is left alone.
_BARE_HEADER = re.compile(
    r"^(?:" + "|".join(SECTION_NAMES) + r")"
    r"(?:\s+\d+)?"
    r"(?:\s*[-–—:]\s*[^\[\]]{1,40})?$",
    re.IGNORECASE,
)


def _bracket_headers(lyrics: str) -> str:
    """The helper's headers, with the brackets it forgot put back.

    Only ever applied to what the *model* wrote. Words they typed themselves are
    left exactly as they typed them - the card tells them to use [Verse], and
    second-guessing them is how an app starts arguing with a child.
    """
    out = []
    for line in lyrics.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("[") and _BARE_HEADER.match(stripped):
            stripped = f"[{stripped}]"
        out.append(stripped)
    return "\n".join(out)


def _as_text(value, joiner: str) -> str:
    """A model's answer as a string, whether it wrote one or a list of them."""
    if isinstance(value, (list, tuple)):
        return joiner.join(str(part).strip() for part in value if str(part).strip())
    return str(value or "")


# "a song in french about my best friend" is an English sentence asking for a
# French song, and looking only at what language they *typed* got it wrong.
# Matched on the *request*, not on the word: "a song about a French bulldog"
# is a song in English, and a bare \bfrench\b caught it. The same trap is set
# in every one of the six - a German shepherd, a Spanish omelette, a Dutch
# barn, a Portuguese man o' war - so none of them is matched bare either.
#
# Three shapes, in the order they are certain: "in <language>", where the
# preposition is the request; "<language> song / lyrics / words", where the
# noun is; and the language's own name for itself standing alone, which is
# only a request because nobody writes "Français" about a bulldog.
_NAMES_RE = {
    "fr": r"french|fran[cç]ais(?:e)?",
    "es": r"spanish|espa[nñ]ol(?:a)?|castellano",
    "it": r"italian|italiano|italiana",
    "de": r"german|deutsch(?:e)?",
    "pt": r"portuguese|portugu[eê]s(?:a)?",
    "nl": r"dutch|nederlands",
}

# Their own names for themselves. "French" on its own is a bulldog; the word a
# French page would put there is not.
_OWN_RE = {
    "fr": r"fran[cç]ais(?:e)?",
    "es": r"espa[nñ]ol(?:a)?|castellano",
    "it": r"italiano|italiana",
    "de": r"deutsch(?:e)?",
    "pt": r"portugu[eê]s(?:a)?",
    "nl": r"nederlands",
}

# The prepositions are every language's, not just English's: they are as likely
# to write "en español" as "in Spanish", and more likely on a page in it.
_IN = r"in|into|en|em|auf|op|su"
_SONG = (r"song|lyrics|words|version|chanson|paroles|canci[oó]n|letra|"
         r"canzone|lied|liedtext|m[uú]sica|can[cç][aã]o|liedje")

_ASKS_IN = {code: re.compile(rf"\b(?:{_IN})\s+(?:{names})\b", re.IGNORECASE)
            for code, names in _NAMES_RE.items()}
_ASKS_SONG = {code: re.compile(rf"\b(?:{names})\s+(?:{_SONG})\b", re.IGNORECASE)
              for code, names in _NAMES_RE.items()}
_ASKS_OWN = {code: re.compile(rf"\b(?:{own})\b", re.IGNORECASE)
             for code, own in _OWN_RE.items()}


def asked_language(idea: str) -> str:
    """The language a sentence *asks* to be sung in, or "" if it asks none."""
    text = idea or ""
    for shapes in (_ASKS_IN, _ASKS_SONG, _ASKS_OWN):
        for code, pattern in shapes.items():
            if pattern.search(text):
                return code
    return ""


def _reply_language(idea: str, selections: dict | None = None) -> str:
    """Unlike a picture prompt, lyrics are never translated - they are the
    words that will be sung. So a French idea gives a French song, and so does an
    English idea that *asks* for one.

    The dropdown wins over both: picking "Français" is a clearer request than
    any sentence, and it is the one they can make without knowing the trick.

    Seven and no more: `safety.py`'s blocklist covers exactly those, so lyrics
    in an eighth would be checked against a list that does not know its words.
    See LANGUAGES.
    """
    chosen = (selections or {}).get("language") or ""
    if chosen not in dict(LANGUAGES):
        # The page being in Spanish counts as asking too: "Write me a song" on
        # a Spanish page should come back in Spanish, the way every other
        # helper does. The dropdown still wins over both, because that is a
        # choice they made about this song rather than about the whole page.
        chosen = asked_language(idea) or scripts.reading_language(idea)
    if chosen == "en":
        return "Write the lyrics in English."
    # The "tags stay in English" half is only worth saying when the lyrics are
    # not: telling it twice reads as a mistake.
    return (f"Write the lyrics in {scripts.LANGUAGE_NAMES[chosen]}. "
            "The tags stay in English.")
