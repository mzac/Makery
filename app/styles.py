"""Optional prompt ingredients: style, place, lighting, mood.

Writing a good image prompt is a skill, and "a cat" gets a dull picture. These
are the dials that make the biggest difference to how a picture looks, offered
as a few words they can pick rather than a phrase they have to know to type.

Each choice carries the wording that gets appended to their prompt, so the actual
phrasing lives here and can be tuned without touching the page. Everything here
is appended *after* their own words, so the picture is still theirs - these change
how it looks, not what it is.
"""

from . import i18n

# group id -> (label shown above the dropdown, [(choice id, label, phrase)])
GROUPS = [
    (
        "style",
        "Style",
        [
            ("cartoon", "Cartoon", "in a bright, friendly cartoon style"),
            ("anime", "Anime", "in a colourful anime style"),
            ("pixar", "3D movie", "as a glossy 3D animated movie still"),
            ("storybook", "Storybook", "as a warm children's storybook illustration"),
            ("watercolour", "Watercolour", "as a soft watercolour painting"),
            ("oil", "Oil painting", "as a rich oil painting with visible brushstrokes"),
            ("sketch", "Pencil sketch", "as a detailed pencil sketch"),
            ("pixel", "Pixel art", "as crisp retro pixel art"),
            ("comic", "Comic book", "as a bold comic book panel with strong ink lines"),
            ("clay", "Claymation", "as a handmade claymation scene"),
            ("papercraft", "Paper craft", "as a layered cut-paper diorama"),
            ("photo", "Photograph", "as a sharp, realistic photograph"),
            # Painting and drawing tools, added alongside the original twelve.
            ("chalk", "Chalk drawing", "as a chalk drawing on a dark blackboard, soft dusty texture"),
            ("crayon", "Crayon drawing", "as a thick wax crayon drawing, bold strokes and visible paper texture"),
            ("charcoal", "Charcoal drawing", "as a charcoal drawing, smudgy black and grey shading on textured paper"),
            ("inkwash", "Ink and wash", "as an ink and wash drawing, loose black ink lines with soft grey washes"),
            ("stainedglass", "Stained glass", "in the style of a stained-glass window, bold black lead lines between panes of coloured glass"),
            ("woodcut", "Woodcut print", "in the style of a woodcut print, bold black lines and rough carved texture"),
            ("popart", "Pop art", "in a bold pop art style like a vintage comic-book advert, thick black outlines and rows of coloured halftone dots for shading"),
            ("ukiyoe", "Japanese woodblock print", "in the style of a Japanese woodblock print, flat colour and bold outlines"),
            ("graffiti", "Graffiti", "as colourful spray-paint graffiti art on a brick wall"),
            # Made out of something, rather than drawn or painted.
            ("bricks", "Toy bricks", "built entirely out of colourful toy building bricks, studs visible on every surface"),
            ("felt", "Felt", "made of soft felt fabric shapes, hand-stitched edges and visible thread"),
            ("knitted", "Knitted wool", "knitted out of chunky coloured wool, like a cosy jumper"),
            ("origami", "Origami", "folded from colourful origami paper, crisp geometric creases"),
            ("sand", "Sand sculpture", "sculpted out of golden beach sand"),
            ("balloon", "Balloon animal", "twisted and shaped entirely out of long balloons"),
            ("gingerbread", "Gingerbread", "made of gingerbread and icing, like a gingerbread house"),
            # Screen and print styles.
            ("retrogame", "Retro video game", "as a chunky 16-bit retro video game scene, simple sprites and a limited colour palette"),
            ("stopmotion", "Stop-motion", "as a stop-motion puppet animation frame, felt and fabric textures with visible seams"),
            ("cartoon80s", "80s cartoon", "in a retro 1980s Saturday-morning cartoon style, thick outlines and flat retro colour"),
            ("sticker", "Sticker", "as a glossy die-cut sticker with a thick white border"),
            ("emoji", "Emoji", "in a bold simple emoji style, thick clean outlines and only a few flat colours"),
            ("lowpoly", "Low-poly 3D", "in a low-poly 3D style, made of flat faceted geometric shapes"),
            ("vectorflat", "Flat vector art", "as a flat vector illustration, clean simple shapes and no shading"),
            # Photographic looks.
            ("vintagephoto", "Vintage photo", "as a faded vintage photograph, grainy and slightly sun-bleached"),
            ("polaroid", "Polaroid", "as an instant polaroid photo with a thick white border"),
            ("macro", "Macro close-up", "as an extreme close-up macro photograph with a soft blurred background"),
            ("bwfilm", "Black-and-white film", "as a black-and-white film photograph with soft grain"),
            # A few favourites of their own.
            ("coloringpage", "Colouring page", "as a black-and-white colouring page, bold clean outlines on plain white paper, no shading, no grey, no colour, ready to print"),
            ("doodle", "Doodle", "as a scribbly hand-drawn doodle in marker pen, loose and playful"),
            ("blueprint", "Blueprint", "as a technical blueprint drawing, pale white outline only on a deep blue background, thin grid lines and dimension marks, no colour, no shading, no text, no words, no labels"),
            ("treasuremap", "Treasure map", "drawn as part of an old treasure map, the whole picture hand-drawn in sepia ink on aged parchment paper, a dotted path and a compass rose worked into the scene, no text, no words, no letters, no writing, no signs, no logos"),
        ],
    ),
    (
        "scene",
        "Where is it?",
        [
            # Real places first, magical ones next, everyday ones last - a
            # dropdown of 40 needs an order, and that is roughly how a person
            # would sort them if you asked.
            ("forest", "Forest", "set deep in a mossy green forest"),
            ("beach", "Beach", "set on a sunny beach with rolling waves"),
            ("city", "City", "set in a busy city street"),
            ("farm", "Farm", "set on a cheerful countryside farm"),
            ("mountains", "Mountains", "set high in snowy mountains"),
            ("mountaintop", "Mountain top", "set on a snowy mountain peak above the clouds"),
            ("snow", "Snowy", "set in deep fresh snow"),
            ("desert", "Desert", "set in a wide golden desert"),
            ("oasis", "Desert oasis", "set at a desert oasis with palm trees around a pool"),
            ("jungle", "Jungle", "set in a steamy jungle full of huge leaves"),
            ("jungletemple", "Jungle temple", "set among the mossy ruins of an old jungle temple"),
            ("savannah", "Savannah", "set on a wide golden savannah dotted with acacia trees"),
            ("rainstreet", "Rainy street", "set on a rainy city street with puddles and umbrellas"),
            ("market", "Busy market", "set in a bustling outdoor market full of colourful stalls"),
            ("lighthouse", "Lighthouse", "set on a windswept cliff beside a tall lighthouse"),
            ("treehouse", "Treehouse", "set in a cosy treehouse high among the branches"),
            ("playground", "Playground", "set on a school playground at recess"),
            ("library", "Library", "set in a quiet library among tall shelves of books"),
            ("volcano", "Inside a volcano", "set in a glowing cavern deep inside a volcano"),
            ("arctic", "The Arctic", "set on Arctic ice among icebergs"),
            ("waterfall", "Waterfall", "set beside a roaring waterfall"),
            ("space", "Space", "set in outer space among stars and planets"),
            ("moon", "On the moon", "set on the moon among craters, Earth glowing in the sky"),
            ("underwater", "Underwater", "set underwater among coral and fish"),
            ("castle", "Castle", "set in a grand old castle"),
            ("candyland", "Candy land", "set in a land made of sweets and candy"),
            ("clouds", "In the clouds", "set high up among fluffy clouds"),
            ("cloudcastle", "Cloud castle", "set atop a castle floating high among the clouds"),
            ("floatingisland", "Floating island", "set on a floating island drifting through the sky"),
            ("snowglobe", "Inside a snow globe", "set inside a snow globe with glitter swirling down"),
            ("giantskitchen", "Giant's kitchen", "set on an enormous kitchen table, dwarfed by giant plates, cups and spoons all around"),
            ("robotcity", "Robot city", "set in a gleaming robot city of towers and gears"),
            ("dragoncave", "Dragon's cave", "set in a friendly dragon's cave, sparkling with treasure"),
            ("dinosaurvalley", "Dinosaur valley", "set in a lush valley among gentle dinosaurs"),
            ("bedroom", "Cosy room", "set in a cosy room full of soft cushions"),
            ("kitchentable", "Kitchen table", "set at the kitchen table at home"),
            ("gardenshed", "Garden shed", "set in a cluttered, cosy garden shed"),
            ("backseat", "Car ride", "set in the back seat of a car on a road trip"),
            ("backyard", "Backyard", "set in a sunny backyard garden"),
        ],
    ),
    (
        "lighting",
        "Lighting",
        [
            ("sunny", "Sunny day", "lit by bright midday sunshine"),
            ("sunset", "Golden sunset", "lit by warm golden sunset light"),
            ("moonlight", "Moonlight", "lit by cool silver moonlight"),
            ("candle", "Candlelight", "lit by flickering candlelight"),
            ("neon", "Neon glow", "lit by glowing neon signs"),
            ("rainbow", "Rainbow light", "lit by shimmering rainbow light"),
            ("misty", "Misty morning", "in soft misty morning light"),
            ("stars", "Starry night", "under a sky full of bright stars"),
            ("fire", "Firelight", "lit by the warm glow of a campfire"),
        ],
    ),
    (
        "mood",
        "Feeling",
        [
            # Each phrase steers the picture itself - expression, posture,
            # palette, weather - rather than just naming the emotion, because
            # "grumpy" as a word does nothing to a diffusion model.
            ("cosy", "Cosy", "with a warm, cosy feeling"),
            ("magical", "Magical", "with a sparkling, magical feeling"),
            ("silly", "Silly", "with a playful, silly feeling"),
            ("epic", "Epic", "with a grand, epic feeling"),
            ("peaceful", "Peaceful", "with a calm, peaceful feeling"),
            ("adventure", "Adventurous", "with an exciting sense of adventure"),
            ("dreamy", "Dreamy", "with a soft, dreamy feeling"),
            ("mysterious", "Mysterious", "with a sly half-smile and narrowed eyes, in dim mysterious light"),
            ("brave", "Brave", "standing tall with fists on hips and a determined look"),
            ("sleepy", "Sleepy", "with heavy eyelids and a big yawn, wrapped in a cosy blanket"),
            ("proud", "Proud", "with head held high, chest puffed out and a beaming grin"),
            ("nervous", "Nervous", "with wide eyes and a nervous smile, fidgeting hands"),
            ("giggly", "Giggly", "laughing with eyes scrunched shut and shoulders shaking"),
            ("dramatic", "Dramatic", "in a bold heroic pose against a stormy sky"),
            ("spookyfun", "Spooky but fun", "with a playful spooky grin under a moody purple twilight"),
            ("lonely", "Lonely", "sitting small and still in a big quiet space, muted colours"),
            ("triumphant", "Triumphant", "with arms raised high in victory and confetti in the air"),
            ("curious", "Curious", "leaning in with wide curious eyes and a raised eyebrow"),
            ("grumpy", "Grumpy", "with a grumpy scowl and crossed arms, in a huffy mood"),
            ("wild", "Wild", "mid-leap with wind-blown hair and a wide excited grin"),
            ("excited", "Excited", "jumping with arms flung wide and a huge open-mouthed grin"),
            ("shy", "Shy", "peeking out from behind something, cheeks blushing pink"),
            ("confident", "Confident", "with a cool smirk and hands on hips, standing steady"),
            ("sneaky", "Sneaky", "tiptoeing with a sly grin and one finger to the lips"),
            ("hopeful", "Hopeful", "gazing upward with hands clasped, soft warm light"),
            ("determined", "Determined", "with narrowed eyes and clenched fists, leaning forward"),
            ("surprised", "Surprised", "with wide eyes, raised eyebrows and an open mouth"),
            ("mischievous", "Mischievous", "with a cheeky grin and one eyebrow raised, up to something"),
        ],
    ),
    # Two more dials, asked for once the first four were in use. Colour is the
    # single biggest change to how a picture *feels* after the art style, and
    # where it is seen from is the one bit of composition worth a dropdown.
    (
        "colours",
        "Colours",
        [
            ("bright", "Bright and bold", "in bright, bold, saturated colours"),
            ("pastel", "Soft pastels", "in soft pastel colours"),
            ("rainbow", "Rainbow", "in every colour of the rainbow"),
            ("warm", "Warm", "in warm reds, oranges and golds"),
            ("cool", "Cool", "in cool blues, greens and purples"),
            ("neon", "Neon", "in glowing neon colours on dark"),
            ("earthy", "Earthy", "in natural earthy browns and greens"),
            ("mono", "Black and white", "in black and white"),
            ("sepia", "Old photo", "in faded sepia tones like an old photograph"),
            ("gold", "Gold and silver", "in shimmering gold and silver"),
            ("icyblue", "Icy blues", "in cool icy blues and whites"),
            ("sunset", "Sunset oranges", "in glowing sunset oranges and pinks"),
            ("candypink", "Candy pink", "in every shade of candy pink"),
            ("forestgreen", "Forest greens", "in deep forest greens"),
            ("goldpurple", "Gold and purple", "in regal gold and purple"),
            ("monored", "Shades of red", "in shades of red, from pale pink to deep crimson"),
            ("blueyellow", "Blue and yellow only", "using only blue and yellow"),
            ("jewel", "Jewel tones", "in rich jewel tones of emerald, ruby and sapphire"),
            ("autumn", "Autumn colours", "in rich autumn oranges, reds and browns"),
            ("spring", "Spring colours", "in fresh spring greens and blossom pinks"),
            ("christmas", "Christmas colours", "in festive Christmas red and green"),
            ("halloween", "Halloween colours", "in spooky Halloween orange and black"),
        ],
    ),
    (
        "seenfrom",
        "Seen from",
        [
            ("closeup", "Close up", "seen in close-up"),
            ("far", "Far away", "seen from far away, small in a big scene"),
            ("above", "From above", "seen from high above, looking down"),
            ("below", "From below", "seen from down low, looking up"),
            ("side", "From the side", "seen from the side, in profile"),
            ("behind", "From behind", "seen from behind"),
            ("eye", "Eye level", "seen straight on at eye level"),
        ],
    ),
]

