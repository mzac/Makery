"""Turning a picture they already have into a different kind of picture.

"Turn it into..." is a row of chips in the gallery viewer - a cartoon, a
watercolour, a pencil drawing, a clay model - and each chip sends one sentence
to Flux 2 Klein with their own picture attached as the reference. The sentences
live here for the same reason the dropdown phrases live in `styles.py`: they
are ours, written once, tuned in one place, and never typed by a child.
Nothing here goes through `safety.check_prompt`, exactly like `styles.CUTOUT`
and `styles.OUTPAINT` - a fixed list we wrote cannot introduce anything the
check would have caught. Their own optional twist *is* checked, on the route.

**`KEEP` is the half that does the work.** Without it Klein reads "make this a
watercolour" as licence to paint *a* watercolour of roughly that subject, and
what comes back is a different picture in the right style. With it, the same
cat is in the same place on the same grass.

Two things learned by rendering, both worth not re-learning:

- **Do not tell it what not to draw.** Cartooning a photograph of a peach gives
  the peach a face. Adding "nothing grows a face, eyes or a mouth it did not
  already have" to `KEEP` made it *worse* - the same render came back with
  eyelashes. There is no negative prompt in the Klein graphs and CFG is 1.0, so
  a forbidding sentence is just those words in the instruction. Say what it
  should draw, never what it should not.
- **Do not name a grid.** "Drawn on a grid just 64 squares across" was an
  attempt to make pixel art bite, and it drew literal graph paper over the
  picture. Pixel art is not in the list at all; see CLAUDE.md for why.
"""

KEEP = ("Keep the same scene: the same things, the same people and animals, "
        "in the same places, doing the same things. Change only how it is "
        "drawn, not what is in it.")


class Restyle:
    """One chip: what it says on the button, to the model, and in their gallery."""

    def __init__(self, ident: str, label: str, instruction: str, asked: str):
        self.id = ident
        self.label = label              # what they tap
        self.instruction = instruction  # what the model is told
        # What the viewer shows as the thing they asked for, when they typed
        # nothing of their own. The label is a noun on a button ("A cartoon");
        # this is the sentence that noun was short for.
        self.asked = asked

    def public(self) -> dict:
        # The instruction is not sent to the page. They pick a picture, not a
        # sentence, and the row would be a wall of text - the wording is the
        # server's business, like every style phrase in styles.py.
        #
        # The label is translated here and the instruction never is: they read
        # the chip, Klein reads the sentence, and Klein reads English.
        from . import i18n

        return {"id": self.id, "label": i18n.label("restyle", self.id, self.label)}


# Order is the order of the row, and it is deliberate: the three they will reach
# for most first, the odder materials after them, and "Make it real" last,
# because on one of their own drawings it is the one that gets a gasp and it
# should be the one they find by reading to the end.
STYLES = [
    Restyle("cartoon", "🖍️ A cartoon",
            "Redraw this as a bright, friendly cartoon with bold outlines and "
            "flat colours.",
            "turn it into a cartoon"),
    Restyle("painting", "🎨 A painting",
            "Repaint this as a soft watercolour painting on textured paper, "
            "with visible brush strokes and colours that run into one another.",
            "turn it into a painting"),
    Restyle("pencil", "✏️ A pencil drawing",
            "Redraw this as a pencil sketch on white paper: grey graphite "
            "lines and cross-hatched shading, no colour.",
            "turn it into a pencil drawing"),
    Restyle("comic", "💥 A comic",
            "Redraw this as one comic-book panel: heavy ink outlines, bold "
            "flat colour and halftone dots. No speech bubbles and no lettering "
            "anywhere.",
            "turn it into a comic"),
    Restyle("clay", "🧸 A clay model",
            "Remake this as a stop-motion clay model, everything moulded out "
            "of soft plasticine with thumbprints still in it.",
            "turn it into a clay model"),
    Restyle("bricks", "🧱 Toy bricks",
            "Rebuild everything in this picture out of toy plastic building "
            "bricks, with studs on top.",
            "build it out of toy bricks"),
    Restyle("glass", "🪟 Stained glass",
            "Remake this as a stained-glass window, pieces of coloured glass "
            "held in black lead lines and lit from behind.",
            "turn it into stained glass"),
    Restyle("real", "📷 Make it real",
            "Turn this into a real photograph of the same scene, with real "
            "materials, real light and real depth.",
            "make it real"),
]

BY_ID = {s.id: s for s in STYLES}
DEFAULT = STYLES[0].id


def choices() -> list[dict]:
    """The row, for the page to build itself from."""
    return [s.public() for s in STYLES]


def known(style_id: str) -> bool:
    return style_id in BY_ID


def _chip(style_id: str) -> Restyle:
    """The chip they tapped, or the first one.

    An unknown id falls back rather than raising: the page can only send one of
    these, so an unknown one means a stale page after a rebuild, and a cartoon
    is a kinder answer to that than a 400 they cannot act on.
    """
    return BY_ID.get(style_id) or BY_ID[DEFAULT]


def label_for(style_id: str) -> str:
    """What they tapped, for a toast."""
    return _chip(style_id).label


def asked_for(style_id: str, words: str = "") -> str:
    """What the viewer shows as the thing they asked for.

    Their own twist is added to the chip's sentence rather than replacing it, so
    a year later the sidecar still says which button made this picture.
    """
    extra = (words or "").strip()
    asked = _chip(style_id).asked
    return f"{asked}, {extra}" if extra else asked


def compose(style_id: str, words: str = "") -> str:
    """The chip's sentence, the rule that keeps the scene, then their own twist.

    Their words go **last** on purpose. `KEEP` is an anchor and their sentence is
    the one thing here they wrote themselves, so it should be the last thing the
    model reads: "and give the cat a wizard hat" then lands as an exception they
    asked for rather than as a line the rule above it has already refused.
    """
    from . import prompts

    chosen = _chip(style_id)
    keep = prompts.text("restyle", KEEP)
    extra = (words or "").strip()
    return f"{chosen.instruction} {keep} {extra}" if extra else \
        f"{chosen.instruction} {keep}"
