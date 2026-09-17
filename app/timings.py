"""How long things take *on this machine*.

"About two minutes" is the single most useful thing the page can say before they
taps Go - a fifteen-second video and a fifteen-second film are a minute apart,
and the difference between waiting and wondering whether it is broken is
knowing which one you are in.

It cannot be a table of numbers in the source, because the number depends
entirely on the card underneath: the same render is 40 seconds on a 5070 Ti and
four minutes on something older. So nothing is assumed. Every finished job is
timed, the times are kept with the app's own state, and the estimate is what this
machine has actually done.

Two ways of answering, in order:

1. **The same job again.** Median of the last few runs of that exact shape -
   same kind, size, quality and length. Median, not mean: one render that
   waited behind a model load should not move the number for the next ten.
2. **Scaled from anything else of that family.** Cost is close enough to
   linear in pixels x frames, so seconds-per-unit learned from *any* video
   predicts a video of a different length or quality. This is what makes the
   second render of a new setting sensible rather than silent.

With nothing recorded at all it says so, and the page says so too. A made-up
number would be worse than no number.
"""

import json
import logging
import statistics
import time

from . import gallery, music, workflows

log = logging.getLogger("makery.timings")

FILE = ".timings.json"

# Per bucket. Long enough to be steady, short enough that a machine that gets
# faster - a driver update, a lighter model - is believed within an evening.
MAX_SAMPLES = 12

# LTX renders 24 frames a second and the latent is duration*fps+1 frames.
FPS = 24

# What counts as the same family for the scaled fallback.
FAMILY = {
    "image": "image", "panel": "image", "banner": "image", "comic": "image",
    "t2v": "video", "i2v": "video", "flf": "video", "story": "video",
    # Its own family: a song's cost is seconds of audio, which has nothing to
    # do with pixels, so it can predict nothing from a picture and vice versa.
    # A little tune and a background hum are the same model, the same graph
    # and the same eight steps, so they share it: their first song ever already
    # taught this family how long a second of audio takes, and a jingle should
    # not have to be rendered twice before the page can say "about ten
    # seconds".
    "music": "music", "jingle": "music", "ambience": "music",
    # The two they make *from* something they already have. Both spend GPU time,
    # neither runs a diffusion model: interpolating a clip is a small fraction
    # of what rendering it cost, and an ESRGAN pass is a fraction of a Flux
    # one. Sharing a family with video or image would have each teaching the
    # other a rate that is wrong by an order of magnitude.
    "smooth": "smooth", "slowmo": "smooth",
    "huge": "huge",
    # The three Klein edits share one family on purpose: one model, one set of
    # four steps, and the cost of all three is the pixels it samples - so the
    # first "change this picture" they do teaches the outpaint how long it
    # will take. Not the picture family: Flux schnell is a different model at
    # a different size and would predict the wrong minute.
    "edit": "edit", "outpaint": "edit", "inpaint": "edit",
    # "Turn it into..." is the same graph at the same four steps, so it belongs
    # in the same family and not in one of its own - their first edit already
    # taught it how long a megapixel takes.
    "restyle": "edit",
}


def shape_of(kind: str, extra: dict | None = None) -> str:
    """The job registry's name for a job, as the *page* asks about it.

    The two have to agree or the "same job again" path is dead, because one
    side writes a key the other never reads. Two of them differ:

    - a comic is one job of kind "comic" and the Comic tab asks about the
      "panel" it is made of, several at a time;
    - a banner is a job of kind "image" that renders at BANNER_SIZE rather
      than the tab's own shape, so filing it as a picture both spoils the
      picture's number and leaves the banner without one of its own.
    """
    if kind == "comic":
        return "panel"
    if kind == "image" and (extra or {}).get("banner"):
        return "banner"
    return kind


def _path():
    return gallery.STATE_DIR / FILE