# Video gets the look dials above plus three of its own. LTX 2.5 renders audio,
# so music and background sound are things the prompt can actually ask for, and
# camera movement is the one cinematic control worth exposing to a child.
VIDEO_ONLY_GROUPS = [
    (
        "camera",
        "Camera",
        [
            ("slowzoom", "Slow zoom in", "the camera slowly pushes in"),
            ("pullback", "Pull back", "the camera slowly pulls back to reveal the scene"),
            ("pan", "Slow pan", "the camera pans slowly across the scene"),
            ("orbit", "Circle around", "the camera circles slowly around the subject"),
            ("follow", "Follow along", "the camera follows alongside the subject"),
            ("closeup", "Close up", "filmed in close-up"),
            ("wide", "Wide shot", "filmed as a wide establishing shot"),
            ("drone", "From above", "filmed from high above, looking down"),
            ("still", "Hold still", "the camera stays completely still"),
            ("tiltup", "Look up", "the camera tilts slowly upward"),
            ("flyover", "Swoop over", "the camera swoops low and fast over the scene"),
            ("timelapse", "Speed up", "the scene plays in a fast, fun time-lapse"),
        ],
    ),
    (
        "music",
        "Music",
        [
            ("ukulele", "Happy ukulele", "cheerful ukulele music plays"),
            ("piano", "Gentle piano", "soft gentle piano music plays"),
            ("orchestra", "Big and epic", "a sweeping orchestral score plays"),
            ("chiptune", "Video game", "bouncy 8-bit chiptune music plays"),
            ("jazz", "Jazzy", "relaxed jazz music plays"),
            ("dreamy", "Dreamy", "slow dreamy synth music plays"),
            ("marching", "Marching band", "a lively marching band plays"),
            ("spooky", "Mysterious", "light mysterious music plays"),
            ("rock", "Upbeat rock", "upbeat rock music plays"),
            ("lullaby", "Lullaby", "a soft gentle lullaby plays"),
            ("circus", "Circus", "bouncy circus music plays"),
            ("none", "None", "no background music"),
        ],
    ),
    (
        "sounds",
        "Background sounds",
        [
            ("none", "None", "no ambient background noise, only the sounds of what is on screen"),
            ("birds", "Birds and wind", "birds sing and wind rustles in the background"),
            ("waves", "Ocean waves", "ocean waves wash in the background"),
            ("rain", "Rain", "gentle rain patters in the background"),
            ("forest", "Forest", "leaves and creaking branches in the background"),
            ("city", "Busy city", "distant city traffic and chatter in the background"),
            ("fire", "Crackling fire", "a fire crackles in the background"),
            ("crowd", "Cheering crowd", "a crowd cheers in the background"),
            ("kitchen", "Kitchen clatter", "pots and pans clatter in the background"),
            ("space", "Deep hum", "a deep quiet hum in the background"),
            ("quiet", "Quiet", "almost silent, just faint room tone"),
            ("thunder", "Distant thunder", "distant thunder rumbles softly in the background"),
            ("playground", "Playground", "children laughing and playing in the background"),
            ("splash", "Splashing water", "water splashes and trickles in the background"),
        ],
    ),
]

