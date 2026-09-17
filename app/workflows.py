"""Load the API-format workflow exports and patch them per job.

The files in `workflows/` are untouched exports from the live ComfyUI, so they
can be re-exported and dropped in at any time. Everything job-specific is
patched into a fresh deep copy here.

Node IDs come from the table in CLAUDE.md, verified against the graphs. If a
re-export renumbers a node, `_patch` raises rather than silently producing a
job that ignores the prompt and renders the sample image instead.
"""

import copy
import json
import logging
import random
from pathlib import Path

from . import music, prompts, safety

log = logging.getLogger("makery.workflows")

WORKFLOW_DIR = Path(__file__).resolve().parent.parent / "workflows"


# Both LTX workflows pick their size with a ResolutionSelector: an aspect
# ratio at 0.9 megapixels, with both sides rounded to a multiple of 32. The
# image workflow has no such node, so its width/height are set directly - and
# they must land on the same numbers the selector produces, or the "Animate
# this" handoff gets quietly cropped or stretched at the video stage.
#
# Verified for landscape against a real render (a 16:9 job produced 1280x704),
# and the same arithmetic gives the portrait pair:
#   landscape  sqrt(0.9MP*9/16)=711.5 -> 704 ; 704*16/9=1252  -> 1280
#   portrait   sqrt(0.9MP*4/3)=1095.4 -> 1088; 1088*3/4=816   -> 832
#
# The aspect string must match one of the node's COMBO options exactly.
ORIENTATIONS = {
    "landscape": {
        "aspect": "16:9 (Widescreen)",
        "width": 1280,
        "height": 704,
        "label": "Landscape",
    },
    "portrait": {
        "aspect": "3:4 (Portrait Standard)",
        "width": 832,
        "height": 1088,
        "label": "Portrait",
    },
    # sqrt(0.9MP) = 948.7 -> 960 (30 x 32) on both sides.
    "square": {
        "aspect": "1:1 (Square)",
        "width": 960,
        "height": 960,
        "label": "Square",
    },
}
DEFAULT_ORIENTATION = "landscape"

# The video workflows' ResolutionSelector takes a target in megapixels and
# rounds both sides to a multiple of 32. 0.9 is what the workflows shipped at
# and what every size in ORIENTATIONS was derived from. Sharper costs VRAM in
# proportion to pixels x frames, and 15s at 0.9MP already peaks near 15.5GB of
# a 16.3GB card - so the sharper setting caps the length (QUALITY_MAX_SECONDS)
# rather than finding out what an OOM looks like.
QUALITY = {"quick": 0.5, "normal": 0.9, "sharp": 1.3}
DEFAULT_QUALITY = "normal"

_RATIO = {"landscape": (16, 9), "portrait": (3, 4), "square": (1, 1)}


def megapixels_for(quality) -> float:
    return QUALITY.get(quality or DEFAULT_QUALITY, QUALITY[DEFAULT_QUALITY])


