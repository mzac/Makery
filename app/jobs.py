"""Job registry and the progress model behind the bar they watch.

ComfyUI reports progress per node. Counting nodes as equal would be useless
here: the LTX graphs are ~50 nodes, of which two SamplerCustomAdvanced passes
take almost all the wall clock, so an unweighted bar leaps to 90% and then
sits there for three minutes. Nodes are weighted by how long their class type
actually takes, which keeps the bar moving roughly in step with the work.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

from . import gallery, i18n, music, notify, timings, workflows
from .comfy import ComfyClient, ComfyError, extract_outputs

log = logging.getLogger("makery.jobs")

# Rough relative cost per node class. Exact values do not matter; the ratios do.
NODE_WEIGHTS = {
    "SamplerCustomAdvanced": 40,
    "KSampler": 40,
    "TextGenerateLTX2Prompt": 12,
    "VAEDecodeTiled": 8,
    "UNETLoader": 6,
    "CheckpointLoaderSimple": 6,
    "CLIPLoader": 4,
    "VAELoader": 3,
    "LatentUpscaleModelLoader": 3,
    "LTXVLatentUpsampler": 4,
    "LTXVAudioVAEDecode": 3,
    "VAEDecode": 3,
    "CreateVideo": 3,
    "SaveVideo": 3,
    "LTXVPreprocess": 2,
    # The two graphs that are made *from* something they already have. Each is
    # one heavy node and four cheap ones, so an unweighted bar would sit at
    # 80% for the whole of it.
    "RIFE VFI": 40,
    "ImageUpscaleWithModel": 40,
    # The Klein edit graphs: one sampler, and an 8-billion-parameter text
    # encoder whose load is a real fraction of the wait.
    "CLIPTextEncode": 4,
    "VAEEncode": 2,
    "VAEEncodeForInpaint": 2,
    "UpscaleModelLoader": 6,
    "GetVideoComponents": 3,
}
DEFAULT_WEIGHT = 1

# What is actually drawing it, in words they could repeat to somebody. The
# status sheet says "Flux schnell" rather than naming a workflow file, and
# these stay English wherever they are reading: they are proper nouns, like the
# chat helper's name.
MODEL_WORDS = {
    "image": "Flux schnell",
    "comic": "Flux schnell",
    "t2v": "LTX 2.5 video",
    "i2v": "LTX 2.5 video",
    "flf": "LTX 2.5 video",
    "story": "LTX 2.5 video",
    "music": "ACE-Step song",
    # The same model and the same graph; what differs is the tag line and
    # whether anything is sung. See music.KINDS.
    "jingle": "ACE-Step tune",
    "ambience": "ACE-Step hum",
    "edit": "Flux 2 Klein edit",
    "inpaint": "Flux 2 Klein edit",
    "outpaint": "Flux 2 Klein edit",
    "restyle": "Flux 2 Klein edit",
    "smooth": "RIFE frames",
    "slowmo": "RIFE frames",
    "huge": "ESRGAN enlarger",
}


def free_after_job() -> bool:
    """Release ComfyUI's VRAM once a job is done.

    On by default: Ollama and both ComfyUI model sets (Flux for pictures, LTX
    for video) do not fit on one 16GB card together, so holding models resident
    between jobs is what causes an OOM when switching. A switch on the parent
    page now, under "The helpers", seeded once from COMFY_FREE_AFTER_JOB - a
    bigger card can afford to keep them loaded and that is a decision about the
    machine's afternoon, not about its build.
    """
    return gallery.flag("comfy_free_after_job", True)


# How much of the bar a job's finishing step is worth, measured in graphs, for
# the kinds that have one. A missing entry is a sliver, not a whole graph: a
# finishing step is usually a second of ffmpeg against minutes of rendering,
# and a slice that is too big is the one failure the child actually sees - the
# bar stopping dead at 50% and then jumping to done.
#
# Only the story's join earns a full graph: it re-encodes every clip into one
# film and really does take about as long as filming one of them.
AFTER_SHARE = {"story": 1.0}
# The kinds whose finishing step is a sliver, listed rather than left to the
# default, so it is on the record what has been measured:
#   jingle, ambience - trimming the silence off the end (gallery.trim_tail)
#   t2v, i2v, flf    - mixing in a chosen sound effect (gallery.add_sound)
#   outpaint         - putting their own picture back into the middle
AFTER_SHARE_DEFAULT = 0.05


def after_share_for(kind: str) -> float:
    """The finishing step's slice of the bar for one kind of job.

    A lookup rather than a default argument so that a new multi-stage kind
    cannot silently inherit the whole-graph slice that broke every jingle and
    every video with a sound effect. Getting it a little wrong costs a bar
    that pauses near the end; getting it wrong the old way cost a bar that sat
    at 50% and then jumped.
    """
    return AFTER_SHARE.get(kind, AFTER_SHARE_DEFAULT)


MAX_JOB_SECONDS = 60 * 60
JOB_TTL_SECONDS = 6 * 60 * 60
MAX_JOBS = 60

# Anything the child sees. Never a stack trace, never an HTTP status.
FRIENDLY_FAILURE = "Something went wrong making that one. Try again!"
FRIENDLY_BUSY = "The art computer is busy with someone else. Waiting for your turn..."
FRIENDLY_CANCELLED = "Stopped! Nothing was made. Try a different idea."


class Progress:
    """One graph's share of the bar.

    A comic is several runs behind a single progress bar, so each graph is told
    which slice of the bar it owns rather than each one sweeping 0-100%.
    """

    def __init__(self, graph: dict, base: float = 0.0, span: float = 1.0):
        self.base = base
        self.span = span
        self.weights = {
            nid: NODE_WEIGHTS.get(node.get("class_type"), DEFAULT_WEIGHT)
            for nid, node in graph.items()
        }
        self.total = sum(self.weights.values()) or 1
        self.done: set[str] = set()
        self.current: str | None = None
        self.current_fraction = 0.0

    def value(self) -> float:
        earned = sum(self.weights.get(n, 0) for n in self.done)
        if self.current and self.current not in self.done:
            earned += self.weights.get(self.current, 0) * self.current_fraction
        # Never show 100% before the file actually exists.
        return min(0.99, self.base + self.span * (earned / self.total))


@dataclass
class Job:
    id: str
    kind: str  # image | t2v | i2v | flf | comic | story | smooth | slowmo |
               # huge | edit | outpaint | inpaint
    prompt: str
    status: str = "pending"  # pending | queued | running | done | error | cancelled
    progress: float = 0.0
    # default_factory, not a plain default: a class-level default is built
    # once at import and would always be English. This one is built when the
    # job is, which is inside their request.
    message: str = field(default_factory=lambda: i18n.t("Getting ready..."))
    error: str | None = None
    prompt_id: str | None = None
    result: dict | None = None  # ComfyUI file ref: filename/subfolder/type
    # One job can produce several files - "four at once" is four runs of the
    # picture graph, one after another. `result` stays the first of them so
    # every existing single-file path keeps working, and `results` **grows as
    # each one lands**, so the page can show a picture the moment it exists
    # rather than when the whole job is over.
    results: list = field(default_factory=list)
    # How many files this job means to make, so the page can tell "three of
    # four so far" from "three, and that is all there is".
    wanted: int = 1
    # Which step is being made, and how many there are. "Picture 2 of 4..."
    # is the whole of what it is for.
    step: int = 0
    steps: int = 1
    # How many of `results` already have a sidecar written. A picture is filed
    # as it lands, not at the end, or the one they can already see would not be
    # in their gallery yet.
    filed: int = 0
    duration: int | None = None  # requested video length, seconds
    orientation: str = "landscape"
    styles: dict | None = None
    idea: str = ""  # their own words, before the style phrases were appended
    # Recorded so "make it again but..." can hand the same seed back, and so
    # a character's own page can find everything they are in.
    seed: int | None = None
    # One seed per file for a job that makes several: four at once is four
    # runs with four seeds, and "make it again, but..." on the third of them
    # has to hand back *that* picture's seed. `seed` stays the first.
    seeds: list = field(default_factory=list)
    character: str = ""
    # Drawn alone on a plain background, so it can be cut out. Recorded so
    # "make another like this" comes back as a character too.
    cutout: bool = False
    # Which language they are reading. Carried on the job for the same reason
    # `who` is: what the bar says is written from the ComfyUI websocket's own
    # task, which was started long before their request and has none of its
    # context - so `i18n.t` there would answer in English whatever they chose.
    lang: str = ""
    # Which child asked for it. Carried on the job rather than read off the
    # request context when it finishes, because by then the request that
    # started a two-minute video is long gone - and this is what decides whose
    # gallery the file lands in.
    who: str = ""
    # Kind-specific payload the page needs back - the comic's panel captions.
    extra: dict = field(default_factory=dict)
    created: float = field(default_factory=time.time)
    started: float | None = None  # when ComfyUI actually began executing
    ended: float | None = None
    eta: float | None = None  # smoothed seconds remaining
    # How many jobs ComfyUI has in front of this one. Only ever more than
    # nothing when somebody else is using ComfyUI directly, since this app
    # allows one job at a time - which is exactly the case where "it hasn't
    # started yet" needs an explanation rather than a bar that does not move.
    ahead: int | None = None
    # What this machine's own history said this would take, asked once when
    # the job was made. The smoothed `eta` is the better answer once a render
    # is under way and says nothing at all before it is, so the sheet has both.
    estimate: dict | None = None
    cancelled: bool = False

    def elapsed(self) -> float:
        if self.started is None:
            return 0.0
        return (self.ended or time.time()) - self.started

    @property
    def is_video(self) -> bool:
        # smooth and slowmo are made from a video they already have rather than
        # rendered from words, but what comes out is a video and the page has
        # to draw one.
        return self.kind in ("t2v", "i2v", "flf", "story", "smooth", "slowmo")

    @property
    def is_audio(self) -> bool:
        return self.kind in music.JOB_KINDS

    @property
    def media(self) -> str:
        """What the page will have to draw. Its own property rather than the
        two-way `is_video` guess everything used to make: a song is neither a
        picture nor a video, and calling it a picture put an <img> in front of
        an mp3."""
        return "video" if self.is_video else "audio" if self.is_audio else "image"

    def size_words(self) -> str | None:
        """How big what they are waiting for comes out, as "1280x704".

        Three kinds of answer, because there are three kinds of job. One made
        from a file they already have knows the size in its own route and writes
        it into `extra`; a video's is the ResolutionSelector's arithmetic,
        which `size_for` already does; a picture's is the table. Anything that
        does not know says nothing, rather than printing a number they could
        hold the finished file up against and find wrong.
        """
        told = (self.extra or {}).get("size")
        if told:
            return str(told)
        if self.is_audio:
            return None
        quality = (self.extra or {}).get("quality") or workflows.DEFAULT_QUALITY
        if self.kind in ("t2v", "i2v", "flf", "story"):
            width, height = workflows.size_for(self.orientation, quality)
        elif self.kind in ("image", "comic"):
            if (self.extra or {}).get("banner"):
                width, height = workflows.BANNER_SIZE
            else:
                shape = workflows.orientation_of(self.orientation)
                width, height = shape["width"], shape["height"]
        else:
            return None
        return f"{width}\u00d7{height}"

    def public(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 3),
            "message": self.message,
            "error": self.error,
            "media": self.media,
            "elapsed": round(self.elapsed()),
            "eta": round(self.eta) if self.eta is not None else None,
            "duration": self.duration,
            "cancellable": self.status in ("pending", "queued", "running"),
            # The gallery id of the finished file, so the page can address it
            # there (poster frame, "Animate this") as well as via /api/result.
            "seed": self.seed,
            "filename": self.result["filename"].rsplit("/", 1)[-1] if self.result else None,
            # Everything that has landed *so far*: four at once fills this one
            # picture at a time while the job runs, and `wanted` against its
            # length is how the page knows more are still coming.
            "filenames": [r["filename"].rsplit("/", 1)[-1] for r in self.results],
            "wanted": self.wanted,
            # Everything the status sheet says about *what* is being made.
            # Spelled out here rather than left for the page to dig out of
            # `extra`, which is a kind-specific bag and not a contract.
            "idea": self.idea,
            "orientation": self.orientation,
            "size": self.size_words(),
            "quality": (self.extra or {}).get("quality"),
            "model": MODEL_WORDS.get(self.kind),
            "step": self.step,
            "steps": self.steps,
            "ahead": self.ahead,
            "estimate": self.estimate,
            "extra": self.extra,
        }

    def update_eta(self) -> None:
        """Project remaining time from the rate so far.

        Held back until the job is properly under way: the first few percent
        include model loading and are not representative, and an ETA that swings
        wildly is worse than none at all. Smoothed so it only ever eases toward
        the new estimate.
        """
        elapsed = self.elapsed()
        if self.progress < 0.05 or elapsed < 8:
            return
        estimate = elapsed * (1 - self.progress) / self.progress
        self.eta = estimate if self.eta is None else self.eta * 0.7 + estimate * 0.3


def _say(job: "Job", key: str, **fmt) -> str:
    """One string in the language of the child who asked for the job.

    Not simply `i18n.t`: the progress messages are written from the websocket
    listener, which runs in a task started at boot, so the language ContextVar
    their request set is not there to read.
    """
    token = i18n.LANG.set(job.lang or i18n.lang())
    try:
        return i18n.t(key, **fmt)
    finally:
        i18n.LANG.reset(token)


def _making(job: "Job", step: int, total: int) -> str:
    """Which of the four is being drawn right now."""
    return _say(job, "Picture {n} of {total}...", n=max(1, step), total=total)


def _step_done(kind: str, done: int, total: int) -> str:
    if kind == "story":
        return i18n.t("Part {done} of {total} filmed...", done=done, total=total)
    return i18n.t("Panel {done} of {total} drawn...", done=done, total=total)


def _item_kind(job: "Job", index: int) -> str:
    """What one of a job's output files should be filed as.

    A comic's panels are pictures, but they belong to the comic rather than to
    the loose-pictures shelf, and the finished page keeps "comic" for itself. A
    story's clips are ordinary videos - the first from words, the rest from the
    frame before - and should count and shelve as exactly that.
    """
    if job.kind == "comic":
        return "panel"
    if job.kind == "story":
        return "t2v" if index == 0 else "i2v"
    return job.kind


def _working_message(job: "Job", fraction: float) -> str:
    """What the bar says right now, in their language.

    Four at once is four runs of one graph, so the useful thing to say is
    which one they are waiting for. Everything else reads the fraction.
    """
    if job.kind == "image" and job.steps > 1:
        return _making(job, job.step, job.steps)
    return _say(job, _working_english(job.kind, fraction))


def _working_english(kind: str, fraction: float) -> str:
    if kind in ("smooth", "slowmo"):
        if fraction < 0.2:
            return "Looking at every frame..."
        if fraction < 0.9:
            return "Drawing all the in-between bits..."
        return "Putting it back together!"
    if kind == "huge":
        if fraction < 0.2:
            return "Getting your picture ready..."
        if fraction < 0.9:
            return "Making it bigger, bit by bit..."
        return "Almost done!"
    if kind in ("edit", "outpaint", "inpaint"):
        if fraction < 0.2:
            return "Looking at your picture..."
        if fraction < 0.9:
            return ("Painting what's outside..." if kind == "outpaint"
                    else "Changing it...")
        return "Nearly there!"
    if kind in music.JOB_KINDS:
        if fraction < 0.2:
            return ("Working out the hum..." if kind == "ambience"
                    else "Working out the tune...")
        if fraction < 0.85:
            return "Playing it... this takes a moment."
        return "Mixing it down!"
    if kind == "comic":
        if fraction < 0.1:
            return "Reading your story..."
        if fraction < 0.9:
            return "Drawing the panels..."
        return "Putting the page together!"
    if kind == "story":
        if fraction < 0.1:
            return "Working out your story..."
        if fraction < 0.9:
            return "Filming it, bit by bit... this takes a while."
        return "Joining it into one film!"
    if kind == "image":
        if fraction < 0.35:
            return "Thinking up your picture..."
        if fraction < 0.8:
            return "Painting it now..."
        return "Almost done!"
    if fraction < 0.15:
        return "Getting the video ready..."
    if fraction < 0.5:
        return "Making your video... this part takes a few minutes."
    if fraction < 0.85:
        return "Adding the details and the sound..."
    return "Nearly there!"


class JobRegistry:
    def __init__(self, client: ComfyClient):
        self.client = client
        self.jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def active(self) -> Job | None:
        """The job currently occupying the machine, if any.

        Only one runs at a time: a second job would just sit in ComfyUI's queue
        behind the first, and two progress bars racing on one GPU is confusing
        rather than useful.
        """
        for job in self.jobs.values():
            if job.status in ("pending", "queued", "running"):
                return job
        return None

    def create(
        self,
        kind: str,
        prompt: str,
        graph,
        duration: int | None = None,
        orientation: str = "landscape",
        styles: dict | None = None,
        idea: str = "",
        extra: dict | None = None,
        seed: int | None = None,
        seeds: list | None = None,
        character: str = "",
        cutout: bool = False,
        who: str = "",
        after=None,
        after_share: float | None = None,
    ) -> Job:
        """Start a job. `graph` is one graph, or a list of them run in order.

        A comic is several different prompts; four at once is the same prompt
        four times with four seeds. Either way it is a list, the bar is divided
        between them, and each file is theirs the moment it lands.

        An entry in that list may instead be an async callable taking the
        outputs so far and returning the next graph. That is what a story is:
        each clip starts from the last frame of the one before, so graph two
        cannot be built until graph one has produced a file.

        `after` is an async callable run once every graph is done, taking
        (job, outputs) and returning anything to merge into `job.extra`. The
        story uses it to join the clips into one film.

        `seeds` is one seed per graph, recorded per file, so "make it again,
        but..." on any of four reproduces that one rather than the first.

        `after_share` is how much of the bar that step is worth, in graphs: 1.0
        for the story's join, which really is a graph's worth of work, and a
        sliver for the outpaint's, which is half a second. Getting it wrong is
        a bar that crawls and then jumps rather than a wrong result. Left
        unsaid it comes from `after_share_for`, keyed on the kind - which is
        what stops a new multi-stage kind inheriting a whole graph's slice and
        halving its bar.
        """
        self._prune()
        graphs = graph if isinstance(graph, list) else [graph]
        job = Job(
            id=uuid.uuid4().hex[:12],
            kind=kind,
            prompt=prompt,
            duration=duration,
            orientation=orientation,
            styles=styles,
            idea=idea or prompt,
            extra=extra or {},
            seed=seed,
            character=character,
            cutout=cutout,
            who=who,
        )
        job.lang = i18n.lang()
        job.seeds = list(seeds or ([] if seed is None else [seed]))
        job.wanted = len(graphs)
        job.steps = len(graphs)
        # What this machine says this takes, asked once and carried, so the
        # status sheet has something honest to show in the first eight seconds
        # - which is exactly as long as `update_eta` deliberately says nothing.
        job.estimate = timings.estimate_for(job)
        self.jobs[job.id] = job
        if after_share is None:
            after_share = after_share_for(kind)
        task = asyncio.create_task(self._run(job, graphs, after, after_share),
                                   name=f"job-{job.id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def _prune(self) -> None:
        cutoff = time.time() - JOB_TTL_SECONDS
        stale = [j.id for j in self.jobs.values() if j.created < cutoff]
        if len(self.jobs) - len(stale) > MAX_JOBS:
            by_age = sorted(self.jobs.values(), key=lambda j: j.created)
            stale += [j.id for j in by_age[: len(self.jobs) - MAX_JOBS]]
        for jid in set(stale):
            self.jobs.pop(jid, None)

    async def _run(self, job: Job, graphs: list, after=None,
                   after_share: float | None = None) -> None:
        """Run each graph in turn, then finish with everything they produced."""
        outputs: list = []
        # File each one as it lands rather than all of them at the end, so a
        # picture they can already see on the page is a real gallery item with
        # its own sidecar. Not for a job with an `after` step: the film's join
        # and the sound effect both rewrite what the sidecar says, and a
        # record written before them would be the wrong one.
        file_as_they_land = len(graphs) > 1 and after is None
        try:
            # The join at the end is real work and gets its own slice of the
            # bar, or the last clip would finish at 100% and then sit there.
            # How big a slice is the caller's to say: see `after_share`.
            share = after_share_for(job.kind) if after_share is None else after_share
            slices = len(graphs) + (max(0.0, share) if after else 0.0)
            for index, entry in enumerate(graphs):
                job.step = index + 1
                if job.kind == "image" and len(graphs) > 1:
                    job.message = _making(job, job.step, len(graphs))
                if callable(entry):
                    # A step that needs the one before it to have finished -
                    # a story clip starting from the last frame of the last.
                    try:
                        graph = await entry(outputs)
                    except Exception as exc:
                        log.exception("job %s could not build step %d", job.id, index + 1)
                        self._fail(job, exc)
                        return
                else:
                    graph = entry
                if job.cancelled:
                    # Stop landed between two graphs - after the last one
                    # finished, before this one was sent. Without this the
                    # runner cheerfully submitted the next panel or clip to a
                    # job the app had already written off as stopped, and that
                    # render had nobody left to interrupt it.
                    self._cancelled(job)
                    return
                got = await self._run_graph(job, graph, index / slices, 1 / slices)
                if got is None:
                    return          # cancelled or failed; the job already says so
                self._name(job, got, len(outputs))
                outputs.extend(got)
                # Visible immediately: `public()` hands these to the page on
                # the very next poll, a second or two after the file exists.
                job.results = list(outputs)
                if file_as_they_land:
                    self._file_from(job, outputs)
                if job.kind != "image" and len(graphs) > 1 and index + 1 < len(graphs):
                    job.message = _step_done(job.kind, index + 1, len(graphs))
            if after is not None:
                job.progress = max(job.progress, len(graphs) / slices)
                job.message = i18n.t("Putting it all together...")
                try:
                    more = await after(job, outputs)
                except Exception as exc:
                    log.exception("job %s failed putting it together", job.id)
                    self._fail(job, exc)
                    return
                if more:
                    job.extra.update(more)
            self._finish(job, outputs)
        except Exception as exc:
            # Nothing may escape this task. An exception out of the runner
            # leaves the job's status on "running" for ever, and `active()`
            # reading that status is the whole of how the app knows it is
            # free - so one bad reply from ComfyUI would wedge it in "busy"
            # until somebody restarted the container. The job dies; the app
            # does not. Already-terminal jobs keep the ending they had: a
            # picture that landed and then tripped over its own sidecar is
            # still a picture they can see.
            log.exception("job %s died unexpectedly", job.id)
            if job.status in ("pending", "queued", "running"):
                self._fail(job, exc)
        finally:
            # Whatever happened - done, failed or cancelled - the card should
            # be empty before anything else wants it. Unless something else
            # already has it: a job stopped a moment ago must not unload the
            # models out from under the one they started right afterwards.
            if free_after_job() and self.active() is None:
                await self.client.free()

    async def _run_graph(self, job: Job, graph: dict, base: float, span: float):
        """One graph start to finish. Returns its outputs, or None if it did not
        get there - in which case the job has already been marked failed or
        cancelled."""
        progress = Progress(graph, base, span)
        finished = asyncio.Event()
        failure: dict = {}

        def on_message(mtype: str, data: dict) -> None:
            if mtype == "execution_cached":
                progress.done.update(str(n) for n in data.get("nodes") or [])
            elif mtype == "executing":
                node = data.get("node")
                if node is None:
                    finished.set()
                else:
                    if progress.current:
                        progress.done.add(progress.current)
                    progress.current = str(node)
                    progress.current_fraction = 0.0
            elif mtype == "progress":
                node = data.get("node")
                if node is not None:
                    progress.current = str(node)
                maximum = data.get("max") or 0
                if maximum:
                    progress.current_fraction = min(1.0, (data.get("value") or 0) / maximum)
            elif mtype == "executed":
                node = data.get("node")
                if node is not None:
                    progress.done.add(str(node))
            elif mtype in ("execution_success",):
                finished.set()
            elif mtype == "execution_error":
                failure["message"] = (
                    f"{data.get('node_type')} (node {data.get('node_id')}): "
                    f"{data.get('exception_message')}"
                )
                finished.set()
            elif mtype == "execution_interrupted":
                # Only ever interrupted because we asked: the interrupt is
                # targeted by prompt_id, so this is a cancellation, not a fault.
                job.cancelled = True
                finished.set()

            if job.status in ("pending", "queued", "running"):
                if job.started is None:
                    job.started = time.time()
                job.ahead = None
                job.status = "running"
                job.progress = max(job.progress, progress.value())
                job.message = _working_message(job, job.progress)
                job.update_eta()

        if job.cancelled:
            self._cancelled(job)
            return None

        try:
            job.prompt_id = await self.client.submit(graph)
        except ComfyError as exc:
            log.error("job %s submit failed: %s", job.id, exc)
            self._fail(job, exc)
            return None

        if job.cancelled:
            # Stop was pressed while this submit was in flight. `cancel` looked
            # for a prompt_id to interrupt, found none, and marked the job
            # stopped - so ComfyUI is now rendering a prompt the app believes
            # does not exist, nothing will ever interrupt it, and the next job
            # queues behind a job nobody can see. The runner owns every prompt
            # it submitted, including one that arrived a moment too late.
            log.info("job %s was stopped mid-submit; interrupting %s",
                     job.id, job.prompt_id)
            await self.client.cancel(job.prompt_id)
            self._cancelled(job)
            return None

        self.client.listen(job.prompt_id, on_message)
        job.status = "queued"
        deadline = time.monotonic() + MAX_JOB_SECONDS

        try:
            while time.monotonic() < deadline:
                try:
                    await asyncio.wait_for(finished.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass

                if job.cancelled:
                    self._cancelled(job)
                    return None

                if failure:
                    self._fail(job, failure["message"])
                    return None

                history = await self.client.history(job.prompt_id)
                if history:
                    outputs = extract_outputs(history)
                    if outputs:
                        return outputs
                    status = (history.get("status") or {})
                    if status.get("status_str") == "error" or (
                        status.get("completed") is False and finished.is_set()
                    ):
                        self._fail(job, f"ComfyUI reported: {status.get('status_str')}")
                        return None

                if job.cancelled:
                    self._cancelled(job)
                    return None

                if finished.is_set():
                    # Socket said done but nothing landed in history. Give the
                    # write a moment, then give up rather than spin forever.
                    await asyncio.sleep(2.0)
                    history = await self.client.history(job.prompt_id)
                    outputs = extract_outputs(history or {})
                    if outputs:
                        return outputs
                    self._fail(job, "job finished but produced no file")
                    return None

                if job.status == "queued":
                    ahead = await self.client.queue_position(job.prompt_id)
                    # Kept on the job rather than only read: the bar says
                    # "something else is going first" and the status sheet says
                    # how many. Asked on a loop that already runs every two
                    # seconds, so nothing polls /queue on their behalf.
                    job.ahead = ahead
                    if ahead:
                        job.message = i18n.t(FRIENDLY_BUSY)
                    else:
                        # Off the queue: start the clock here too, in case the
                        # WebSocket is down and no message ever sets it.
                        if job.started is None:
                            job.started = time.time()
                        job.status = "running"
                        job.message = _working_message(job, job.progress)

            # Giving up on watching it is not the same as it having stopped.
            # Without the interrupt the app goes idle while ComfyUI carries on
            # rendering something nothing is waiting for, and the next job
            # queues behind it.
            await self.client.cancel(job.prompt_id)
            self._fail(job, f"gave up after {MAX_JOB_SECONDS}s")
            return None
        finally:
            if job.prompt_id:
                self.client.unlisten(job.prompt_id)

    def _finish(self, job: Job, outputs: list, timed: bool = True) -> None:
        job.results = list(outputs)
        job.result = outputs[0]
        job.progress = 1.0
        job.status = "done"
        job.eta = 0
        job.ended = time.time()
        if job.started is None:
            job.started = job.created
        if job.cancelled:
            # Stopped after some had already landed. Those are theirs - saying
            # "nothing was made" over pictures they are looking at is untrue.
            job.message = (i18n.t("Stopped! Here's the one you got.")
                           if len(outputs) == 1 else
                           i18n.t("Stopped! Here are the {n} you got.", n=len(outputs)))
        elif job.kind == "comic":
            job.message = i18n.t("Your comic is ready!")
        elif job.kind == "story":
            job.message = i18n.t("Your film is ready!")
        elif job.is_audio:
            # One key per kind rather than a noun dropped into one sentence -
            # the same reason "your video is ready" has its own: every
            # language but English agrees the adjective with what is ready,
            # and "prête" for a hum is not what it is for a song.
            job.message = i18n.t(
                {"jingle": "Your tune is ready!",
                 "ambience": "Your sound is ready!"}.get(job.kind,
                                                         "Your song is ready!"))
        elif job.is_video:
            job.message = i18n.t("Your video is ready!")
        elif len(outputs) > 1:
            job.message = i18n.t("All {n} pictures are ready - pick your favourite!",
                                 n=len(outputs))
        else:
            job.message = i18n.t("Your picture is ready!")
        # A job stopped half way took as long as they let it, which is not how
        # long it takes - timing it would teach the estimate a lie.
        if timed:
            timings.record(job)
        log.info("job %s (%s) done in %.0fs, %d file(s)",
                 job.id, job.kind, job.elapsed(), len(outputs))

        # Record what made each file so the gallery can show it back to them -
        # whatever has not been filed already on its way past.
        self._file_from(job, outputs)

    def _name(self, job: Job, landed: list, first: int) -> None:
        """Rename what ComfyUI just wrote to what the parent's pattern asks.

        Here rather than in `_file` because `_file` waits for the `after` step
        on the jobs that have one, and the film's join and the sound effect
        both go looking for the file **by name**. Here it happens the moment
        the file exists, before anything - the sidecar, the after step, the
        page's next poll - has been told a name at all.

        The dicts are mutated in place, which is what carries the new name into
        `job.results`, `job.result`, `public()["filename"]` and the gallery id
        the page addresses it by, without a second list to keep in step.
        """
        for offset, result in enumerate(landed):
            index = first + offset
            result["filename"] = gallery.rename_new(
                result["filename"], _item_kind(job, index),
                idea=job.idea, who=job.who,
                seed=job.seeds[index] if index < len(job.seeds) else job.seed,
            )
        # `subfolder` and `type` are left on the dict as ComfyUI gave them: a
        # rename that could not happen leaves the file where `/view` can still
        # find it, and that fallback is the only thing they are still for.

    def _file_from(self, job: Job, outputs: list) -> None:
        """File every output that has not been filed yet.

        Called once per graph while a several-picture job runs, and again at
        the end for anything left (a single picture, or a job whose sidecars
        wait on an `after` step). `job.filed` is how far it has got.
        """
        for index in range(job.filed, len(outputs)):
            self._file(job, outputs[index], index)
        job.filed = len(outputs)

    def _file(self, job: Job, result: dict, index: int) -> None:
        """One finished file: its sidecar, and a note to the grown-ups.

        Metadata only: a failure here must never affect the result.
        """
        gallery.record(
            result["filename"],
            prompt=job.prompt,
            idea=job.idea,
            kind=_item_kind(job, index),
            duration=job.duration,
            orientation=job.orientation,
            styles=job.styles or {},
            job_id=job.id,
            # Its *own* seed. Four at once is four runs with four seeds, and
            # "make it again, but..." on the third of them means that one.
            seed=job.seeds[index] if index < len(job.seeds) else job.seed,
            character=job.character,
            cutout=job.cutout,
            who=job.who,
            created=time.time(),
            # What the job recorded about itself that belongs on the file:
            # the sound an after-step put in (which it wrote into the
            # sidecar already, and this write would otherwise lose), the
            # quality it was rendered at, which two pictures a
            # first-and-last clip ran between, the line they asked the
            # character to say - without that one, "make it again but..."
            # came back with an empty speech box - and a song's words,
            # without which opening one showed a description of the sound
            # and not a word of what it actually sang.
            # ... and which of their own things a made-from-one-they-have job
            # was made out of, so the viewer can say where it came from.
            **{k: v for k, v in job.extra.items()
               if k in ("effect", "effect_at", "quality", "first", "last",
                        "said", "lyrics", "singing", "bpm",
                        # Which of "What kind of sound" they chose, so "make
                        # another like this" puts the chip back rather than
                        # opening the card on a song; and how long the file
                        # actually plays for once the silence ACE-Step left
                        # on the end was cut off, which is not the length
                        # they asked for and is the one the viewer should
                        # eventually believe.
                        "sound_kind", "played_seconds",
                        "smooth_of", "huge_of",
                        # Which picture an edit was made from, and how the
                        # outpaint grew it - "make it again, but..." on an
                        # edit reopens the sheet on that same picture.
                        "edit_of", "with_me", "side", "amount",
                        # ...and which picture they turned into a cartoon,
                        # which chip they tapped and what they typed beside
                        # it, so the sheet can be reopened on all three.
                        "restyle_of", "turned_into", "twist")},
        )
        # A copy on the parent's phone, if they asked for one. Fired, not
        # awaited: a push service being slow must not hold up the result.
        notify.fire(notify.made(
            result["filename"].rsplit("/", 1)[-1], _item_kind(job, index),
            job.idea, who=job.who,
        ))

    def _cancelled(self, job: Job) -> None:
        if job.status in ("done", "error", "cancelled"):
            return          # both ends of the run noticed; once is enough
        if job.kind == "image" and job.results:
            # Stop, with some already made. They are finished files in the
            # gallery with their own sidecars, so the job ends as a smaller
            # version of itself rather than throwing away what they have. Only
            # pictures: a comic missing three panels or a film missing the
            # join is not a smaller comic or a shorter film, it is a broken
            # one, and those still stop the way they always did.
            self._finish(job, list(job.results), timed=False)
            return
        job.status = "cancelled"
        job.message = i18n.t(FRIENDLY_CANCELLED)
        job.eta = None
        job.ended = time.time()
        log.info("job %s (%s) cancelled after %.0fs", job.id, job.kind, job.elapsed())

    async def cancel(self, job_id: str) -> bool:
        """Stop pressed.

        The flag goes up first and is never lowered: everything the runner is
        about to do checks it, including the submit it may be in the middle of.
        A prompt that only exists after this point is the runner's to interrupt
        - see `_run_graph` - which is what stops a stop from leaving a render
        on the card that the app has already forgotten about.
        """
        job = self.jobs.get(job_id)
        if job is None or job.status not in ("pending", "queued", "running"):
            return False
        job.cancelled = True
        if job.prompt_id:
            await self.client.cancel(job.prompt_id)
        self._cancelled(job)
        return True

    def _fail(self, job: Job, detail) -> None:
        job.ended = time.time()
        job.eta = None
        job.status = "error"
        job.message = i18n.t(FRIENDLY_FAILURE)
        job.error = FRIENDLY_FAILURE
        log.error("job %s (%s) failed: %s", job.id, job.kind, detail)