# Where a group should start somewhere other than "Any" (no phrase, the model
# decides). Music and background sound default to none: left to itself the
# model invents a soundtrack, and an unasked-for one over their dialogue is worse
# than silence. They can still pick "Any" to let it choose.
DEFAULTS = {"music": "none", "sounds": "none"}

# Which groups make sense in which video mode. Starting from a picture, the
# scene, style and lighting are already decided by that picture - offering them
# again would only fight it - but the camera and the sound are still open.
I2V_GROUPS = {"camera", "music", "sounds", "mood"}

# A comic gets the look, the place and the feeling; lighting is left out
# because the panel style already fixes it and a sixth dropdown on that card
# was more to read than to choose from. Whatever they pick is repeated in
# *every* panel, which is half of why the panels look like one strip.
COMIC_GROUPS = {"style", "scene", "mood", "colours"}

# Flattened for lookup: {group id: {choice id: phrase}}
ALL_GROUPS = GROUPS + VIDEO_ONLY_GROUPS
_PHRASES = {gid: {cid: phrase for cid, _, phrase in choices} for gid, _, choices in ALL_GROUPS}

# The order phrases are appended in. Subject first (theirs), then where it is,
# then how it is drawn, then the light, then the feeling - which reads the way
# a person would describe a picture out loud.
ORDER = ["seenfrom", "scene", "style", "colours", "lighting", "mood", "camera", "music", "sounds"]

