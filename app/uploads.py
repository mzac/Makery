"""Photos they take or pick on the iPad, and drawings from the drawing pad.

Two steps, used at different times:

- `keep()` runs once, on upload: re-encode the whole picture (EXIF and any GPS
  stripped, proven to really be an image, capped in size) so it can be saved
  into the gallery as it is, uncropped. Drawings and photos are kept, not
  thrown away after a few hours as they once were.
- `prepare()` runs when the picture is about to become a video: crop and
  scale it to exactly the shape the video stage works at, so it animates as
  cleanly as a generated picture does.
"""

import io
import logging

from PIL import Image, ImageOps, PngImagePlugin

from .workflows import DEFAULT_ORIENTATION, size_for

try:
    # Safari usually transcodes HEIC to JPEG on upload, but not always - and a
    # photo they cannot animate because of a container format would be baffling.
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:  # pragma: no cover
    HEIF_SUPPORTED = False

log = logging.getLogger("makery.uploads")

MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # a 12MP iPad HEIC/JPEG is far below this
KEEP_MAX_SIDE = 2048  # plenty for a 1280x704 or 832x1088 crop later

FRIENDLY_BAD_IMAGE = "That file isn't a picture I can use. Try taking a photo!"
FRIENDLY_TOO_BIG = "That picture is too big! Try taking a new photo."


class UploadError(ValueError):
    """The bytes were not a usable image."""


def detect_orientation(data: bytes) -> str:
    """Landscape or portrait, from the photo's own shape.

    They will mostly be picking photos straight off the iPad, where holding it
    upright is the normal thing to do. Asking them to also set the shape by hand
    is a step they would forget, so the photo decides and the picker just shows
    what was chosen. Square photos fall to landscape.
    """
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)  # a portrait photo is often a
        width, height = image.size              # rotated landscape one on disk
    except Exception:
        return DEFAULT_ORIENTATION
    # Near enough square (an Instagram-style crop, a sticker) is square.
    if abs(width - height) / max(width, height) < 0.08:
        return "square"
    return "portrait" if height > width else "landscape"


def _open(data: bytes) -> Image.Image:
    if not data:
        raise UploadError(FRIENDLY_BAD_IMAGE)
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError(FRIENDLY_TOO_BIG)
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:  # Pillow raises a wide variety here
        raise UploadError(FRIENDLY_BAD_IMAGE) from exc
    # iPad photos carry an EXIF orientation flag; without this a portrait photo
    # arrives on its side.
    image = ImageOps.exif_transpose(image)
    return image.convert("RGB")


def keep(data: bytes) -> bytes:
    """The whole picture, cleaned and capped, as PNG - what goes in the gallery."""
    image = _open(data)
    if max(image.size) > KEEP_MAX_SIDE:
        image.thumbnail((KEEP_MAX_SIDE, KEEP_MAX_SIDE), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def prepare(data: bytes, orientation: str = DEFAULT_ORIENTATION, quality: str = "normal") -> bytes:
    """Crop to the video shape and return PNG bytes.

    The size follows the quality as well as the shape: the video stage works
    at whatever the ResolutionSelector produces for that megapixel target,
    and the frame has to be exactly that or LTX resamples it. A picture
    already at that size (a generated one, at normal) passes through.
    """
    image = _open(data)
    width, height = size_for(orientation, quality)
    if image.size == (width, height):
        return data

    # Centre-crop to the video aspect, then scale. `fit` does both, and crops
    # rather than squashing, which matters for faces.
    image = ImageOps.fit(
        image,
        (width, height),
        method=Image.LANCZOS,
        centering=(0.5, 0.5),
    )

    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


# Four times a 1280x704 picture is 5120x2816 - a 17MB PNG that opens on an
# iPad without complaint. Four times a 2048x1536 photo off their camera roll is
# fifty megapixels, which is neither quick to write nor pleasant to open. So
# anything bigger than this goes down to it first: the point is a big version
# of their picture, not the largest file the machine can be talked into writing.
UPSCALE_MAX_PIXELS = 1_300_000


def for_upscale(data: bytes) -> tuple[bytes, int, int]:
    """The picture as PNG, shrunk first if four times it would be absurd.

    Returns the bytes and the size they are, because how big the *input* was
    is what decides how long the upscale takes, and timings wants to know.
    """
    image = _open(data)
    pixels = image.width * image.height
    if pixels > UPSCALE_MAX_PIXELS:
        scale = (UPSCALE_MAX_PIXELS / pixels) ** 0.5
        image = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            Image.LANCZOS,
        )
        log.info("shrank a %d x %d picture before upscaling it", *image.size)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue(), image.width, image.height