def size_for(orientation: str, quality: str = DEFAULT_QUALITY) -> tuple[int, int]:
    """The (width, height) the video actually comes out at.

    Two steps, both read off the real thing rather than guessed. First the
    ResolutionSelector's own arithmetic (comfy_extras/nodes_resolution.py):
    megapixels x 1024 x 1024 - not a million - spread over the aspect ratio,
    each side rounded to the nearest multiple of 32. Then the LTX pipeline
    takes each side down to a multiple of 64: the selector says 1280x736 at
    0.9MP landscape and the file is 1280x704, says 1568x864 at 1.3MP and the
    file is 1536x832. Checked against four real renders in the test below
    this function. The i2v crop has to land on exactly this, or LTX resamples
    the frame they chose.
    """
    w_r, h_r = _RATIO.get(orientation, _RATIO[DEFAULT_ORIENTATION])
    total = megapixels_for(quality) * 1024 * 1024
    scale = (total / (w_r * h_r)) ** 0.5
    width = round(w_r * scale / 32) * 32
    height = round(h_r * scale / 32) * 32
    return (width // 64) * 64, (height // 64) * 64


def clamp_for_quality(seconds: int, quality: str) -> int:
    return min(clamp_duration(seconds),
               quality_max_seconds().get(quality, max_duration()))

# ResolutionSelector node in each video workflow.
T2V_RESOLUTION_NODE = "409"
I2V_RESOLUTION_NODE = "403"


def orientation_of(name) -> dict:
    return ORIENTATIONS.get(name or DEFAULT_ORIENTATION, ORIENTATIONS[DEFAULT_ORIENTATION])


def nearest_orientation(width: int, height: int) -> str:
    """Which of their three shapes a picture is closest to.

    Not a claim that it *is* one of them. The three edit graphs hand back
    whatever size their picture was, and an outpainted one is a shape none of the
    makers can produce - but a sidecar with no orientation in it leaves the
    video card and the viewer guessing, so they get the nearest one. The file's
    real size is read off the file and shown on the facts line, as it always
    was.
    """
    if not width or not height:
        return DEFAULT_ORIENTATION
    aspect = width / height
    return min(ORIENTATIONS, key=lambda name: abs(aspect - (
        ORIENTATIONS[name]["width"] / ORIENTATIONS[name]["height"])))


# The SaveImage/SaveVideo prefix every graph gets patched with, and so the
# subdirectory ComfyUI writes into: `/basedir/output/makery`, which is the
# host directory bind-mounted here as GALLERY_DIR. Changing it means moving
# that mount to match, or the gallery goes empty.
OUTPUT_PREFIX = "makery"

# Both LTX workflows shipped at 5s. The Duration primitive feeds a
# "a * b + 1" math node, so latent length is duration*fps+1 frames - 121 at 5s,
# 361 at 15s. The card has 16GB and the models hold ~13GB of it, so the long
# end is where it will fail first if it fails.
#
# **Raising the ceiling is the one control in this app that can make a render
# fail rather than merely look different**: 15s at 0.9MP peaks near 15.5GB of
# 16.3GB here, and a 24GB card has room for more. It lived in the environment
# for exactly that reason - it is a property of the card - and it is on the
# parent page now, where the VRAM figure a parent would raise it against is
# already on the screen. VIDEO_MIN_SECONDS and its three neighbours seed the
# settings on the first start; app/gallery.py has the rest of that rule.
#
# Read through functions rather than held as constants, because a parent
# changing one has to reach the next render without a restart. The module's
# `__getattr__` keeps MIN_DURATION and friends working as names.


def _seconds(key: str, low: int, high: int) -> int:
    from . import gallery

    return gallery.whole(key, low, high)


def min_duration() -> int:
    return _seconds("video_min_seconds", 1, 600)


def max_duration() -> int:
    return max(min_duration(), _seconds("video_max_seconds", 1, 600))


def default_duration() -> int:
    return max(min_duration(), min(max_duration(),
                                   _seconds("video_default_seconds", 1, 600)))


# Sharper is more pixels per frame, so it runs out of card sooner. Its own
# number rather than a fraction of the above: what fits is a measurement, not
# an arithmetic relationship.
def quality_max_seconds() -> dict:
    longest = max_duration()
    return {
        "quick": longest,
        "normal": longest,
        "sharp": max(min_duration(),
                     min(longest, _seconds("video_max_seconds_sharp", 1, 600))),
    }


def __getattr__(name: str):
    """The four names this module used to export as constants.

    Every caller says `workflows.MAX_DURATION`, and every one of them means
    "right now" rather than "at import". Keeping the spelling and losing the
    staleness is what this is for; a module-level `__getattr__` only runs for
    names that are not in the module, which is why the constants are gone.
    """
    if name == "MIN_DURATION":
        return min_duration()
    if name == "MAX_DURATION":
        return max_duration()
    if name == "DEFAULT_DURATION":
        return default_duration()
    if name == "QUALITY_MAX_SECONDS":
        return quality_max_seconds()
    raise AttributeError(name)


def clamp_duration(seconds) -> int:
    """Into the bounds a parent set. 0 - what a route sends when the page said
    nothing - means the default length rather than the shortest one."""
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return default_duration()
    if value <= 0:
        return default_duration()
    return max(min_duration(), min(max_duration(), value))

IMAGE_FILE = "flux_schnell-api.json"
T2V_FILE = "video_ltx2_5_t2v-api.json"
I2V_FILE = "video_ltx2_5_i2v-api.json"
# First frame and last frame given, the model fills in between. No
# ResolutionSelector in this one: width and height are two primitives that
# feed a centre-crop resize of both pictures, so size_for() is patched in
# directly - the same 64-multiple numbers the other two come out at.
FLF_FILE = "video_ltx2_5_flf2v-api.json"
# ACE-Step 1.5 XL turbo: eight steps at CFG 1, like Flux schnell. Two fields
# hold the length and both have to agree - the latent's `seconds` is how much
# audio is made, the encoder's `duration` is how long the song is *written* to
# be, and a mismatch gives a song that stops in the middle of a line.
MUSIC_FILE = "audio_ace_step1_5_xl_turbo-api.json"
# The two that are ours rather than ComfyUI's - built from /object_info and
# verified by a render, because no shipped template fits. See CLAUDE.md.
#
# One file covers both "make it smooth" and "slow it down": the graph is the
# same twice as many frames either way, and the only difference is the frame
# rate they are played back at. Smooth keeps the original sound because the
# clip is still the same length; slow motion has the audio wire taken out
# altogether - see build_interpolated.
SMOOTH_FILE = "video_smooth_rife-api.json"
HUGE_FILE = "image_upscale_esrgan-api.json"

# Flux 2 Klein 9B, three ways. The first two are ComfyUI's own template for
# this model converted to API format - one reference picture and two - and the
# last two are that same graph with its sampling latent swapped, because
# nothing shipped outpaints or inpaints with Flux 2. Every one of the four
# carries a "_note" naming where it came from and the render that proved it.
#
# They share every setting the model's authors chose: four steps on
# Flux2Scheduler, euler, and CFGGuider at 1.0 with a zeroed-out negative.
# **There is no negative prompt in any of them**, and putting one in would be
# worse than useless: at CFG 1.0 it cannot affect the picture (the same
# arithmetic as the Flux schnell and LTX graphs - see CLAUDE.md), and unlike
# those it would cost a whole extra pass through an 8-billion-parameter text
# encoder to have no effect. safety.check_prompt is the filter, as everywhere.
EDIT_FILE = "image_flux2_klein_edit-api.json"
EDIT_TWO_FILE = "image_flux2_klein_edit_two-api.json"
OUTPAINT_FILE = "image_flux2_klein_outpaint-api.json"
INPAINT_FILE = "image_flux2_klein_inpaint-api.json"

_cache: dict[str, dict] = {}


class WorkflowError(RuntimeError):
    """A workflow file no longer matches the node map."""


def _load(name: str) -> dict:
    if name not in _cache:
        path = WORKFLOW_DIR / name
        if not path.is_file():
            raise WorkflowError(f"workflow file missing: {path}")
        data = json.loads(path.read_text())
        # A top-level key starting with an underscore is a note from us, not a
        # node. The two graphs that were built from /object_info rather than
        # exported from ComfyUI say so in a "_note", and everything else in
        # this dict is handed straight to ComfyUI as a node - so it comes off
        # here rather than becoming a node ComfyUI cannot execute.
        _cache[name] = {k: v for k, v in data.items() if not k.startswith("_")}
    return copy.deepcopy(_cache[name])


def _patch(graph: dict, file: str, node_id: str, field: str, value) -> None:
    node = graph.get(node_id)
    if node is None:
        raise WorkflowError(
            f"{file}: node {node_id} is missing - was the workflow re-exported "
            f"with different node IDs? Update the node map in CLAUDE.md."
        )
    inputs = node.setdefault("inputs", {})
    if field not in inputs:
        raise WorkflowError(
            f"{file}: node {node_id} ({node.get('class_type')}) has no input "
            f"'{field}' (has: {', '.join(sorted(inputs)) or 'none'})"
        )
    inputs[field] = value


MAX_SEED = 2**53 - 1


def _seed() -> int:
    return random.randint(0, MAX_SEED)


def pick_seed(seed=None) -> int:
    """The seed to draw with: the one asked for, or a fresh one.

    Handed back to the caller so it can be written into the sidecar, which is
    what makes "make it again but..." possible - the same seed with a changed
    prompt gives a variation on the picture they already have, where a new seed
    gives an unrelated picture that merely matches the words.
    """
    try:
        value = int(seed)
    except (TypeError, ValueError):
        return _seed()
    return value if 0 <= value <= MAX_SEED else _seed()


def _second_seed(seed: int) -> int:
    """The video graphs sample twice and want two seeds. Derived rather than
    random, so one recorded seed really does reproduce the whole clip."""
    return (seed * 6364136223846793005 + 1442695040888963407) % (MAX_SEED + 1)


# How many of one idea the picture card will make. No longer a batch size -
# it is how many times the graph is run - but it is still what the count
# picker offers and what the daily limit is asked for.
MAX_BATCH = 4


# The strip across the top of their page. Wider than any of the ORIENTATIONS and
# deliberately not one of them: it is not a shape to make a picture in, it is
# the one size the banner slot is. Both sides are multiples of 64.
BANNER_SIZE = (1536, 384)


def build_image(prompt: str, orientation: str = DEFAULT_ORIENTATION,
                seed=None, size: tuple[int, int] | None = None) -> dict:
    """One picture.

    Exactly one. "Four at once" used to be this graph with `batch_size` 4 -
    one run for all four, 20s against 15s for a single - but a batch denoises
    together and leaves the decoder together, so there was nothing to show
    until the last second of it. It is four runs of this now, each shown the
    moment it lands, which costs about four times as long and is what was
    asked for. `batch_size` is patched to 1 rather than trusted to the export,
    so nobody has to open the JSON to know what it is.

    `size` overrides the orientation outright, for the banner - which has one
    shape and is not a shape they pick.
    """
    g = _load(IMAGE_FILE)
    f = IMAGE_FILE
    shape = orientation_of(orientation)
    width, height = size or (shape["width"], shape["height"])
    _patch(g, f, "6", "text", prompt)
    _patch(g, f, "33", "text", prompts.text("negative_image", safety.NEGATIVE_IMAGE))
    _patch(g, f, "31", "seed", pick_seed(seed))
    _patch(g, f, "27", "width", width)
    _patch(g, f, "27", "height", height)
    _patch(g, f, "27", "batch_size", 1)
    _patch(g, f, "9", "filename_prefix", f"{OUTPUT_PREFIX}/image")
    return g


def build_music(tags: str, lyrics: str, seconds: int, bpm: int,
                keyscale: str, language: str = "en", seed=None) -> dict:
    """One song.

    `tags` is what it sounds like, `lyrics` is what is sung - two fields on the
    encoder rather than one prompt, which is why music.py composes them
    separately. The seed is a primitive feeding both the encoder and the
    sampler, so it is patched once.
    """
    g = _load(MUSIC_FILE)
    f = MUSIC_FILE
    length = music.clamp_seconds(seconds)
    _patch(g, f, "94", "tags", tags)
    _patch(g, f, "94", "lyrics", lyrics)
    _patch(g, f, "94", "duration", float(length))
    _patch(g, f, "94", "bpm", max(10, min(300, int(bpm))))
    _patch(g, f, "94", "keyscale", keyscale)
    _patch(g, f, "94", "language", language)
    # The latent has to be the same length as the song the encoder was told to
    # write, or it is cut off mid-line.
    _patch(g, f, "98", "seconds", float(length))
    _patch(g, f, "109", "value", pick_seed(seed))
    _patch(g, f, "111", "filename_prefix", f"{OUTPUT_PREFIX}/music")
    return g


def build_t2v(
    prompt: str,
    duration: int = 0,
    orientation: str = DEFAULT_ORIENTATION,
    seed=None,
    quality: str = DEFAULT_QUALITY,
) -> dict:
    g = _load(T2V_FILE)
    f = T2V_FILE
    _patch(g, f, T2V_RESOLUTION_NODE, "aspect_ratio", orientation_of(orientation)["aspect"])
    _patch(g, f, T2V_RESOLUTION_NODE, "megapixels", megapixels_for(quality))
    _patch(g, f, "405:362", "value", clamp_duration(duration))
    _patch(g, f, "405:376", "value", prompt)
    _patch(g, f, "405:373", "text", prompts.text("negative_video", safety.NEGATIVE_VIDEO))
    noise = pick_seed(seed)
    _patch(g, f, "405:338", "noise_seed", noise)
    _patch(g, f, "405:339", "noise_seed", _second_seed(noise))
    _patch(g, f, "75", "filename_prefix", f"{OUTPUT_PREFIX}/t2v")
    # Prompt enhance routes their text through an LLM before the model sees it.
    # Forced off, not merely assumed off.
    _patch(g, f, "405:383", "value", False)
    return g


def build_i2v(
    prompt: str,
    image_ref: str,
    duration: int = 0,
    orientation: str = DEFAULT_ORIENTATION,
    seed=None,
    quality: str = DEFAULT_QUALITY,
) -> dict:
    g = _load(I2V_FILE)
    f = I2V_FILE
    _patch(g, f, I2V_RESOLUTION_NODE, "aspect_ratio", orientation_of(orientation)["aspect"])
    _patch(g, f, I2V_RESOLUTION_NODE, "megapixels", megapixels_for(quality))
    _patch(g, f, "398:362", "value", clamp_duration(duration))
    _patch(g, f, "398:376", "value", prompt)
    _patch(g, f, "398:373", "text", prompts.text("negative_video", safety.NEGATIVE_VIDEO))
    noise = pick_seed(seed)
    _patch(g, f, "398:338", "noise_seed", noise)
    _patch(g, f, "398:339", "noise_seed", _second_seed(noise))
    _patch(g, f, "395", "image", image_ref)
    _patch(g, f, "75", "filename_prefix", f"{OUTPUT_PREFIX}/i2v")
    _patch(g, f, "398:383", "value", False)  # prompt enhance off
    _patch(g, f, "398:363", "value", False)  # "Switch to Text to Video?" off
    return g


def build_flf2v(
    prompt: str,
    first_ref: str,
    last_ref: str,
    duration: int = 0,
    orientation: str = DEFAULT_ORIENTATION,
    seed=None,
    quality: str = DEFAULT_QUALITY,
) -> dict:
    """A clip that starts on one picture and ends on another.

    Node ids from the export in workflows/ (see the table in CLAUDE.md). One
    sampler pass with manual sigmas rather than the two-pass upscale the other
    video graphs run, so it is a little quicker than i2v for the same length.
    """
    g = _load(FLF_FILE)
    f = FLF_FILE
    width, height = size_for(orientation, quality)
    _patch(g, f, "31", "image", first_ref)
    _patch(g, f, "39", "image", last_ref)
    _patch(g, f, "251:215", "value", width)
    _patch(g, f, "251:216", "value", height)
    _patch(g, f, "251:198", "value", clamp_duration(duration))
    _patch(g, f, "251:252", "value", prompt)
    _patch(g, f, "251:217", "text", prompts.text("negative_video", safety.NEGATIVE_VIDEO))
    _patch(g, f, "251:196", "noise_seed", pick_seed(seed))
    _patch(g, f, "68", "filename_prefix", f"{OUTPUT_PREFIX}/flf")
    _patch(g, f, "251:250", "value", False)  # prompt enhance off, as everywhere
    return g


def build_interpolated(video_ref: str, fps: float, keep_sound: bool = True) -> dict:
    """Twice the frames of one of their videos, played at `fps`.

    Two things come out of the one graph. At twice the original rate the clip
    is the same length and simply moves more smoothly; at the original rate it
    is the same frames over twice as long, which is slow motion.

    `keep_sound` is not a preference. A video with no audio stream has nothing
    on GetVideoComponents' audio output, and leaving the wire in place stops
    the graph with an error they did nothing to cause - so the input is removed
    rather than left dangling. Slow motion passes False for a different reason:
    see the route.
    """
    g = _load(SMOOTH_FILE)
    f = SMOOTH_FILE
    _patch(g, f, "1", "file", video_ref)
    _patch(g, f, "4", "fps", float(fps))
    _patch(g, f, "5", "filename_prefix",
           f"{OUTPUT_PREFIX}/{'smooth' if keep_sound else 'slowmo'}")
    if not keep_sound:
        g["4"]["inputs"].pop("audio", None)
    return g


def build_huge(image_ref: str) -> dict:
    """One of their pictures, four times the size, through an ESRGAN model.

    No sampler and no prompt: the model is read straight off the picture, so
    this is one pass rather than twenty steps. Which model it is stays in the
    file - it is not a knob, and reading it from there is what keeps
    wanted_models() honest about what a render will ask ComfyUI for.
    """
    g = _load(HUGE_FILE)
    f = HUGE_FILE
    _patch(g, f, "1", "image", image_ref)
    _patch(g, f, "4", "filename_prefix", f"{OUTPUT_PREFIX}/huge")
    return g


# --- the three edits they can make to a picture they already have ---------------

# What Flux 2 Klein's own template renders at, and what the three graphs below
# inherit: four steps, euler, CFG 1.0. Kept here as a name rather than patched,
# because the model's authors picked it and nothing in this app has any
# business overriding it - but named so the node map in CLAUDE.md is checkable.
EDIT_STEPS = 4

# How much bigger "a bit" and "a lot" make the picture. Fractions of the side
# being grown, so a quarter on both left and right is a canvas half again as
# wide - which is what "all round, a lot" means to them.
OUTPAINT_AMOUNTS = {"bit": 0.25, "lot": 0.5}
DEFAULT_OUTPAINT_AMOUNT = "bit"
OUTPAINT_SIDES = ("all", "left", "right", "top", "bottom")
DEFAULT_OUTPAINT_SIDE = "all"

# The whole outpainted canvas, not their picture: what is rendered is picture
# plus border and it all has to fit on the card at once. Measured, not
# guessed - a 1600x880 canvas (1.41MP) peaked at 15837 MiB of 16303, and an
# ordinary edit at 0.9MP peaked at 15293. The cap sits a whisker above that
# measured canvas on purpose: a quarter all round on their landscape size comes
# to 1600x896, which is 1.43MP, and shrinking their picture by two percent to
# dodge a number nobody measured would be arithmetic pretending to be safety.
# Anything past it shrinks the picture to fit rather than finding out what an
# OOM looks like.
OUTPAINT_MAX_PIXELS = 1_450_000


def outpaint_grow(side: str, amount: str) -> tuple[float, float, float, float]:
    """How far to grow each of the four edges, as a fraction of the side.

    "All round" splits the amount between the two opposite edges, so a quarter
    all round is a canvas a quarter bigger - not half again as big, which is
    what growing each edge by a quarter would give.
    """
    fraction = OUTPAINT_AMOUNTS.get(amount, OUTPAINT_AMOUNTS[DEFAULT_OUTPAINT_AMOUNT])
    if side not in OUTPAINT_SIDES:
        side = DEFAULT_OUTPAINT_SIDE
    if side == "all":
        half = fraction / 2
        return half, half, half, half
    return (fraction if side == "left" else 0.0,
            fraction if side == "top" else 0.0,
            fraction if side == "right" else 0.0,
            fraction if side == "bottom" else 0.0)


def outpaint_budget(side: str, amount: str) -> int:
    """How big their picture may be so that the padded canvas still fits."""
    left, top, right, bottom = outpaint_grow(side, amount)
    return int(OUTPAINT_MAX_PIXELS / ((1 + left + right) * (1 + top + bottom)))


def outpaint_pads(width: int, height: int, side: str,
                  amount: str) -> tuple[int, int, int, int]:
    """The four pads in pixels, each a multiple of 16.

    The node's own step is 8, but the picture's sides are multiples of 16
    (uploads.EDIT_GRID) and the latent wants the *total* on that grid too, so
    the pads are as well.
    """
    left, top, right, bottom = outpaint_grow(side, amount)
    grid = 16

    def pad(size: int, fraction: float) -> int:
        return int(round(size * fraction / grid)) * grid if fraction else 0

    return (pad(width, left), pad(height, top), pad(width, right), pad(height, bottom))


def build_edit(image_ref: str, prompt: str, seed=None,
               second_ref: str = "") -> dict:
    """Their picture, changed by what they typed.

    The picture is the reference - `ReferenceLatent` on both the positive and
    the zeroed negative conditioning, exactly as ComfyUI's Klein edit template
    does it - and the canvas is an empty latent the same size, so the model
    redraws the whole picture while being shown what it looked like. That is
    why the composition survives and only what they asked for changes.

    `second_ref` is their own face, for "and put me in it": a second picture
    chained onto the same conditioning, which is the other half of the same
    official template. It is a different file rather than four nodes added
    here, because the template ships it as a second graph and a graph in a
    file is a graph ComfyUI has validated.

    No width or height to patch: `GetImageSize` reads them off the picture
    that was uploaded, which `uploads.for_edit` has already put on the grid.
    """
    f = EDIT_TWO_FILE if second_ref else EDIT_FILE
    g = _load(f)
    _patch(g, f, "76", "image", image_ref)
    if second_ref:
        _patch(g, f, "121", "image", second_ref)
    _patch(g, f, "74", "text", prompt)
    _patch(g, f, "73", "noise_seed", pick_seed(seed))
    _patch(g, f, "9", "filename_prefix", f"{OUTPUT_PREFIX}/edit")
    return g


def build_restyle(image_ref: str, prompt: str, seed=None) -> dict:
    """The same picture, drawn a different way.

    **This is the edit graph and nothing else**, with a filename prefix of its
    own so a restyled picture is recognisable on disk. That is the finding, not
    a shortcut: Klein is a reference model, and "redraw this as a stained-glass
    window, keep the same scene" is an instruction of exactly the kind it was
    trained for. The classic img2img alternative - VAE-encode their picture,
    denoise part of the way on flux1-schnell - was tried at 0.65 and 0.8 and
    came back with the style words ignored entirely. See CLAUDE.md for the
    renders.

    Which also means there is no strength knob to offer them. `SamplerCustom-
    Advanced` over an empty latent has no `denoise`, and the graph that does
    have one is the one that did not work.
    """
    g = build_edit(image_ref, prompt, seed)
    _patch(g, EDIT_FILE, "9", "filename_prefix", f"{OUTPUT_PREFIX}/style")
    return g


def build_outpaint(image_ref: str, prompt: str, pads: tuple[int, int, int, int],
                   seed=None) -> dict:
    """What is outside the frame of one of their pictures.

    `ImagePadForOutpaint` grows the canvas and hands its own mask straight to
    `VAEEncodeForInpaint`, so only the new border is denoised and their own
    picture is carried through the sampler untouched. The reference is still
    the *unpadded* picture, which is what tells the model what it is
    continuing - a reference full of grey border would only teach it to draw
    more grey border.

    **`feathering` stays at 0.** See the file's own note: the node's default of
    40 feathers the mask, `VAEEncodeForInpaint` blends grey into every
    half-masked pixel, and the first render came back with a bright band
    across the sky where the old edge had been.
    """
    g = _load(OUTPAINT_FILE)
    f = OUTPAINT_FILE
    left, top, right, bottom = pads
    _patch(g, f, "76", "image", image_ref)
    _patch(g, f, "74", "text", prompt)
    _patch(g, f, "73", "noise_seed", pick_seed(seed))
    _patch(g, f, "201", "left", int(left))
    _patch(g, f, "201", "top", int(top))
    _patch(g, f, "201", "right", int(right))
    _patch(g, f, "201", "bottom", int(bottom))
    _patch(g, f, "9", "filename_prefix", f"{OUTPUT_PREFIX}/outside")
    return g


def build_inpaint(image_ref: str, mask_ref: str, prompt: str, seed=None) -> dict:
    """Just the bit they painted over, changed to what they typed.

    The mask goes to `VAEEncodeForInpaint`, whose noise mask is what confines
    the change to the bit they painted. The reference is the whole clean
    picture, so the new bit is drawn knowing what it has to match.

    Everything outside their brush comes back through the same VAE as the rest
    of the picture, so it is a round trip of itself rather than the original
    bytes - measured at 2.8 of 255 on average against 28 inside the brush.
    Invisible, but it is not "untouched" and this file does not say it is.
    """
    g = _load(INPAINT_FILE)
    f = INPAINT_FILE
    _patch(g, f, "76", "image", image_ref)
    _patch(g, f, "210", "image", mask_ref)
    _patch(g, f, "74", "text", prompt)
    _patch(g, f, "73", "noise_seed", pick_seed(seed))
    _patch(g, f, "9", "filename_prefix", f"{OUTPUT_PREFIX}/fixed")
    return g


def preflight() -> None:
    """Build one of each at import time so a bad workflow file fails loudly."""
    for name in ORIENTATIONS:
        build_image("preflight", name)
        build_t2v("preflight", max_duration(), name)
        build_i2v("preflight", "preflight.png", max_duration(), name)
        build_flf2v("preflight", "a.png", "b.png", max_duration(), name)
    build_interpolated("preflight.mp4", 48.0)
    build_interpolated("preflight.mp4", 24.0, keep_sound=False)
    build_huge("preflight.png")
    build_edit("preflight.png", "preflight")
    build_edit("preflight.png", "preflight", second_ref="me.png")
    for side in OUTPAINT_SIDES:
        for amount in OUTPAINT_AMOUNTS:
            build_outpaint("preflight.png", "preflight",
                           outpaint_pads(1280, 704, side, amount))
    build_inpaint("preflight.png", "mask.png", "preflight")
    build_restyle("preflight.png", "preflight")
    if (WORKFLOW_DIR / MUSIC_FILE).is_file():
        build_music("preflight", "[inst]", music.DEFAULT_SECONDS, 120, "C major")


# Anything that looks like a model file, by extension, in any loader input.
MODEL_SUFFIXES = (".safetensors", ".sft", ".gguf", ".ckpt", ".pt", ".pth")


ALL_FILES = (IMAGE_FILE, T2V_FILE, I2V_FILE, FLF_FILE, MUSIC_FILE,
             SMOOTH_FILE, HUGE_FILE,
             EDIT_FILE, EDIT_TWO_FILE, OUTPAINT_FILE, INPAINT_FILE)


def wanted_models(only: str | None = None) -> dict:
    """Every model file the workflows load, as {filename: [where it is used]}.

    Read out of the exports rather than listed here, so it cannot drift from
    what a render will actually ask ComfyUI for. `only` narrows it to one
    workflow, which is how the music tab decides whether it can work at all.
    """
    wanted: dict[str, list[str]] = {}
    for file in ((only,) if only else ALL_FILES):
        try:
            graph = _load(file)
        except WorkflowError:
            continue
        for node in graph.values():
            for value in (node.get("inputs") or {}).values():
                if isinstance(value, str) and value.lower().endswith(MODEL_SUFFIXES):
                    wanted.setdefault(value, []).append(node.get("class_type", "?"))
    return wanted


def missing_models(object_info: dict) -> list[str]:
    """Which of those ComfyUI does not have, from its own /object_info.

    A loader advertises its choices in its input spec, and ComfyUI writes that
    in two shapes depending on the node: the old `[[names...], {...}]`, and the
    newer `["COMBO", {"options": [names...]}]`. Both are read here - checking
    only the old one reported the latent upscaler as missing on a machine where
    it was plainly there and working, which is exactly the kind of wrong a
    startup warning must not be.

    A name ComfyUI cannot see will fail at render time with an error they are the
    first to encounter, which is a bad way to find out a 21GB download did not
    finish.
    """
    available: set[str] = set()
    for node in (object_info or {}).values():
        inputs = (node.get("input") or {})
        for group in ("required", "optional"):
            for spec in (inputs.get(group) or {}).values():
                if not isinstance(spec, (list, tuple)) or not spec:
                    continue
                options = None
                if isinstance(spec[0], list):
                    options = spec[0]
                elif (spec[0] == "COMBO" and len(spec) > 1
                        and isinstance(spec[1], dict)):
                    options = spec[1].get("options")
                if isinstance(options, list):
                    available.update(x for x in options if isinstance(x, str))
    if not available:
        return []   # nothing readable; say nothing rather than cry wolf
    return sorted(name for name in wanted_models() if name not in available)