# A choice that looks right in a still can still go wrong once LTX puts it in
# motion - fine detail that flickers or crawls frame to frame, mostly. Rather
# than a fourth element on every tuple (which every unpacking site above would
# have to learn to ignore), picture-only choices are named here instead, by
# (group id, choice id), and only `options("video")` reads this set. The id
# keeps working everywhere else - compose(), random_selection(), "make
# another like this" off an old picture - only the video dropdown loses the
# option. Populated only by a render that proved a style does not hold up
# moving - see CLAUDE.md's "Style dropdowns" for what each one actually did.
PICTURE_ONLY: set[tuple[str, str]] = {
    # Flat line art with no shading: LTX redrew it as an ordinary grainy
    # monochrome nature clip, shading and all - the "no shading" instruction
    # held for a still and lost the moment there was motion to render.
    ("style", "coloringpage"),
    # The halftone dot pattern and bold flat colour both went: it came out as
    # a fine-line pencil/etching sketch with stippled shading, not pop art.
    ("style", "popart"),
    # Kept the drawn white-line border but filled the middle with an ordinary
    # colour photograph instead of extending the blueprint linework into it.
    ("style", "blueprint"),
    # The faceted geometry didn't survive motion: it came out as an ordinary
    # smooth 3D-movie render, indistinguishable from "3D movie".
    ("style", "lowpoly"),
}