# --- sizing a picture Flux 2 Klein is about to edit --------------------------
#
# Klein works at about a megapixel and its latent is on a 16-pixel grid, so
# every one of the three edit graphs wants a picture whose sides are a multiple
# of 16 and whose area is somewhere near 1MP. The official template does this
# in the graph with an `ImageScaleToTotalPixels` node, and that is where this
# came from - but the node resampled a 1280x704 picture of theirs *up* to
# 1376x752 to land on its own grid, which is a slightly soft copy of their
# picture at a shape that is no longer one of `workflows.ORIENTATIONS`.
#
# Both of their sizes (1280x704, 832x1088, 960x960) are already multiples of 16
# and already under the cap, so doing it here instead means an edit of a
# picture they made comes back at exactly the size it went in - and "Animate
# this" on the result is still pixel-exact.

EDIT_MAX_PIXELS = 1_050_000   # 1280x704 is 901k, so it passes untouched
EDIT_MIN_PIXELS = 500_000     # a small drawing is worth scaling *up* to
EDIT_GRID = 16                # EmptyFlux2LatentImage's own step


def _on_grid(width: int, height: int, budget: int) -> tuple[int, int]:
    """The nearest size on the 16-pixel grid at roughly `budget` pixels."""
    scale = (budget / max(1, width * height)) ** 0.5
    return (max(EDIT_GRID, round(width * scale / EDIT_GRID) * EDIT_GRID),
            max(EDIT_GRID, round(height * scale / EDIT_GRID) * EDIT_GRID))


def for_edit(data: bytes, budget: int = EDIT_MAX_PIXELS) -> tuple[bytes, int, int]:
    """The picture as PNG at a size Klein is happy with, and that size.

    `budget` is how many pixels the *finished* picture may be. Outpainting
    passes a smaller one, because what it renders is their picture plus a border
    and the whole canvas has to fit on the card.

    Anything already on the grid and inside the budget is left exactly as it
    is - the whole point of doing this here rather than in the graph.
    """
    image = _open(data)
    width, height = image.size
    pixels = width * height
    if (pixels <= budget and pixels >= EDIT_MIN_PIXELS
            and width % EDIT_GRID == 0 and height % EDIT_GRID == 0):
        out = io.BytesIO()
        image.save(out, format="PNG", optimize=True)
        return out.getvalue(), width, height

    want = min(budget, max(EDIT_MIN_PIXELS, min(pixels, budget)))
    new_width, new_height = _on_grid(width, height, want)
    image = image.resize((new_width, new_height), Image.LANCZOS)
    log.info("sized a %d x %d picture to %d x %d for editing",
             width, height, new_width, new_height)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue(), new_width, new_height


def mask_for_edit(data: bytes, width: int, height: int) -> bytes:
    """Their painted mask as a black-and-white PNG at exactly the picture's size.

    The page paints at whatever size the canvas happened to be on their screen,
    so it is scaled here rather than there; `LoadImageMask` reads the red
    channel and white means "change this bit". Nearest-neighbour on purpose -
    a smoothly resampled edge would make half-masked pixels, which is what
    made the first outpaint render come back with a grey band in it.
    """
    image = _open(data).convert("L").resize((width, height), Image.NEAREST)
    out = io.BytesIO()
    image.point(lambda v: 255 if v > 127 else 0).convert("RGB").save(out, format="PNG")
    return out.getvalue()