def _read() -> dict:
    try:
        data = json.loads(_path().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(data: dict) -> None:
    # Atomic, like the other small state files: an interrupted write is read
    # back as "this machine has never rendered anything". See
    # gallery.write_json.
    try:
        gallery.write_json(_path(), data)
    except OSError as exc:
        log.warning("could not save the timings: %s", exc)


# --- how much work a job is -------------------------------------------------

def units(kind: str, duration=None, orientation: str = "landscape",
          quality: str = workflows.DEFAULT_QUALITY, pixels: int = 0) -> float:
    """Megapixels for **one** picture; megapixel-frames for a video.

    One, not several: four at once is four runs of the picture graph now, so
    what is worth learning is what a single one costs. `record` divides by how
    many were made and `estimate` multiplies by how many are wanted.

    Not an attempt at a cost model - it only has to be close to proportional
    to the real thing, so that one measured render predicts another of a
    different size. Pixels x frames is close enough that the estimate lands
    inside the minute.

    `pixels` is one frame of the thing being worked *on*, and only the two
    made-from-one-they-have families use it: they start from a file they already
    has, whatever size it happens to be, so the render sizes in ORIENTATIONS
    would be a guess about somebody else's picture.
    """
    family = FAMILY.get(kind, "image")
    if family == "smooth":
        return float(pixels) * max(1, int(duration or 1)) * FPS / 1e6
    if family in ("huge", "edit"):
        return float(pixels) / 1e6
    if family == "music":
        # Seconds of audio. Not comparable to a megapixel, which is why music
        # is its own family and never scales off a picture's rate.
        return float(max(1, int(duration or 30)))
    if FAMILY.get(kind, "image") == "video":
        width, height = workflows.size_for(orientation, quality)
        frames = max(1, int(duration or workflows.DEFAULT_DURATION)) * FPS + 1
        return width * height * frames / 1e6
    if kind == "banner":
        # A strip, not a picture: it ignores the tab's orientation entirely.
        width, height = workflows.BANNER_SIZE
        return width * height / 1e6
    shape = workflows.orientation_of(orientation)
    return shape["width"] * shape["height"] / 1e6


def bucket(kind: str, duration=None, orientation: str = "landscape",
           quality: str = workflows.DEFAULT_QUALITY,
           parts: int = 1, pixels: int = 0) -> str:
    """The key for "this exact job again".

    `parts` is in the key for a film and nowhere else: a four-part film is
    twice the work of a two-part one at the same length and quality, so
    sharing a bucket would hand the second one the first one's number and
    call it measured.
    """
    # Each kind of sound keys on its own name, so a ten-second jingle and a
    # ten-second song do not share a measurement - but they share the
    # *family* above, so the very first one of a new kind still gets a
    # sensible number scaled off every song already rendered. "music|15" is
    # what a song has always been filed under and still is.
    if FAMILY.get(kind) == "music":
        return f"{kind}|{int(duration or 0)}"
    # Rounded to a tenth of a megapixel so that their three landscape sizes do
    # not each need their own measurement before either says anything useful.
    if FAMILY.get(kind) == "smooth":
        return f"{kind}|{round(pixels / 1e6, 1)}|{int(duration or 0)}"
    if FAMILY.get(kind) == "huge":
        return f"huge|{round(pixels / 1e6, 1)}"
    # One key for all three: what a Klein pass costs is the canvas, and an
    # outpaint's canvas is simply a bigger one.
    if FAMILY.get(kind) == "edit":
        return f"edit|{round(pixels / 1e6, 1)}"
    if FAMILY.get(kind, "image") == "video":
        key = f"{kind}|{orientation}|{quality}|{int(duration or 0)}"
        return f"{key}|{max(1, int(parts or 1))}" if kind == "story" else key
    # One picture, whatever they asked for four of. Four at once is four runs
    # of the same graph, so four is not a different job, it is this one four
    # times - and a bucket per count would need its own measurements before
    # any of them said anything. The trailing 1 is kept so the samples
    # measured before all this still count: they were single pictures too.
    return f"{kind}|{orientation}|1"


# --- recording --------------------------------------------------------------

def record(job) -> None:
    """Time a finished job. Never raises: this is bookkeeping, and a job that
    worked must not be reported as failed because a note about it did not."""
    try:
        seconds = job.elapsed()
        if seconds <= 0 or job.status != "done":
            return
        extra = job.extra or {}
        kind = shape_of(job.kind, extra)
        quality = extra.get("quality") or workflows.DEFAULT_QUALITY
        count = max(1, len(job.results or [job.result]))
        parts = max(1, len(extra.get("beats") or []) or count)
        # A film is several clips of `duration` each, and is timed as the whole
        # thing, which is what they wait for. Pictures go the other way: a
        # comic's panels and four at once are runs of one graph, so they are
        # timed per picture and multiplied back up when they are asked.
        # One frame of the source, for the two families that work on a file
        # they already have. Zero for everything else, which never reads it.
        pixels = int(extra.get("pixels") or 0)
        work = units(kind, job.duration, job.orientation, quality, pixels)
        if kind == "story":
            work *= parts
        key = bucket(kind, job.duration, job.orientation, quality, parts, pixels)

        # Pictures are made one at a time, so a run of four measured one
        # picture four times over. Recording the total against "four" would
        # leave the single-picture estimate none the wiser, and a job that was
        # stopped half way would be timed as though it had finished.
        if FAMILY.get(kind, "image") == "image" and count > 1:
            seconds = seconds / count

        data = _read()
        runs = data.setdefault("runs", {})
        samples = runs.setdefault(key, [])
        samples.append(round(seconds, 1))
        del samples[:-MAX_SAMPLES]

        if work > 0:
            family = FAMILY.get(kind, "image")
            rates = data.setdefault("rates", {})
            per = rates.setdefault(family, [])
            per.append(round(seconds / work, 6))
            del per[:-MAX_SAMPLES]

        data["updated"] = time.time()
        _write(data)
    except Exception:  # pragma: no cover
        log.exception("could not record how long that took")


# --- answering --------------------------------------------------------------

def estimate(kind: str, duration=None, orientation: str = "landscape",
             quality: str = workflows.DEFAULT_QUALITY, count: int = 1,
             parts: int = 1, pixels: int = 0) -> dict:
    """How long this is likely to take, and how much to believe it."""
    data = _read()
    # Four pictures is four times one picture: they are drawn one after
    # another so that each can be shown as it lands.
    each = max(1, int(count)) if FAMILY.get(kind, "image") == "image" else 1
    key = bucket(kind, duration, orientation, quality, parts, pixels)
    samples = (data.get("runs") or {}).get(key) or []
    if len(samples) >= 2:
        return {"seconds": round(statistics.median(samples) * each),
                "confidence": "measured", "samples": len(samples)}

    work = units(kind, duration, orientation, quality, pixels)
    if kind == "story":
        work *= max(1, parts)
    rates = (data.get("rates") or {}).get(FAMILY.get(kind, "image")) or []
    if work > 0 and rates:
        return {"seconds": round(statistics.median(rates) * work * each),
                "confidence": "guess", "samples": len(rates)}
    if len(samples) == 1:
        return {"seconds": round(samples[0] * each),
                "confidence": "guess", "samples": 1}
    return {"seconds": None, "confidence": "none", "samples": 0}


def estimate_for(job) -> dict:
    """The same question, asked about a job that already exists.

    The page asks `/api/estimate` about what is on the card; this asks about
    the render that is actually running, which is not always the same thing -
    they can move the length slider while they wait. It reads the job exactly
    the way `record` does, so the number they are shown and the number that gets
    written when it finishes are about the same bucket.
    """
    extra = job.extra or {}
    kind = shape_of(job.kind, extra)
    quality = extra.get("quality") or workflows.DEFAULT_QUALITY
    count = max(1, int(getattr(job, "wanted", 1) or 1))
    parts = max(1, len(extra.get("beats") or []) or count)
    return estimate(kind, job.duration, job.orientation, quality, count, parts,
                    int(extra.get("pixels") or 0))


def summary() -> dict:
    """What has been learned, for the parent page."""
    data = _read()
    runs = data.get("runs") or {}
    rates = data.get("rates") or {}
    rows = []
    for key, samples in sorted(runs.items()):
        if not samples:
            continue
        rows.append({"what": key, "seconds": round(statistics.median(samples)),
                     "runs": len(samples)})
    return {
        "rows": rows,
        "families": {k: round(statistics.median(v), 4) for k, v in rates.items() if v},
        "updated": data.get("updated"),
    }


def forget() -> None:
    """Start the timings again - after a new graphics card, or a model swap
    that makes every number here a lie."""
    try:
        _path().unlink()
    except FileNotFoundError:
        pass