# The cards that render motion, in every spelling a caller uses for one: the
# page says "video", the remix route says which mode they are in. A picture-only
# style is dropped for all of them and for none of the others.
VIDEO_KINDS = frozenset({"video", "t2v", "i2v", "flf", "story"})


def groups_for(kind: str = "image") -> list[tuple]:
    """The groups one card actually has.

    One answer for both the dropdowns and the random draw behind Surprise me:
    a draw from a group the card does not show sets a dropdown that is not
    there, and a group it does show and the draw skips is a dial left on Any.
    """
    if kind in VIDEO_KINDS:
        # "Seen from" and the video card's own Camera dropdown ask the same
        # question, and the camera one also moves. One of them goes.
        groups = [g for g in ALL_GROUPS if g[0] != "seenfrom"]
        if kind == "i2v":
            # Starting from a picture, the page hides everything the picture
            # has already decided - see I2V_GROUPS.
            groups = [g for g in groups if g[0] in I2V_GROUPS]
        return groups
    if kind == "comic":
        return [g for g in GROUPS if g[0] in COMIC_GROUPS]
    return list(GROUPS)


def options(kind: str = "image") -> list[dict]:
    """The dropdowns, for the page to render."""
    groups = groups_for(kind)
    # The labels are translated here, on the way out, rather than carried in
    # the tuples above: these lists grow, and a French column beside every
    # choice is one more thing for whoever adds one to get wrong. i18n keeps
    # them by (group, choice) and falls back to the English, so a new choice
    # turns up working and untranslated rather than blank.
    return [
        {
            "id": gid,
            "label": i18n.t(label),
            "choices": [
                {"id": cid, "label": i18n.label(gid, cid, clabel)}
                for cid, clabel, _ in choices
                if kind not in VIDEO_KINDS or (gid, cid) not in PICTURE_ONLY
            ],
            # The page hides groups that do not apply to the current mode.
            "modes": ["t2v", "i2v"] if gid in I2V_GROUPS else ["t2v"],
            # Pre-selected on the page, and what "Clear all" returns to.
            "default": DEFAULTS.get(gid, ""),
        }
        for gid, label, choices in groups
    ]