# --- putting their picture back into an outpainted one -------------------------
#
# The outpaint graph keeps the middle out of the denoise - that is what the pad
# node's mask is for - but the whole canvas still comes home through VAEDecode,
# and that round trip *moves* their picture. Measured against the file they
# started from, on the beach render that started this: a per-channel mean of
# +11, +10, -3 out of 255, four times the drift an inpaint shows and quite
# enough to see. The model then continues the scene outwards from the shifted
# middle, so the new border does not match the picture they are looking at
# either, and what comes back has their picture sitting inside it as a rectangle
# with a line round it.
#
# None of that can be argued out of the graph, because the middle is not
# supposed to be a render at all. So it is put back here, in three steps:
#
#   1. their tone, over the whole canvas. The middle of the render is the same
#      scene as their picture, pixel for pixel, so a per-channel mean-and-spread
#      fit between the two measures the round trip and nothing else - there is
#      no difference in content for it to be fooled by. Applying it to the
#      whole canvas carries the invented border into their tones as well. On that
#      render it was a gain of 1.09 and a lift of -31 on red, and it took the
#      middle from 9 off their picture to 3.8.
#   2. what is left of the join, levelled. A global fit cannot fix a sky that
#      is a shade lighter above the old top edge than below it, which is
#      exactly what a flat sky shows. The low-frequency difference between their
#      picture and the render's middle is spread outwards over the border and
#      added to it, fading out over OUTPAINT_REACH: that pins the broad tone of
#      the new border to theirs at the join and lets the model's own back in
#      further out, where nothing is there to compare it against.
#   3. their own pixels, pasted back. Full weight over every pixel of their picture
#      - so the middle is their file byte for byte, which is what "keeping
#      everything already in the picture exactly as it is" promises them - and
#      fading out over OUTPAINT_FEATHER into the border, so there is nowhere a
#      hard line could be.
#
# Steps 1 and 2 are why the paste in step 3 is invisible rather than being the
# rectangle it was. Pasting on its own made it *worse*: their picture is duller
# than the render, and the fit is what closes that gap.

OUTPAINT_FEATHER = 32   # px the paste fades out over, into the new border
OUTPAINT_REACH = 160    # px the levelling is carried out to
OUTPAINT_DETAIL = 24    # px across: anything smaller does not survive the blur


def _fades_outwards(shape: tuple[int, int], pads, size, over: int):
    """1 over their picture, falling to 0 `over` pixels out into the border.

    Smoothstep rather than a straight ramp: a linear one has a corner at each
    end, and a corner in the weights is a faint edge of its own.
    """
    import numpy as np

    left, top, right, bottom = pads
    width, height = size
    rows, cols = np.arange(shape[0]), np.arange(shape[1])
    # How far outside their picture each row and each column is, negative inside.
    down = np.maximum(top - rows, rows - (top + height - 1))
    across = np.maximum(left - cols, cols - (left + width - 1))
    out = np.clip(np.maximum(down[:, None], across[None, :]), 0, None)
    if over <= 0:
        return (out == 0).astype("float64")
    step = np.clip(out / over, 0.0, 1.0)
    return 1.0 - step * step * (3.0 - 2.0 * step)


def _broad(field, detail: int):
    """`field` with everything finer than `detail` pixels blurred out of it.

    Down to a thumbnail and back up rather than a Gaussian: at this radius the
    two are indistinguishable, and this one is a pair of Pillow resizes instead
    of a convolution the size of the picture.
    """
    import numpy as np

    height, width = field.shape[:2]
    small = (max(1, round(width / detail)), max(1, round(height / detail)))
    out = np.empty_like(field)
    for channel in range(field.shape[2]):
        plane = Image.fromarray(field[..., channel].astype("float32"), mode="F")
        out[..., channel] = np.asarray(
            plane.resize(small, Image.BOX).resize((width, height), Image.BICUBIC),
            dtype=field.dtype,
        )
    return out