def random_selection(groups: list[str] | None = None,
                     kind: str = "image") -> dict:
    """One random choice per group, for the Surprise me button.

    Every choice in every group is safe on its own and safe in combination -
    that is the point of them being a fixed list - so any draw is fine to use
    without further checking.

    `kind` is the card asking, and it decides which groups are drawn from when
    nothing is named: the video card's own Camera, Music and Sounds were never
    in the draw (the fallback list was the picture groups), and the picture-only
    styles were, although `options("video")` does not offer them - so a surprise
    on the video card set dropdowns that were not there and left the ones that
    were on Any. `groups` still wins when a caller names its own.
    """
    import random

    available = groups_for(kind)
    wanted = groups if groups is not None else [gid for gid, _, _ in available]
    picked = {}
    for gid, _, choices in available:
        if gid not in wanted:
            continue
        # The same list the dropdown shows: a style that does not survive
        # motion must not be drawn for a video either.
        offered = [c for c in choices
                   if kind not in VIDEO_KINDS or (gid, c[0]) not in PICTURE_ONLY]
        if offered:
            picked[gid] = random.choice(offered)[0]
    return picked


def compose(prompt: str, selections: dict | None) -> str:
    """Append the chosen phrases to their prompt. Unknown ids are ignored."""
    text = (prompt or "").strip()
    if not selections:
        return text

    extras = []
    for gid in ORDER:
        phrase = _PHRASES.get(gid, {}).get(selections.get(gid) or "")
        if phrase:
            extras.append(phrase)

    if not extras:
        return text
    # Drop a trailing full stop so the additions read as one sentence.
    if text.endswith("."):
        text = text[:-1]
    return text + ", " + ", ".join(extras)


# --- a picture meant to be cut out ------------------------------------------

# Appended when they ask for a character rather than a scene. This is what
# makes the sticker cut-out work at all: the flood fill has no subject
# detection in it, only "the background is whatever touches the edge and looks
# like the edge", so it needs a background that is genuinely plain. Flux gives
# one reliably when asked in these terms.
#
# Deliberately silent about art style. Cartoon, watercolour, pixel art - that
# is still theirs, and saying "sticker illustration" here would quietly overrule
# whatever they picked.
CUTOUT = (
    "the whole subject visible and centred with space around it, "
    "alone on a plain flat white background, nothing else in the picture, "
    "no scenery, no floor, no shadow, soft even lighting"
)

# The banner across the top of their page. A wide strip with the title drawn over
# it as real text, so the picture itself must have none: Flux schnell at four
# steps cannot spell, and a misspelled banner is worse than no banner. The
# middle is asked to stay quiet because that is where the title sits.
BANNER = (
    "a wide decorative banner illustration, filling the whole frame, "
    "no text, no words, no letters, no writing, no signs, no logos, "
    "nothing important in the very middle, "
    "bright and cheerful, rich colour"
)


def compose_banner(prompt: str, selections: dict | None = None) -> str:
    """Their words and their look, plus what makes a strip work as a background."""
    from . import prompts

    return f"{compose(prompt, selections).rstrip('. ')}, {prompts.text('banner', BANNER)}"


# A place and a plain background are contradictory instructions, and Flux
# resolves the contradiction by drawing the place. A lighting choice puts
# coloured light and cast shadows onto what needs to stay flat white. The page
# hides both dropdowns in character mode; this is the half that means they
# cannot be sent anyway.
CUTOUT_DROPS = ("scene", "lighting")


# --- what is outside the frame ----------------------------------------------

# "What's outside the frame?" has an *optional* words box: the picture is the
# instruction and "show me more of it" is a complete request. So something has
# to be said to the model when they say nothing, and this is it - ours, in the
# same way the cut-out and banner wordings are, so it needs no filtering and
# cannot introduce anything their own words would have been stopped for.
#
# "The same scene" is the working half. Without it Klein reads a bigger canvas
# as licence to compose a new picture in the space.
OUTPAINT = ("Zoom out and continue the same scene outwards, keeping "
            "everything already in the picture exactly as it is.")


def compose_outpaint(prompt: str = "") -> str:
    """Our framing sentence, and their own words after it if they typed any."""
    from . import prompts

    lead = prompts.text("outpaint", OUTPAINT)
    words = (prompt or "").strip()
    return f"{lead} {words}" if words else lead


def compose_cutout(prompt: str, selections: dict | None) -> str:
    """Their words and their look, plus the wording that gets a cuttable picture."""
    kept = {k: v for k, v in (selections or {}).items() if k not in CUTOUT_DROPS}
    from . import prompts

    return f"{compose(prompt, kept).rstrip('. ')}, {prompts.text('cutout', CUTOUT)}"