def rejoin_outpaint(rendered: bytes, source: bytes, pads) -> bytes:
    """The outpaint, with their own picture put back into the middle of it.

    `pads` is what went to the pad node - left, top, right, bottom - so the
    middle is known exactly rather than being looked for.

    Raises ValueError if the render is not the size those pads make, which
    means something upstream changed and the caller should keep the render as
    it came back rather than paste their picture into the wrong place.
    """
    import numpy as np

    left, top, right, bottom = (int(p) for p in pads)
    original = np.asarray(_open(source), dtype="float64")
    height, width = original.shape[:2]
    # The text chunks ComfyUI wrote, kept: gallery.recover_sidecar reads the
    # graph back out of them when a sidecar has gone missing, and saving this
    # file again would otherwise be the thing that lost it.
    came_back = Image.open(io.BytesIO(rendered))
    came_back.load()
    chunks = dict(getattr(came_back, "text", {}) or {})
    grown = np.asarray(_open(rendered), dtype="float64")
    if grown.shape[:2] != (height + top + bottom, width + left + right):
        raise ValueError(
            f"a {grown.shape[1]}x{grown.shape[0]} render is not what pads "
            f"{(left, top, right, bottom)} make of {width}x{height}")

    # 1. Their tone, over the whole canvas.
    for channel in range(3):
        middle = grown[top:top + height, left:left + width, channel]
        spread = float(middle.std())
        if spread < 1e-6:          # a flat channel has no scale to fit
            continue
        gain = float(original[..., channel].std()) / spread
        lift = float(original[..., channel].mean()) - gain * float(middle.mean())
        grown[..., channel] = grown[..., channel] * gain + lift

    # 2. What is left of the join, levelled.
    drift = original - grown[top:top + height, left:left + width]
    drift = _broad(np.pad(drift, ((top, bottom), (left, right), (0, 0)), mode="edge"),
                   OUTPAINT_DETAIL)
    grown += drift * _fades_outwards(grown.shape[:2], (left, top, right, bottom),
                                     (width, height), OUTPAINT_REACH)[..., None]

    # 3. Their own pixels, pasted back. The border of the overlay is their edge
    # pixels repeated outwards, which is only ever seen through a weight that
    # is already falling away - at the join itself it is their edge exactly, so
    # the two sides meet on the same colour by construction.
    #
    # The fade is capped at half the shallowest pad: a fade wider than the
    # border it has to finish in would still be part their picture at the edge of
    # the canvas, which is a repeated pixel nobody asked for.
    room = min([p for p in (left, top, right, bottom) if p] or [OUTPAINT_FEATHER])
    over = min(OUTPAINT_FEATHER, max(1, room // 2))
    weight = _fades_outwards(grown.shape[:2], (left, top, right, bottom),
                             (width, height), over)[..., None]
    overlay = np.pad(original, ((top, bottom), (left, right), (0, 0)), mode="edge")
    joined = overlay * weight + np.clip(grown, 0.0, 255.0) * (1.0 - weight)

    out = io.BytesIO()
    keep = PngImagePlugin.PngInfo()
    for key, value in chunks.items():
        keep.add_text(key, value)
    # No optimize= here, unlike everything else in this file: on a 1.4MP canvas
    # it costs 1.6s of the fifteen their render took to save four percent of the
    # file, and ComfyUI's own PNG is bigger than the plain save anyway.
    Image.fromarray(np.rint(np.clip(joined, 0.0, 255.0)).astype("uint8")).save(
        out, format="PNG", pnginfo=keep)
    return out.getvalue()
