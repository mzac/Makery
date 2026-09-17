# Makery

A kid-friendly web front-end for an existing ComfyUI instance. Built so an
11-year-old can generate images and videos from their iPad without ever seeing
ComfyUI itself.

Runs on the server next to ComfyUI, as its own compose file joined to the
stack's network.

---

## What it does

Two cards on one page:

1. **Make a picture** — text → image (Flux schnell), with optional
   style / place / lighting / mood dropdowns
2. **Make a video** — LTX 2.5, starting from either **words** or **a picture**,
   chosen with a toggle inside the one card; the same dropdowns plus camera,
   music and background-sound ones (LTX renders audio, so those are real)

Plus a **Gallery** card at the top: a gallery of everything they have made.

It was three cards until the video pair was merged: the page was long enough
that the image-to-video section was easy to scroll past and miss.

The connective tissue: when an image finishes, they get a **Save** button and an
**Animate this** button. "Animate this" carries that exact image into the video
card and flips it to picture mode — no saving, re-uploading, or file juggling on
the iPad. They can also **take or choose a photo** on the iPad and animate that.

---

## It used to be called easy-iv-gen

The project is **Makery** now, published at `github.com/mzac/Makery`.
`Makery` in prose, `makery` in identifiers, container and service names,
paths, loggers and file prefixes.

The rename is not purely cosmetic - five things carry the name into data that
already exists, and every one of them still reads the old spelling. None of
them ever *writes* it again.

| Where | New | Old, still read |
|---|---|---|
| Gallery sidecars | `<name>.makery.json` | `<name>.easy-iv-gen.json` - read, moved and deleted with their media file; rewritten under the new name the first time anything touches them. See "The gallery" |
| Frames in ComfyUI's input dir | `makery-*` | `easy-iv-gen-*` - the janitor's sweep matches both, or frames already there would never be swept |
| Backup files | `makery-backup-*.json`, `"app": "makery"` | `easy-iv-gen-backup-*.json`, `"app": "easy-iv-gen"` - still listed, still trimmed, still accepted by restore. `backup.APP_WAS` |
| What the browser remembers | `makery:theme`, `makery:lang`, `makery:tab`, `makery:chat`, `makery:picked` | the same keys under `easy-iv-gen:`, re-keyed once by the pre-paint script at the top of `index.html`, before a line of the app reads any of them |
| ComfyUI's output prefix | `makery/<kind>` | nothing: the host directory has to be re-mounted at `/basedir/output/makery` to match, and `GALLERY_DIR` pointed at it. **A deployment that skips this gets an empty gallery**, because the app reads one directory and ComfyUI writes to another |

One more trap, in the compose file rather than the code: the default state
volume is `makery-state` where it was `easy-iv-gen-state`. An installation that
left `STATE_VOLUME` empty gets a **brand new, empty** named volume on the first
`up` after the rename - every setting, profile, character, timing and backup
still sitting in the old one. Copy it across before the first start:

```bash
docker run --rm -v <project>_easy-iv-gen-state:/old -v <project>_makery-state:/new \
  alpine sh -c 'cp -a /old/. /new/'
```

The `LoadImage`/`LoadVideo` placeholders inside `workflows/*.json` still say
`easy-iv-gen-*.png`. They are inert - `workflows._patch` overwrites every one
of them with the real uploaded reference before a graph is ever submitted -
and they were left alone to keep the hand-edit of those files down to the one
`filename_prefix` string each.

---

## Non-goals

- No model pickers, step counts, seeds, CFG, or any other advanced control.
  Shape, length and the style dropdowns are the only knobs.
- No auth. LAN-only.

**"No history or gallery" was a non-goal and is no longer one.** The files were
already being kept on disk, so refusing to show them just meant they could not
get at their own work. See the Gallery section below.

---

## Decisions already made

| Topic | Decision |
|---|---|
| ComfyUI address | `COMFY_URL`, a container name on the shared Docker network |
| Auth | None |
| Persistence | Files stay on disk and show in the gallery; a reload reattaches to a running job. The in-memory job list itself is not persisted. |
| Controls exposed | Prompt box, video length, shape, and the dropdowns on both cards. No model pickers, steps, seeds or CFG. |
| Video length | A slider with a large readout, **5-15s by default and set on the parent page** (`VIDEO_*_SECONDS` seeds it on the first start). The right ceiling is a property of the card, not of this app - 15s at 0.9MP peaks near 15.5GB of 16.3GB here. The page takes its bounds from `/api/styles` rather than carrying them as HTML literals |
| Song length | The same, 10-120s by default (`MUSIC_*_SECONDS` seeds it). Cheap by comparison: ACE-Step turbo is about 1.1s of wall clock per second of audio, so the limit is patience rather than memory |
| Video quality | Quick 0.5MP / Normal 0.9MP / Sharper 1.3MP on the ResolutionSelector. Sharper caps the length at 10s, page and server both: 10s at 1.3MP peaks at 15577 MiB, the same ceiling 15s at 0.9MP hits. The i2v crop follows the quality via `workflows.size_for()` |
| Size in the viewer | Width x height on the facts line. Read off the file once and written into the sidecar, so it costs one header read per file ever |
| Shape | Landscape 16:9 (1280×704), portrait 3:4 (832×1088) or square 1:1 (960×960), for both pictures and video. Uploaded photos set it themselves. |
| Movies | Multi-select videos → "Join into a movie": re-encoded into one h264/AAC file, opening on a title card the page draws. Mixed shapes are letterboxed to the first clip |
| Open hours | A weekly timetable: seven rows on the parent page (`OPEN_HOURS` seeds it). Outside it they see a sign saying *when* it opens again, and get thirty minutes' warning before it shuts. The pause switch still wins; "let them in anyway" waives today's hours and expires at midnight |
| Profiles | Several children, one installation. Each has a face, an age, their own gallery and their own copy of every rule. With one profile there is no sign-in screen at all. Adding one needs the parent PIN, because a new profile is otherwise the way round a daily limit |
| Family shelf | A child can put one of *their own* things where every profile can see it - a **Family** shelf in each one's Gallery, without the parent switch that shares everything. They can see it and save it; they cannot star, rename, trash, build on or unshare somebody else's. Like the picker, it does not exist at all with one profile |
| Warm-up | Three sums before the factory opens, once a calendar day, at a level and in the kinds a parent picks per child. **Off unless a parent turns it on** - it is a house rule, not a safety one. The parent page can also wave them through for the day, or ask them to do it again |
| Ask the bot | Telegram only, off by default. `/today`, `/more 5`, `/pause`, `/open`, `/hours`, `/last`, plus questions in plain words answered by Ollama from today's numbers. Read-only: every change is a slash command |
| Model instructions | All twenty-one listed on the parent page, with what each one decides, where it lives, and whether it carries safety rules. Overrides go in `.prompt-overrides.json` beside the media; editing is off until a switch on that tab turns it on |
| Parent page | `/parent`: today's counts and thumbnails, a one-line status, which model does which job, save-it-all zips, a space breakdown with a tidy-up, the pause switch, daily picture and video limits with one-tap top-ups, the emails, the trash, the uploads the screen refused (with Allow), and the activity log. The PIN that gates it is a card on Settings, as are the two addresses, the clock and the log level; the three credentials sit beside the settings they belong with, on Alerts |
| Live stats | GPU %, VRAM and CPU % ride along with every job poll (NVML, so the service has `gpus: all`) |
| What's happening | The now-bar is a **button**. It opens a sheet saying what is being made and in whose words, how big / how long / how good / which of how many, what is drawing it, the step in words, the percent, elapsed and two kinds of ETA, a live GPU/VRAM/CPU strip on its own two-second clock, ComfyUI's queue when something else is in front, Stop, and a way to the card. `GET /api/now` is the strip's route, and it touches nothing off the box |
| Comics | A third card: a story in 3, 4 or 6 panels. Ollama writes the panels, ComfyUI draws them, the *page* lays out the finished sheet |
| Four at once | The picture card can make four of one idea to choose between, **one after another, each shown the moment it lands**. Four runs of the graph (about 35s) rather than one batched run (20s): a batch has nothing to show until the end, and watching them arrive is worth the extra fifteen seconds - their call. "Keep this one" bins the others *to the trash* and stops any not yet drawn, and the kept one then gets a single picture's buttons |
| Sound at creation | A sound-effect dropdown on the video card, applied by the job's `after` step and written *over* the rendered file (one video with a boing in it, not a video and a copy). "At the start / middle / end", since a number of seconds means nothing before the video exists |
| Sums count | `QUIZ_QUESTIONS` is the default; the parent page can set 1-10 (`quiz_questions`, 0 = default). The overlay's wording follows it |
| How hard the sums are | Three levels on the parent page, per child - **Easy** (single digits, adding to 20, tables to 5), **Medium** (what it always asked, and still the default) and **Harder** (two- and three-digit, tables to 12, some two-step). Plus four ticks for adding / taking away / times / sharing out, at least one of them on. `quiz_level` and `quiz_ops`, seeded once from `QUIZ_LEVEL` and `QUIZ_OPS` |
| Two pictures | `video_ltx2_5_flf2v-api.json`: they pick where the clip starts and where it ends, and LTX fills the middle. Both ends are `LTXVAddGuide` at 0.7 strength, and it shows - measured, the first frame is 2.6 away from the first input and 52.3 from the last, the last frame 5.2 from the last input and 55.0 from the first. A *video* in the first slot means its last frame and in the last slot its first, so two of their clips can be bridged |
| Films | The video card's fourth mode: 2-4 clips where each one starts from the *last frame* of the one before, joined into a single film. Ollama writes the beats; the job registry builds each graph only once the previous clip exists |
| Music | ACE-Step 1.5 XL turbo, 10-90s. Two boxes - what it sounds like and what is sung - plus a singing/instrumental toggle. "Help me write it" writes both halves at once. Its own daily limit; the tab hides itself if ComfyUI has no ACE-Step model |
| What kind of sound | Three chips at the top of the Music card - **a song**, **a little tune** (short, instrumental, 8-20s) and **a background hum** (long, no beat, 15-60s). One model, one graph, one daily allowance; what differs is the tag line, the length and whether anything is sung. `jingle` and `ambience` are their own sidecar kinds with their own badges. A **sound effect** chip was measured and left out, and so was anything made of noise - see "What else ACE-Step can make" |
| Silence on the end | ACE-Step is given a length and writes something shorter, then leaves the rest silent - measured over fourteen renders, a median of 3.0s and as much as 6.2. `gallery.trim_tail` cuts it off the two instrumental kinds after the render, keeping a 0.35s breath, and only when the tail really is silent. A song is left exactly as rendered |
| Who sings | A second vocal dropdown: one singer (the default), two taking turns, a group joining in on the chorus, everyone together, or call and answer. It writes the arrangement into the tags *and* tells the lyric helper to lay the words out for it - alternating verses, a chorus marked as sung together, paired call-and-answer lines. Words they typed themselves are never restructured |
| Modules | Picture, Video, Comic, Music, Chat and the Story maker are each a switch on the parent page, per child. Off takes the tab away *and* makes its routes refuse; everything already made stays in their gallery |
| Story maker | A sixth tab that makes nothing of its own: one idea walked through **the idea → the opening picture → the film → the song → put it together**, each step one of the other cards' routes, each result on the screen before the next step starts. No allowance of its own - every step spends what that step would spend on its own card. The last step lays the song under the film as a lossless remux and lands as `kind: "storyfilm"` on the Films shelf |
| Seven languages | The whole child-facing page is English, French, German, Spanish, Italian, Dutch or Portuguese, switched by a row of chips in their own Settings tab. **A cookie, not a profile setting, and nothing on the parent page**: whoever is at the screen decides, two sisters on one iPad can read different ones, and neither of them has to find a grown-up. `UI_LANG` is only what a browser that has never chosen opens in. The helpers follow the switch; what the picture and video models are sent stays English. **Seven is the number `safety.py` can check** - that is what decides how many there are. The parent page stays English |
| Chat | A fifth tab. `gemma4:12b` through Ollama by default, non-streamed so the whole reply is filtered before they see any of it. Every turn is written to `.chat.json` and shown on the parent page |
| Which model does which job | Three dropdowns on the parent page (Settings → The helpers), fed from Ollama's own `/api/tags`: the idea helper, the Chat tab and the Telegram answers. `script_model`, `chat_model` and `telegram_model`, seeded once from `SCRIPT_MODEL` / `CHAT_MODEL` / `TELEGRAM_MODEL`. **The app never pulls a model** - it offers what is already there, says how big each one is and whether it can see a picture, and has a Test button that asks one short question and reports tokens/sec. A choice Ollama no longer has falls back to the seed at the next start, with a warning |
| Seeds | Recorded in the sidecar, so "Make it again, but…" reproduces a picture exactly and changes only the words they edit. "Make another like this" deliberately re-rolls |
| Stickers | Any picture → background flood-filled away → a cropped PNG with alpha, on its own shelf. Refused, with a reason, when the picture has no plain background |
| A picture, or a character | A two-way picker on the picture card. "A character" draws the same idea alone on a plain background, which is what makes the sticker cut-out reliable instead of a gamble - and gives the vision model nothing but the character to describe when saving one |
| Sound effects | Twelve of them, **synthesised in numpy**, mixed into a video at a moment they pick. No sample files to license, download or ship |
| Frame grab | Scrub a video and keep any frame as a picture. The preview under the slider is fetched from the server, so what they see is the frame they get |
| Smooth / slow | RIFE puts a frame between every frame of one of their clips. Played at double the rate it is the same length and silkier; played at the original rate it is half speed. Slow motion comes out **silent**, on purpose. A render, so it queues and shows a bar - but not one of the videos their daily limit counts |
| Moving stickers | Up to two seconds of any video as a looping animated WebP, 320px, 12fps, on the Stickers shelf. PyAV and Pillow, no GPU at all |
| Make it huge | One ESRGAN pass over a picture: 1280x704 comes back 5120x2816 in six seconds. The picture they already have with the edges worked out, not a new picture that resembles it |
| Compare | Choose exactly two pictures → a wipe slider between them, with a star button under each. For picking one of the four-at-once |
| Change this picture | Any picture of theirs, plus a sentence: "make it night-time", "give the fox a scarf". Flux 2 Klein 9B with their own picture as the reference, so it is the same picture changed rather than a new one that matches the words. **This one costs a picture** from the daily limit, unlike smooth and huge - a model invents the whole thing |
| What's outside the frame? | The same model, a bigger canvas, and their picture carried through the sampler untouched. A side or all round, a bit (+25%) or a lot (+50%). The words box is optional: the picture is the instruction |
| Fix just this bit | The drawing pad in mask mode - one thick brush, a see-through pink overlay - plus a words box. Only what they painted over changes |
| ...and put me in it | A second reference picture on the edit graph: their own saved face. The box only appears once a face has actually been saved, and no profile on the machine this was built on had one, so it is untested against a real face |
| Turn it into... | Any picture of theirs and a row of chips - a cartoon, a painting, a pencil drawing, a comic, a clay model, toy bricks, stained glass, make it real - and it comes back drawn that way with everything still where it was. **A drawing off the drawing pad is what it is really for.** The same Klein edit graph; the eight sentences are in `app/restyles.py`. Costs a picture, like the three edits |
| Characters | Save somebody from a picture, then rename them, reword how they look, see everything they are in, or say goodbye. The look sentence is repeated into every prompt they appear in, which is the whole mechanism. Their cast is a **shelf of faces at the top of the Gallery**; a tap opens that character's own page, which is where all four of those live |
| Mix up an old one | One of their own past ideas with a fresh random draw of every dropdown. Instant from their history; falls through to the Surprise inventor before they have one |
| Things I've asked for before | Their own words per kind, newest first, deduped, 30 deep. Each has an ✕ that forgets just that one - no confirmation, because the worst case is retyping a sentence |
| Concurrency | One job at a time, enforced in the backend (409), not just the UI |
| Cancel | Yes - `/queue` delete plus a prompt_id-targeted `/interrupt` |
| Idea helper | Local Ollama expands a one-line idea into a full prompt with a spoken line. Given a picture, the same model *looks at it* and writes a prompt that animates what is actually there |
| Surprise me | Ollama invents an idea from a random seed theme, plus a random draw of every dropdown, with confetti |
| VRAM | Both ComfyUI (`/free`) and Ollama (`keep_alive: 0`) release the card the moment they finish. Neither model set fits alongside the other on 16GB |
| Image aspect | **1280×704** landscape or **832×1088** portrait, changed from the workflow's 1024×1024 — see below |
| Safety | Input-side blocklist is the real filter; negative prompts are secondary — see below |
| Gallery | Reads ComfyUI's output directory directly, with per-file sidecar metadata for the prompts. Favourites (a star in the sidecar) get their own shelf |
| Gallery | The page itself, not a card in front of a sheet. Two views they switch between and the page remembers: **In groups** (a sideways shelf per kind) and **Everything** (one grid, newest first, ordered four ways, every tile carrying its kind). Search, the tag chips, choosing several and the trash are all on it |
| Deleting | Moves to `.trash/`; a janitor empties it after `trash_days` (7, on the parent page). "Delete for good" is a second, armed step from inside the trash |
| Binning it where they made it | A 🗑️ Delete last in the row under any finished result, and on the "it's ready" line for the things they start from their gallery, which have no card. Same arming, same trash, same undo - and the day's allowance does not move, because `usage_today` counts the trash on purpose |
| Uploads | Kept in the gallery, whole and uncropped, on a "Photos & drawings" shelf; cropped to the chosen shape only when they become a video. Screened by the vision model with a deliberately short list of things to say no to. Fails *open* if Ollama is unreachable - it is their own camera roll on a LAN app |
| Dialogue | A "What should they say?" box; the line is safety-checked and appended as `The main character says "…"` |
| Output cleanup | Deferred. The ComfyUI Dockerfile will be modified later to handle its own output dir. For now everything lands in ComfyUI's output under a `makery/` prefix. |
| Settings | One `state.db` in `STATE_DIR`, keyed by (scope, key), with the parent page as the only place any of it is changed. `.env` is **seven** variables compose has to read before there is an app, **nine** the parent page can also set (app/config.py: the page wins, `.env` is the fallback, nothing is copied), plus a set of first-run defaults it seeds once and never reads again - see "Where settings live" |
| Backup | One JSON file with every setting, profile, face, character, override and timing in it - not the gallery, which is the gigabytes. Downloaded from the parent page, restored with an armed two-tap, and written once a night to `STATE_DIR/backups/` keeping the last few (`backup_keep`, seven by default) |
| The log | Everything the app does, in an **append-only table in `state.db`** with a hash chain over it, on a **Log** tab of its own. No route deletes or shortens it; "check the chain" says *intact* or names where it breaks. `AUDIT_KEEP_DAYS` is 0 - for ever - and a trim writes its own entry saying it ran |
| How files are named | A template per kind on the parent page - `{date} {time} {kind} {who} {n} {idea} {seed}` - applied by **renaming the file the moment it lands**, not by touching the graphs' `filename_prefix`. `{n}` is a counter in `state.db` that only ever goes up, where ComfyUI's renumbers by scanning the folder and hands a name back after a delete. The defaults reproduce what it writes today. **Nothing already on disk is renamed**, and the page says so |
| Host port | `HOST_PORT` (8095 by default), published for direct access and debugging |
| Hostname | Behind whatever proxy the host already runs. **https matters**: `getUserMedia` needs a secure context, so the voice recorder does not exist over plain http |

---

## Two findings that shaped the design

### 1. The negative prompts do nothing at current settings

Every workflow here runs at **CFG 1.0**:

- `flux_schnell-api.json` — KSampler node `31` has `cfg: 1`, 4 steps (schnell)
- both LTX workflows — `LTXVDualCFGGuider` has `video_cfg: 1, audio_cfg: 1`
- the four Flux 2 Klein edit graphs — `CFGGuider` has `cfg: 1`, which is the
  official template's own setting. Those four carry **no negative prompt at
  all**, deliberately: see their node map for why writing one out there would
  cost an 8B text-encoder pass to achieve nothing

At CFG 1.0 the negative conditioning is mathematically ignored — the guidance
term that would subtract it is multiplied by zero. A negative prompt there has
**literally no effect on the output.**

So the actual safety mechanism is **[app/safety.py](app/safety.py) →
`check_prompt()`**, which rejects the prompt in the backend before it is ever
submitted to ComfyUI, and shows them a friendly "let's pick something else"
message. It covers sexual content, sexualized minors, gore and violence,
weapons, drugs, hate symbols, deepfakes, and horror imagery, with l33t-speak
and punctuation-splitting normalization to catch simple evasion.

The negative prompts (`NEGATIVE_IMAGE`, `NEGATIVE_VIDEO`) are still written out
in full and injected into every job, so they start working the moment anyone
raises CFG. **Do not treat them as protection while CFG is 1.0.**

If real negative-prompt filtering is ever wanted: Flux would need `flux1-dev`
with a real CFG and more steps (much slower), and the LTX guiders would need
`video_cfg` raised.

### 1b. What size a video really comes out at

The ResolutionSelector's own arithmetic (`comfy_extras/nodes_resolution.py`)
is `megapixels x 1024 x 1024` - not a million - spread over the aspect ratio,
each side rounded to the nearest multiple of 32. **Then the LTX pipeline takes
each side down to a multiple of 64**: the selector says 1280x736 at 0.9MP
landscape and the file is 1280x704; it says 1568x864 at 1.3MP and the file is
1536x832. `workflows.size_for()` does both steps and is checked against four
real renders. The i2v crop has to land on exactly that or LTX resamples the
frame they chose - verified at quick/portrait: frame in 640x832, video out
640x832.

### 2. Square images into 16:9 video workflows

The Flux workflow shipped at 1024×1024. Both LTX workflows have their
`ResolutionSelector` locked to **16:9 at 0.9 megapixels, sides a multiple of
32**. A square image handed to the image-to-video step would get cropped or
stretched.

That selector resolves to exactly **1280×704**: `sqrt(0.9MP × 9/16) = 711.5`
rounds to `704`, and `704 × 16/9 = 1252` rounds up to `1280`. Confirmed against
a real render — an i2v job produced a 1280×704 h264 file.

Images are therefore generated at **1280×704**, the same size the video stage
works at, so the "Animate this" handoff is pixel-exact with nothing to crop or
stretch. Portrait works the same way: the selector's `3:4 (Portrait Standard)`
gives **832×1088** by the same arithmetic, confirmed by a real portrait i2v
render. Both pairs live in `ORIENTATIONS` in [app/workflows.py](app/workflows.py),
which is the single source of truth - the image workflow has no
ResolutionSelector, so its width/height are set from that table by hand and must
stay in step with it.

An earlier note in this file said 1216×704. That is `38 × 32` and an aspect of
1.727 against the video's 1.818, so it would have been quietly resampled at the
i2v step. `IMAGE_WIDTH` / `IMAGE_HEIGHT` in [app/workflows.py](app/workflows.py)
are the single source of truth.


---

## Where settings live

**One database, one place to change anything.** `state.db` in `STATE_DIR`, in
WAL mode, with a `settings` table keyed by `(scope, key)` - scope `""` for the
household and a profile id for a child - and the value stored as JSON text so a
number stays a number and a list stays a list. `app/store.py` owns it; nothing
else opens it.

Everything above it is unchanged. `gallery.get_settings(who)`,
`update_settings(who, **changes)`, `flag()`, `public_settings()`,
`PRIVATE_SETTINGS` and the `PER_CHILD` split have the same signatures and the
same meanings they had when this was two JSON files; only what is underneath
them moved. The adopter-is-household rule is the same too: the profile that
`adopts` writes the `""` scope, so a one-child installation has exactly one set
of rows and the Telegram bot - which runs with nobody signed in - reads the
numbers the parent page just saved.

### Why, and what it fixed

Two problems, and they were the same problem twice.

- **Two writers, no lock.** A route, the janitor and the Telegram bot all write
  settings, from different threads, and a JSON file was read-modify-written
  whole. Two of those landing together lost one of them silently. Writes now
  take `BEGIN IMMEDIATE` under a process-wide lock, and a save that spans the
  household and a child is one transaction rather than two files.
- **Half the controls were not settings at all.** A parent who wanted to change
  how long a video could be edited `.env` and rebuilt a container; one who
  wanted to change the daily limit used the parent page. Same kind of decision,
  two places, and no way to tell from either which one was in force.

The second one had produced a **tri-state** running through the whole file:
`-1` in a switch (or `"-"`, or `""`) meant "whatever the environment says". One
value in two places with a third value to say which of them counted, and the
honest answer to "is the nightly email on?" was "open the compose file and
see". It is gone. A switch is `0` or `1` and means it.

`schedule_on` keeps its `-1` and is the only one left, because it is not an
environment indirection: `-1` there means *on if there is a timetable at all*,
since setting seven rows of times and then having to tick a box to make them
apply is a trap.

### `.env` seeds, the parent page owns

Every behavioural variable in `.env` is read **once**, on the first start
against an empty database, to fill its row in. After that the row is the
answer and the variable is never looked at again. `gallery.SEEDED_FROM_ENV` is
that list, and `seed_settings()` is the one moment it is used; `.env.example`
carries the same list under a *FIRST-RUN DEFAULTS* heading that says the rule
once.

**What only `.env` can answer is seven variables.** `GALLERY_DIR`,
`STATE_VOLUME`, `COMFY_INPUT_DIR_HOST`, `RUN_AS`, `NETWORK_NAME`, `HOST_PORT`
and `CONTAINER_NAME`. Compose reads every one of them to build the container -
the paths it mounts, the uid it runs as, the network it joins, the port it
publishes and what to call it - and at that moment there is no app to ask, no
`state.db` to read and nowhere else they could come from. `DEPLOYMENT` in
`app/main.py` is the three paths' half of that list, named in one line each at
startup if unset.

It was thirty-six. The first pass moved everything *behavioural* and left the
addresses on the argument that a mail relay or a chat id belongs to the house
rather than to the app - which is true and was not the question. **An address
is exactly the kind of thing a parent changes**, and "edit a file and rebuild a
container" was the same mistake the daily limit used to make. So the relay, the
recipients, the sender, the subject lines, the allowlist, the two timeouts, the
attachment cap, the keep-alives and the helper's name all became rows.

### The other nine: `app/config.py`, which overrides rather than seeds

The third pass took the rest - `COMFY_URL`, `OLLAMA_URL`, `TZ`, `LOG_LEVEL`,
`PARENT_PIN`, `DIGEST_SMTP_PASS`, `DIGEST_URL`, `NOTIFY_URLS` and
`TELEGRAM_BOT_TOKEN`. They
are on the parent page too, and they are deliberately **not** rows in
`DEFAULT_SETTINGS` and **not** in `SEEDED_FROM_ENV`, because the seed model is
the wrong one for them twice over:

- **Seeding copies a credential into the database on the first start**, whether
  anybody asked for it or not - and every row in that table goes into the
  backup file.
- **An upgrade has to change nothing.** A value that is only in `.env` must
  keep working exactly as it did, for ever, with no first-start moment where it
  is copied somewhere else and the file quietly stops mattering.

So `config.value(key)` is three states and no sentinel: a row in **its own
scope** (`config.SCOPE`, `"deploy"`) wins; otherwise `.env`; otherwise a
built-in default. Clear deletes the row, which puts `.env` back. There is no
"stored as empty" - that would be the tri-state this file spent a whole round
getting rid of, in a new coat.

**The separate scope is the load-bearing part.** It is what keeps these out of
`get_settings()`, out of `public_settings()`, out of every route that answers
with the settings whole, and out of `backup.build()`, which exports the
settings table scope by scope. `backup.SKIP_SCOPES` is that one constant, and
both halves of the backup read it: `build()` leaves the scope out of the file,
and `apply()` reads the live values *before* `store.replace_all` wipes the
table and writes them back in the same transaction - so restoring last week's
backup does not take the relay password off a working installation, and a
hand-edited backup cannot set a PIN on somebody else's.

**One logging filter covers all five credentials**, `config.HideSecrets`,
installed on the **root handlers** by `main` at import. It reads a tuple that
is rebuilt at startup and after every change - not the database, because it
runs on every record in the process including httpx's request lines, and a
SQLite call per log line is not a thing to do. It redacts the value in force
*and* the one in `.env`, since replacing a credential from the page does not
make the old one fit to print. It replaced `telegram._HideToken`, which did
this for the bot token alone.

Two rules the routes hold rather than the module:

- **`parent_pin` is refused by `PUT`/`DELETE /api/parent/config`** outright.
  It is the lock on the page those routes are on, so it has
  `POST /api/parent/pin`, which needs the current PIN typed in again (not
  taken from the header the browser already holds), refuses an empty or
  three-character new one, and **has no Clear at all**. Turning the lock off
  from behind it is how a page like this is left open by accident; removing
  the stored PIN takes a shell on the host, and the README says how.
- **Three boxes take the PIN, and each keeps its own five tries and refuses on
  its own count.** See `app/pinbox.py`, which is all three and nothing else:
  the grown-up box on the sums (`pinbox.SHARED`, on the child's own page), the
  parent page's header gate (`pinbox.GATE`, shared by `_parent()` and
  `_grownup()` because it is the same credential presented the same way), and
  changing the PIN (`pinbox.PIN_CHANGE`). Same five tries, same ten minutes
  each, and `main._refuse_if_locked()` runs *before* the comparison so a
  locked box answers nothing, right or wrong. A wrong guess still goes through
  `_bad_pin(box)` into the log and the alert, like every other one - and that
  is the only place a guess is counted, so passing the wrong box there would
  quietly undo the separation. Nothing anywhere lifts
  `safety.check_prompt`.

**Why that is a module and not a pile of lists in `main.py`** is the same
mistake three times, and it is worth writing down because none of the three is
obvious from the code it was in.

*First*: a shared counter cannot throttle a box inside the parent page.
Reaching one of those routes means passing `_parent()`, which cleared the
shared list on a good header - and a browser with the PIN in its sessionStorage
sends a good header without anybody typing anything. The count was wiped before
every guess. That is why the two inner boxes stopped sharing.

*Second, and worse*: clearing on a correct **header** was wrong in general, not
just for those two. The list being cleared was the *shared* one, whose box is
the grown-up box on the sums - on the child's device. The parent page polls
every thirty seconds, so a parent's tab left open on a laptop was handing back
a child's guesses five at a time, all day, and neither of them could have known.
`main._forgive()` is the fix and it keeps the intent rather than dropping it: a
PIN somebody **typed** still forgives the misses, because a parent who fumbles
their own PIN four times and then gets it right should not be locked out for
ten minutes. The page marks those requests with `X-Parent-Pin-Typed` for the
burst that follows the gate box, and nothing else ever sends it. `_grownup()`
no longer forgives at all - it is only ever reached by a stored header, so
there is nobody there to forgive on behalf of. This is not a defence against
devtools: anybody who can set that header by hand can already read the PIN out
of the same tab's sessionStorage. It stops the app undoing its own lockout
while nobody is looking, which is what was actually happening.

It forgives **two** boxes, not four: the gate, which is what was typed into,
and the sums overlay, because a grown-up standing at the parent page is the
person that box exists to let through. The PIN-change and grown-up-mode boxes
forgive only on their own typed PINs - each of those is a second deliberate
act, and signing in should not hand back tries at the two things inside the
page worth guessing at.

*Third, and it only appeared once the second was fixed*: sharing the
**refusal** lets one box lock another. `_parent()` refused on the sums box's
count, which was harmless while that count was being wiped every thirty
seconds and is not harmless now. Five wrong guesses at a box on the child's own
screen would have shut a parent out of the parent page for ten minutes - and
out of the typed PIN that is the way back in. A child could have done it on
purpose. `pinbox.GATE` is the gate's own counter, and the cost of separating
the four is that a guesser working through all of them gets twenty tries in ten
minutes rather than five. Twenty is still nothing against a four-digit PIN,
every one of the twenty is logged and alerted on, and what it buys is that no
box can be used to disable another.

*Fourth*: `app/telegram.py` offers `/unlock` to a parent locked out by somebody
else's guessing, and says it clears "any wrong-PIN lockout". It cannot import
`main` - `main` imports it - so while these lived in `main` that sentence could
only ever be true of the one `quiz` held. `pinbox.clear_all()` clears all four
and returns the names of the ones that actually had guesses waiting, and
`/unlock` repeats that back: either "I also cleared the wrong-PIN lockout on X
and Y" or "There was no wrong-PIN lockout to clear". Being told a thing is
fixed when it is not is worse than not being offered the fix.

**What is live and what needs a restart**, said once here and on the page:

| | Live? |
|---|---|
| `NOTIFY_URLS` | live - `notify.targets()` re-parses when the string moves |
| `TELEGRAM_BOT_TOKEN` | live - `run()` asks `token()` inside the loop now, so a bot starts listening within half a minute rather than at the next restart |
| `DIGEST_SMTP_PASS` | live - `digest.smtp_pass()` is read as the URL is built |
| `DIGEST_URL` | live - `digest.direct_url()` is read as the URL is built |
| `PARENT_PIN` | live - asked per request |
| `LOG_LEVEL` | live - the root logger's level is set on save |
| `OLLAMA_URL` | live - `ollama_url()` in `chat`, `scripts` and `telegram`, read at the call |
| `COMFY_URL` | **restart** - `ComfyClient` holds one WebSocket open for progress and cannot be re-pointed under it |
| `TZ` | **restart** - applied once by `config.apply_timezone()` before anything asks what day it is |

`TZ` is the one that could have gone either way, and the reason it did not is
worth keeping. Every "today" here is `time.localtime()` - the daily limits, the
sums, `digest_last_sent`, the `{date}` in a filename - so moving it while the
app runs means `time.tzset()`, which is process-global, not thread-safe, and
would shift the day boundary under a day that is already half over: the
allowance would reset, or freeze, mid-afternoon. Applying it once at startup
gives the process one answer to "what time is it here" instead of two, and a
restart is the honest way to move a clock.

Verified on a sandbox container: with a password in `.env` and another set from
the page, the page's is the one `digest.mail_url()` builds with, and **neither
string appears anywhere in `/api/parent/summary`, in a downloaded backup, in
the exported activity log, or in the container log** - 0 matches each, with a
deliberately planted log line coming out as `<secret>`. A restore of that
backup left all five credentials in place. The PIN box refused an empty and a
three-character value, refused a wrong current PIN, and locked after five
tries; while locked, the right PIN opens nothing. The same was verified for the
PIN-change box: six wrong PINs, the sixth a 429, and the right PIN refused
while the lockout stood.

**`DIGEST_URL` was an ordinary settings row until it was not**, and it is the
one that says why the scope matters. The "Apprise URL, used as it is" box is
documented everywhere - here, the README, `.env.example`, the placeholder on
the page itself - as `mailtos://user:apppassword@gmail.com`. A parent who used
it as documented put a mail app password into `DEFAULT_SETTINGS`, and therefore
into every backup file they had emailed themselves since. It is a `config`
field now, secret like the relay password, and `config.migrate_from_settings()`
runs from `apply_startup()` on every boot: if the old row is still there its
value is moved into `config.SCOPE` - unless the page has already set one, in
which case the page's wins - and **the old row is deleted either way**, because
leaving it would leave the credential exactly where the problem was. A backup
made before this still restores; `apply()` drops any `digest_url` it carries,
because incoming rows are filtered against `DEFAULT_SETTINGS` and it is no
longer in there.

Its neighbour is `NOTIFY_URLS`, which is also Apprise URLs, and the page now
says in both places which is which: `DIGEST_URL` sends the nightly email,
`NOTIFY_URLS` sends alerts to a phone, and neither does the other's job.

`KID_NAME` and `KID_AGE` are **not** deployment and are in the first-run half
now. They make the *first profile* and nothing else; after that the profile is
the answer. `branding.household()` reads the profile that `adopts` - the same
one that owns the `""` settings scope - so `branding.KID_NAME`, `AGE`, `WHO`
and `TITLE` follow a rename on the parent page. Before this they were frozen at
import against `.env`, and renaming a child left tonight's email subject saying
the old name.

What moved, and where its control is now:

| Was in `.env` | Is now | On the parent page |
|---|---|---|
| `ENABLE_PICTURE` … `ENABLE_CHAT`, `ENABLE_STORY` | `module_*` | Rules → What they can make |
| `OPEN_HOURS` | `schedule` | Rules → When it is open |
| `DAILY_QUIZ`, `QUIZ_QUESTIONS` | `quiz_enabled`, `quiz_questions` | Rules → Sums first |
| `QUIZ_LEVEL`, `QUIZ_OPS` | `quiz_level`, `quiz_ops` | Rules → Sums first |
| `QUIZ_BYPASS_MINUTES` | `quiz_bypass_minutes` | Rules → Sums first |
| `CLOSE_ON_REFUSAL` | `close_on` | Rules → If the filter says no |
| `SCREEN_UPLOADS` | `screen_uploads` | Rules → If the filter says no |
| `CHAT_STRICT`, `MUSIC_STRICT` | `chat_strict`, `music_strict` | Rules → If the filter says no |
| `VIDEO_*_SECONDS`, `MUSIC_*_SECONDS` | `video_*_seconds`, `music_*_seconds` | Settings → How long things can be |
| `UI_LANG`, `KID_PRONOUN` | `ui_lang`, `kid_pronoun` | Settings → Words and wording |
| `APP_TITLE` | `app_title` | Settings → Words and wording |
| `DIGEST_ENABLED`, `DIGEST_AT`, `DIGEST_LIMIT_NOTICE` | same names | Alerts → Daily email |
| `DIGEST_MAX_ITEMS` | `digest_max_items` | Alerts → Daily email |
| `DIGEST_TO`, `DIGEST_SMTP_{HOST,PORT,STARTTLS,USER}`, `DIGEST_FROM`, `DIGEST_FROM_NAME`, `DIGEST_SUBJECT`, `DIGEST_LIMIT_SUBJECT` | `digest_to` … `digest_limit_subject` | Alerts → Daily email → **Email server** |
| `DIGEST_URL` | `config.SCOPE`, not a settings row - see below | Alerts → Daily email → **Or one Apprise URL** |
| `NOTIFY_ON_*`, `NOTIFY_ATTACH` | `notify_*` | Alerts → Messages to your phone |
| `NOTIFY_MAX_MB` | `notify_max_mb` | Alerts → Messages to your phone |
| `TELEGRAM_ASK` | `telegram_ask` | Alerts → Asking the bot things |
| `TELEGRAM_CHAT_IDS`, `TELEGRAM_TIMEOUT` | `telegram_chat_ids`, `telegram_timeout` | Alerts → Asking the bot things |
| `TRASH_DAYS`, `INPUT_SWEEP_HOURS` | `trash_days`, `input_sweep_hours` | Settings → Tidying up |
| `FILENAME_PICTURE` … `FILENAME_OTHER` | `filename_*` | Settings → How files are named |
| `MAX_CHARACTERS` | `max_characters` | Settings → Tidying up |
| `PROMPT_EDITING` | `prompt_editing` | What it tells the AI |
| `SCRIPT_MODEL`, `CHAT_MODEL`, `TELEGRAM_MODEL` | `script_model`, `chat_model`, `telegram_model` | Settings → The helpers |
| `SCRIPT_KEEP_ALIVE`, `CHAT_KEEP_ALIVE`, `COMFY_FREE_AFTER_JOB` | same names, lower-cased | Settings → The helpers → How they are held |
| `CHAT_NAME`, `CHAT_KEEP_MESSAGES` | `chat_name`, `chat_keep_messages` | Settings → The helpers → How they are held |
| `KID_NAME`, `KID_AGE` | the first profile's `name` and `age` | Who uses it |
| `AUDIT_KEEP_DAYS`, `AUDIT_WORDS` | same names | Log → How long to keep it |

`VOICE_DUCK` was never an environment variable; it is a mix ratio in
`app/gallery.py`. `SCRIPT_TIMEOUT`, `CHAT_TIMEOUT` and `TELEGRAM_API` are read
from the environment but are not in `.env.example` and never were - escape
hatches, not configuration.

**Two of the new rows are the page's own validation problem**, because the
value goes to somebody else's parser. `script_keep_alive` and `chat_keep_alive`
are Ollama's `keep_alive`: a number of seconds or a Go duration ("0", "90",
"60s", "5m"). Anything else Ollama *ignores silently*, which on a settings page
reads as the box doing nothing at all - so `main._keep_alive()` checks the
shape and falls back to the safe value rather than storing it, the same way an
unknown `close_on` falls back rather than losing the rest of the save.

The per-child split did not move either. The new settings are all the
household's: a video ceiling is a property of the graphics card, a trash sweep
is the janitor's, and a pronoun is wording in an email that is the household's
anyway. What is per child is what it was - the limits, the makers, the sums,
the timetable, the theme (`profiles.PER_CHILD`).

### Constants that became functions

`scripts.SCRIPT_MODEL`, `chat.CHAT_MODEL` and `telegram.MODEL` went the same
way and are now `scripts.model()`, `chat.model()` and `telegram.model()`, with
the `.env` value kept beside each as `SEED_MODEL` for the first-run seed and
for the startup fallback. Here the spelling did change, because there were
nine call sites rather than twenty and a name that *looks* like a constant and
is not is worse than a pair of brackets. `telegram.model()` resolves an empty
`telegram_model` to `scripts.model()`, which is what an empty `TELEGRAM_MODEL`
always meant - and it keeps meaning it when the idea helper is changed.

The second pass did the same to every remaining import-time read. In
`app/digest.py` there is no relay constant left at all: `smtp_host()`,
`smtp_port()`, `smtp_user()`, `smtp_starttls()`, `from_address()`,
`from_name()`, `subject()`, `limit_subject()` and `recipients()` are functions,
and `mail_url()` is rebuilt per send, so a corrected address reaches tonight's
email. `notify.MAX_ATTACH_MB` is `notify.max_attach_mb()`,
`telegram.MODEL_TIMEOUT` is `telegram.model_timeout()`, `telegram.ALLOWED` is
`telegram.allowed_ids()`, `jobs.FREE_AFTER_JOB` is `jobs.free_after_job()`,
`scripts.KEEP_ALIVE` and `chat.KEEP_ALIVE` are `keep_alive()`,
`chat.KEEP_MESSAGES` is `keep_messages()` and `chat.HELPER_NAME` is
`chat.helper_name()`. `chat.GREETING` went altogether: it was a dead duplicate
of `greeting()` with the name baked into it. The three `SEED_MODEL`s now read
`gallery.DEFAULT_SETTINGS` rather than the environment a second time, so the
default for a setting is written down in exactly one place.

**What needs a restart, and what does not.** Of the settings, nothing. The
digest scheduler asks `settings()` every minute and `mail_url()` on every send.
The chat and idea helpers read the store per request - verified, the next
`/api/chat` greeting carries a new name. The Telegram poller asks `token()` and
`enabled()` once per cycle and `allowed_ids()` **per message**, so setting a
token, turning the switch on or adding the first chat id each start it
listening within half a minute; `run()` used to return early on a missing
token, which was the last thing on that card needing a rebuild, and does not
any more. Of the nine `app/config.py` owns, two do: `COMFY_URL` and `TZ` - see
that section for why each.

`workflows.MAX_DURATION`, `music.MIN_SECONDS` and `branding.THEIR` were module
constants read at import. A setting a parent can move cannot be read at import,
so each of those modules grew a `__getattr__`: the spelling at every call site
is unchanged and the value is now read when it is asked for. The three Pydantic
`Field(default=workflows.DEFAULT_DURATION)` defaults went the other way and
became `0`, which `clamp_duration` reads as "the page did not say" - a `Field`
default really is frozen at import and there is no hook for it.

### Migration, which happens once

On startup, if `.settings.json` / `.settings-<id>.json` are in `STATE_DIR` and
the database has **no settings at all**, they are imported and then **renamed
to `*.json.migrated`** - never deleted. The log says how many values came from
each file. A second start finds rows and does nothing, so the rename failing
(a permissions problem, say) cannot cause a double import.

A value that still held the old "ask the environment" sentinel is **dropped**
rather than imported, which is what preserves the behaviour rather than the
bytes: for the household the seeded row then says the same thing the
environment said, and for a child, dropping it leaves them falling through to
the household, which is exactly what `-1` meant there.

**Only the settings moved.** `.profiles.json`, `.characters.json`,
`.prompts*.json`, `.timings.json`, `.chat.json` and `.prompt-overrides.json`
are still JSON files beside the database, for the reason they always were:
nothing to rewrite when an item is added, nothing to corrupt when two writes
race, and a human can read one.

### Reads are on the request path

Every route that asks whether the factory is paused asks this. So each thread
keeps its own connection and its own cache of the whole table, and the cache is
thrown away when anything is written - by this thread (a generation counter) or
by another connection, **including one in another process** (`PRAGMA
data_version`, which is what it is for). Measured against the JSON version on
this box: `GET /api/allowance` 1.47ms before, 1.54ms after, over 200 calls
apiece - the gallery directory read dominates either way.

The second-process case is not hypothetical: an earlier Telegram sandbox test
had two containers sharing one state volume. Verified here by writing from a
second process while uvicorn was serving, and by 8 threads × 25 writes from
that process finishing in 1.1s with the server reading throughout.

`store` raises **`OSError`**, not `sqlite3.Error`. Every caller already caught
`OSError` around a settings write, because that is what a file write raised; a
`sqlite3.Error` escaping into a route would have turned a full disk from a 500
with a sentence into a 500 with a traceback.

---

## Backup and restore

`app/backup.py`, all of it behind `_parent`.

**One JSON file with everything a parent has decided in it.** Every setting for
every scope, the profiles, the characters, the prompt overrides, the timings,
the prompt history (the household's and each child's), the chat transcript, the
banner if they have chosen one and every avatar - the two picture kinds base64 in
the file, because one file is the thing a parent can email to themselves. Plus
a `version` and a `made_at`. A few hundred kilobytes.

**Not the gallery.** The pictures, videos and songs are the gigabytes, and they
are already files on a disk somebody can copy. The card on the parent page says
so rather than leaving it to be discovered.

**And not a credential.** This file is the reason `DIGEST_SMTP_PASS`,
`DIGEST_URL`, `NOTIFY_URLS`, `TELEGRAM_BOT_TOKEN` and `PARENT_PIN` are not
settings rows while the rest of the email and bot settings are: a backup a parent emails to
themselves must not be a copy of the relay password. They are on the parent
page - see "The other nine" above - in `app/config.py`'s own settings scope,
and `backup.SKIP_SCOPES` is the one constant that keeps them out of this file.
It does carry the *address*, the host and the port, which is the point of it.

**Both halves of the backup read that constant**, and the second half matters
as much as the first. `build()` leaves the scope out of the file; `apply()`
reads the live values *before* `store.replace_all` empties the table and writes
them back in the same transaction. Without that, restoring a backup - which by
construction has no value for any of them - would have cleared the relay
password, the bot token and the notify URLs off a working installation, and
"restore last week's settings" would have meant "and stop being able to send
anything". A scope the *file* claims is dropped on the way in for the other
direction: a hand-edited backup is not a way to set a PIN on somebody else's
install. Verified on a sandbox: four credentials set, 0 matches for any of them
in the downloaded file, and all four still in force after restoring it.

- `GET /api/parent/backup` → the file, `Content-Disposition: attachment`,
  named `makery-backup-<date>.json`. The page fetches it as a blob rather
  than using a plain `<a download>`, because it needs the PIN header on it.
- `POST /api/parent/restore`, multipart, **armed with a two-tap** and a
  sentence naming what gets replaced. Everything is decoded and checked before
  anything is written; a safety copy of what is there now is taken into
  `STATE_DIR/backups/` first; the settings go in as one `replace_all`
  transaction and each file lands with `os.replace`. A half-restored install -
  new settings, old profiles - would have children whose ids match nothing, and
  that is the outcome worth spending the code on.
- **Profile ids are never renumbered.** A gallery sidecar records `who` as an
  id and the media is not in the backup, so inventing new ids would detach
  every child from everything they had made.
- `GET /api/parent/backups` lists the copies on the server and
  `POST /api/parent/restore/saved` puts one back, through the same armed flow.
  `POST /api/parent/backup` makes one by hand.
- **One a night from the janitor**, skipped if today's is already there.
- **Every copy written rotates the old ones**, whether it came from the
  janitor, a restore or the parent page's "back it up now" - `backup_keep`
  (seven by default, seeded from `BACKUP_KEEP`) of **each kind**, counted
  separately. Separately because a safety copy is exactly the one somebody
  wants five minutes after a restore, and a run of nightlies must not push it
  out; the by-hand ones are a kind too, and used to be trimmed by nothing.
- The name that comes back from the browser goes through the same kind of guard
  a gallery id does: no separators, no leading dot, and it has to resolve to a
  direct child of the backups directory.

A file that is not one of ours is refused with a sentence
("That file was not made by this app."), not a traceback, and nothing is
written.

---

## What has happened (`app/audit.py`)

A parent asked for "a log file of everything done that is persistent and cannot
be deleted easily", and the honest version of that on a box you own is worth
stating before anything else.

**A parent with a shell can delete `state.db`.** No application can keep a
secret from the person who runs it, and this one does not pretend to. What it
does instead is never delete the log itself, offer no route that shortens it,
and seal each entry against the one before it, so that an entry edited, removed
or reordered afterwards shows up as a break at a named position. The promise is
not "you cannot" but "you cannot quietly".

### A table, not a file

Hash-chained JSONL in `STATE_DIR` was the obvious alternative and loses on
three counts:

- **Appending is not atomic.** A route, the janitor and the Telegram loop all
  write from different threads, and two appends can interleave; a crash
  mid-write leaves half a line, which is indistinguishable from tampering.
  `store.chain_append` reads the last hash, seals the new row against it and
  inserts it **inside one `BEGIN IMMEDIATE`**, so two writers can never seal
  against the same predecessor and fork the chain.
- **A second process.** The Telegram sandbox test proved two containers can
  share one state volume. `BEGIN IMMEDIATE` plus `busy_timeout` makes the
  second one wait; two file handles on one JSONL just corrupt it.
- **The database is already the thing that is checkpointed, backed up and
  copied.** One file to keep, not two.

The one thing a file would have won - a human can `cat` it - is answered by the
download: the Log tab hands the whole thing out as CSV or JSONL, hashes
included, and that copy is as readable as a file and verifies away from this
box.

### The chain

    hash = sha256(prev_hash ␟ id ␟ at ␟ actor ␟ event ␟ details)

`at` to the millisecond so it round-trips through JSON, `details` the exact
stored JSON text, and the first entry sealed against sixty-four zeros. The id
column is `AUTOINCREMENT`, so a number is never handed out twice after a trim
and a gap stays readable as a gap. `audit._seal` is the only place the recipe
is written down, and the verifier calls that same function - the two cannot
drift.

"Check the chain" walks the log in id order and recomputes. Measured against a
hand-edited copy of a real database:

- editing one row's `details` → *"The chain breaks at entry #7 … its contents
  do not match its seal - it has been edited. The 6 entries before it are
  intact."*
- deleting that row instead → *"The chain breaks at entry #8 … it does not
  follow on from the entry before it."*
- a truncated *tail* is the one shape that leaves nothing wrong behind, which
  is why the check reports the **last seal**: a shorter log whose last seal is
  not the one in last night's backup is a log that was cut.

### What is written down, and where it hangs

One `audit.record()` call at each chokepoint, never more, and **never fatal** -
every call is wrapped, because a child unable to make a picture because a log
row would not write is worse than a gap.

| Event | Where it hangs |
|---|---|
| `render.started` / `.cancelled` | `main._started`, the cancel route |
| `render.finished` | `gallery.record` - every finished file passes through it |
| `gallery.deleted` / `.restored` / `.destroyed` / `.emptied` | `gallery.delete`, `restore`, `destroy`, `note_trash_emptied` |
| `upload.kept` / `.refused` | the upload route, both sides of the photo screen |
| `safety.refused`, `factory.closed` | `lockdown.refused` - the words box, the chat and the photo screen all come through it |
| `setting.changed` | `gallery.update_settings`, the one place a setting is ever written |
| `profile.added` / `.renamed` / `.removed` | `profiles.add` / `update` / `remove` |
| `profile.switched` | the pick route |
| `pin.failed`, `pin.lockout` | `main._bad_pin` |
| `parent.opened` | `main._parent`, at most once per ten minutes |
| `telegram.command` | `telegram._handle`, before the command runs |
| `backup.written` / `.restored` | `backup.write_one` / `apply` |
| `log.trimmed` / `.kept` | the age trim, and a restore that kept what was here |

Three deliberate silences:

- **The first-start seeding is not a settings change.** `seed_settings()` goes
  through `store.write` rather than `update_settings`, so the seventy-odd rows
  arriving from `.env` on an empty database do not land in the log as seventy
  edits. Nobody changed anything; a default was filled in. The same holds for
  an upgrade: the second pass added nineteen keys, and on a database that
  already had the rest only those nineteen were written and nothing was
  logged - verified against a copy of the live state.
- **`QUIET_SETTINGS` are the machinery's own bookkeeping** - the date they
  passed the sums, which limit email has gone out, the milestones already
  shown, when the trash was emptied. All of it is on the parent page anyway,
  and a hundred rows a day of it would bury the ones a parent actually made.
  `quiz_secret` is in that set for a second reason: it is a signing key, and a
  log that quoted it would hand out a forged pass to anybody who downloaded
  it.
- **A refusal records the category, not the words**, unless a parent turns
  `audit_words` on. Which category stopped something answers "is the filter
  working"; the sentence itself is theirs.

**Who did it** is a ContextVar off the request, exactly like `gallery.WHO`: a
profile id for a child, `parent`, `telegram` or `system`.
`audit.BY_PARENT` is set by `_parent()` and checked first, because a parent
editing the Rules tab is signed in as *somebody* in their browser, and without
it every household setting they changed went into the log against a
nine-year-old's name. The details carry `whose` for which child it was about.

### The Log tab

Seventh, and read-only. Filters by day (a local calendar date - "what happened
on Tuesday" is the question, and an epoch range is not), by child and by kind;
newest first, fifty to a page; "check the chain"; and a download as CSV or
JSONL. **There is no delete button, and no route behind one.**

### Rotation

`audit_keep_days` is **0 - for ever - by default**, because a log that quietly
throws the oldest week away is not what was asked for. When a parent does set a
number, the janitor trims and then writes a `log.trimmed` entry: the gap at the
front of the chain then has a sealed explanation at the back of it, and
`verify()` says which entry is the oldest kept and why anything before it is
missing.

### The backup

The log rides in the backup file as raw rows, seals included, and is **the one
section a restore may only add to**:

- nothing logged here yet → the backup's entries go back whole, ids and hashes
  intact, and the restored chain verifies exactly as the original did
  (checked: 61 entries back, and entry #61's seal identical on both sides);
- anything logged here → this installation's log wins, the backup's is left
  alone, and a `log.kept` entry records how many the backup carried.

Merging two chains would mean re-sealing one of them, which is precisely the
operation the chain exists to make visible. The check happens **first in
`apply()`, before the safety copy** - which writes an entry of its own, and
would otherwise have made the empty case unreachable.

---

## Workflow node map

The four files in [workflows/](workflows/) are valid ComfyUI **API-format**
exports. These are the exact nodes the backend patches at submit time. **They
were verified by reading the graphs — trust this table over guessing.**

**Models are checked at startup, not at first tap.** `_check_models()` asks
ComfyUI for `/object_info` two seconds in and names any model file the
workflows load that ComfyUI cannot see. Two shapes of combo spec have to be
read - the old `[[names...], {...}]` and the newer
`["COMBO", {"options": [...]}]` - because reading only the first reported the
latent upscaler as missing on a machine where it was plainly there and working.
A startup warning that cries wolf is worse than no warning. The check never
fails the app: the picture half may be fine while a 21GB video model is still
downloading. The list comes out of the exports rather than being written down,
so it cannot drift from what a render will actually ask for.

### `flux_schnell-api.json`

Model is **flux1-schnell-fp8** (not flux1-dev), 4 steps, euler/simple.

| Node | Field | Patch to |
|---|---|---|
| `6` | `inputs.text` | their prompt |
| `33` | `inputs.text` | `safety.NEGATIVE_IMAGE` (inert at CFG 1) |
| `31` | `inputs.seed` | random each run |
| `27` | `inputs.width` / `inputs.height` | `1280` / `704` |
| `9` | `inputs.filename_prefix` | `makery/image` |

### `audio_ace_step1_5_xl_turbo-api.json`

ACE-Step 1.5 XL turbo: eight steps at CFG 1, like Flux schnell. Two fields hold
the length and **both have to be patched**: the latent's `seconds` is how much
audio is rendered, the encoder's `duration` is how long the song is *written*
to be, and a mismatch gives a song that stops in the middle of a line.

| Node | Field | Patch to |
|---|---|---|
| `94` | `inputs.tags` | what it should sound like, comma-separated - including who sings it and how many of them |
| `94` | `inputs.lyrics` | what is sung, or `[inst]`, with `[Verse 1 - Singer 1]`-style headers |
| `94` | `inputs.duration` | seconds, as a float |
| `94` | `inputs.bpm` | from the kind of music (`music.BPM`) |
| `94` | `inputs.keyscale` | from the mood (`music.KEYSCALE`) |
| `94` | `inputs.language` | `en` or `fr`, guessed from the lyrics |
| `98` | `inputs.seconds` | the same length |
| `109` | `inputs.value` | the seed - one primitive feeding encoder *and* sampler |
| `111` | `inputs.filename_prefix` | `makery/music` |

Measured on this box: a 15-second song took **16.7 seconds**, about 1.1s of
wall clock per second of audio. Far cheaper than video.

**Neither field has a tag vocabulary**, and this is worth knowing before
anybody goes looking for the list. Read the node
(`comfy_extras/nodes_ace.py`) and its tokenizer
(`comfy/text_encoders/ace15.py`) and `tags` turns out to be a free-text
`# Caption` and `lyrics` a free-text `# Lyric`, both handed to a small Qwen3
language model that writes the audio tokens. There is nothing to look a word
up in: what the caption gets is whatever that model understands by it. The
1.0 node is the one with a fixed vocabulary - its lyric tokenizer has
`[verse]`, `[chorus]`, `[bridge]`, `[intro]`, `[outro]`, `[pre-chorus]`,
`[hook]`, `[solo]`, `[break]`, `[inst]`, `[start]` and `[end]` as tokens of
their own - and **1.5 does not use that tokenizer at all**.

So the only real evidence of what 1.5 honours is how its own authors write
for it. ComfyUI ships six 1.5 templates, and they say the arrangement in
plain words in the caption - "Male Rap Vocals + Seductive Female Vocals",
"Female Background Vocals", "A tight three-part vocal harmony stack fills out
the chorus", "The lead vocalist is a powerful, expressive woman" - and
annotate the lyric headers - `[Verse 1 - Trap Rap]`, `[Intro - Synth Rise &
Vocal Chop]`, `[Final Chorus]`. That is the convention "How many singers"
follows.

### `video_ltx2_5_t2v-api.json`

| Node | Field | Patch to |
|---|---|---|
| `405:376` | `inputs.value` | their prompt (`PrimitiveStringMultiline`) |
| `405:373` | `inputs.text` | `safety.NEGATIVE_VIDEO` |
| `405:338` | `inputs.noise_seed` | random |
| `405:339` | `inputs.noise_seed` | random |
| `75` | `inputs.filename_prefix` | `makery/t2v` |
| `405:362` | `inputs.value` | video length in seconds (`PrimitiveInt` "Duration") |
| `409` | `inputs.aspect_ratio` | `ResolutionSelector`, landscape or portrait |

### `video_ltx2_5_flf2v-api.json`

No ResolutionSelector in this one: width and height are two `PrimitiveInt`s
feeding a centre-crop resize of both pictures, so `size_for()` is patched
straight in. One `SamplerCustomAdvanced` pass with `ManualSigmas` rather than
the two-pass upscale the other video graphs run, which is why a 5s clip takes
about a minute rather than two.

| Node | Field | Patch to |
|---|---|---|
| `31` | `inputs.image` | the first frame, via `/upload/image` |
| `39` | `inputs.image` | the last frame |
| `251:215` / `251:216` | `inputs.value` | width / height from `size_for()` |
| `251:198` | `inputs.value` | duration in seconds |
| `251:252` | `inputs.value` | their prompt |
| `251:217` | `inputs.text` | `safety.NEGATIVE_VIDEO` |
| `251:196` | `inputs.noise_seed` | the seed |
| `68` | `inputs.filename_prefix` | `makery/flf` |
| `251:250` | `inputs.value` | `false` - prompt enhance off, as everywhere |

### `video_ltx2_5_i2v-api.json`

| Node | Field | Patch to |
|---|---|---|
| `398:376` | `inputs.value` | their prompt |
| `398:373` | `inputs.text` | `safety.NEGATIVE_VIDEO` |
| `395` | `inputs.image` | filename returned by ComfyUI's `/upload/image` |
| `398:338` | `inputs.noise_seed` | random |
| `398:339` | `inputs.noise_seed` | random |
| `75` | `inputs.filename_prefix` | `makery/i2v` |
| `398:362` | `inputs.value` | video length in seconds (`PrimitiveInt` "Duration") |
| `403` | `inputs.aspect_ratio` | `ResolutionSelector`, landscape or portrait |

Leave `398:363` (`Switch to Text to Video?`) at `false`.

### The two that are ours: built from `/object_info`, not exported

**Every other file in `workflows/` is an untouched ComfyUI export, and the
convention in this file says to keep it that way.** These two are the
exception, deliberately and with the reason written down.

There is no official template that fits either job. `GET
/api/workflow_templates` on this box offers exactly one frame-interpolation
example, `comfy-mtb`'s `02-film_interpolation`, and comfy-mtb's FILM nodes need
TensorFlow, which has no cp314 wheel and cannot load in this venv at all (see
the stack's own notes). The nearest upscaling template,
`comfyui_ultimatesdupscale`'s `basic-usdu`, is a diffusion re-render - a
different and far slower thing than a single ESRGAN pass. So both graphs were
written by hand from `GET /object_info`, taking the exact input names, types
and combo values ComfyUI reports, and **each counts only because a real render
succeeded**. Both did, on 2026-09-15, and each file carries a `"_note"` saying
so.

`_load()` drops any top-level key starting with an underscore, because
everything else in that dict is handed to ComfyUI as a node and a note would
be a node it cannot execute. `_meta` inside a node is untouched, as in the
exports.

Three things learned building them that are worth not re-learning:

- **`LoadVideo`'s `file` is a combo whose options are empty** unless there is
  already a video in ComfyUI's input directory. That does not matter: the node
  defines `validate_inputs`, which replaces the combo-membership check with
  "does the file exist", so a freshly uploaded name validates. `POST
  /upload/image` takes an mp4 perfectly happily - it writes whatever bytes it
  is given under whatever filename - which is how the clip gets from the
  *output* directory into the *input* one, the same round trip "Animate this"
  makes with a picture.
- **`LoadVideo` reports a UI output of its own**, the input file, so a history
  blob has two entries in it. `extract_outputs` already prefers
  `type == "output"` over everything else, so it is dropped - but a change
  there would quietly make "the video they just smoothed" be the video they
  started from.
- **`VHS_VideoCombine` was the obvious choice and is the wrong one.** It saves
  the first frame as a PNG beside the video to hold the metadata, and that PNG
  lands in their gallery as a stray picture. Turning it off needs
  `extra_pnginfo.workflow.extra.VHS_MetadataImage`, which arrives in the
  prompt's `extra_data` and nothing here sends any. Core `CreateVideo` +
  `SaveVideo` writes one file and nothing else.
- **`SaveVideo`'s `format` is a `COMFY_DYNAMICCOMBO_V3`** and looks alarming in
  `/object_info`. In API format it is just the option's key as a string:
  `"format": "mp4"`. The nested `codec` is optional and defaults to `auto`,
  which gives h264 in an mp4 - verified.

### `video_smooth_rife-api.json`

One file, both answers. `build_interpolated()` patches the frame rate and
nothing else decides which it is: at twice the original rate the clip is the
same length and moves more smoothly, at the original rate the same frames take
twice as long.

| Node | Field | Patch to |
|---|---|---|
| `1` | `inputs.file` | their clip, via `/upload/image` into ComfyUI's *input* dir |
| `4` | `inputs.fps` | the source's own rate, doubled for smooth, as-is for slow |
| `5` | `inputs.filename_prefix` | `makery/smooth` or `makery/slowmo` |

The chain is `LoadVideo` → `GetVideoComponents` → `RIFE VFI` (multiplier 2,
`rife49.pth`) → `CreateVideo` → `SaveVideo`.

- **The original sound is carried through the graph, not remuxed afterwards.**
  `GetVideoComponents` hands its `audio` output straight to `CreateVideo`, so
  there is no PyAV round trip and no second file - which is one fewer thing to
  get wrong than `_with_new_audio` does for the voice-over. Verified: 241
  frames at 48fps, 5.02s, AAC intact.
- **A clip with no audio stream has its `audio` wire removed**, not left
  dangling. `build_interpolated(keep_sound=False)` pops the input. Leaving it
  in stops the graph with an error they did nothing to cause - and a slow-motion
  clip made from a silent one would have hit it.
- **Slow motion is deliberately silent.** RIFE can invent the pictures in
  between; nothing here can invent the sound. The only cheap thing to do with
  it is play it at half speed, which drops it an octave and turns their
  character's line into a growl and the music into a drone. A silent
  slow-motion clip is a better thing to hand a child than one that sounds
  broken, and the button's own toast says so before they tap it.
- Measured: a 5.04s 960x512 clip is **10 seconds** either way.

### `image_upscale_esrgan-api.json`

| Node | Field | Patch to |
|---|---|---|
| `1` | `inputs.image` | their picture, via `/upload/image` |
| `4` | `inputs.filename_prefix` | `makery/huge` |

`LoadImage` → `UpscaleModelLoader` (`4x-UltraSharp.pth`) → `ImageUpscaleWithModel`
→ `SaveImage`. No sampler, no prompt, no seed.

**Which model is in the file and is not patched.** ComfyUI has three others
here (`RealESRGAN_x4plus.pth`, `remacri_original.pth`, `4x-ESRGAN.pth`) and a
picker for them would be exactly the kind of knob this app exists to remove.
Reading the name off the file rather than out of the code is also what keeps
`wanted_models()` honest: the startup check now covers 13 model files, and it
covers these two because they were added to `ALL_FILES`.

Measured: 1280x704 → **5120x2816 in 6 seconds**, a 17MB PNG.

### The four Klein edit graphs

Flux 2 Klein 9B, three things to do with it. **Two of these are ComfyUI's own
template converted to API format, and two are that template with its sampling
latent swapped** - which is a different kind of departure from the
no-hand-editing convention than the RIFE and ESRGAN pair above, and worth
being clear about:

- `image_flux2_klein_edit-api.json` and `image_flux2_klein_edit_two-api.json`
  are the two subgraphs of
  **`image_flux2_klein_image_edit_9b_distilled.json`**, which ships in the
  `comfyui_workflow_templates_json` package on this box. The template is
  UI-format and its two graphs are *subgraphs* (their node `type` is a UUID
  into `definitions.subgraphs`), so they had to be flattened by hand -
  reading the subgraph's own `nodes` and `links` and resolving each one. Every
  node, every wire and every setting the model's authors chose came across
  unchanged.
- `image_flux2_klein_outpaint-api.json` and
  `image_flux2_klein_inpaint-api.json` are the first of those with
  `EmptyFlux2LatentImage` replaced by `VAEEncodeForInpaint`. Nothing shipped
  outpaints or inpaints with Flux 2: `GET /api/workflow_templates` and the
  template directory between them offer `flux_fill_inpaint_example`,
  `flux_fill_outpaint_example`, a Qwen controlnet and Wan VACE, all for other
  models. Every added input was checked against `GET /object_info`.

Each of the four carries a `"_note"` naming its source and the render that
proved it, and **each counts only because a real render succeeded** - all four
did, on 2026-09-15.

Three settings are the template's and are deliberately not patched: **four
steps** on `Flux2Scheduler`, **euler**, and **`CFGGuider` at cfg 1.0** with the
negative made by `ConditioningZeroOut` rather than by a text encode.

**There is no negative prompt in any of the four, and adding one would be
worse than useless.** At CFG 1.0 it cannot reach the picture - the same
arithmetic that makes `NEGATIVE_IMAGE` inert in the Flux schnell graph - and
unlike that graph, where the negative is one cheap CLIP pass kept in place
against the day somebody raises CFG, here it would cost a whole extra pass
through an 8-billion-parameter text encoder to have no effect at all.
`safety.check_prompt` is the filter, as everywhere else.

#### `image_flux2_klein_edit-api.json`

`LoadImage` → `VAEEncode` → two `ReferenceLatent`s (one on their words, one on
the zeroed negative) → `CFGGuider` → `SamplerCustomAdvanced` over an
`EmptyFlux2LatentImage` the same size → `VAEDecode` → `SaveImage`. The
reference is what keeps the composition; the empty latent is why the whole
picture is redrawn rather than patched.

| Node | Field | Patch to |
|---|---|---|
| `76` | `inputs.image` | their picture, via `/upload/image` |
| `74` | `inputs.text` | their instruction, after `_checked` |
| `73` | `inputs.noise_seed` | the seed, recorded in the sidecar |
| `9` | `inputs.filename_prefix` | `makery/edit`, or `makery/style` |

**This file does two jobs.** `build_restyle()` is `build_edit()` with the
prefix changed, because "Turn it into..." is the same graph with a sentence of
ours in node `74` instead of one of theirs - see its own section for the renders
that say so and for the img2img variant that was tried and was worse.

Models: `flux-2-klein-9b-fp8.safetensors`, `qwen_3_8b_fp8mixed.safetensors`
(CLIPLoader type `flux2`), `flux2-vae.safetensors`.

**The VAE is the one change from the template that is not about sizing.** The
template names `full_encoder_small_decoder.safetensors`, which this box does
not have; `flux2-vae.safetensors`, which it does, is the Flux 2 VAE and is
what rendered.

**`ImageScaleToTotalPixels` was taken out**, and this is the change most
likely to be undone by somebody being faithful. The template scales the
reference to 1.0 megapixels in the graph, on a 16-pixel grid - which turns a
1280x704 picture of theirs into 1376x752: a slightly soft copy, at a shape that
is not one of `ORIENTATIONS` and that "Animate this" would then have to crop.
`uploads.for_edit()` does the same job before the upload and leaves anything
already on the grid and under the cap exactly as it is, so an edit of one of
their pictures comes back at precisely the size it went in. Verified: 1280x704
in, 1280x704 out.

#### `image_flux2_klein_edit_two-api.json`

The template's second subgraph, which is switched off in it (`mode: 4`). Two
references instead of one, and the only structural difference is that the
`ReferenceLatent`s are **chained**: positive runs `74` → `128` (their picture) →
`131` (their face), and the zeroed negative runs `82` → `126` → `129`. That is
how Flux 2 takes more than one reference;
`FluxKontextMultiReferenceLatentMethod` exists on this box and is deliberately
not used, because the official template does it this way and this way is what
rendered. Size and canvas come from the first picture.

| Node | Field | Patch to |
|---|---|---|
| `76` | `inputs.image` | their picture |
| `121` | `inputs.image` | their profile face (`profiles.avatar_path`) |
| `74` | `inputs.text` | their instruction |
| `73` | `inputs.noise_seed` | the seed |
| `9` | `inputs.filename_prefix` | `makery/edit` |

#### `image_flux2_klein_outpaint-api.json`

The edit graph with `EmptyFlux2LatentImage` gone and
`ImagePadForOutpaint` → `VAEEncodeForInpaint` in its place: the pad node grows
the canvas and hands its **own mask** to the encoder, so only the new border is
denoised and their picture is carried through the sampler. The `ReferenceLatent`
pair still sees the *unpadded* picture - a reference full of grey border would
only teach the model to draw more grey border.

**"Carried through untouched" is not quite true and the join is fixed in
Python**, not here: the middle still makes a VAE round trip and comes back
about 9 of 255 away from their file. See "Their picture is put back into the render
afterwards" below.

| Node | Field | Patch to |
|---|---|---|
| `76` | `inputs.image` | their picture |
| `74` | `inputs.text` | `styles.compose_outpaint()` - our framing sentence, plus their words if they typed any |
| `201` | `inputs.left` / `top` / `right` / `bottom` | `workflows.outpaint_pads()`, each a multiple of 16 |
| `73` | `inputs.noise_seed` | the seed |
| `9` | `inputs.filename_prefix` | `makery/outside` |

**`feathering` is 0 and the node's default is 40.** This is the one thing that
took two renders to find. At 40 the pad's mask is feathered,
`VAEEncodeForInpaint` blends its grey fill into every half-masked pixel, and
the first render came back with a bright grey band straight across the sky
where the old top edge had been - most visible exactly where the picture is
most even. At 0 the hard mask goes in and `grow_mask_by: 6` does the softening
in the latent instead, which is a sixteenth of the resolution and blends
without bleeding. Same seed, same everything else, and the band is gone.

#### `image_flux2_klein_inpaint-api.json`

The same swap, with the mask coming from the child instead of from a pad node.

| Node | Field | Patch to |
|---|---|---|
| `76` | `inputs.image` | their picture |
| `210` | `inputs.image` | the mask they painted, white where it should change (`LoadImageMask`, red channel) |
| `74` | `inputs.text` | what they typed, after `_checked` |
| `73` | `inputs.noise_seed` | the seed |
| `9` | `inputs.filename_prefix` | `makery/fixed` |

**"Untouched" is not quite the word for the rest of the picture**, and the
file's note says so. The noise mask keeps the *change* inside their brush, but
the whole picture goes out through `VAEDecode`, so everything else is a round
trip of itself rather than the original bytes. Measured against the original on
the validation render: the painted box moved by 28 of 255 on average and
everything outside it by 2.8. Invisible, and worth not claiming more than.

### Shared notes on both video workflows

- The prompt does **not** go into `CLIPTextEncode` directly. It goes into a
  `PrimitiveStringMultiline`, through a `ComfySwitchNode` that picks between the
  raw prompt and an LLM-enhanced version, and only then into the encoder.
  Patch the primitive, not the encoder.
- `PrimitiveBoolean` "Enable Prompt Enhance" (`405:383` / `398:383`) is `false`.
  Leave it — turning it on routes their prompt through `TextGenerateLTX2Prompt`,
  which is slower and puts an unfiltered LLM between their input and the model.
- Defaults kept: **24fps, 0.9MP**. Length and aspect are now patched per job;
  the Duration primitive feeds a `a * b + 1` math node, so the latent is
  `duration * fps + 1` frames - 121 at 5s, 361 at 15s.
- **LTX 2.5 generates audio too** (`LTXVAudioVAEDecode`, `LTXVEmptyLatentAudio`).
  Videos have sound. The player needs controls, and this is worth knowing about.
- Each video runs **two** `SamplerCustomAdvanced` passes with a latent upscale
  between them. These are not fast. The UI needs a real progress indicator.

---

## Architecture

Single container: FastAPI backend serving a static frontend, talking to
ComfyUI's HTTP API over the Docker network, and to Ollama for the idea helper.

```
iPad ──HTTP──> makery container ──HTTP/WS──> $COMFY_URL
           (FastAPI + static/)  ──HTTP────> ollama:11434
```

Layout:

```
app/
  main.py        FastAPI routes, result streaming
  jobs.py        job registry, weighted progress model, cancellation
  comfy.py       ComfyUI client: submit, progress WebSocket, fetch, upload, cancel
  workflows.py   load JSON, patch nodes per the table above
  safety.py      blocklist + negative prompts
  styles.py      the style / place / lighting / mood phrases
  restyles.py    the eight "Turn it into..." chips and what each one says
  gallery.py     list, zip and delete what is on disk; settings, limits, trash
  naming.py      what a finished file is called: the patterns, the tokens,
                 the counter that never repeats a number
  config.py      the nine deployment values the parent page can set: the
                 page over .env, credentials kept out of the backup and out
                 of every log line
  store.py       the settings, the counters and the activity log, in one
                 SQLite file
  audit.py       what happened, sealed entry by entry so an edit shows
  backup.py      one JSON file with everything a parent has decided in it
  profiles.py    who is using it: faces, ages, and a set of rules each
  quiz.py        the daily three sums: questions, marking, the signed day cookie
  pinbox.py      wrong guesses at the PIN, counted per box - the three boxes
                 that take it, and the only state main and telegram share
  schedule.py    the weekly timetable: when it is open, and when it opens next
  scripts.py     Ollama idea helper
  digest.py      the nightly email: thumbnails, SMTP, the minute-loop scheduler
  stats.py       NVML + /proc/stat sampler for the live GPU/CPU figures
  uploads.py     photos from the iPad: validate, orient, crop, re-encode
  i18n.py        seven dictionaries for everything the server writes, and
                 every dropdown label; the language is a ContextVar off the
                 cookie
static/
  index.html     two cards
  i18n.js        the same, for the page - loaded before app.js
  app.js         submit, poll, render, save, "Animate this", cancel
  style.css      big touch targets, iPad Safari
workflows/       the API-format JSONs (patch at runtime, do not hand-edit -
                 except the two that are ours; see the workflow node map)
Dockerfile
docker-compose.yml
```

The compose file joins `$NETWORK_NAME` as an external network - the one
ComfyUI and Ollama are already on - and publishes `$HOST_PORT:8000`. A proxy in
front should reach the container port over that shared network rather than the
published host port.

`.env` holds three different kinds of thing and `.env.example` is the
documented copy: **seven** compose reads to build the container at all, **nine**
that `app/config.py` owns (the parent page wins, `.env` is the fallback, and
nothing is copied between them), and **first-run defaults**, read once to seed
a setting and never again. See "Where settings live" above. `.env` itself is
gitignored.

### ComfyUI API endpoints used

- `POST /prompt` — submit `{prompt: <graph>, client_id}` → `{prompt_id}`
- `GET /history/{prompt_id}` — poll for completion and output filenames
- `GET /view?filename=&subfolder=&type=output` — fetch the result bytes
- `POST /upload/image` — multipart, for the i2v first frame
- `POST /queue` `{"delete": [prompt_id]}` — drop it while still pending
- `POST /interrupt` `{"prompt_id": ...}` — stop it while running. **Targeted:**
  ComfyUI checks the id against the running prompt and does nothing if it does
  not match, so cancelling can never kill an unrelated job.
- `WS /ws?clientId=` — live progress (`progress`, `executing`, `executed`,
  `execution_error`, `execution_interrupted`, each carrying `prompt_id`)

### Backend contract

- `POST /api/generate/image` `{prompt, orientation, styles}` → `{job_id}`
- `POST /api/generate/t2v` `{prompt, orientation, duration, dialogue?, styles}` → `{job_id}`
- `POST /api/generate/i2v` `{prompt, orientation, duration, dialogue?, source_job_id | source_gallery_id}` → `{job_id}`.
  A gallery *video* as the source means its **last frame** - that is "what happens next?"
- `GET  /api/job/{job_id}` → `{status, progress, message, elapsed, eta, cancellable, ...}`
- `POST /api/job/{job_id}/cancel` → the job, now `cancelled`
- `GET  /api/result/{job_id}` → streams the image or video (`?download=1` sets
  `Content-Disposition: attachment`)
- `POST /api/upload` (multipart `photo`, `source=camera|drawing`) → `{gallery_id, orientation, source, preview_url}`
- `GET  /api/gallery/{id}/preview?orientation=` → any item cropped to that shape (a video's last frame)
- `GET  /api/gallery` → `{available, items[]}` — everything on disk, newest first
- `GET  /api/gallery/{id}/file` → the file (`?download=1` attaches it)
- `GET  /api/gallery/zip?ids=a,b,c` or `?what=today|favourites|all` → several as one zip
- `DELETE /api/gallery/{id}` and `POST /api/gallery/delete` `{ids}` → remove
- `GET  /api/profiles` → `{who[], shared, pick, emoji[], colours[]}` — the picker.
  `POST /api/profiles/pick` `{id}` sets the year-long `who` cookie;
  `POST /api/profiles` `{name, age}` adds one (parent PIN);
  `PUT|DELETE /api/profiles/{id}` and `/{id}/avatar`;
  `PUT /api/profiles/shared` `{shared}` — everybody sees everybody's
- `GET  /api/styles` → the dropdown groups
- `POST /api/script` `{prompt, duration, source_*_id?}` → `{prompt}`, or
  `{description, prompt}` when a picture is named — the idea helper
- `POST /api/surprise` `{duration?}` → `{prompt, styles}` — an idea from nothing
- `GET  /api/gallery/{id}/thumb` → a cached 400x300 cover crop of anything, for grids
- `GET  /api/gallery/{id}/poster` → a JPEG still of a video's first frame
- `GET  /api/gallery/{id}/last-frame` → a PNG of a video's last frame
- `POST /api/gallery/join` (multipart `ids`, `title`, `card` PNG) → `{gallery_id}` — a new movie
- `POST /api/generate/story` `{prompt, parts, orientation, duration, quality,
  styles, character?, source_gallery_id?, title_card?}` → `{job_id}` — the
  film. `source_gallery_id` films part one from a picture they already have
  instead of from words (the Story maker always sends it); `title_card` is a
  PNG data URL the page drew, which the join opens on
- `POST /api/story/finish` `{film, song, picture?, keep_sound}` →
  `{gallery_id}` — the Story maker's last step: the song laid under the film.
  No GPU, so no job and no allowance
- `GET  /api/quiz` → `{needed, questions[], token, grownup}`; `POST /api/quiz` `{token, answers[]}`
  → `{passed, wrong[]}`, setting the day cookie on a pass (a wrong answer
  returns a whole new set); `POST /api/quiz/grownup` `{pin}` → a clock-limited
  grown-up cookie, recording nothing
- `GET  /api/allowance` → `{paused, by_hand, closed_sub, opens_at, closes_in,
  closes_at, allowance:{image,video}, quiz_needed}` — what is left today.
  `paused` is true for either kind of closure; `by_hand` says which
  Deliberately cheap: unlike `/api/health` it talks to nothing but the gallery
  directory, because the page polls it every minute
- `GET  /api/parent/summary`,
  `PUT /api/parent/settings` `{paused, quiz_enabled, quiz_questions, quiz_level,
  quiz_ops, daily_image_limit, daily_video_limit}`,
  `POST /api/parent/quiz/bypass` (today only) and `POST /api/parent/quiz/reset`,
  `POST /api/parent/bonus` `{kind, extra}` (negative takes it back),
  `PUT /api/parent/digest` `{enabled, at, limit_mail, max_items, to,
  smtp_host, smtp_port, smtp_starttls, smtp_user, sender, sender_name, subject,
  limit_subject}` — the whole email card, both halves, every field optional.
  **No `url` and no password**: those two are credentials and go through
  `PUT /api/parent/config`;
  `POST /api/parent/digest/send` (the whole day) and `POST /api/parent/digest/test`
  (two lines, to prove the relay),
  `POST /api/parent/cleanup` `{days, keep_favourites, preview}`,
  `PUT /api/parent/naming` `{picture, video, song, comic, film, photo, sticker,
  other}` — the filename patterns; a bad one is a 400 with the sentence to show
  and nothing is saved,
  `PUT /api/parent/schedule` `{text, on}` and `POST /api/parent/schedule/override` `{on}`,
  `POST /api/parent/trash/empty`,
  `GET|DELETE /api/parent/refused/{id}`, `POST .../allow`,
  `GET|PUT /api/parent/models` (what Ollama has, and which of it does what) and
  `POST /api/parent/models/test` `{role}` (one short question through that
  role's model, back with the reply and tokens/sec; 409 while a render is on),
  `GET /api/parent/backup` (the whole configuration as one JSON file),
  `GET|POST /api/parent/backups`, `POST /api/parent/restore` (multipart) and
  `POST /api/parent/restore/saved` `{name}` — all behind `X-Parent-Pin` if
  a PIN is set
- `PUT /api/parent/config` `{key, value}` and
  `DELETE /api/parent/config/{key}` — the nine deployment values
  (app/config.py). Answers `{set, source, env, env_set, restart}` and
  **never a value for one of the five that are credentials**. `parent_pin` is
  refused by both with a 400 saying where it is changed instead
- `POST /api/parent/pin` `{current, new}` — move the PIN. Needs the current
  one typed into the body, not the header; refuses an empty or three-character
  new one; five wrong goes lock the box for ten minutes on its own counter
  (`pinbox.PIN_CHANGE` — the shared one cannot work here, see "Where settings
  live").
  **There is no route that clears it**
- `GET /api/parent/log?day=&who=&kind=&page=&limit=` → the activity log,
  newest first; `GET /api/parent/log/verify` → `{ok, says, last_hash, ...}`;
  `GET /api/parent/log/export?kind=csv|jsonl` → the whole thing as a file;
  `PUT /api/parent/log/settings` `{keep_days, keep_words}`. **Nothing deletes
  it** — there is no route to
- `POST /api/gallery/{id}/smooth` `{slow}` → `{job_id}` — twice the frames of
  one of their videos: silkier at double the rate, half speed at the original one
- `POST /api/gallery/{id}/huge` → `{job_id}` — one of their pictures, four times
  the size, through an ESRGAN model
- `POST /api/gallery/{id}/edit` `{prompt, seed?, with_me?}` → `{job_id}` — one
  of their pictures, changed by what they typed. Costs a picture from the daily
  limit; `with_me` adds their own face as a second reference
- `POST /api/gallery/{id}/outpaint` `{prompt?, side, amount}` → `{job_id}` —
  what is outside the frame. `side` is `all|left|right|top|bottom`, `amount` is
  `bit` (+25%) or `lot` (+50%). The only route whose prompt may be empty
- `POST /api/gallery/{id}/inpaint` (multipart `mask` PNG, `prompt`) →
  `{job_id}` — just the bit they painted over. White in the mask means change
- `POST /api/gallery/{id}/restyle` `{style, prompt?, seed?}` → `{job_id}` —
  the same picture drawn as a different kind of picture. `style` is one of the
  ids in `GET /api/styles` → `restyles`; the words are optional, like the
  outpaint's. Costs a picture
- `POST /api/gallery/{id}/loop` `{at, seconds}` → `{gallery_id}` — up to two
  seconds of a video as a looping animated WebP. No GPU, so no job
- `PUT  /api/gallery/{id}/favourite` `{on}` → star or unstar
- `PUT  /api/gallery/{id}/family` `{on}` → put it on the family shelf, or take it off
- `GET  /api/gallery/trash`, `GET .../trash/{id}/file`, `POST .../trash/{id}/restore`, `DELETE .../trash/{id}`
- `GET  /api/active` → the running job, so a reload can reattach
- `GET  /api/now` → `{system, busy, job, ahead}` — the live GPU/VRAM/CPU
  numbers and ComfyUI's queue position, for the status sheet's two-second
  strip. Touches nothing off the box, unlike `/api/health`, which pings
  ComfyUI and Ollama
- `GET  /api/health` → ComfyUI reachable, websocket state, busy flag

Every `/api/generate/*` route runs `safety.check_prompt()` first and returns
`400` with the friendly message on rejection. **Never bypass this.**

### One job at a time

`_require_idle()` rejects a second job with `409`, and the page locks every
start button while one is running. Two jobs would only queue inside ComfyUI
anyway, and two progress bars racing over one GPU reads as a bug.

### The "Animate this" handoff

The generated image lives in ComfyUI's *output* directory, but `LoadImage`
reads from its *input* directory. So the backend fetches the image via `/view`
and re-uploads it through `POST /upload/image`, then patches the returned
filename into node `395`. The child never sees any of this.

### Photos and drawings from the iPad

`POST /api/upload` takes a photo from the camera or library, or a drawing from
the drawing pad. `uploads.keep()` decodes it with Pillow and re-encodes it -
which strips EXIF (including the GPS the iPad attaches), proves the bytes really
are an image, and caps the longest side at 2048px - and then it is **saved into
the gallery whole**, uncropped, as `upload_<time>_<rand>.png` with a sidecar of
`kind: "upload"` and `source: "camera" | "drawing"`. It shows on its own
"Photos & drawings" shelf, with a badge saying which it was, and gets favourite,
share, trash and "Animate this" like everything else. There is no separate store
and nothing expires: their drawings are theirs to keep.

The Picture card offers two doors onto the same room: 📷 "Start from a photo"
uploads through this route and opens the result in the viewer, and 🖼️ "Pick one
from my gallery" opens the video slots' own picker - narrowed to pictures by an
`only` test on `openGallery()` - and calls `openViewerById()` on whatever they
taps. Nothing new lives behind either one; everything that can be done to a
picture is already in the viewer.

Cropping happens only when the picture becomes a video. The i2v route runs
`uploads.prepare(bytes, orientation)` on every gallery source at submit time, so
the crop follows whichever shape is selected then; a picture already at that
exact size (a generated one) passes through untouched. The source thumbnail
uses `GET /api/gallery/{id}/preview?orientation=` for the same crop, which for a
video is its last frame. Previews are cached in memory by (id, mtime, shape).

The shape is read from the photo itself (after `exif_transpose`, since a
portrait snap is usually a rotated landscape on disk) and the picker is set to
match — they should not have to tell the app something it can see.

HEIC is handled via `pillow-heif`. Safari usually transcodes to JPEG on upload,
but not always, and a photo that will not animate because of a container format
would be baffling.

### The idea helper

`POST /api/script` sends their one-line idea to local Ollama and returns a fuller
prompt containing a line of spoken dialogue. Two things make this safe to put in
front of a child:

- Their idea is checked by `safety.check_prompt` **before** it reaches the model,
  and the model's output is checked again **before** it reaches them. That is
  exactly what the workflows' own `TextGenerateLTX2Prompt` node does not do,
  and why that node stays off.
- The model is asked to unload immediately before any render starts
  (`scripts.release()`). Ollama and ComfyUI share one 16GB card and a video
  render peaks near 15.5GB, so an LLM still holding VRAM would cause an OOM.

Model is `qwen3-vl:4b-instruct` by default, from those already on the box. It
was picked over the larger `qwen3:8b` on merit as well as size: it wrote richer
scene descriptions and worked the spoken line in more naturally, at 3.3GB
instead of 5.2GB. **Which model it is is a setting** - `script_model`, chosen
on the parent page from what Ollama reports, with `SCRIPT_MODEL` as the
first-run seed. `scripts.model()` reads it at the call, so a change takes
effect on the next tap without a restart.

**It is a vision model** (the "vl"), which is what makes the picture-aware
helper possible without a second model: name a picture in `POST /api/script`
and it is downscaled to 768px, sent in Ollama's `images` field, and the model
answers with one line of what it sees plus a prompt that animates *that*. A
drawing they upload comes back with a script about their drawing. Their typed words
go in as a steer and are checked first; the description and the prompt are
checked on the way out. Measured at ~2s and ~190 tok/s on the GPU.

The model unloads the moment it answers (`keep_alive: 0`), and ComfyUI is asked
to `/free` its VRAM *before* every Ollama call: Ollama silently falls back to
CPU when a model will not fit, and the only symptom is that the helper gets
slow. `/api/health` reports the last run's tokens/sec and whether it looked
GPU-accelerated (under 25 tok/s means CPU), plus what Ollama has loaded.

Small models drift into other scripts now and then ("a cheerful
octopus吹泡泡"). Output containing CJK or Hangul is retried once, then refused.

### Style dropdowns

`app/styles.py` holds the style / place / lighting / mood choices and the exact
wording each one appends. The page builds its dropdowns from `GET /api/styles`,
so the phrasing lives in one place and can be tuned without touching HTML or JS.

Phrases are appended **after** their own words, in the order subject → place →
style → lighting → mood, which is roughly how a person describes a picture out
loud. They are a fixed list written by us, so they cannot introduce anything
`check_prompt` would have caught on their input.

**Scene, mood and colours were thin and were expanded**: scene 14 → 39, mood
7 → 28, colours 10 → 22. Camera, music and background sounds picked up a few
more each too (9→12, 9→12, 11→14) - LTX 2.5 renders audio, so those are real
choices, not decoration.

**Scene is ordered real → magical → everyday**, because a dropdown of 40 reads
better with a shape than sorted however the ideas arrived: real-world places
first (forest, city, a rainy street, a lighthouse, a jungle temple), then
imagined ones (a giant's kitchen, a snow globe, a dragon's cave), then the
everyday ones closest to home (bedroom, kitchen table, the back seat of a
car). Ids for every existing choice were left untouched - they are recorded in
sidecars and "make another like this" replays them - only new ids were added,
and reordering the list is safe because selection is stored by id, not
position.

**Every mood phrase steers the picture, not just names the feeling.** "Grumpy"
as a bare word does nothing to a diffusion model; `("grumpy", "Grumpy", "with
a grumpy scowl and crossed arms, in a huffy mood")` gives it something to
draw - an expression, a posture, sometimes a palette or the weather.

**Verified by render**, not by taste: six of the least-certain new choices
were each rendered once through the real `/api/generate/image` route (Flux
schnell) and looked at. Five matched their label on the first try. The
sixth, `giantskitchen`, did not - "towering above everything" produced an
ordinary kitchen at ordinary scale, because nothing in the frame gave the
model something *else* to be big against. Reworded to name the giant
crockery directly (`"dwarfed by giant plates, cups and spoons all around"`),
it rendered correctly on the second attempt. That is the version in git.

**Style was the thinnest of all and was expanded too**: 12 → 43. Painting and
drawing tools (chalk, crayon, charcoal, ink and wash, stained glass, woodcut,
pop art, a Japanese woodblock print, graffiti), things made *out of* something
rather than drawn (toy bricks, felt, knitted wool, origami, sand, balloon,
gingerbread), screen and print looks (retro video game, stop-motion, an 80s
cartoon, sticker, emoji, low-poly, flat vector art), photographic looks
(vintage photo, polaroid, macro close-up, black-and-white film) and three of
their own favourites (a colouring page, a doodle, a treasure map) on top of a
blueprint. All twelve original ids and phrases are untouched.

Eight of the least-certain new style choices were each rendered once through
`/api/generate/image` (Flux schnell) and looked at:

- **Pop art** came back as a flat vector illustration with no dot pattern at
  all - "big dot shading" was not enough on its own. Reworded to name a
  vintage comic-book advert and "rows of coloured halftone dots for shading"
  explicitly; the halftone screen showed up on the second render.
- **Blueprint** put a full-colour illustration inside a blueprint-styled
  border instead of drawing the fox itself as line art, and Flux's usual
  can't-spell problem covered it in garbled labels. Reworded to spell out
  "pale white outline only... no colour, no shading" and to ban text outright
  the same way `BANNER` does, which fixed both.
- **Treasure map** put a realistic photo of the fox next to a small map prop,
  again with invented gibberish text ("Bulled Treasure Map", then a title that
  read as a plausible name on the next try). Reworded so the instruction is
  explicit that the *whole picture* is the map ("drawn as part of an old
  treasure map... hand-drawn in sepia ink on aged parchment") and given the
  same full no-text wording the banner uses (`no text, no words, no letters,
  no writing, no signs, no logos`) - the exact phrase, not a paraphrase,
  because that is the one proven to hold Flux schnell off spelling anything.
  Verified clean on the third render.
- **Tiltshift** ("Miniature (tilt-shift)") was dropped after two failed
  renders. The look only reads as a miniature model from an elevated view over
  a *wide* scene - confirmed with a third render of a hillside village, which
  came out as a textbook tilt-shift photograph - but almost everything asked
  for on this page is a single close subject (an animal, a character), and on
  that framing it renders as an ordinary shallow-depth-of-field photo with
  nothing miniature about it. A style that only works for the framing nobody
  actually uses is worse than no style.
- Chalk drawing, stained glass, low-poly and macro close-up all matched their
  label on the first render and needed no changes.

**Video needed its own pass, because a look that survives a still can still
fail once LTX puts it in motion.** Five of the new style choices were rendered
once each through the real `/api/generate/t2v` route (5s, LTX 2.5) and a frame
pulled with `GET /api/gallery/{id}/frame?at=2`:

- **Colouring page** came back as an ordinary grainy monochrome nature clip -
  full tonal shading, not flat line art. The "no shading" instruction that
  held for a still picture did not survive motion.
- **Pop art** lost both the halftone dots and the bold flat colour; it came
  out as a fine-line pencil/etching sketch with stippled shading instead.
- **Blueprint** kept its drawn border but filled the middle with an ordinary
  colour photograph rather than extending the line art into it.
- **Low-poly** lost its facets entirely and rendered as an ordinary smooth 3D
  movie - indistinguishable from the existing `pixar` choice.
- **Woodcut**, the fifth, held up: a consistent monochrome engraving look all
  the way through, no drift into an ordinary photograph. Kept for video.

Those four failures are why `styles.PICTURE_ONLY` exists: a
`{(group id, choice id)}` set that `options("video")` checks before it builds
a dropdown's choice list. It was chosen over a fourth element on every choice
tuple because every unpacking site in the file (`_PHRASES`, `compose()`,
`random_selection()`) would otherwise have had to learn to ignore it; instead
only `options()` reads the set, so a picture-only id still composes correctly
if it ever reaches the server another way (an old sidecar, "make another like
this" off a picture made before a style was marked picture-only), and only
the video dropdown loses the option. Verified: `GET /api/styles` returns 43
`style` choices for `image` and `comic`, 39 for `video` - `coloringpage`,
`popart`, `blueprint` and `lowpoly` are the four missing.

The 390px layout was checked with headless Chrome against the longest new
label, "Japanese woodblock print" (25 characters, the longest label of any
dropdown in the app): selected on both the picture and video cards' Style
dropdown, `document.documentElement.scrollWidth` never exceeded
`clientWidth`. The native `<select>` just truncates its own text inside the
pill, which is what a phone does anyway - there was nothing to fix.

### The gallery

Everything lands in one directory already: ComfyUI writes to
`/basedir/output/makery`, which is the host's `$GALLERY_DIR`.
That same directory is bind-mounted here at `/gallery`, so the gallery is a
direct read of it - nothing is copied and there is no second source of truth.

Prompts live in a **sidecar JSON per media file** (`<name>.makery.json`)
rather than one index: nothing to rewrite when a file is added, nothing to
corrupt when two writes race, and deleting is just deleting two files. A media
file with no sidecar still lists - it simply shows no prompt, which is what
happens to anything made before this existed or straight from ComfyUI.

The suffix was `.easy-iv-gen.json` before the rename, and
`gallery.LEGACY_SIDECAR_SUFFIX` keeps it readable. `_sidecars_for()` returns
both names; everything that reads, moves, trashes or deletes an item goes
through it, so an item made before the rename keeps its prompt, seed, star,
tags and owner, and goes into and out of the trash with its notes intact.
`_write_sidecar()` writes the current name and drops the old file, so an item
converges the first time anything touches it and there is never more than one
sidecar per item. **Migrate on write rather than a sweep at startup**: a
gallery can hold thousands of files, most of them owned by ComfyUI's user at
644, and rewriting all of them buys nothing over reading the old name where it
already sits.

Deleting needs write permission on the directory, so the container runs as
`RUN_AS` - its own `appuser`, with ComfyUI's group. The directory is owned by
ComfyUI, group-writable and setgid, and unlinking needs write on the
*directory*, not the file. **See "File ownership" in the README before changing
any of that.**

`_safe_path()` is the guard on every id that comes in from the page: no
separators, no leading dot, must resolve to a direct child of the gallery
directory, must be a known media suffix. Sidecars are deliberately not
reachable through it.

**Video thumbnails are server-made stills, not `<video>` elements.** iOS only
lets around sixteen `<video>` elements decode at once; past that the tiles
render blank, which is what a phone showed with a grid of live videos. PyAV
decodes the first frame on first request and caches a 640px JPEG in the hidden
`.posters/` directory (`GET /api/gallery/{id}/poster`), so every tile is a plain
`<img>`. If a poster cannot be made the tile falls back to a `<video>` with a
`#t=0.1` fragment. Posters are deleted with their media.

Filenames are reused after a delete (ComfyUI numbers by scanning the
directory), so every gallery URL carries `?v=<mtime>` - without that the browser
served the *old* video under the new one's name for an hour.

The sidecar records both the **composed** prompt (their words plus the style
phrases, which is what the viewer shows as "what you asked for") and their raw
**idea**. "Make another like this" refills from the idea and re-applies the
dropdowns, shape and length; refilling from the composed prompt would double
the phrases.

Multi-select saves as a **zip built server-side** (`GET /api/gallery/zip?ids=`).
It is a GET so a plain `<a download>` works - Safari will not start a download
from a fetch POST - and the archive is `ZIP_STORED`, since PNGs and MP4s are
already compressed.

### How files are named (`app/naming.py`)

**A pattern per kind, on the parent page, under *Settings* → "How files are
named".** Eight of them - pictures, videos, songs, comics, films, photos and
drawings, stickers, and everything else - each a template of plain
`[A-Za-z0-9._-]` and tokens:

| Token | Is |
|---|---|
| `{date}` | `2026-09-16` |
| `{time}` | `1432` |
| `{kind}` | what it is: `image`, `t2v`, `sticker` |
| `{who}` | the name on the profile, slugged |
| `{n}` | counts up and never repeats. `{n:05}` pads it to `00007` |
| `{idea}` | the first five words they asked for, slugged |
| `{seed}` | the number that drew it, where there is one |

`check()` refuses anything else: an unknown token, a format spec on anything
but `{n}`, a separator, a leading dot, more than 80 characters, and a pattern
with neither `{n}` nor `{time}` in it - which would be a pattern that wants to
give every file the same name. **Every rule there exists so that
`gallery._safe_path` accepts every name the thing can produce**, and the route
(`PUT /api/parent/naming`) refuses all eight on one bad one rather than saving
some: half-applied patterns would leave a parent guessing which took.

Three things worth knowing before changing any of it.

- **The rename happens after the file lands, not in the graph.**
  `jobs._name()` runs on every output the moment `_run_graph` returns, *before*
  the sidecar, before the job's `after` step, and before the page's next poll.
  It mutates the output dicts in place, which is what carries the new name into
  `job.result`, `job.results`, `public()["filename"]` and the gallery id the
  page addresses it by, with no second list to keep in step. It is deliberately
  **not** in `_file()`: that one waits for the `after` step on the jobs that
  have one, and the film's join and the sound effect both go looking for the
  file *by name*. The four functions that name their own output -
  `save_upload`, `save_derived`, `join` and `_with_new_audio` - ask
  `gallery.name_for()` up front instead, which is the same thing one step
  earlier.
- **`filename_prefix` in the graphs is untouched**, and should stay that way.
  Those files are ComfyUI exports and the convention in this file says not to
  hand-edit them; patching a pattern into `SaveImage` would also mean
  re-deriving the counter from the directory, which is the very thing being
  fixed.
- **`{n}` is ours.** One row per bucket in a `counters` table in `state.db`,
  incremented inside `BEGIN IMMEDIATE`, so four-at-once gets four numbers and a
  second process sharing the state volume cannot be handed one twice. It is not
  a setting: a setting is read-modify-written from a per-thread cache and two
  renders landing together would collide. It goes in the backup and
  `set_counters` never moves one *down*, so restoring last week's file cannot
  hand out this week's numbers again.

`render()` asks the disk before it commits to a name: a taken one simply takes
the next number (or, for a `{time}`-only pattern, a `-2` tail). That is also
what carries an upgrade over a directory that already holds forty
`image_000NN_` files - it walks past them. Verified.

**Existing files are never renamed and this is not an oversight.** An id in
this app *is* a filename: renaming their gallery would invalidate every sidecar,
poster, thumbnail, open tab and shared link at once, and they would not see a
thing for it. The card says so in bold.

Two things do change for an install that predates this, and both are named on
purpose. Comic panels were `image_000NN_` (the comic builds them with
`build_image`) and are now `panel_000NN_`, so a panel and a loose picture
cannot want the same number out of two different counters. And the eight kinds
the app named itself - uploads, stickers, frames, moving stickers, films,
voice-overs, sound versions, comic sheets - were `upload_20260916-143012_a1b2c3`
and are now counted like everything else; the random tail existed only because
a random tail cannot collide with ComfyUI's counting, and a counter that never
repeats is a better answer to that. Everything ComfyUI numbers is byte-for-byte
what it was, `outside` / `fixed` / `style` included - `naming.WORD` keeps those
three words because that is what the graphs put in front of the number.

`/api/result/{job}` reads the file **from the gallery** now, with the ComfyUI
`/view` proxy kept only as the fallback for a rename that could not happen: the
file no longer has the name ComfyUI wrote, so `/view` cannot find it. It is a
`FileResponse`, so that route answers a `Range` request too, which the proxied
stream never could.

### The trash and the janitor

**The trash is on disk**, in `.trash/` inside the same bind-mounted directory
as the output, so it survives a container restart - verified by trashing
something, restarting and finding it still there. When it *is* emptied, by the
parent page or by the janitor's `trash_days` sweep, that is recorded
(`trash_emptied_at` / `_count` / `_by`) and the parent page says so: an empty
trash and "nothing was ever deleted" look identical otherwise, and the second
is what a parent is actually asking about.


`gallery.delete()` moves the file and its sidecar into `.trash/` (the poster is
dropped and remade on restore) and stamps `deleted_at` into the sidecar. The
viewer opens a trashed item with only "Put it back" and "Delete for good"; the
latter is armed like any other delete. `restore()` renames if the name has
since been reused by a newer render.

`_janitor()` runs hourly from `lifespan`: it purges trash older than
`trash_days`, and sweeps `makery-*` older than `input_sweep_hours` from
ComfyUI's **input** directory, which is now mounted at `/comfy-input` for that
purpose alone. Every "Animate this" leaves a frame there that ComfyUI never
cleans and they never see; it was unbounded. The glob used to say
`easy-iv-gen-*.png`, which was right until "make it smooth" started leaving a
whole mp4 there - those would have accumulated for ever.

It matches **two** prefixes, not one: `makery-*` for everything this app has
uploaded since the rename, and `easy-iv-gen-*` for every frame left behind
before it. Both are ours and nothing else in ComfyUI's input directory is
named either way, so the old one stays until that directory has aged out.

### Movies, cards and the parent page

- **Join** (`gallery.join`): every clip is decoded and re-encoded to the
  first clip's size at 24fps (`libx264`, crf 20) with audio resampled to 48kHz
  stereo AAC, so clips of different shapes can be mixed - a portrait clip in a
  landscape movie is letterboxed. Runs in a thread (`asyncio.to_thread`); ~1s
  per 5s clip. The temp file is `<name>.part`, which is why `av.open` is given
  `format="mp4"` explicitly. The **title card** is drawn by the page on a
  canvas (the banner behind, the page's own font) and sent as a PNG; the server
  has no fonts and needs none. Sidecar `kind: "movie"` with `parts`.
- **Cards** are the same idea: the page composes picture + message on a canvas
  and uploads it with `source=card`. The message is blocklist-checked; the
  picture is not re-screened (it was already in the gallery).
- **Draw on it**: the drawing pad opens with a gallery picture as the base
  layer and keeps that picture's aspect for the canvas, so the export is the
  picture's shape. "Start again" repaints the base. Stamps are one-tap emoji
  drawn with `fillText`.
- **Print** is `window.print()` with a `@media print` block that hides
  everything but the viewer's image.
- **Parent page**: `static/parent` + `parent.js`, plain fetches to
  `/api/parent/*`. Settings live in `state.db` in `STATE_DIR`, so they survive
  a rebuild and there is one place any of them is changed. Pausing makes every job route answer 503 with a friendly
  line. Refused uploads are kept in `.refused/` as the cropped preview;
  "Allow" turns one into an ordinary upload.

  **Scripts and styles are served `Cache-Control: no-cache`.** StaticFiles
  sends an ETag and nothing else, so Safari applied its own freshness rule and
  kept a `parent.js` for hours after a rebuild - the page rendered with new
  HTML and an old script and looked half done. no-cache means "keep it, but
  ask"; an unchanged file is a 304. The `?v=` on the script tags was a one-off
  to flush what was already cached.

  **It is eight tabs in the order a parent asks the questions**, remembered
  between visits like the main page's: *Right now* (the one-line verdict,
  today's counts, today's pictures, the machine details folded away, space),
  *Who uses it* (the profiles and the shared-gallery tick),
  *Rules* (open or closed, sums, daily limits, per child), *Alerts* (the
  nightly email, messages to a phone, asking the bot things), *Their stuff* (the
  chat transcript, trash, refused uploads, save it all), *Log* (everything
  that has happened, and the chain check), *Settings* (backup and restore, the
  helpers *and how they are held*, how files are named, how long things can be,
  words and wording - including what the whole thing is called - and tidying
  up: every household-level knob that is not a per-child rule and not an
  alert), and *What it tells the AI* (the model instructions, including the
  prompt-editing switch - it reads better next to the prompts it gates than on
  a tab of unrelated knobs). It was nine cards in the order they were written,
  then seven tabs, and is now eight: backup and restore moved out to its own
  tab, and everything else that was a household setting rather than a rule, an
  alert or a thing of theirs followed it there. Every element id survived both
  moves, so `parent.js` did not change shape - only `renderToday` and
  `showBig` did the first time, and nothing did this time: every control is
  still found by the same id, wherever its card now sits.

  The Trash card split in two: the listing itself (what is in it, put it back,
  empty it) stayed under *Their stuff* with everything else of theirs, and the
  three settings that used to share its markup - how long to keep deleted
  things, how big their cast can grow, how long an uploaded frame sits in the
  picture maker's inbox - moved to *Settings* as "Tidying up". Same ids, two
  cards.

  The chat transcript lives under *Their stuff* rather than *Alerts*: it is a
  thing of theirs to read, not something the app decided to tell you about.

  **`.parent details summary` in the page's own stylesheet is (0,1,2)** and beat
  the bare `.pr > summary` that gives the model-instruction rows their padding,
  so every one of those titles sat on its own left border. They are
  `.parent .pr > summary` now. Worth remembering before adding another generic
  element selector to that block - it reaches every `<details>` on the page.

  **Today's pictures are pictures.** The strip used to print the whole
  composed prompt under each thumbnail - forty words of style phrases per
  tile, a wall of text. The tiles are image-only now with a ▶ or ⭐ mark, and
  a tap opens the modal with the kind, time, their words, the full prompt in
  small type, tags, and a "Move to the trash" button, which is the thing a
  parent looking at a picture actually wants to be able to do.

  It is written for a non-technical parent, which drives most of its design:

  - **One line of status**, not numbers. `#verdict` says "Everything's
    working", "The picture maker is offline", "the idea helper is offline" or
    "a video is being made right now (40%)"; the tok/s and VRAM figures are
    still there, folded into a `<details>`.
  - **Today's thumbnails** on the page itself, so the day can be seen without
    going into their gallery. They use `/api/gallery/{id}/thumb` - a cached
    400x300 cover crop kept in `.thumbs/`, made from a video's poster frame
    for videos, so a grid costs kilobytes rather than serving full PNGs.
  - **Save it all** is three `<a download>` links at `/api/gallery/zip?what=
    today|favourites|all`. `what=` rather than every id in the URL: a few
    hundred ids is longer than nginx will accept in a request line. A plain
    link also streams, where fetch-to-blob would hold the whole zip in memory.
  - **Space** is a breakdown, not a total - "videos are 90% of it" tells you
    which button to reach for; "5 GB used" does not. **Tidy up** moves
    anything older than 3/6/12 months to the *trash* (never straight out), and
    spares favourites by default. It previews first: "that would move 24
    things", and only then does the button become the one that moves them.

### Four at once

**They arrive one at a time now, and each is on the page the moment it
exists.** It used to be one graph with `batch_size` 4 on node `27`: 20s for
four against 15s for a single, because the model load and the text encode
happen once either way. The trouble with a batch is that all four latents
denoise together and leave the decoder together, so there is nothing to show
until the last second of it - twenty seconds of a bar and then four pictures
at once.

So `generate_image` submits a **list of `count` graphs**, through the same
list-of-graphs path the comic uses, each `build_image(..., seed=seed+i)`. The
cost is honest and was measured: **about 35s for four** (12-14s for the first,
which includes the model load, then 3-4s each) against 20s batched. That is
the trade they asked for, and it buys a picture to look at every three seconds
instead of a wait and then a flood. `batch_size` is patched to 1 and
`build_image` no longer takes a `count` - nothing in the app wants a batch any
more, and a parameter nothing passes would only suggest that this is still how
four are made. `MAX_BATCH` stays as what the count picker offers.

What makes "as soon as it is ready" work:

- **`Job.results` grows**, and `public()` hands the page `filenames` plus
  `wanted`. Length against `wanted` is how the page knows more are coming.
  `Job.result` still stays the first of them, so every single-file path
  (`/api/result`, "Animate this") works unchanged.
- **Each file is filed as it lands.** `_file()` is one file's sidecar and one
  `notify.made`, factored out of `_finish` and called per graph by `_run`
  (`job.filed` is how far it has got, so `_finish` only does what is left).
  Without that, a picture they can see would not be in their gallery yet - the
  strip, the viewer and "Make it again, but..." all read the sidecar.
  Deliberately **not** for a job with an `after` step: the film's join and the
  sound effect rewrite what the sidecar says, and a record written before them
  would be the wrong one.
- **A seed each**, `seed..seed+count-1`, recorded per file, so "Make it again,
  but..." on the third of four reproduces *that* picture. Verified: the third
  of a run and a single render at its seed are byte-identical. `job.seed`
  stays the first, which is what a single picture has always recorded.
- **The bar says "Picture 2 of 4..."** and the percentage is that picture's
  own progress folded into the whole - `Progress(graph, base, span)` again,
  exactly as the comic divides it.
- **Stop keeps what they already have.** `_cancelled` finishes the job with
  `job.results` instead of binning them: two of four is two finished pictures
  with sidecars, and "Stopped! Nothing was made." over two pictures they are
  looking at would be a lie. It is not timed - a run they cut short is not how
  long a run takes. Pictures only: a comic missing three panels or a film
  missing its join is not a smaller comic or a shorter film, it is a broken
  one, and those stop the way they always did.
- **The page adds tiles in place.** `growChoices()` appends a tile per new
  filename on each poll; the state (which are binned, which was kept) lives on
  the card, so a poll never rebuilds the grid. `/api/active` does the same on
  a reload, so refreshing half way through shows the ones already drawn.

"Keep this one" **stops the rest** if the job is still running, and bins the
others that have landed: they have seen the one they want, so there is nothing
to wait for and no reason to spend the day's pictures on rivals they are about
to bin. One that lands in the moment between the tap and the interrupt is
binned too, with the same undo. The bin **on a tile** is the one delete
button `setBusy` no longer disables mid-render: those tiles appear one at a
time while the rest are still being drawn, and each one is a finished picture
the moment it is there.

The rest is unchanged: the others go to the **trash**, not out of existence,
and a daily limit does not refuse a batch it cannot fill -
`_require_budget(kind, want)` returns how many they may actually have, so
asking for four with two left gets two.

**Timings had to be told.** A picture is now timed **per picture**:
`bucket()` no longer keys on the count (the old `image|landscape|4` samples
were batch runs and would have said 20s for ever), `record` divides by how
many were made, and `estimate` multiplies by how many are wanted. So one
four-at-once teaches the single-picture estimate too, and vice versa.
Measured on this box: `/api/estimate?count=1` says 10 seconds and `count=4`
says 40.

**One thing was quietly wrong and is fixed here**: what the bar says was
always English, whatever they had chosen. `job.message` is written from the
ComfyUI websocket listener, which runs in a task started at boot and has none
of the request's context, so `i18n.t` there answered in the default language.
The job now carries their `lang` and `_say()` sets it around the lookup -
checked on the French page: "Image 2 sur 4...".

### Their own voice over a video

`POST /api/gallery/{id}/voice` takes a recording from the page and writes a
**new** video with it as the sound. Three decisions:

- **The video is remuxed, not re-encoded.** The frames are already exactly
  what they want, so the packets are copied straight across - instant, and
  lossless where a decode/encode round trip would be neither. Verified byte
  for byte: 241 video packets and 2,347,085 bytes in and out, with the audio
  different. In PyAV 18 the call is `add_stream_from_template`;
  `add_stream(template=)` was the old name and is gone.
- **Their voice goes over the video's own sound, not instead of it.** LTX
  generates music, effects and dialogue, and throwing that away was the wrong
  default - replacing it is now a choice ("Keep the video's own sound too",
  on by default). The original is **ducked** to `VOICE_DUCK` while they are
  actually talking, detected in 20ms blocks with a quarter-second hold so the
  gaps between words do not make the music pump, and smoothed over 50ms so it
  fades rather than switches. Verified by decoding the result: after they stop
  the mix matches the original second for second, and while they talk the
  original is well under half its level.
- **Only the audio is rebuilt**, to AAC, because the iPad hands over whatever
  container Safari felt like (`audio/mp4` there, webm on Chrome) and it has to
  be mixed with what the video already had. Everything is resampled to stereo
  float32 at 48kHz first (`_pcm`), which is what `numpy` is in
  `requirements.txt` for. It is truncated at the video's length - audio
  running past the last frame confuses some players and helps nobody.
- **The original is untouched** and this is a new item, so "that sounded
  wrong" is deleting one file rather than having lost the video. Its sidecar
  `kind` is `voice`, which keeps it out of the daily *video* limit: it costs
  no GPU time, so it is not one of the videos that limit is counting.

**`onstop` fires on a later task.** `stopRecording()` nulls `recorder`
immediately, so the stop handler must hold the recorder in a closure local
(`rec`) rather than reading the shared variable - doing the latter threw
`null is not an object` on the iPad *after* a perfectly good take, losing the
recording every time and looking exactly like a button that did nothing. The
stub used to test this fired `onstop` **synchronously**, which hid the bug
completely; it now fires on a later task like every real browser, and the
recorder is started with a one-second timeslice so audio accumulates while they
talks rather than arriving only at the end.

The page records with `MediaRecorder` and plays the video alongside so they can
talk in time with it. Both that and `getUserMedia` need a **secure context**,
so over plain http - the published `$HOST_PORT`, say - there is no
`navigator.mediaDevices` at all. Reach it over https.

That case used to hide the button, which made "nothing happens" the whole
experience. Now the button is shown for every video and the sheet explains
itself instead: it names *why* it cannot record (no https, permission refused,
no microphone - by `err.name`, the only reliable part of those errors), puts
that message at the **top** of the sheet rather than under the buttons where
it was never seen, and offers a file picker so a voice memo can be used
instead. The server takes whatever the browser produced - verified through the
real route with both `audio/webm;codecs=opus` (desktop Chrome) and
`audio/mp4` (iOS Safari).

Closing the voice sheet only unlocks the page if the gallery and viewer are
both closed; they did the locking, and unlocking under them let the page
scroll about behind them.

### Characters they can keep (`app/characters.py`)

A character is a name plus one sentence about how they look, written by the
**vision** model from a picture they already made, and repeated in later
prompts by name and description: "goes to the moon in a rocket. Ollie is a
purple octopus with big eyes, wearing a yellow hat and orange glasses."

**Be honest about what this does.** It is a family resemblance, not the same
character twice - Flux cannot promise identity without extra models, and
saying otherwise would only disappoint them. What it reliably delivers is the
same species, colours and clothes every time, which is enough for a story to
read as being about one person. Their saved picture is kept alongside, so
"Animate this" on *that* still gives a genuinely identical starting frame.

Stored in `.characters.json` beside the media - there are only ever a handful,
and a file that can be read with `cat` is easier to fix than a database. The
name is safety-checked when saved and the look when written, so neither needs
re-checking at prompt time. The model writes "A purple octopus..."; mid
sentence that reads as a typo, so the leading capital is dropped unless the
first word is a real acronym (`NASA-style` survives, `A purple` does not).

### How a maker card is laid out

Three things, in this order, on every card: **the idea, then every choice in
one box, then Go.** It used to be a bordered fieldset per setting, a
collapsible bar or two, and a bare label with chips - three treatments fighting
on one card, with the word-helpers split above and below the box and the
Surprise button drawn as the hero when the textarea is the thing they actually
uses.

- **The idea box comes first** (after "Start from" on the video card, which
  changes what the box means). Every tool that helps with the words - Help me
  write it, Surprise me, Mix it up - is one row directly under it, at 56px
  rather than the 68px hero height. In picture-animating mode the two random
  ones hide and the helper, which looks at the picture, takes the row.
- **`.settings` is one box, `.setting` one labelled row each**: label on the
  left at a fixed 118px, choices on the right. The dividers are a 1px `gap`
  over the container's background rather than a border on each row, so a
  hidden row (no characters yet, not in film mode) leaves no stray line.
- **The style dropdowns are the last row of that box, always open.** As a
  collapsed "Make it look a certain way" bar they were the one thing on the
  card they never found, and they are the choices that change a picture most.
  Three across on an iPad (the video card's seven fit in three lines), two on
  a phone. The row keeps class `extras` so the script can still hide the whole
  thing if `/api/styles` is down; `applyStyles` setting `.open` on it is a
  harmless no-op now.
- **Below 560px** the label goes above the choices, three-way choices go
  three across at 28% basis with the shape glyphs dropped ("Landscape" beside
  its glyph is wider than a third of a phone row and left "Square" alone on a
  line), and the helper takes a row with the two idea buttons sharing the next.
- The "your videos have sound" collapsible is gone; the one line they need is a
  hint under the "what should they say" box.

### Which makers exist (`app/modules.py`)

Not every household wants every tab, so each maker is a switch - on the
parent page, seeded once from `.env`
(`ENABLE_PICTURE` and friends) and on the parent page, which wins.

**There are six**: picture, video, comic, music, chat and story.

- **The server enforces it.** `_require_module()` sits on every route a module
  owns, next to `_require_idle()`. Hiding a tab is the friendly half; this is
  the half that means reloading past it achieves nothing - the same split the
  warm-up sums and the pause already use. Eleven routes carry it, including
  `/api/gallery/join`, which starts from the gallery but is the Video tab's
  work, and the banner maker, which is a picture however it is dressed.
- **Off and cannot are different things**, and `listing()` reports both. A
  parent turning the chat off and a machine with no chat model pulled want
  different sentences and different remedies; the parent page says which, and
  greys the row it cannot act on.
- **A missing `ENABLE_*` means on.** Nobody should have to list all six in
  `.env` to keep what they already had.
- **The Story maker is the one that depends on the others.** It owns no graph;
  it runs the picture, video and music routes in order. `story_steps()` reports
  which of those three can run, `/api/styles` carries it, and the card says
  which step it cannot do and carries on - *except* the film, where the page
  hides the tab, because a story with no film is the picture and the song they
  could have made on their own cards. Two hand-written lists caught this out
  and are gone: `ModulesIn` had five fields and answered **500** to a body with
  six, and `parent.js`'s `saveModules` sent five ids although `paintModules`
  had drawn six - it reads what it drew now.
- **Everything can be off.** `firstTab()` falls through to *the Gallery*, so the
  page lands on their gallery rather than on nothing. A remembered tab that has
  since gone does the same - checked by setting `localStorage` to `comic` and
  then turning comics off.
- **Settings keeps what is theirs.** With pictures off, the banner *maker* goes
  and the colours and "put the first one back" stay, with a line pointing at
  the thing that still works: any picture in their gallery can go up there from
  the viewer.

### Start again

One button per maker card, at the right-hand end of its own `<h2>` - which was
already a flex row, so `margin-left: auto` is the whole layout. It puts the
card back to how it looked before they touched it: the words and their
localStorage drafts, the dropdowns, the shape, the length, the quality, the
count, the panels, the parts, character mode, the singing toggle, who is in it,
and on the video card the mode, the source picture, both film slots and the
sound effect.

- **`pickIn()` exists because the setters change the value and not the
  buttons.** `wireChoice` draws the is-on state on a tap and nothing else was
  putting it back, so a reset moved the setting and left the wrong button
  looking pressed.
- **Armed only when there is something to lose.** Clearing four dropdowns is
  not worth a second tap; a verse they have just written is. `hasTyped()` decides,
  and the arming reuses `arm()`/`disarm()` like every other destructive button.
- **Disabled while a render runs.** Clearing the card mid-render would throw
  away the words that made the thing they are watching and would not stop it.
  Stop does that.
- The defaults come from `LENGTHS`, filled from `/api/styles`, not from the
  markup - the sliders stopped carrying their own bounds when those became
  settings, and a reset that put back 15s on a machine configured for 30 would
  be its own bug. They now follow a change on the parent page with no rebuild
  at all, which is the same reason.

Exercised in headless Chrome rather than reasoned about: typed text, four
choice groups and a dropdown on the picture card, then mode/say/quality/parts/
length on the video card and the lyrics and singing toggle on the music card,
all back to their defaults with no page errors and no overflow at 390px.

### Tabs, and what is happening right now

The page had grown to four tall cards and the one they wanted was usually below
the fold, so they are tabs - Picture, Video, Comic, Gallery, in that order,
because three of them are things to do and the fourth is where they end up.
Two things about the bar itself:

- **It is z-index 20, below the sheets at 30.** As page chrome it has to sit
  *under* anything that covers the page; at 40 it floated over the gallery and
  the picture viewer. The stack now reads: tabs 20, sheets 30, the
  choose-things bar 35 - it lives on the Gallery page rather than in a sheet,
  so it has to clear the tab bar and still sit under anything that covers the
  page - confetti 60, the "closed" and warm-up overlays 80, the toast 90.
- **It has no background at all until it is stuck.** The page carries a radial
  gradient that is lightest exactly where the bar sits, so *any* fill - flat or
  translucent - reads as a dark box printed on top of it. The buttons carry
  their own background and are all that needs to be visible at rest; the bar
  only needs a backing once it is over scrolling content. A zero-height
  sentinel above it drives a `.stuck` class through an IntersectionObserver -
  no scroll handler and no layout reads.

Mechanically: `showTab()` sets the `hidden` attribute on each
card (not a CSS class - `[hidden] { display: none !important }` would win over
any `display` rule) and remembers the choice in `localStorage`. Anything that
needs a particular card calls `showTab` itself: "Animate this" and friends go
to the video tab, "Make another like this" to whichever card made it, and
reattaching to a running job after a reload lands on the one that is working.

Under the banner, `#nowbar` says what is rendering and how far along, on every
tab, with a "Show me" button that appears only when they are looking at
something else. The tab of the working card also carries a pulsing dot. A
finished job leaves the bar up for eight seconds saying so, rather than
vanishing - "it's done" should be something they see, not something they miss.

#### And the whole story behind it

"Nearly there" is the right amount to read on a page they are doing something
else on, and the wrong amount when the question is whether it is stuck. So the
bar is **tappable**, with a `›` on the end saying so, and what it opens is a
sheet with everything the job knows about itself:

- **What is being made**, one string per kind (`MAKING` in `app.js`) rather
  than a noun dropped into one sentence - the same reason "your video is
  ready" needs one per kind, since French agrees the article with it.
- **Their own words**, from `idea` and never translated, exactly as the viewer
  shows them: the composed prompt is English by construction.
- **A row of facts**: the size as `1280×704`, the length in seconds, the
  quality, which of how many, and what is drawing it - "Flux schnell",
  "LTX 2.5 video", "ACE-Step song", "Flux 2 Klein edit". The model names stay
  English wherever they are reading. They are proper nouns, like the helper's.
- **The step in words** (the message the bar already carries), the percent on
  the card's own `.bar`, and **two kinds of ETA**: `job.eta` once there is one,
  and what this machine's history says the whole thing takes until then -
  `update_eta` deliberately says nothing for the first eight seconds, because
  they are a model load and not a rate, and that is exactly the stretch where
  "is it broken?" gets asked.
- **A live GPU / VRAM / CPU strip**, on its own two-second clock. The VRAM
  figure, which steps aside on a phone to keep the card's status line on one
  row, comes back here: the sheet gives it a row of its own, and it is the
  number that says whether the card is full.
- **ComfyUI's queue position**, when something is in front. Almost never: this
  app runs one job at a time, so anything there is somebody using ComfyUI
  directly - which is exactly the case where a bar that does not move needs an
  explanation.
- **Stop**, armed like every other destructive button, calling the card's own
  `stop()` rather than a second way of stopping things - that one knows about
  four at once keeping what has already landed. Not offered for the renders
  they start from their gallery: those have never had a Stop and this is not
  the place to add one (see "They go through the job registry, and they have
  no card").
- **"Show me"**, which becomes **"Look at it!"** once the job is done and
  opens the finished thing.

Three things about how it is wired:

- **The bar is a `<div>` and the tappable part is a `<button>` inside it.**
  "Show me" is a button too, and a button inside a button is not markup any
  browser agrees about. `aria-haspopup="dialog"` and an `aria-expanded` that
  the open and close both set.
- **`showNow()` keeps the job it was given**, so the sheet has something to
  draw whenever they open it - and that is all it took to make this work for
  the derived renders and for reattaching after a reload, because both of
  those already went through `showNow`.
- **The eight-second hold does not close a sheet they are reading.** `hideNow()`
  takes the bar away and leaves the sheet up saying "Done! ✨" with the way to
  the result. Closing a page somebody is looking at is its own small bug.

**`GET /api/now` is the strip's route, and it exists because `/api/health`
costs too much to ask every two seconds.** Health pings ComfyUI *and* Ollama on
every call; measured on this box, 6.63ms against 0.66ms over 30 calls apiece.
`/api/now` touches nothing off the box at all: `stats.snapshot()` is filled in
by the sampler task once a second, and `ahead` is what the job's own two-second
poll loop last read off ComfyUI's `/queue` - so nothing new polls ComfyUI on
their behalf either. `/api/job/{id}` still carries `system` as it always has;
this route is for the moment after a job ends, when nothing is polling that one
any more and the sheet is still open.

`Job.public()` grew the fields all of this reads: `idea`, `orientation`,
`size`, `quality`, `model`, `step`, `steps`, `ahead` and `estimate`.
`Job.size_words()` answers the first of those three ways - `extra["size"]`,
written by the routes that make something out of a file they already have and so
know the size in their own hands; `size_for()` for a video; the `ORIENTATIONS`
table for a picture - and answers **nothing** for anything that does not know,
rather than printing a number they could hold the finished file up against and
find wrong. `timings.estimate_for(job)` is `/api/estimate` asked about a job
rather than about a card, reading the job the way `record` does, so what they are
shown and what gets written when it finishes are about the same bucket.

### Asking the iPad what happened

`POST /api/client-log` writes one line to the container log, and the page calls
it at every step of anything that has misbehaved on a device I cannot open a
console on - plus on `window.onerror` and unhandled rejections. The voice sheet
reports whether it can record, what `getUserMedia` returned, the size and type
of every chunk, and what it tried to upload.

This exists because "it didn't do anything" cost two rounds of guessing. The
log is the only witness to what an iPad on the other side of the house
actually did. Nothing identifying is sent and nothing is kept.

### Recovering notes from the files themselves

ComfyUI embeds the whole submitted graph in what it writes - a PNG text chunk
for images, an mp4 metadata field for videos - so **a lost sidecar is
recoverable from the file**. `gallery.recover_missing()` runs at startup and
hourly from the janitor, and `recover_sidecar()` fills in what is missing
rather than replacing what is there, so a file can keep its star and its album
while getting its prompt back.

This matters more than it sounds: a container restarted mid-render finishes
the file in ComfyUI but never runs `_finish`, so the prompt was simply lost.
Four videos on this box had already been orphaned that way and all four came
back. What it recovers is the **composed** prompt, not their raw idea, which was
never in the graph - so recovered sidecars carry `recovered: true` and the
viewer says where the text came from.

`_from_graph` reads the known node ids first (`6`, `405:376`, `398:376`,
`251:252`, and `74` for the three Klein edit graphs) and
falls back to scanning for the positive prompt when a workflow has been
re-exported with different ids - picking the candidate with the fewest commas
per word, since the negative is a comma-separated list and the positive reads
as prose.

### Shelves, and the .count collision

Everything that is not a plain picture is matched to its shelf **by kind**
first (`BY_KIND` in app.js), so the Pictures shelf holds only pictures they
asked for directly. A comic's panels are recorded as `kind: "panel"` and the
finished page as `kind: "comic"`, each with its own shelf - otherwise three or
six panels swamp the pictures they actually asked for every time they make one.

Inside the "Gallery" card the shelves are separated by a hairline rather than
each sitting in its own bordered box. Six boxes, most holding one or two
things, read as a wall of empty rectangles. An empty shelf is hidden
altogether, which is also what hides the Family shelf on a one-child
installation and the characters shelf before they have saved anybody.

A shelf shows **everything on it**, scrolling sideways. It used to show six
and offer "+N more", which opened the gallery sheet - a second, fuller copy of
the same shelves. There is no fuller copy any more, so there is nothing for
"more" to open: see "The Gallery, in groups or all at once" below.

`homeOf()` is the shelf lookup on its own, because the Everything view's "by
kind" order is these same groups flattened into `SHELF_ORDER`. `kindLabel()`
is the badge text on its own for the same reason: in one mixed grid the badge
is the only thing saying what a tile is, so a tile in the grid and a tile on a
shelf must not word it differently.

**Watch the class names.** The "four at once" picker buttons were given
`class="count"`, which is also what every shelf's item count span is called, so
they picked up `flex: 1 1 0` and a border from the picker rule and rendered as
huge empty boxes next to each heading. They are `.count-pick` now.

### The Gallery, in groups or all at once

The card used to be nine headings, a strip of six under each, and two buttons:
"See all my stuff", which opened a sheet with the same nine shelves in full,
and "My characters", which opened a sheet listing their cast. Both were things
the page knew and would not show until asked.

So the card is the page now:

- **Two views, and a switch at the top.** *In groups* is what it always was, a
  shelf per kind, and it is how they look for a kind of thing. *Everything* is
  one grid, newest first, with the kind on every tile - which is how they look
  for the thing they made ten minutes ago. Both are painted from the same
  `allItems`; **only the view they are looking at is built**, so "Choose all"
  means what is on screen and a phone is not decoding two copies of every
  thumbnail.
- **The order row only exists in the Everything view.** Newest, oldest,
  favourites first, or by kind - the shelves already have an order of their
  own, so offering one over them would be a choice with no effect.
- Both are remembered in `localStorage`, like the tab is.
- **Search and the tag chips are on the page**, filtering `allItems` in the
  browser as they type, and they apply to whichever view is showing.
- **Choosing several, the zip, the bulk tag, the bulk delete and the trash all
  moved onto the page** with it. The choose bar is still `position: fixed`, and
  it is inside the card, which is what takes it away when they go to another
  tab - `showTab` also cancels the choosing itself, or they would come back to a
  bar full of ids they had forgotten about.
- **`#gallery` is now only the picture picker** - "where does this clip start",
  "where does it end". It keeps its own search box and its own filter string
  (`pickFind`), deliberately separate from theirs: what they last searched for on
  their own page has nothing to do with the picture they are picking here. It has no
  choose button and no trash any more.
- The viewer's "← Back" goes back to wherever it was opened from. That is
  almost always the page, where "back" means closing the viewer; the picker
  only gets there when they tap a family tile that is not theirs, which cannot be
  picked and so opens to be looked at.
- **The trash is folded shut and builds its tiles when they unfold it.** A
  trashed video tile is a `<video>` asking the network for a frame; fifteen of
  those behind a closed summary, on every page load, is work nobody asked for.

The character shelf is the same shape as the rest: their own saved picture as
the face (`picture_id`), their name under it, a tap opens their page. Their
page already existed as the "everything with Luna in it" sheet; it gained
Rename and "How they look" from the list that is gone, so all four things they
can do to a character are in one place. Characters are still
household-level - see the profiles section - and the shelf shows exactly what
`/api/characters` returns.

### The things they have asked for before

`GET /api/history` returns their own words per kind, newest first, deduped, 30
each, from `.prompts.json` beside the media - on the server rather than in the
browser so it follows them from the iPad to anything else and survives a cleared
browser. Recorded in `_started`, so it captures what they asked for whether or
not the render finished. The composed prompt is deliberately not kept: nobody
wants to read their own words with forty words of style phrases on the end.

### Finding things, albums, undo and milestones

- **Search filters in the page**, not on the server: the gallery listing is
  already in hand, so every keystroke is instant and there is no request to
  debounce. Every word has to appear somewhere in the idea, prompt, album or
  kind - "blue dragon" should not match a picture that is merely blue.
- **Names and tags.** `name` is theirs to type in the viewer, saved 700ms after
  they stop typing rather than behind a button they have to notice, and shown as
  a caption on the tile so a named thing is recognisable without opening it.
  `tags` is a list of up to eight short words, added from the viewer or onto
  everything they have chosen at once; the chips above the shelves filter by one,
  and search matches names and tags as well as prompts. Both go through
  `safety.check_prompt`. Albums were the earlier shape of this and are gone -
  anything still carrying one reads as a tag rather than being lost.
- **Undo is just "put it back"** - deleting already moves to the trash, so the
  toast only has to offer it. The point is that they should not need to know a
  trash exists to feel safe tapping delete.
- **Milestones** are checked after a job finishes (`gallery.milestone_reached`)
  rather than counted as they go, so they stay right for anything made outside
  the app, and the ones already celebrated are recorded in `milestones_seen`
  so a milestone is a moment and not a banner that returns on every reload.
  Deliberately no streaks and no daily goals: these fire for something they have
  already done, never as a nudge to do more.

### They type in them too

*This section is about what they **type**. For the switch that puts the whole
page in another language, see "Seven languages" below.*

Everything they read is in the language they wrote in; everything the picture
models read is English. That split is measured, not assumed: the same seed
with "un petit renard roux portant un bonnet de laine... regardant les aurores
boréales" produced a plain fox on a rock - no hat, no aurora - where the
English gave both. Flux does not understand French well enough to trust, and
there is no reason to think it understands the other five better.

- **`safety.py` blocklists all seven.** `normalize()` folds accents, the
  characters that are not drawn at all (everything in Unicode's `Cf`, which is
  how a zero-width space between two letters used to walk a word straight
  through) and the Cyrillic and Greek letters drawn as Latin ones; each
  category is compiled twice, as written and unaccented, so "épée" and "epee"
  hit the same entry. An entry of three letters or fewer in a non-English list
  is matched only when that language is on the screen - the lists are otherwise
  all applied at once, and a two-letter word belongs to every language.
  `check_categories()` is the one loop: the chat tab and the lyric check pass a
  narrower set of category names rather than writing their own. See "What each list leaves out" below - every one of the
  six has words deliberately missing from it, and the reasons are in the file.
- **`scripts.detect()`** replaced `looks_french()`: stop-word lists, one per
  language, plus the four letters that belong to only one of them (`ñ¿¡` is
  Spanish, `ãõ` Portuguese, `äöüß` German, `œ` French). Two points to answer
  at all, because a lone "de" is French, Spanish, Portuguese and Dutch at
  once. Words that are also ordinary English are left out however common they
  are - French "chat", which is a whole tab of this app, German "die" and
  "hat", Dutch "is" and "en" - so an English sentence scores zero in all six.
  Checked against seventeen sentences, five of them English: seventeen right.
- **`scripts.to_english()`** runs after the safety check and before the graph
  is built, and its output is checked again, because the translation is what
  reaches ComfyUI. `detect()` decides whether to spend the call at all - a
  wrong guess costs a second, never a refusal - and a translation failure
  falls back to their own words rather than refusing.
- **Their spoken line is never translated.** If they want the character to say
  something in Italian, that is the point.
- **The helpers answer in their language** (`scripts.reading_language` feeding
  `_reply_language`), since they read and edit what comes back. The switch
  wins whenever it is not English; what they typed is the fallback, which is
  all there was to go on before there was a switch.
- **A comic's story is translated up front**, not during. Asking a 4b model to
  restructure and translate at once went badly - one French hedgehog came back
  as a musk ox in panel one and an otter in panels two and three. Given an
  English story it only has to translate the short spoken lines, which it does
  reliably; the speech bubbles stay in their language because they read those.
  `comic._speech_note()` is the one sentence that tells it which.

#### What each list leaves out, and why

**Every one of the seven has words deliberately missing**, and the rule is the
one French set: a word that is vulgar in one sense and completely ordinary in
another belongs off the list, because refusing a child's picture of a fox's
tail is a visible failure where letting a rude word through to Flux is not.
The commonest shape of it is an anatomical slang word that is also an animal
or a part of one.

| | left out | because |
|---|---|---|
| fr | bite, sang, queue | a mouthful, the past tense of sing, a tail |
| es | zorra, concha, coger, heroína, granada, cañón, vino, coca, pecho, herido | a vixen, a seashell, "to take" in Spain, the same word as *heroine*, a pomegranate and a city, a canyon, "he came", a fizzy drink, a chest, a hurt knee |
| it | uccello, sedere, troia, canna, fatto, eroina, seno, ferito | a bird, "to sit", a sow and the city of Troy, a fishing rod, "done", the same word as *heroine*, a bosom and a sine, wounded |
| de | Schwanz, Muschi, schießen, dampfen, Waffe, Kanone, gruselig, Po, Wunde | a tail, a cat's name, what you do to a football, a steam engine, a knight's sword, a star player, the word the **Spooky** mood is made of, a small child's word, a wound |
| pt | rabo, pinto, heroína, peito, matar, ferido, arma | a tail, a chick and "I paint", the same word as *heroine*, a chest, too broad alone, wounded, a toy sword |
| nl | poes, string, pik, lijken, ophangen, schieten, dampen, wapen, eng, heroïne | a cat, a piece of string, a pickaxe, "to seem", hanging up a picture, what you do to a football, a steam engine, a coat of arms, the **Spooky** word, the same word as *heroine* |

German is the one language that *can* block "Heroin": its word for a brave
heroine is "Heldin", so there is no collision to work around. None of the
seven blocks the word for *wine*, because the English list does not either -
the rule was to say the English categories in another language, not to improve
on them on the way past.

**Every list is matched against every prompt**, whatever page they are on, so a
word only has to be innocent in *one* of the seven to be a false positive in
all of them. That is a class of mistake French could not make on its own and
it caught seven words: "bom" is a bomb in Dutch and "good" in Portuguese,
"pila" is vulgar in Portuguese and a battery in Spanish, "porro" is a joint in
Spanish and a leek in Italian, "charro" is a joint in Portuguese and a Mexican
horseman in Spanish, "colocado" is stoned and also simply "placed", "scopare"
is vulgar and also sweeping the floor, and "joint" is an ordinary English word
for the bend in a robot's arm. All seven are out; the compounds that can only
mean the bad thing stay (`bomaanslag`, `injectiespuit`, `handgranate`). The
grenade went the same way in four languages at once - *granada* is a
pomegranate and a city, *granata* and *granate* are a garnet - so it is
`granada de mão`, `bomba a mano`, `handgranate` and `handgranaat`.

Two more folded forms land on an ordinary word and are matched **as written
only**: "soûl" folds to "soul", and "dämon" folds to "damon", which is
somebody's name. Both join "héroïne" in `_COLLIDES_WHEN_FOLDED`.

**An adjective in front of a noun takes an ending**, and this is the miss that
reading would not have found: `"nackt"` does not match *eine nackte Frau*.
`_inflect()` writes each adjective once and expands it - six endings for
German, one for Dutch, the plural for Spanish and Portuguese, four off the
stem for Italian. The endings are bounded on both sides, which is the point:
"nackt" as a *prefix* would match "Nacktschnecke", which is a slug.

**Checked, per language: ten prompts that must be refused and ten innocent
sentences that must pass**, each innocent one chosen because something on one
of the seven lists was nearly close enough to refuse it. 50/50 caught, 50/50
passed, plus the English and French cases unchanged.

| | hits caught | innocents passed |
|---|---|---|
| es | 10/10 | 10/10 |
| it | 10/10 | 10/10 |
| de | 10/10 | 10/10 |
| pt | 10/10 | 10/10 |
| nl | 10/10 | 10/10 |

`CHAT_CATEGORIES` and `LYRIC_CATEGORIES` no longer name each language's copy
by hand - `safety.in_every_language("sexual", ...)` builds the names from the
list itself, because with one other language that was two strings and with six
it would be seven, and the way that goes wrong is somebody adding a language
and leaving the chat checking English only.

### Seven languages

The first child to use this read English and French and asked for more, so
the *whole* child-facing page does seven: 🇬🇧 English, 🇫🇷 Français, 🇩🇪 Deutsch, 🇪🇸 Español,
🇮🇹 Italiano, 🇳🇱 Nederlands and 🇵🇹 Português, as chips in their own Settings
tab. Picking one reloads the page with everything in it changed. Nothing on
the parent page, which stays English.

**The choice is a cookie, deliberately, and not a per-profile setting.** Two
sisters share one iPad, and which language is wanted is a property of whoever
is holding it rather than of whose gallery is open - and a child who wants
another one should not have to find a grown-up. `lang`, a year,
`samesite=lax`, mirrored into `localStorage` for the same pre-paint reason the
colour scheme is: `i18n.js` reads the cookie before the first line of markup
is touched, so there is no flash of the wrong language. `/api/app` returns
`lang` and corrects both if they chose on another device. The `ui_lang`
setting - "Their page opens in", under Settings → Words and wording, seeded
from `UI_LANG` - is
only the starting language for a browser that has never chosen.

**Seven is the number the blocklist can check**, and that is the whole rule.
Adding an eighth means four things and not one: a dictionary in
`static/i18n.js`, a dictionary and a `CHOICES_XX` table in `app/i18n.py`, a
blocklist in `safety.py`, and a stop-word list in `scripts.py`. Three of those
are comfort; the blocklist is not. `music.LANGUAGES` is built from
`i18n.LANGS` rather than written out again, so the song dropdown cannot come
to offer one the filter does not know.

**One mechanism on each side of the wire, and they work the same way.** The
key *is* the English string:

- `static/i18n.js` holds `EN` and one dict per language and a `t()`, loaded
  before `app.js`, so every string `app.js` writes is `t("Make my picture")`.
  Static markup carries `data-i18n="<the English>"` for text and
  `data-i18n-attr="placeholder:…;aria-label:…"` for attributes, and
  `I18N.apply()` runs at the end of `i18n.js` - which is after the markup and
  before the first paint.
- `app/i18n.py` holds the same six dicts and the same `t(key, **fmt)`, reading
  a ContextVar that `WhoIsThis` sets from the cookie alongside `gallery.WHO`
  and `branding.CHILD`. Nothing else had to grow a language argument.

**Every one of them was translated from the English, not from the French.** A
chain of translations drifts, and the English is the sentence somebody wrote
on purpose. The six dictionaries are also written in the *same key order,
under the same section headings*, as the French one, so they diff against each
other line for line and a line missing from one is visible without reading it.

Keying on the English means a call site reads as the sentence it produces, and
a **missing** translation shows the English rather than a blank or a key name.
A handful of keys are symbolic instead (`_SHAPE` in the Python, `EN` in the
JS): the ones whose languages differ in *shape* rather than in words - the "it
opens again on Tuesday" line, `title_for`, and the picture-of-me wizard's
sentence, where English writes "a friendly purple fox", French "un renard en
violet" and German "ein Fuchs, in Lila, ganz freundlich".

#### The three shapes of the title

The possessive is the part that does not translate, and `branding.title_for`
picks between two dictionary entries per language rather than four:

- **English and German** hang the name off the front. English adds `'s`;
  German adds a bare s - *Adas KI-Fabrik* - and an apostrophe alone after a
  name that already hisses, *Max' KI-Fabrik*. That second form is the
  `factory-of-elided` key, named for the French case it was written for.
- **French, Spanish, Italian and Portuguese** put the name last after
  *de* / *di*, and French alone elides before a vowel or a mute h - *d'Ada*.
- **Dutch** sidesteps the question with *De AI-fabriek van Ada*, which is
  right whatever the name ends in. That is a translation decision, not a gap.

**The page no longer works the split out for itself.** The header prints the
name big and the factory in gold underneath, and which half is which used to
be a regular expression per language in `app.js`. Seven of those is seven ways
to print half a title, so `branding.title_pieces()` does it where the sentence
was built and the name is known, and `/api/app` carries `title_parts`.

#### Times, and the words that are not numbers

`schedule.friendly` is a table of two formats per language (`_CLOCK`). The
twelve-hour clock with am or pm on the end is an English habit and nobody
else's; the other six count to twenty-four and differ only in the separator -
`16h30`, `16:30`, `16:30 Uhr`, `16.30 uur`.

**Midday and midnight have to fit the preposition the sentence already
carries**, and this is the one thing testing caught that reading had not. The
closed sign says "Abre a las {when}", "Apre alle {when}", "um {when} auf" -
and *a las mediodía*, *alle mezzogiorno* and *um Mittag* are all wrong. The
fix is in the word, not in the sentence: each language's entry says the form
that fits its own slot (*12 del mediodía*, *12:00*, *12 Uhr mittags*). Where
the word already fits - French *à midi*, Dutch *om twaalf uur 's middags*,
Portuguese *às meia-noite*, German *um Mitternacht* - it was left alone.

#### The punctuation rules, which are one language's and not seven

**A no-break space before `!` `?` `:` `;` is added by `t()` for French only.**
Spanish opens its questions and exclamations instead (`¿…?`, `¡…!`), and that
is a *character*, written into the entries where it belongs. German, Dutch,
Italian and Portuguese set their marks tight against the word the way English
does. One rule applied to all seven would put a gap in front of every
exclamation mark on six pages that do not want one, so `_SPACED` is `{"fr"}`
and says why.

German quotes are `„…“` and the rest use `“…”`; Portuguese chose `“…”` over
`«…»` so it reads the same to a Brazilian child.

#### The glossaries

One word each, used everywhere; informal throughout - *tu / tú / du / tu /
jij*. Kept small on purpose: a glossary nobody can hold in their head is a
glossary that drifts.

| English | fr | es | it | de | nl | pt |
|---|---|---|---|---|---|---|
| the factory | la fabrique | la fábrica | la fabbrica | die Fabrik | de fabriek | a fábrica |
| a picture | une image | una imagen | un'immagine | ein Bild | een plaatje | uma imagem |
| a video | une vidéo | un vídeo | un video | ein Video | een video | um vídeo |
| a song | une chanson | una canción | una canzone | ein Lied | een liedje | uma canção |
| a comic | une BD | un cómic | un fumetto | ein Comic | een strip | uma BD |
| a character | un personnage | un personaje | un personaggio | eine Figur | een personage | uma personagem |
| a sticker | un autocollant | una pegatina | un adesivo | ein Sticker | een sticker | um autocolante |
| the gallery | Galerie | Galería | Galleria | Galerie | Galerij | Galeria |
| the trash | la corbeille | la papelera | il cestino | der Papierkorb | de prullenbak | o lixo |
| Put it back | Remets-la | Devolver | Rimettila a posto | Zurückholen | Terugzetten | Põe de volta |
| Surprise me | Surprends-moi | Sorpréndeme | Sorprendimi | Überrasch mich | Verras me | Surpreende-me |
| Help me write it | Aide-moi à l'écrire | Ayúdame a escribirlo | Aiutami a scrivere | Hilf mir beim Schreiben | Help me schrijven | Ajuda-me a escrever |
| Make it again, but… | Refais-la, mais… | Hazlo otra vez, pero… | Rifalla, ma… | Nochmal, aber… | Nog eens, maar… | Faz outra vez, mas… |
| Make another like this | Fais-en une autre comme ça | Haz otro como este | Fanne un'altra così | Noch so eins | Nog zo eentje | Faz outra assim |
| Turn it into… | Transforme-la en… | Conviértela en… | Trasformala in… | Mach daraus… | Omtoveren tot… | Transforma em… |
| Change this picture | Change cette image | Cambia esta imagen | Cambia questa immagine | Bild ändern | Dit plaatje veranderen | Muda esta imagem |
| Show the family | Montrer à la famille | Mostrar a la familia | Mostra alla famiglia | Der Familie zeigen | Aan familie laten zien | Mostrar à família |
| the warm-up sums | les petits calculs | las sumas rápidas | i conti veloci | Rechenaufgaben | snelle sommetjes | as contas rápidas |
| the parent page | la page des parents | la página de los padres | la pagina dei genitori | die Eltern-Seite | de ouderpagina | a página dos adultos |
| Go! | ✨ Go | ✨ ¡Vamos! | Vai! | Los! | Start | ✨ Vai |
| Save | Garder | Guardar | Salva | Speichern | Opslaan | Guardar |
| a grown-up | un adulte | un adulto | un grande | ein Erwachsener | een volwassene | um adulto |

Each language also made one decision English does not force, and they are
worth knowing before editing a string:

- **Grammatical gender.** Spanish, Italian and Portuguese agree everything
  with the noun chosen above, so *una imagen* makes every "it's ready" and
  "make another" feminine. Where a button can land on a video too, Spanish
  takes the neutral masculine; where a toast would have to pick, it was
  reworded to dodge - *¡De vuelta!* rather than *¡Devuelta/o!*.
- **The colour in the wizard's sentence.** Every language but English puts it
  after the noun, and four of them had to stop it agreeing: *en {colour}* in
  French, *de color {colour}* in Spanish, *di colore {colour}* in Italian,
  *in de kleur {colour}* in Dutch, *em {colour}* in Portuguese. German moved
  the whole adjective into a comma appositive - *ein Fuchs, in Lila, ganz
  freundlich* - because a German adjective in front of a noun inflects and
  cannot be assembled from fragments.
- **A character of no stated gender.** English uses singular *they*. French
  and Italian commit to masculine (*le personnage*, *il personaggio*), German
  to feminine (*die Figur*), Portuguese to feminine (*a personagem*). Each
  agrees with its own noun and none of them misgenders the *child*.
- **`[Verse]` / `[Chorus]`** are localised in all six, following the French
  (`[Couplet]`, `[Estrofa]`, `[Strofa]`, `[Strophe]`, `[Couplet]`,
  `[Estrofe]`). They are the placeholder lyric and the hint card - what they
  reads - and ACE-Step 1.5 takes a free-text lyric field, so a localised
  header is as fine as a localised verse.

#### The Story maker's strings

Every string on the Story card goes through `t()` like the rest of the page,
and **French is done; the other five fall back to the English**, which is what
a missing key does by design. That is the same shape the app has always had
for a card added after a language sweep - a choice added later turns up
working and untranslated rather than blank - and the next full coverage walk
is where German, Spanish, Italian, Dutch and Portuguese should catch up.

The trail chips are the tight spot at 390px: five of them with an emoji and a
word each do not fit a phone row, so **the words are hidden under 560px** and
the emoji carries it, with the line under the trail saying in words what the
step is. Checked at 390px in both languages: `scrollWidth` never exceeds
`clientWidth` and nothing on the card is wider than the viewport.

#### What stays English, and why

Unchanged from the French work, and it is the whole of it:

- **Everything a model reads.** The style, place, lighting, mood, colour,
  camera, music and sound phrases; the character looks; the comic panel rules;
  the eight restyle instructions; the cut-out, banner and outpaint wordings.
  Flux measurably does not understand any of the six, and `scripts.to_english`
  already translates their own words on the way to ComfyUI. Only the **labels**
  on those choices are translated.
- **Their own words, wherever they are shown back to them.** On any page that is
  not English the viewer prefers `item.idea` over `item.prompt`, because the
  composed prompt is English by construction.
- **The lyric *tags*.** `language` is its own field on the ACE-Step encoder;
  the tag line that decides what the song sounds like is English whatever is
  sung.
- **The chat helper's name** (`chat_name`, a box on the parent page) and the
  model names. Proper nouns.
- **The third chat starter**, which is in *another* language on purpose: it is
  there to show them they can type in one. On an English page it is "Donne-moi
  une idée de dessin"; on all six others it is "Give me a drawing idea".
- **The parent page**, all of it, and every parent-facing string underneath
  it - the emails, the Telegram bot, `schedule.state()["says"]`, which is why
  `schedule._friendly_en` exists beside the language-aware `friendly`. Two
  audiences, and only one of them chose a language.

#### Where the translations live, and where they do not

The dropdown labels are **not** in the choice tuples in `styles.py`,
`music.py`, `restyles.py` or `sounds.py`. Those lists grow - `scene` went from
14 to 39 entries in one sitting - and six columns beside every choice are six
more things for whoever adds one to get wrong. `CHOICES_FR`, `CHOICES_DE` and
the rest key them by `(group id, choice id)` and `styles.options()` translates
on the way out, with the English label as the fallback: **a choice added later
turns up working and untranslated rather than blank.**

Which is exactly what had happened: the thirty-one styles added after the
French work - chalk, woodcut, origami, treasure map and the rest - had been
showing their English labels on a French page ever since. They are translated
in all six now, French included, in a block of its own at the end of
`CHOICES_FR` so the list above it is still the one that was written and
checked at the time.

#### The coverage check

The same walk the French work used, run for all seven: a throwaway `test.js`
sets the `lang` cookie, walks every tab, all four video modes, every sheet on
the page, and the closed sign and sums overlay (stubbed from the *real*
`/api/allowance` with two flags flipped, so nothing English is injected by the
test itself), then scans every visible text node plus every `placeholder`,
`aria-label`, `title` and `alt` against ~140 English UI words. Anything
holding *their own* words is excluded.

**4069 strings per language, and the only English left in any of them is the
chat starter that is meant to be there.** Per language, the raw count of
flagged words was 0 / 2 / 2 / 1 / 2 / 2 / 2 (en, fr, de, es, it, nl, pt) and
every one is either "Give me a drawing idea" or a word that language shares
with English - Spanish *idea*, Dutch *help*, *warm* and *camera*, French
*portrait*.

- **No page errors in any language**, and **nothing wider than the viewport at
  390px in any language**, which is the thing German and Dutch were expected
  to break. They did not, because the translators shortened rather than
  translated: *Einstellungen* (13) and *Instellingen* (12) would not fit the
  seven-tab row and are **Optionen** and **Opties**; the two-across dropdown
  empties are *Egal* / *Alles mag*, *Meine Wörter* / *Zoals ik typ*, *Eine
  Stimme* / *Eén zanger*. The tab words are the tight spot as always: Bild,
  Video, Comic, Musik, Chat, Galerie, Optionen / Plaatje, Video, Strip,
  Muziek, Chat, Galerij, Opties.
- **One real leftover was found and fixed**: the `✕ Close` button on all seven
  sheets had no `data-i18n` at all and had been English in French too, since
  the day it was written.
- **The language chips wrap to four rows of two** at 390px (284px of row,
  nothing clipped). Seven chips will not sit on one line with a readable name
  on each, and a flag alone is not a name, so they wrap.

The helpers, live against the real Ollama, one call each:

| | `/api/script` on "a fox reading a book in a library" |
|---|---|
| es | *"Un zorro con pelaje dorado y ojos inteligentes lee un libro antiguo…"* |
| it | *"Un fox marrone con orecchie dritte legge un libro di storie…"* |
| de | *"Ein roter Fuchs sitzt auf einer Holzbank in einer stillen Bibliothek…"* |
| pt | *"Uma raposa sentada em uma cadeira de madeira antiga, lendo um livro…"* |
| nl | *"Een vos zit aan een houten tafel in een rustige bibliotheek…"* |

`/api/surprise` invented in each of the five as well (*"Un cuco construye una
pequeña torre de hojas secas…"*, *"Ein kleiner, bunter Käfer klettert…"*), and
`/api/song-words` in Spanish came back with Spanish verses and an English tag
line, which is the split that matters.

And the measured half - what ComfyUI is actually handed, which is the whole
reason any of this translates:

| what was typed | node 6 got |
|---|---|
| *un zorro pequeño con un gorro de lana mirando la aurora boreal* | a small fox with a woolen hat looking at the northern lights |
| *una piccola volpe rossa con un berretto di lana che guarda l'aurora boreale* | a small red fox with a woolen hat looking at the northern lights |
| *ein kleiner roter Fuchs mit einer Wollmütze, der das Nordlicht anschaut* | a small red fox wearing a woolen hat, looking at the northern lights |
| *uma raposa pequena com um gorro de lã a olhar para a aurora boreal* | a small fox with a woolen hat looking at the northern lights |
| *een kleine rode vos met een wollen muts die naar het noorderlicht kijkt* | a small red fox with a woolen hat looking at the northern lights |

An English prompt is detected as English and never spends the call.

### Three helpers, one button

`POST /api/script` takes a `kind`, because "help me write it" means three
different things:

- `picture` - one still described in 35-60 words. The video prompt is the
  wrong shape for this: it asks for camera movement and a line of dialogue,
  neither of which a picture has, and the quoted words get rendered as literal
  text in the image often enough to matter.
- `video` - one continuous shot with a spoken line, as before.
- `comic` - two or three sentences with a beginning, a middle and an end. "A
  hedgehog in a pond" is a picture, not a story, and panels need something to
  happen.

### Comics (`app/comic.py`)

They type a story; the model turns it into panels; each panel is drawn; the
page composes the finished sheet. Three things are worth knowing:

- **Consistency between panels cannot be solved honestly with Flux alone**, so
  this does the two cheap things that help most. The model writes one `look`
  sentence - "a hedgehog with spiky brown fur, wearing a blue swimsuit and a
  yellow hat" - which is repeated verbatim in **every** panel's prompt, and a
  fixed `PANEL_STYLE` suffix goes on all of them. The result reads as one strip
  even though it is not the same character each time. Verified: four panels of
  the same hedgehog in the same blue swimsuit, telling a story start to finish.
- **The model is asked for JSON** (`format: "json"`), and `_extract_json`
  still digs the first object out of whatever prose or code fence it arrives
  wrapped in - small models do that however firmly they are told not to, and
  losing the comic to a stray "Here you go:" would be silly. Everything it
  writes - the look, every scene, every line of speech - goes through
  `safety.check_prompt` before it reaches ComfyUI or their eyes.
- **Their style choices go into every panel**, alongside the repeated character
  description. Comics get a cut-down set of dropdowns (`COMIC_GROUPS`: style,
  place, feeling - lighting is left out because the panel rules already fix it
  and a sixth dropdown was more to read than to choose from). The "no text, no
  speech bubbles" half of `PANEL_RULES` is not negotiable and stays whatever
  they pick: Flux will happily letter its own bubbles over the ones the page
  draws.
- **The page is laid out in the browser**, like the card maker and the movie
  title card, so the server needs no font files. The finished sheet goes back
  through `/api/upload` with `source=comic`, which gives it `kind: "comic"` in
  the sidecar rather than filing it under photos and drawings.

A comic is several *different* prompts, so it was never one batched run -
and four at once is a list of graphs now too, for a different reason (see its
own section). `registry.create()` accepts a list of graphs and
`_run` works through them in order, each owning `1/n` of the progress bar
(`Progress(graph, base, span)`). `_run_graph` is one graph start to finish and
returns its outputs, or `None` if it was cancelled or failed.

### Songs (`app/music.py`)

The picture and video cards take a sentence and add style phrases. A song is
the same shape with two real differences:

- **It has words.** `tags` (what it sounds like) and `lyrics` (what is sung)
  are two fields on the encoder, so the card has two boxes. "Help me write it"
  fills both from one idea in **one** call - they have to agree, and asking
  twice gets two models' worth of disagreement for twice the wait.
- **Some choices are numbers.** A lullaby is not a pop song with the word
  "lullaby" added; it is slower. The kind of music carries a BPM and the mood
  carries a key, and both go into their own fields. That is the difference
  between "sounds a bit like" and "is".

Other things worth knowing:

- **Both boxes go through a filter, but not the same one.** The tags describe
  the song and get the picture prompt's full blocklist. The **lyrics get a
  narrower list** (`LYRIC_CATEGORIES`), the same argument the chat tab makes:
  the full list exists to keep things out of a *picture*, and applied to a song
  it refuses the ordinary - "hanging" from a tree, "wound" round a spool,
  "blood brothers", "killing it". The first surprise song this app ever wrote
  was about a sloth stuck upside-down in a tree and was refused for violence.
  Two categories chat leaves out are kept: a child's song has no business
  naming a drug or a firearm, and neither turns up by accident the way "wound"
  does. `scary` is left out on purpose - the card offers a **Spooky** mood, and
  a filter that then refuses "terrifying" is a feature fighting itself.
  The "…and song words too" switch on the Rules tab uses the whole list.
- **The model answers with a list about a third of the time**, however firmly
  the instruction says otherwise - lyrics as a list of lines, tags as a list of
  words. `_as_text()` joins either; `str()` on a list hands ACE-Step a Python
  repr to sing, brackets and quotes included.
- **Lyrics are never translated.** A Spanish idea gives a Spanish song - and
  so does an English idea that *asks* for one. "A song sung in french about my
  best friend" is an English sentence, so looking only at what language they
  typed got it wrong and wrote English words; `asked_language()` matches the
  *request* rather than the word, because a bare `\bfrench\b` also caught "a
  song about a French bulldog" - and every one of the six sets that trap. A
  German shepherd, a Spanish omelette, a Dutch barn, a Portuguese man o' war.
  So a bare name never counts: it takes a preposition in front of it ("in
  Spanish", "en español", "auf Deutsch"), a noun after it ("German lyrics"),
  or the language's own name for itself, which nobody writes about a dog.
- **"Sung in" is a dropdown**, and it wins over both of those: picking
  *Español* is a clearer request than any sentence, and it is the one they can
  make without knowing the trick. "Match my words" is the empty option and
  falls back to reading the lyrics, which is what happened before there was a
  dropdown at all. `language_for()` decides; `_reply_language()` tells the
  helper the same thing so **Write me a song** writes in it too.
- **It is not a tag.** `language` is its own field on the encoder, so `NOT_TAGS`
  keeps `compose_tags` from writing the word "fr" into the line that decides
  what the song *sounds* like.
- **Seven and no more, on purpose.** `safety.py`'s blocklist covers exactly
  those, so lyrics in an eighth would be checked against a list that does not
  know its words - and the lyric check is the only thing between them and
  whatever the helper feels like writing. `LANGUAGES` is built from
  `i18n.LANGS` rather than written out again, so the dropdown cannot come to
  offer one the filter does not know: adding a language means adding it to
  `BLOCKLIST` first, and then the song card follows on its own.
  `language_of()` sniffs the finished lyrics when they have not chosen. It used
  to keep a French word list of its own, on the argument that `scripts` was
  tuned for a different question - whether to spend a translation call. With
  six to tell apart that stops paying for itself: a second set of stop-word
  lists is a second thing to get wrong, and what is at stake here is only the
  singer's accent. It is `scripts.detect()` now.
- **Singing with an empty words box is an instrumental**, both ends agreeing:
  Go is not the button that invents lyrics, "Help me write it" is. **Surprise
  me** does, though - it returns the idea, the dropdowns *and* the words in one
  answer, because a surprise song with no words is half a surprise. If the word
  half fails the idea still comes back rather than losing the whole thing.
- **"How many singers" is the one dropdown that writes both halves.** Every
  other choice on the card is a phrase in the tag line; this one is a phrase
  *and* an instruction to the lyric helper, because a duet is nothing but a
  tag unless the verses actually alternate. `GROUPS` carries the tag phrase
  and `LYRIC_PLAN` the instruction, side by side, so one choice cannot get
  half-applied. The five: one singer (the empty option, and what every song
  did before this existed), two taking turns, a group joining in on the
  chorus, everyone together, and call and answer.
- **The two vocal dropdowns are combined, not listed.** "Who sings it" says
  what one singer sounds like and "How many singers" says how many there are;
  written side by side they argue, because "female vocals, duet" leaves the
  model to guess whether the second singer is female too. So each arrangement
  phrase has a `{who}` slot that `VOICE_WORD` fills from the voice choice - *a
  girl* plus *two taking turns* is a **young female duet** - and the voice's
  own phrase still follows it, describing the lead. *A whole choir* fills that
  slot with nothing, since "choir duet" is a contradiction and the
  arrangement reads perfectly well alone; so does no voice at all, and a
  plain "duet" is understood to be two different singers.
- **Their own words are never restructured.** `singing_plan()` is only ever sent
  to the helper. Lyrics they typed go to ACE-Step exactly as typed with the
  arrangement tags on top, because rewriting their verses to fit a dropdown
  would be the app arguing with a child.
- **What the arrangement does to the sound has to be judged by ear.** The tags
  are the ones ComfyUI's own 1.5 templates use and the renders accepted them,
  but there is no tag vocabulary to check them against (see the node map) and
  nothing here can listen. Five songs were rendered, one per choice, and what
  is *verified* is that each came out 15.0s with the arrangement in the tag
  line, the structured lyrics in the sidecar and both round-tripping out of
  the mp3's own metadata. Whether the model really hands the second verse to a
  second singer is a question for somebody with ears.
- **The helper drops the brackets round a header every few answers**, writing
  `Verse 1 - Singer 1` where `[Verse 1 - Singer 1]` was asked for - and an
  unbracketed header is not a header, it is four words ACE-Step sings in the
  middle of the song. `_bracket_headers()` puts them back, on the model's
  output only. It is deliberately narrow: a section name, an optional number,
  an optional note after a dash, and nothing else, so a sung line that starts
  with the word "Chorus" is left alone.
- **`_is_header()` replaced an exact match against `SECTIONS`.** The rule that
  drops a trailing header with nothing under it used to compare the line to a
  list of the nine markers; an annotated one is a header just as much, so
  anything that is one pair of square brackets and nothing else now counts.
- **"Everyone together" is the one the helper is worst at.** It marks every
  header correctly, but about a third of the time it answers with a single
  section instead of verses and a chorus - a 4B model told "everybody sings
  all of it" hears "write one block". The wording that works best leans on the
  shape the model already follows ("write the usual verses and choruses, and
  put - everyone inside each header") rather than describing the sections from
  scratch. Tapping it again is the fix, and their own words are unaffected.
- **Surprise me can draw "one singer".** It is the empty option rather than a
  row in the list, so `random_selection()` throws it into the hat by hand;
  without that every surprise song would be a duet or a choir, which is the
  one arrangement they get most often by choice.
- **Songs have their own daily limit** (`daily_music_limit`). They cost GPU
  time like a picture, but nobody thinks of a song as one of their pictures.
- **The tab hides itself** when ComfyUI has no ACE-Step model, on the
  `music_ready` flag `/api/styles` carries, the same way the Chat tab hides
  without its model. A tab that answers "not set up" on every tap is worse
  than no tab.

### What else ACE-Step can make, measured

"Other than songs, are there other types of audio we can create?" The answer
is **two**, and the way it was arrived at is worth keeping, because most of
what was tried did not work and the reasons are not obvious.

**ACE-Step 1.5 XL turbo is the only audio generator on this box.** MiniMax
Music 3 has its nodes (`MiniMaxMusic3TextEncode`,
`EmptyMiniMaxMusic3LatentAudio`), its `minimax` CLIP type and its shipped
template, and **none of its three weight files**: the template asks for
`minimax_music3_dit_*`, `minimax_music3_text_encoder_pruned_int8_convrot` and
`minimax_music3_dav`, and what is on disk is `minimax_h3_*`, which is a
first-last-frame-to-video-with-audio **video** model that happens to share the
first half of its name. YuE2 is the same story: nodes, no weights. So nothing
here needs a second model, and nothing here can have one without a download.

**There is no text-to-speech of any kind.** Every speech-shaped node in
`/object_info` is a cloud partner node needing an API key and an outbound
connection - `ElevenLabsTextToSpeech`, `ElevenLabsTextToSoundEffects`,
`FishAudioTextToSpeech`, `HeyGenTextToSpeechNode`, `ByteDanceSeedAudio`, the
`ComfyCloudMiniMax*` set. `mtb`'s `Audio To Text` is the other direction.
Narration - a comic read aloud, a film with a voice over it - would need a TTS
custom-node family **and** a model: Kokoro ONNX (~350MB, fixed voices, CPU),
F5-TTS (~1.5GB), Chatterbox (~2-3GB, clones a voice from a few seconds),
Higgs Audio v2 (~10-12GB, the best of them). Each is an install plus a
download plus its `requirements.txt` folded into the stack's
`10-custom-node-deps.sh`. **Nothing was installed.** Worth saying before
anybody does: a voice-cloning model on a child's machine is a deepfake tool,
and `safety.py` has a `real_people` category for a reason.

#### How each kind was judged

Nothing here can listen, so each render was measured with numpy and PyAV - the
duration, the loudness, how bright it is (the spectral centroid and the share
of energy above 2kHz), how regular its onsets are, and how much it repeats.
Sixteen renders, against a plain pop song as the control.

| | duration | centroid | above 2kHz | onsets/s | onset spread | verdict |
|---|---|---|---|---|---|---|
| a song (control) | 15.0 asked, 15.0 out | 499 Hz | 4.4% | 2.73 | 0.28 | |
| 8-bit tune | 12 → 12 | 416 Hz | 4.4% | 1.33 | 0.35 | **ships** |
| ukulele jingle | 10 → 10 | 507 Hz | 3.7% | 4.40 | 0.33 | **ships** |
| 8-bit fanfare | 8 → 8 | 435 Hz | 2.2% | 0.62 | **0.01** | **ships** |
| spaceship hum | 15 → 15 | **141 Hz** | **0.2%** | 2.47 | **3.51** | **ships** |
| underwater | 15 → 15 | **141 Hz** | **0.7%** | 2.67 | 0.43 | **ships** |
| wind | 15 → 15 | 841 Hz | **0.2%** | **0.20** | 0.58 | **ships** |
| rain on a tent | 15 → 15 | 150 Hz | **0.6%** | 1.07 | 0.39 | **no** |
| rain, retried as noise | 15 → 15 | 405 Hz | **0.1%** | 0.27 | 0.10 | **no** |
| busy market | 15 → 15 | 510 Hz | 5.0% | 1.73 | 0.68 | **no** |
| one door creak | 4 → 4 | 1015 Hz | 15.0% | 2.50 | 0.09 | **no** |

- **The length is always right.** Every render came out at exactly the
  duration asked for, to the hundredth of a second, at 4, 8, 10, 12, 15 and 20
  seconds. The node's floor is 1 second, so the app's old 10-second minimum
  was the app's, not the model's.
- **The `bpm` field is really obeyed**, which was worth proving before the
  jingle leaned on it: a song at 120bpm put its onsets a median 0.235s apart
  (the half-beat is 0.25s) and a jingle at 140 put them 0.427s apart (one beat
  is 0.429s).
- **A little tune works because it is the thing the model already is.**
  Strongly pitched, on the grid, repeating.
- **A background hum is a real, measurable difference** rather than a wish.
  Against a song's 500Hz centre of gravity and 4.4% of energy above 2kHz, the
  hums came out at 141-405Hz and **0.1-0.7%** - a tenth to a fiftieth as much
  high end - and their onsets are three to twelve times as raggedly spaced.
  Not every one is beatless (the underwater one still pulses), but none of
  them is a song.
- **Noise is the thing it cannot do at all.** Rain was asked for twice, the
  second time in as many words as exist for it - *white noise, rain hiss,
  heavy static texture, pure noise, no instruments, no music* - and came back
  at -41 dBFS with **0.1%** of its energy above 2kHz. Rain is almost nothing
  *but* energy above 2kHz. A crowded market was indistinguishable from a song
  on every measure but onset spread. So the chip is called "a background hum",
  not "a soundscape": it promises what it can keep.
- **A sound effect is deliberately not offered.** One door creak gave 1.2
  seconds of sound in a 4-second file, once, and there is no way from this
  side to tell whether it was a door. `app/sounds.py` already has twelve
  effects synthesised in numpy - exact, instant, free, identical every time -
  and a diffusion model that spends GPU seconds to maybe produce a creak is
  strictly worse than one that always does.
- **Spoken, rap and chant needed nothing built.** "Hip hop" is already in the
  genre dropdown and a playground chant is a song with claps; both rendered
  like songs (onsets 2.9-3.1/s, centroid 720-900Hz). There is no new kind
  there, only words they can already type.

#### The silence on the end, which is the real defect

**ACE-Step is given a length, writes something shorter, and leaves the rest of
the file silent.** Over fourteen renders the gap between the last sound and
the end of the file was a **median of 3.0 seconds and as much as 6.2**: a
twelve-second jingle that stopped playing at 6.9, a fifteen-second song that
stopped at 11.95 because four lines of lyrics do not fill fifteen seconds.
On a two-minute song nobody notices. On a ten-second jingle it is half the
file, and they think it broke.

Two halves to the fix, and both are needed:

- **Do not ask for it.** Each kind's default length sits where the model
  actually delivers - 15s for a tune, which is about ten seconds of music.
- **Cut what is left.** `gallery.trim_tail` decodes the finished mp3, walks
  back in 50ms windows to the last one above -45 dBFS **relative to the file's
  own peak**, keeps a 0.35-second breath so it does not click, and re-encodes.
  Verified end to end: a 12s jingle came out 9.0s with its last sound at 8.54,
  a 20s hum came out 17.35s.

It is deliberately timid. It does nothing at all unless there is more than a
**whole second** of silence, so a piece that really does fade to nothing keeps
its fade; it runs **only for the two instrumental kinds**, because a song's
tail is short and a fade somebody wrote is not silence; and it is wrapped, so
a failure logs and leaves the file exactly as rendered. **ComfyUI's graph is
in the mp3's tags and `recover_sidecar` reads it back**, so the metadata is
carried across the re-encode on purpose - dropping it would quietly break
recovery for precisely the files this touches. The measured length goes into
the sidecar as `played_seconds`, *beside* `duration` rather than over it:
`duration` is what they asked for and what the timings are filed under.

#### Where the three kinds are wired

One route, one graph, one daily allowance. `music.KINDS` is the whole model -
the tags prepended to theirs, whether anything is sung, and the window of
seconds, which is clamped into the song bounds a parent set rather than
ignoring them. `music.JOB_KIND` maps a chip to the kind a job and a file
carry, and is the **one source of truth** for the three strings that half a
dozen modules key off (`jobs.Job.is_audio`, `timings.FAMILY`,
`gallery.usage_today`, `naming.BUCKET`, the digest, the bot) - three literal
tuples that had to agree is how one of them ends up quietly not counting.

- **A song keeps the kind it has always had.** Nothing already in their gallery
  moves and no sidecar is rewritten; only the two new chips get new names.
- **They count against the song limit.** `_require_budget("music", 1)` is
  unchanged and `usage_today` adds all three into `songs` - same model, same
  graph, same GPU seconds, and leaving them out would have made the chip
  picker the way round the limit.
- **`timings` gives them the music family and their own bucket.** The family
  is seconds of audio, so their first song ever already taught a jingle how long
  one second costs; the bucket is `"{kind}|{seconds}"`, which is byte-for-byte
  what a song was already filed under and keeps a 15s hum from inheriting a
  15s song's number.
- **The genre dropdown is hidden for a hum** (`HIDDEN_FOR`), on the page and
  in the tag line: "marching band, snare drums, bold brass" in front of a
  drone is a contradiction the model settles by making a march. Its bpm is a
  flat 60, since with no genre there is nothing to look one up from. Mood and
  main instrument are kept - a spooky hum and a harp drone are both perfectly
  good things to want.
- **The page does not get to decide what is sung.** The route forces `[inst]`
  for the two instrumental kinds whatever it was sent, and clamps the length
  to that kind's own bounds, so a page that has drifted cannot ask for a
  two-minute jingle with a verse in it.
- **`.sound-kind-pick`, not `.kind-pick`.** The picture card's "a picture or a
  character" already owns that class and card elements are looked up per card
  by class name. Two cards sharing one is exactly how the `.count` collision
  happened.

**One pre-existing bug fell out of this.** `setLengthRange` kept their current
length "if it still fits" by reading the input's value *after* setting
`max` - and setting `max` on a range input clamps the value there and then, so
the test always said yes. It never mattered while a card's bounds arrived once
at load; the chips change them on a tap, and a 30-second song became a
20-second jingle pinned to its ceiling rather than the default the kind asks
for. The value is read first now.

### Audio in the gallery

`MEDIA_SUFFIXES` grew a third media type, and that is the part that touched
everything:

- **A song's "poster" is a drawn waveform** (`_waveform_at`), decoded with PyAV
  and drawn with Pillow: one column per pixel at the *peak* of its slice, or
  every song looks like a flat grey bar. A wall of identical music-note icons
  would say nothing about which song is which; a waveform is recognisably the
  shape of that one.
- **The trash needed its own route.** Both trash grids drew anything that was
  not a video as an `<img>` pointing straight at the file, which for a song is
  an mp3 and a broken-image icon - a row of them on the parent page, which is
  how this was found. `GET /api/gallery/trash/{id}/poster` is `still(trashed=
  True)`, so the waveform is cached under the `trash-` prefix that already
  exists to stop a deleted clip and a new one that reused its name from sharing
  a picture. The child's page keeps the inline SVG as an `onerror` fallback.
- **The parent page's lightbox takes a media *string*, not `isVideo`.** A song
  is both halves - the waveform in the `<img>` and the file in an `<audio>`
  under it - which a boolean cannot express. The old boolean callers still
  work; `showBig` maps `true`/`false` on the way in.
- **`still()` now means "image or drawn"**, not "image or video". It was a
  two-way `!= "video"` test in half a dozen places; the ones that are genuinely
  video-only (frame grab, voice-over, sound effects, join) still say so and
  refuse a song with a reason.
- **`Job.media` is a property now.** It was `"video" if is_video else "image"`
  in three places, which put an `<img>` in front of an mp3 and told them
  "Your picture is ready!" about a song.
- **A song has a length, not a size.** `_dimensions()` returns None for audio
  rather than letting Pillow fail on every page load, and `_seconds()` caches
  the duration into the sidecar the same way width and height are cached. It
  has no *shape* either - the facts line was falling through to whatever
  orientation the card happened to be set to and calling a song "landscape".
- **The words are in the sidecar and in the viewer.** Opening a song showed the
  tags - a description of how it should *sound* - and not one word of what it
  actually sang, because `lyrics` was in `job.extra` and `_finish` only copies
  a named few of those onto the file. They are shown as written, in a `<pre>`:
  the line breaks and the `[Verse]` markers are how a song is read. An
  instrumental says so instead.
- **And they are recoverable.** ComfyUI writes the graph into an mp3's tags
  just as it does into an mp4's, and the words are right there in node 94, so
  `recover_sidecar()` brings back the lyrics of songs made before any of this
  existed. Two changes made that work: the guard was `if existing.get("prompt")
  : return False`, and a song has a prompt (the tags) while missing the half
  worth reading; and `_from_graph` reads the ACE node first, because a song's
  text is in named fields rather than in a prompt node. Adding lyrics to a
  sidecar that already had their idea does **not** set `recovered` - nothing was
  guessed, so the viewer should not warn about a file that is fine.

### The daily warm-up (`app/quiz.py`)

Three sums before the first make of the day, in whichever of addition,
subtraction, multiplication and division a parent has ticked, at one of three
levels. Division always comes out exact and subtraction never goes negative -
it is a warm-up, not an exam. There is no lockout and no score is kept, but
**any wrong answer means a whole new set of three**: retrying a single sum is a
guessing game, and the point is the arithmetic. The wrong ones are outlined for
a beat first so they can see which they were, then the new ones swap in.

- **Three levels, and one of them is what this always did.** `_easy`, `_medium`
  and `_hard` are a function each, because the numbers *are* the design here
  and a parent deciding whether a level suits their own child should be able to
  read the ranges at a glance rather than unpick a formula. **Easy** is single
  digits, adding to 20, tables to 5, and a subtraction whose answer is at least
  1 - a 0 reads as a trick. **Medium** is the generator this app has always
  had, unchanged line for line, and it is the default, so an installation that
  upgrades sees no difference at all. **Harder** is two- and three-digit
  numbers, tables to 12, division with an answer up to 60, and about a third of
  its sums have a second step (`a + b + c`, `a − b − c`).
- **A two-step sum stays inside its own operation.** A parent who ticked adding
  only should not be handed a subtraction to do, so the hard subtraction takes
  two bites out of a number big enough for both (at most 480 off at least 500)
  rather than mixing a `+` into a `−`.
- **Three rules hold at every level**, and they are why the levels are written
  out rather than scaled: no answer below zero, division that comes out exact,
  and nothing longer than the four digits that fit the answer box. Measured at
  390px: the widest sum these can produce (`951 − 209 − 142`) does not wrap and
  a four-digit answer does not clip, so **the overlay needed no change at all**.
- **Which kinds is a list, and it can never be empty.** `quiz_ops` is
  `"add,sub,mul,div"` in any order; the parent page springs the last tick back
  rather than saving none, the route writes back only what it recognises, and
  `operations()` falls through to addition for a settings file edited by hand
  into nonsense - a quiz with no questions in it is one they can never pass.
- **No sum is asked twice in one set.** With one kind ticked and easy numbers
  there are not many to draw from (easy times is sixteen distinct questions),
  and two identical rows read as a mistake in the page rather than as a
  question worth answering.
- **`quiz_level` and `quiz_ops` are ordinary settings**, per child
  (`PER_CHILD`), with `QUIZ_LEVEL` and `QUIZ_OPS` seeding them on the first
  start and never read again - see "Where settings live". They had a `"-"`/`""`
  sentinel meaning "whatever the environment says" and do not any more: the
  page had no option for that state, and neither has anything else now.
  `quiz_ops` is written back **cleaned**, in the canonical order, by both the
  route and the seed, so the database never holds a string the question
  generator would have to guess at.

- **The server makes and marks them.** The answers are never in the page. Open
  quizzes live in a dict keyed by a random token, with a fifteen-minute TTL - a
  restart mid-quiz costs them a fresh set of questions, which is a kinder
  failure than a token they could read the answers out of. `mark()` spends the
  token either way, so the same set can never be submitted twice.
- **It is enforced, not just displayed.** `_require_warmed_up()` hangs off
  `_require_idle()`, so every generate and upload route answers `403` until the
  sums are done - and `/api/gallery/join` calls it directly, since a movie is
  something they make too. The overlay is the friendly half; this is the half
  that means reloading past it achieves nothing. `_require_idle()` takes the
  request as a **required** argument: an optional one is an invitation to add a
  route that quietly skips the sums.
- **"Tomorrow" is a date, not a duration.** Passing sets `warm-up` to
  `<YYYY-MM-DD>.<hmac>`, HttpOnly, expiring at local midnight, and the check
  compares date strings. Being up late does not earn a second go, and neither
  does being up early.
- The pass is **also recorded server-side** (`quiz_passed_day`), and either one
  will do. The cookie lets the page decide without waiting; the record is what
  stops a cleared cookie - or a different browser - from being a fresh start.
  The signing key is a setting, made once, so a rebuild does not
  re-quiz them - and it never leaves the box: every route that answers with the
  settings goes through `gallery.public_settings()`, which strips it, because
  the key is a forged pass to anyone holding it.
- **"Ask for them again" rotates the key.** Clearing `quiz_passed_day`
  alone would do nothing on the one device that matters: `passed_today()` falls
  back to the cookie once the record is gone, and this morning's cookie is
  still a valid signature over today's date. `reset()` writes a fresh
  `quiz_secret`, which is what actually stops it verifying.
- **A closed factory means no sums.** Warming up for a door that will not open
  is a mean trick, so `paused` suppresses the quiz entirely and the "back soon"
  sign is the only thing they see. They are asked when it reopens; the pass is
  per calendar day, so being closed in the morning costs them nothing later.
- **Two different bypasses, deliberately.** On the *parent page*, "Skip them
  today" writes the same record a pass writes, so they are through for
  the day on every device. On the *quiz overlay* there is a folded-away "I'm a
  grown-up" box that takes `PARENT_PIN` and sets a separate, clock-limited
  cookie (`warm-up-grownup`, `quiz_bypass_minutes`, default 60) and writes
  **nothing** - it is for whoever is standing at the iPad needing the page for
  a minute, and they still owe the factory three sums. The box is only offered
  when a `PARENT_PIN` exists; without one it would be a skip button with their
  name on it. Five wrong PINs lock it for ten minutes, because four digits is
  ten thousand guesses and an afternoon.
- **The parent-page bypass is today-only by construction.** It writes the same
  record a real pass writes, so it expires with the date - there is no way to
  leave the quiz accidentally off tomorrow. `quiz_bypassed_day` is kept purely
  so the page can say "you waved them through" rather than "they did them".

### Who is using it (`app/profiles.py`)

One installation, one address, one GPU, and a nine-year-old who should not
have the chat tab or fifteen-second videos while their sister does. A profile
carries a name, a face, an age and its own copy of every rule a parent can set.

**One profile means no sign-in screen at all**, and that is the property the
whole design protects: the picker, the header chip and the "You" row in
Settings are all hidden when `profiles.several()` is false, so a household with
one child sees no trace of any of it. Verified in headless Chrome after the
fact, not assumed.

What a profile owns: its own gallery, its own daily limits, its own makers, its
own timetable, its own sums, its own colour scheme, and its own **age**, which
is the single thing most of the model instructions are really asking about.
What it does not: the email, the phone messages, the PIN, the trash, the pause
switch and the refusal rule - splitting those would mean configuring the same
thing three times.

- **A ContextVar, not sixty extra arguments.** `gallery.WHO` is set once per
  request by `WhoIsThis`, a **pure ASGI middleware** - deliberately not
  `@app.middleware("http")`, which runs `call_next` in its own task where a
  ContextVar set outside it is not reliably visible. Everything per-child hangs
  off that: the settings, the listing filter, the age in `branding.about()`.
  `None` means the household, which is what the janitor, the nightly email and
  the Telegram bot see, and is the right answer for all three.
- **The first child's rules are the household's.** The profile that `adopts`
  the pre-profiles files reads and writes the household scope itself
  (`gallery.IS_ADOPTER`, `_settings_owner`): there is never a scope of its own
  for that child, so a one-child installation keeps one set of rows, and the
  Telegram bot - which runs with nobody signed in - reads the same numbers the
  parent page just saved. Reviewing found the
  earlier version writing every Rules-tab save into a child file the bot never
  read, so `/today` said "no limit" while they were limited.
- **Every other child is laid over that, not copied from it.** A child's scope
  holds only what a parent has set for them specifically,
  so a limit nobody has touched for them still follows the first child's when
  it changes. Nothing is copied at add time except their own `quiz_secret`.
  `update_settings` splits a write by key, which is what stops a route
  accidentally giving one child their own copy of the SMTP settings - and what
  let the whole Rules tab become the same routes with `?who=` on the end.
  `get_settings` filters the child scope to `PER_CHILD` on the way in: a
  household key written there would shadow the household's own. The same
  mapping gives each added child their own `.prompts-<id>.json`, because a
  sibling's typed ideas are not a shelf to browse.
- **Adding a profile needs the parent PIN.** Not because a first name is
  sensitive, but because a new profile starts with its own daily allowance -
  without the gate, the way round "three pictures a day" is to make a fourth
  child. For the same reason a new profile inherits the first one's *rules*
  (`INHERIT`) and none of its counters, and gets its own `quiz_secret` so two
  children on one iPad do not share a pass on the sums.
- **Sealing, honestly: it is a curtain.** *While signed in as themselves*, a
  sibling cannot find another child's work in any listing and cannot star,
  rename, trash or build on it - `_may_change` on the changing routes and
  `_require_mine` on everything that makes a new file from an old one (i2v,
  first-and-last, join, frame grab, the avatar), both answering 404 rather
  than 403 so the refusal does not confirm the file exists. Two things the
  curtain does not cover, on purpose and said out loud: a direct media URL
  still opens, because the parent page shows those pictures in plain `<img>`
  tags that cannot carry a PIN; and **switching profiles is one tap with no
  PIN**, which is the Netflix model and the right one for a shared iPad, so a
  determined sibling can simply become the other child. A per-profile code,
  optional, is the obvious next step if a household needs the lock.
- **Removing somebody deletes nothing.** Their files keep their name, stop
  showing in anybody's gallery, and stay in the nightly email and on the parent
  page. If they were the profile that `adopts` - the one that owns everything
  made before profiles existed - that flag moves to whoever is left.
- **A face is a colour and an emoji until they make one.** That means a profile
  works the moment it is named, with the render as the treat rather than the
  toll. The wizard is three questions that compose a prompt and then **fill the
  Picture card and switch to it** - the same handoff "Animate this" uses. There
  is deliberately no avatar generator: a picture of you is a picture, with the
  same route, the same word filter, the same daily allowance and the same four
  at once. It sets square, four, and character mode, which is what puts the
  subject alone on a plain background - which is what makes a face read as a
  face at thirty pixels.
- **Picking reloads the page.** The title, the colours, the tabs that exist,
  the gallery, the countdown and the sums all belong to whoever was picked, and
  putting them back one at a time is a long list of things to forget one of.
  `sessionStorage` remembers that a choice was made this visit, or that reload
  would land straight back on the picker.
- **The bot is the household's, and knows it.** Telegram runs with nobody
  signed in, so `/open` waives *every* child's timetable
  (`schedule.open_anyway_for_everyone`). `/today`, `/hours` and the facts page
  answer per child once there is more than one, by running each answer under
  that child's context inside the `to_thread` call (`_as`) - the thread's
  context is a copy, so nothing leaks back. `/more 5` is the first child's;
  `/more 5 for Max` is anybody's, and an unknown name is refused by name
  rather than topping up the wrong child.
- **The nightly email names the maker** under each thumbnail once there is
  more than one child (`digest._maker`), and never before - "Ada" on every
  one of Ada's pictures says nothing. The summary sentence and the subject
  use `branding.KID_NAME`, which is now the name on the profile that `adopts`
  rather than a variable - so renaming the first child changes them.
- **Files with no `who` are the adopter's everywhere.** The server's `mine()`
  gives them to the profile flagged `adopts`; the parent page does the same
  when it marks today's tiles, which is why `profiles.public()` exposes that
  flag - without it those tiles read "nobody in particular".
- **`PUT /api/profiles/shared` is declared above `/api/profiles/{pid}`.**
  Routes match in declaration order; with it second, "shared" was read as a
  profile id and answered "no such profile".

The parent page has its own tab for it, **Who uses it**, second in the row -
it is about people rather than about rules, and it is where a second person is
added in the first place. The Rules tab carries a "Whose rules?" bar that
scopes everything below it, with a line saying which cards above are the
household's.

### The family shelf

Profiles gave each child their own gallery, and the only way out of that was
the parent switch that shows everybody everything. The shelf is the middle
ground: they mark one picture, video or song "show the family", and it turns up
on a **Family** shelf in every profile's Gallery while the rest of their work
stays theirs.

- **One flag in the sidecar**, `family`, stored and toggled exactly like the
  star (`gallery.set_family`, `PUT /api/gallery/{id}/family`). No index, so
  nothing to rewrite when a file appears and nothing to corrupt when two writes
  race, and the flag travels with the file into the trash and back.
- **Only the listing is widened, not the curtain.** `listing(family=True)`
  adds other children's shared items back in; `mine()` and `belongs_to_me()`
  are untouched, so every route that *changes* something still refuses. A
  sibling can look at a family item and save it, and cannot star, rename, tag,
  trash, build on it (i2v, frame grab, join, avatar - all still `_require_mine`)
  or take it off the shelf. `_may_change` is the only gate on the new route,
  which means sharing and unsharing both belong to whoever made it.
- **`family=True` is opt-in and `GET /api/gallery` is the only caller that
  passes it.** Everything else asking `listing()` a question is asking "what is
  theirs" rather than "what may they see": `usage_today` counts what they have made
  against their daily limit, `all_tags` lists the words they have typed, the
  character counts are their cast's. Defaulting the other way would have let a
  sister putting a video on the shelf spend this child's three videos for the
  day - verified with two profiles: Ada's music count read 1 and the
  sibling's 0 with the same song on the shelf.
- **Each item says whose it is.** `listing()` returns `who` and a server-side
  `mine` (computed there because "no owner recorded" means the profile carrying
  `adopts`, and only the server knows which that is). A tile that is not theirs
  carries the maker's face and name in the top-right corner, and the viewer
  says "Ada made this" and retitles the prompt "What Ada asked for". A
  picture that is not theirs reading as theirs is the one thing this shelf must not
  do.
- **Somebody else's lives on the Family shelf and nowhere else.** Pictures,
  Videos and Favourites are theirs - a star on a sibling's picture is theirs, and
  "You've made 16 things" should not count a sibling's song. Their *own* shared
  things do show on the Family shelf as well, or they would have no way to see
  what they have put out there before deciding to take it back.
- **They cannot be chosen.** Choosing feeds delete, tag, join, save-as-zip and
  the "pick a picture" handoffs, and the server refuses nearly all of those on
  somebody else's file, so a family tile takes no tick and a tap always opens
  the viewer. "Choose all" counts only theirs.
- **Not armed.** Sharing and unsharing lose nothing and the same button undoes
  either, so a second tap would only be in the way - `arm()` is for the things
  that cannot be taken back.
- **With one profile none of it exists.** The shelf and the button are both
  gated on `/api/profiles` → `pick`, the same flag that hides the picker and
  the header chip. Checked in headless Chrome with the second profile removed:
  no Family shelf, no button, all sixteen items selectable, the same buttons in
  the viewer as before. Because that answer arrives on its own fetch, and races
  the gallery's, `loadWho` repaints the Gallery card from the listing already
  in hand rather than asking the server twice.

### When it is open (`app/schedule.py`)

The pause switch answers "is it open *now*", which means remembering to flip
it twice a day. A timetable answers it for the week. Both exist and the switch
wins: a timetable is the normal case and the switch is the exception to it.

The format is one line in the settings, readable and editable by hand -
`mon=16:00-18:30;...;sat=09:00-12:00,14:00-20:00;sun=`. Up to four windows a
day; a day with nothing after the `=` is shut; anything unparseable is dropped
rather than raising, because a typo in Wednesday should cost Wednesday and not
the week. `OPEN_HOURS` in `.env` seeds it on the first start and is not read
again. `schedule_on` is -1 by default, meaning **on if there is a timetable at
all**: setting times and then having to tick a box to make them apply is a
trap. That is the only tri-state left anywhere in the settings, and it is not
an environment indirection - see "Where settings live".

Four things it does deliberately:

- **It says when, not just no.** "Back soon" is the right sign for a parent who
  shut it by hand and the wrong one for a timetable, where the answer is known.
  `reopen_line()` gives the overlay "It opens at 4pm. See you then!" on its own,
  because the overlay already says it is closed in large letters over a sleeping
  factory; `closed_message()` puts the whole sentence in the 503 body, which has
  no such heading.
- **It warns before it shuts.** `closes_in` appears on `/api/allowance` only
  inside the last `CLOSING_SOON` (30) minutes - long enough to finish a video
  and start one more, short enough that it is not on the screen all afternoon.
  The overlay arriving in the middle of typing is the thing this prevents.
- **It can be waived.** `POST /api/parent/schedule/override` opens it for the
  rest of today without touching the timetable, and `/open` on Telegram does
  the same when the timetable is what shut it. It expires at midnight on its
  own, which is the part that makes it safe to reach for - a timetable with no
  way round it is a trap, because the one evening it matters the fix would be
  editing seven rows and remembering to put them back.
- **It never stops a render already going.** Like the pause switch it is
  checked when something starts. Taking a video away at 17:59 because it would
  finish at 18:01 would teach them not to start anything after half past.

**The parent grid stops repainting once it is touched.** The page reloads
itself every 30 seconds, which is fine for a number in a box and ruinous for
seven rows somebody is halfway through editing. `hoursDirty` freezes the grid
until Save; the live status line above it is outside that guard, because it is
read-only and it is the point.

A week out lands on the same weekday it is now, so `opens_day` says "next
Tuesday" rather than "Tuesday" past six days - only a one-day-a-week timetable
can produce that, which is exactly where the ambiguity would hurt most.

### Daily limits

`daily_image_limit` and `daily_video_limit` (0 = no limit) cap how many of each
they can make between local midnights. Three things are worth knowing:

- **`usage_today()` counts the trash as well as the gallery.** A limit that a
  delete gives back is not a limit; it just teaches them to delete the ones they
  likes least.
- **The countdown is their own.** `GET /api/allowance` returns `{paused,
  allowance:{image,video}}` where `left` is `null` when no limit is set - that
  is the difference between "no countdown to show" and "none left", and the
  page must not confuse the two. The page polls it every minute, after every
  finished job, and after any refusal, and disables the start button when
  `left` hits 0. The server refuses with 409 regardless; the countdown only
  means the refusal is never a surprise.
- **Top-ups expire on their own.** `POST /api/parent/bonus {kind, extra}`
  adds to today only - `bonus_day` carries the date it was granted, so it
  stops counting at midnight without anyone having to remember to undo it.
  `extra` may be negative, which is how "take today's extras back" works.

### The nightly email (`app/digest.py`)

One mail a day with a letterboxed 320x200 thumbnail of everything they made,
their words under each, sent as `multipart/alternative` (plain text + HTML with
the images `cid:`-attached to the **HTML part**, not the message - attach them
to the message and the `cid:` references point at nothing). Videos use their
cached poster frame. Every thumbnail is letterboxed into the same box on a
light mat: email clients cannot be relied on for `object-fit`, and a row of
tiles at different heights looks broken rather than varied.

- **It goes out through Apprise**, like the phone messages, rather than a
  second hand-rolled smtplib path. `mail_url()` turns the relay settings into
  the one `mailto://` URL Apprise wants - and is rebuilt on every send now,
  not held at import, so a corrected host reaches tonight's email. The
  "Apprise URL" box takes anything else Apprise speaks - Gmail with an app
  password, SendGrid, SES - and wins over the rest of the card.

  Two things that cost an afternoon. **Apprise matches a `cid:` in the HTML
  against an attachment's *filename***, so the thumbnails are written to a
  temp directory as `shot-00.jpg` and the HTML says `cid:shot-00.jpg`; that is
  why `built()` is a context manager rather than returning a message. And
  **Apprise's From validator rejects a straight apostrophe** - "Ada's AI
  Factory" is refused and no mail goes at all - while the typographic one is
  accepted and RFC 2047-encoded properly. Swapping it is the workaround and
  the better typography; anything else it dislikes drops the display name
  rather than the email.

  Verified on the real relay: `multipart/related` wrapping a
  `multipart/alternative` of text and HTML, then sixteen `image/jpeg` parts
  each `inline` with a `Content-ID` matching a `cid:` in the body. Apprise
  sends one message **per recipient** rather than one with several on the To
  line, which is a change from before and arguably the better behaviour.

- **All of it is on the Alerts tab now**, in two halves of one card: whether it
  goes, when, how many thumbnails and whether the "they have run out" note goes
  too; and under an **Email server** heading, the recipients, the relay, the
  port, STARTTLS, the username, the sender, the display name and the two
  subject templates. Every `DIGEST_*` variable seeds its row on the first start
  and is not read again. **Except the two credentials**, which are on that card
  too but are *not* rows - see "The other nine" and "Backup and restore" for
  why - with `DIGEST_SMTP_PASS` and `DIGEST_URL` in `.env` behind them. Those
  are the relay password and the one raw Apprise URL that overrides the whole
  card, whose documented shape is `mailtos://user:apppassword@gmail.com` and is
  therefore a password too. The card reports only that each is set and where it
  came from, takes a new one, and clears back to `.env`; it never shows one
  back, and `digest.smtp_pass()` and `digest.direct_url()` are read as the
  relay URL is built, so a new one reaches tonight's email. There is a **Send a test
  email** button beside "Send a report now": two lines through the relay, no
  thumbnails, because the question after typing an address is whether the
  address works and an empty day answers it as well as a busy one. With nothing
  set up it answers 400 and a sentence, not a traceback.
- **Nothing is sent on a day they made nothing.**
- **Today's trash is in it.** Something they made and then deleted is still
  something they made, and it sits recoverable in the trash for `trash_days`,
  so it appears dimmed with a "deleted" badge and a line saying how to put it
  back. This also keeps the email agreeing with the daily limits, which have
  counted the trash from the start. Drawing those tiles is why
  `gallery.still(id, trashed)` exists: it hands back the picture itself, or a
  video's cached poster frame, from either place. Posters for trashed videos
  are cached under a `trash-` prefix - ComfyUI reuses a filename once its file
  is gone, so a deleted clip and a new one can share a name and must not share
  a poster - and are dropped on the way out of the trash in either direction.
- The scheduler is a plain minute loop, not cron. It fires inside a ten-minute
  window after the configured time so a restart cannot skip the day, and
  `digest_last_sent` (one date string) is what stops a second copy. A send
  that *fails* does not set it, so the next minute in the window tries again.
- "Send a report now" on the parent page hits `POST /api/parent/digest/send`,
  which always sends even on an empty day and does **not** touch
  `digest_last_sent` - a test at 3pm must not cancel the real one at 9pm.

### Messages to a phone (`app/notify.py`)

The nightly email is a good end-of-day summary and a bad way to be told
something *now*. Apprise is the right-now half: one URL per service in
`NOTIFY_URLS` and it speaks Telegram, WhatsApp, Signal, ntfy, Discord, Matrix,
Pushover and about 150 others - 155 schemes in 1.13.1 - rather than 150
integrations to keep working.

Five things can go out, each switchable on the parent page: **every picture and
video as it lands** (optionally with the file attached, which is the "send me a
copy of everything" a parent actually wants), **running out** for the day, **the
daily summary** as text, **anything the word filter stopped**, which is the one
worth knowing about immediately rather than at nine tonight, and **somebody
getting the parent PIN wrong**.

The PIN one is the only event that goes by *both* channels - `notify.bad_pin()`
and `digest.pin_notice()` - under one switch, because wanting to be told is one
want and not two. Its rate limit lives in `main._bad_pin()` rather than in
either sender, so that one limit covers both: one alert per ten minutes however
many guesses there are, plus the one that trips the lockout, which always goes.
A child at the keypad must not be able to fill a mailbox.

Each place can also be told *what* it wants, by naming events in front of the
URL the way Apprise's own config files do - `made`, `limit`, `digest`,
`flagged`, plus `file` as a modifier meaning "attach the picture for this one":

```
NOTIFY_URLS="
  made,file=tgram://<bot token>/<chat id>
  limit,flagged=ntfy://ntfy.sh/mytopic
  mailto://user:pass@smtp.example.net
"
```

- **A target that names no event gets every event.** So does one with a tag
  nobody recognises, which is logged: a typo should be noisy rather than
  silently mute a parent's only alert.
- Whitespace separates targets; a comma separates *tags*. It also still splits
  bare URLs, so a pre-tags `a,b` list keeps working - `_split()` only does the
  comma split on a token with no tag prefix.
- Routing is ours, not Apprise's tag matching: `_parse()` builds `Target`
  objects and each send builds a box from the targets that asked for that
  event. Explicit, and testable without a network.
- An attachment is per *send*, not per target, so `made` is up to two sends:
  one carrying the file to the places that want it, one without to the rest.
  `_send_split()` does that. The parent-page attach switch means "all of them";
  the `file` tag means "this one regardless".
- The parent-page switches are still master switches - an event turned off
  there goes nowhere, whatever the tags say.
- Everything is off until at least one URL is set. Where they go is a box on
  that same card now, with `NOTIFY_URLS` in `.env` behind it - `app/config.py`,
  and `notify.targets()` re-parses when the string moves, so a change reaches
  the next message rather than the next restart. `settings()` reports only the
  URL *scheme* to the browser, never the token, and `urls` is
  `config.state()`: set or not, and where from. `routes` carries the scheme
  and the event names for the list on the parent page - same rule.
- Sending is `asyncio.to_thread` behind `notify.fire()`, which holds the task
  in a module-level set. Nothing here may make a child wait on somebody's push
  service, and nothing here may raise into a render.
- Attachments over `notify_max_mb` (20, and a box on the card) are mentioned
  rather than sent. A parent would rather have the note than nothing. It is a
  property of whichever service the URLs point at - Telegram takes 50MB, most
  others less - and the person holding the phone is the one who knows which,
  which is why it stopped being a variable.
- `digest.limit_notice()` treats the phone and the email as separate wants: a
  household may have a Telegram bot and no mail relay at all, so the early
  return now checks both.

### After the filter says no (`app/lockdown.py`)

Refusing the thing and telling the grown-ups are two different jobs, and this
is the second. One entry point, `refused(trigger, where, text, image)`, called
from the photo screen, from `_checked()` and from the chat.

- **Closing the factory is off by default**, and the setting has three levels
  rather than a checkbox. A word filter that closes the whole app punishes a
  child for typing "gun" in a sentence about a water pistol; a photo the vision
  model called unsuitable is a much stronger signal, because it looked at an
  actual image. So `"photo"` is the level to recommend and `"words"` is the
  strict one.
- `close_on` stores `"-"` for "nobody has chosen", the string equivalent of the
  `-1` the other tri-states use, because `""` has to mean a parent deliberately
  choosing *just tell me* and winning over `CLOSE_ON_REFUSAL`. The summary
  sends the *effective* value as a top-level `close_on`, since the dropdown has
  no option for `"-"`.
- **A closure is always reported**, whatever the notification switches say: the
  parent is the only person who can reopen it. A refusal that closed nothing is
  an ordinary filter alert and obeys the `flagged` switch, or turning that off
  would stop meaning anything.
- Reopening from the parent page clears `closed_reason`, so the reason on the
  page is always about the closure being looked at.
- It has its own `fire()` rather than `notify.fire()`, which does nothing when
  no phone is configured - closing the factory and emailing about it do not
  depend on there being a Telegram bot.
- `notify.flagged()` is gone; this replaced it. Two paths for one event would
  have drifted, and this one carries the refused picture as an attachment.

### Asking the bot things (`app/telegram.py`)

The other half of `notify.py`: the same bot token is long-polled for messages,
so a parent can ask it things from wherever they are. `/today`, `/more 5`,
`/pause`, `/open`, `/last`, `/help` - and anything else goes to Ollama with a
page of today's real numbers.

- **Reading is the model's job; writing is not.** A question is answered from
  a generated brief with a rule that nothing may be invented; everything that
  *changes* the app is a slash command a person typed. A model that misreads
  "give them five more" as an instruction is unable to act on it.
- **The allowlist is the whole security story**, and it is a box on the card
  now (`telegram_chat_ids`). Left empty it falls back to the ids inside the
  `tgram://` URL that sends the notifications, which is where they have always
  been derived from - and those are what the box shows as its placeholder, so
  the fallback is visible rather than folklore. The bot's username is
  discoverable, so anyone can message it; anyone not on the list is logged and
  ignored with no reply. `allowed_ids()` is read **per message**, so adding
  somebody reaches the next one they send. With a token and no ids the card is
  still shown, `enabled()` is false, and filling the box in starts the loop
  within half a minute. **The token is a box on that card too** - `token()`,
  read at the call, page over `.env` over the `tgram://` URL - so `run()` asks
  for it inside the loop rather than returning early without one, and a bot set
  up from the page starts listening within half a minute as well. It is kept
  out of the settings table, and so out of the backup, like the relay
  password.
- **Which model answers is a setting**, `telegram_model`, empty by default and
  empty meaning "the same as the idea helper". Nothing here is ever shown a
  picture, so this is the one of the three that may be a words-only model.
- **Never loads a model during a render.** ComfyUI and the helper share one
  card. `_busy_now()` in main hands the loop the running job; if there is one,
  the question is answered from the brief alone and the GPU is left alone.
  Slash commands cost nothing and always work.
- **The token is filtered out of the log.** httpx logs every request at INFO
  with the full URL, and here the URL *is* the credential -
  `/bot<token>/getUpdates`, every fifty seconds, forever. `_HideToken` is a
  `logging.Filter` on the `httpx` logger that rewrites the rendered message.
- `/lock` bolts the parent page shut on top of the PIN, and `/unlock` opens it
  again *and* clears the wrong-PIN throttle on **all four** PIN boxes -
  somebody locked out by another person's guessing wants one word to fix that.
  It reached only one of them until `app/pinbox.py` existed, because the other
  two lived in `main`, which this file cannot import; it said "any wrong-PIN
  lockout is cleared" either way, which is the kind of true-sounding sentence
  that teaches a parent to stop believing the next one. It now names what it
  cleared, or says there was nothing to clear. `_parent()` checks the lock
  before it looks at the PIN, because the point of it is that knowing the PIN
  is not enough. Telegram is the only way back: the page that would carry the
  switch is the page it locks. (The other way out is the `parent_locked`
  setting.)
- `setMyCommands` runs when the switch is first seen on, not at startup, so
  turning it on from the parent page makes the menu appear without a restart.
  Commands that are not registered are invisible, which is the same as not
  existing.
- Pending updates are drained with `offset=-1` at startup and thrown away. A
  night of queued messages must not run as a night of commands.
- The brief says explicitly when a limit is *not* set. Without that sentence,
  "how many are left?" got answered by counting something else and reporting
  it as an allowance.

### The "they have run out" email

When `_require_budget` refuses them, it also fires `digest.limit_notice(kind)`
as a background task - they must not wait on an SMTP handshake to be told no.
Once a day per kind: `limit_mail_image` / `limit_mail_video` hold the date, and
the date is written **before** the send, so a relay that hangs cannot turn into
one email per tap. It has its own switch (`DIGEST_LIMIT_NOTICE`, and a checkbox
on the parent page) because wanting the nightly summary and wanting this are
different wants.
- **Live stats** (`app/stats.py`): a sampler task reads NVML once a second
  (utilisation, VRAM) and whole-machine CPU from `/proc/stat` deltas. The
  snapshot rides along on `/api/job/{id}` so the page shows "GPU 98% · 14.1 of
  16.3 GB · CPU 12%" under the bar. Needs `gpus: all` on the service; without
  it the GPU fields are None and the page leaves them out. It shares one flex
  row (`.status-line`) with the elapsed/ETA text so the status block stays
  three lines tall; each figure is its own `<span>` and the " · " between them
  comes from CSS, so hiding the VRAM one under 560px does not strand its
  separator.

### Drawing, "what happens next?", and the rest of the batch

- **Draw one**: a pointer-events canvas in a full-screen sheet (finger or
  Pencil, pressure honoured for a pen), sized at device pixel ratio, with an
  undo stack of twenty. `toBlob` → the ordinary `/api/upload` path, so the
  vision helper and screening apply to a drawing exactly as to a photo.
  `.canvas-wrap` has `touch-action: none` - without it a stroke scrolls.
- **What happens next?**: `pickSource({galleryId})` with a *video* id; the i2v
  route uses `gallery.last_frame()` (PyAV seeks to 0.5s before the end rather
  than decoding all 360 frames). The thumbnail is `/last-frame`. The vision
  helper looks at the same frame.
- **Try again**: the card remembers `lastBody` and re-posts it; the seed is
  random server-side, so it is the same request and a new picture.
- **Share**: `navigator.share({files})`, shown only when `canShare` says files
  are supported (iOS Safari, not desktop Chrome). Fetches the blob first.
- **Ding**: three sine notes via Web Audio. The context is created on the Go
  tap - Safari refuses to make a sound without a gesture first.

### Deleting asks in the button

Tapping Delete turns that button into "Really delete it?" and a second tap does
it; it disarms itself after 4 seconds, if they tap anything else, or if the
selection count changes. This replaced a confirmation panel below the button,
which was easy to miss - the eye stays on the thing just tapped.

It asks in the same way wherever it is, and it is now under the thing they have
just made as well as in the viewer: binning a picture they can see they do not
want used to mean opening the Gallery and finding it again.

- **`binThem()` is the one trip to the trash.** The Delete under a result, the
  bin on one of four, and "Keep this one" binning the three they did not choose
  all go through it - one id takes `DELETE /api/gallery/{id}`, several take the
  bulk route, and either way the Gallery strip is repainted afterwards. It
  asks nothing about the allowance, deliberately: `usage_today` counts the
  trash, so a delete never gives a picture back, and refreshing the countdown
  there would only suggest it might.
- **What is left is the line and "Try again".** Every other button in that row
  needed the file - animate it, cut it out, put it at the top - and a button
  that cannot work is worse than no button. "Try again" only appears if the
  card still remembers what it sent, which after a reload it does not.
- **Undo puts the result back, not just the file.** `offerUndo()` takes a
  `back` function that re-renders the card's result, or re-shows the "it's
  ready" line with its own Delete on it; returning true from it means it has
  said so itself and the "Put back!" line would paint over what it just put up.
- **Four at once: one bin per tile**, the glyph alone in the tile's far corner
  from "Keep this one" - two worded buttons do not fit a 151px tile at 390px,
  and along the same edge the bin sat on the end of the other one. A tile they
  has already binned is not sent again when they later keep one, because the
  bulk route refuses an empty list.
- **A comic's page, not its panels.** The panels are pictures of theirs on their
  own shelf and are usually worth keeping even when the sheet is not, so
  binning the page quietly binning six other things would be a delete they did
  not ask for. "Keep this one" bins the leftovers because those are rivals to
  the same picture; panels are parts of this one. A film is the same: the
  joined film goes, the clips it was made of stay.
- **Disabled while anything is rendering**, exactly as "Start again" is -
  `setBusy` reaches into each card's result for `.bin`. It never appears on a
  failed or cancelled result, because only a finished job draws one. The
  `.bin-one` on a tile is the exception and is left alone: four at once fills
  the grid in one picture at a time, and each of those tiles is a finished
  picture the moment it appears.
- **The toast grew a second button** for the renders they start from their
  gallery: those answer through `watchDerived()`, which has no card to draw a
  result into, so that line is the whole of what they see. It holds the toast
  open while it is asking. The toast is `width: max-content` for this - fixed
  and pulled back by half its own width, it is offered only half the screen,
  and without that it wrapped a line that fitted.

### Result parsing

`SaveImage` and `SaveVideo` use different keys in the history `outputs` blob
(`images` vs `videos`). Scan every value in the node's outputs for a list of
dicts containing a `filename` key rather than hardcoding either.

## The chat tab

A fifth tab where they can talk to `gemma4:12b` through Ollama. `app/chat.py`.
Which model, like the other two, is a dropdown on the parent page
(`chat_model`, seeded from `CHAT_MODEL`); `chat.model()` is read per message,
and `available()` - which is what hides the tab - asks about whichever one is
chosen now.

**It does not stream, and that is the point.** A streamed reply is on the
screen before any filter could have looked at it. The whole reply is generated,
checked, and only then shown. The cost is about twenty seconds on the first
message (model load) and three or four after that, which is why there is a
thinking animation rather than a spinner.

**The blocklist here is deliberately not the one used for prompts.** The full
list exists to keep things out of a picture, so it blocks ordinary words that
only matter to an image model: `blood`, `wound`, `gun`, `beer`, `terrifying`.
Applying it to a conversation refuses *"why is blood red?"*, which is both
useless and baffling to them. So `CHAT_CATEGORIES` checks only the categories
where a match is almost never innocent - sexual, minors, hate, real people -
and leaves the rest to the system prompt, which tells the model to decline and
redirect. Measured, on the live model:

| They type | What happens |
|---|---|
| `show me a naked lady` | Blocked before the model sees it, flagged in the transcript |
| `why is blood red?` | Not blocked; the model itself redirects to something it can help with |
| `Donne-moi une idée de dessin` | Answered in French |
| `Are you a real person?` | *"I'm not a person; I'm a computer program"* |

"Check the chat against the whole picture word list" on the Rules tab uses the
whole blocklist instead. Off by default, and `CHAT_STRICT` only seeds it.

**The transcript is the real backstop.** Every turn goes to `.chat.json` beside
the media, capped at `chat_keep_messages` (400, and a box on the parent page),
and the whole thing is on the parent page with anything the filter stopped
marked in red. The system prompt
tells them that their grown-ups can read it, and to say so plainly if they ask.
The nightly email says how much they used it.

**VRAM.** gemma4:12b is 7.6GB and holds the card for `chat_keep_alive` (5m,
on the parent page under "The helpers") so
a back-and-forth does not reload it every turn. That does not fit alongside a
render, so two things happen: chat is refused outright while a job is running
(409, with a friendly line), and `main._started` calls `chat.release()` before
every single generate. Verified: release drops VRAM from 9890 MiB to 785 MiB.

---

## Seeds, and "Make it again, but…"

`workflows.pick_seed()` resolves the seed once, the caller hands the same value
to the graph builder *and* to the job, and `jobs._finish` writes it into the
sidecar. The video graphs sample twice and derive their second seed from the
first, so one recorded number really does reproduce the whole clip.

Two buttons that look similar and are not:

- **Make another like this** refills the card with their words and dropdowns and
  a *new* seed. A different picture that matches the same description.
- **Make it again, but…** does the same and hands back the *old* seed, so
  changing one word gives a variation on the picture they already have.

Verified: the same prompt at seed `46032651551630` produced two byte-identical
PNGs. The seed is spent on exactly one generation - `lastBody` deliberately
carries none, so the "Try again" button under the result still means "give me a
different one".

---

## Films: several clips that actually join up

The video card's third mode. Ollama writes 2-4 beats of one story, the first is
filmed from words, and **every clip after that starts from the last frame of
the one before**. That is the whole difference between this and making three
videos about the same subject.

It needed two things from the job registry:

- **An entry in the graph list may be an async callable**, taking the outputs so
  far and returning the next graph. Clip two cannot be built until clip one has
  produced a file to take a frame from.
- **An `after` callable** run once every graph is done, whose return value is
  merged into `job.extra`. The film uses it to `gallery.join` the clips, and the
  page plays `extra.movie` rather than the first clip.

The progress bar is divided between the graphs *and* the join, or the last clip
would finish at 100% and then sit there while the stitch ran.

It costs one of their daily videos per part, which is honestly what it costs, and
the countdown on the card says so before they tap.

---

## The Story maker (`module story`)

**"Can we have a workflow mode: generate picture, generate sound, generate
film?"** This is that, as a sixth tab, and the thing worth understanding first
is that **it renders nothing of its own.** Every step is a route one of the
other cards already owns, run in order, with what it made on the screen before
the next one starts:

| Step | Route it reuses | What it spends |
|---|---|---|
| 1. The idea | `POST /api/script` with `kind: "story"` (and Surprise me) | nothing |
| 2. The picture | `POST /api/generate/image` | one picture |
| 3. The film | `POST /api/generate/story`, with `source_gallery_id` = the picture | one video per part |
| 4. The song | `POST /api/song-words` then `POST /api/generate/music` | one song |
| 5. Put it together | `POST /api/story/finish` | nothing |

**The order is the whole feature.** Filming three parts from a picture they have
not seen is three minutes of GPU spent on a guess; showing them the opening
frame first costs twelve seconds and makes the rest theirs. That is also why the
picture step's button is "Make another" rather than four-at-once: a grid of
four rivals is a second decision inside a decision, and they can tap again as
many times as they like for the same cost.

- **No allowance of its own, on purpose.** A "story allowance" would be a
  fourth number on the parent page that means the same as the three already
  there, and a way round them. Each step calls the same `_require_budget` its
  own card does, and the countdown on the card follows the step
  (`spendsOf(card)` rather than `SPENDS[card.kind]`, which is fixed per card
  for the other five).
- **`kind: "storyfilm"`, and *not* `"story"`.** `story` is already the film
  mode's *job* kind, threaded through `jobs`, `timings`, `digest` and the video
  card's mode switch. The sidecar carries `story_of: {picture, film, song}`,
  `song_of` and `kept_original_sound`; it lands on the **Films shelf** with its
  own badge, 🎭 Story film, so it is not mistaken for the film it was made of.
- **The film opens on a title card now.** `_join_story` used to pass
  `title_card=None` - the join has always been able to draw one and the Video
  card's film simply never sent one. The Story card draws it on a canvas the
  way the movie maker does (the server has no fonts and needs none) and sends
  it as a data URL, which `_title_card()` runs through `uploads.keep` like any
  other picture off a browser. A card that will not decode costs the card,
  never the film.

### Putting it together, which is a remux and not a render

`gallery.add_song()` on `_with_new_audio`, exactly like their voice-over and the
sound effects: **the video packets are copied across, not re-encoded.**
Measured on the real end-to-end run - 290 video packets and 1,247,476 bytes in
the film and 290 packets and 1,247,476 bytes in the story film, with a
different soundtrack. It costs no GPU and loses not one bit of the film, which
is why it is not one of their daily videos and has no job to watch.

- **The song goes over at a constant ratio**, `SONG_UNDER = 0.25`, and this is
  deliberately **not** the voice-over's duck. `_mixed` drops the original only
  while they are actually talking, detected in 20ms blocks - and a song is
  talking from the first second to the last, so that detector would be on
  throughout and would cost a convolution to say what one number says. The
  `ratio` argument on `_with_new_audio` is that one number; `ratio=None` still
  means "the caller has already mixed it", which is what the voice and the
  sound effects hand over.
- **The film's own sound is kept by default.** LTX writes music, effects and
  the line their character says, and throwing that away would lose the line. The
  tick box on the last step replaces it instead. Verified by correlating the
  result against both sources over the same window: **0.987 against the song
  and 0.126 against the film's own audio.**
- The song is truncated to the film's length by `_pcm`, which is also what the
  song step asks for in the first place - the film's real `duration` off the
  gallery listing, clamped to the `music_*_seconds` bounds - so the trim is
  usually a fraction of a second of tail.

### Resuming, which is the part that had a bug in it

The card remembers `{step, ids, jobId, done}` in `localStorage` and the ids are
what matter: a Stop half way through the film, or a reload, must not lose the
picture they chose or the song they have already heard.

**`story.jobId` is the only thing that can tell a reload the running job is
this card's**, because three of the four routes belong to other cards -
`/api/active` says a job of kind `image` is running and nothing else. The first
version wrote the id in a `setTimeout(..., 0)`, which fires *before* the route
has answered, so it wrote `null`; reloading twenty seconds into a film came
back on the **Video** tab. It is written the moment `card.jobId` exists now.
Verified: a reload mid-film comes back on the Story tab at 10%, with the
opening picture still on the card.

Every step is skippable (the picture and the song) or redoable ("Make another"
on any of them), and stepping back along the trail shows what that step made
rather than starting it again.

### What it costs, measured

One real run on this box, at 2 parts of 5s, landscape, normal quality:

| Step | Wall clock |
|---|---|
| The opening picture | 13s |
| The film (2 parts + the join) | 104s |
| The song (words + 12s of audio) | 22s |
| Putting it together | under a second, no GPU |

---

## Stickers

Flood fill inwards from the edges and make everything it reaches transparent.
That is the honest description: there is no subject-detection model here, only
*"the background is whatever touches the edge and looks like the edge"*. It
works beautifully on "a duck on a plain white background" and not at all on a
photo of a room.

The fill is repeated dilation in numpy - four array shifts per pass - on a
320px copy, so a picture that would take most of a minute pixel by pixel takes
a few milliseconds.

**The test for "did this work" is how much of the border the fill reached, not
how much of the picture it removed.** Measured across a plain background, a
gradient, and two real photos, that is the line that separates them cleanly:

| Picture | Border cleared | Verdict |
|---|---|---|
| Subject on a plain colour | 100% at the very first tolerance | sticker |
| Subject on a gradient | 100%, but only at tolerance 90 | sticker |
| Photo of a room | never past 79% at any tolerance | refused |

Area removed is *not* that signal - a busy photo happily gives up a third of
itself and still looks half-eaten. There is deliberately no ceiling on the
proportion removed either: a duck on white is 95% background, and that is the
ideal case, not a failure. What catches "the subject went with the background"
is an empty bounding box, plus `STICKER_MAX_KEPT` - if what is left still fills
more than 72% of the frame, the fill found a uniform wall behind a room rather
than an object, and it is refused with a reason they can act on.

---

### Asking for a cuttable picture in the first place

The cut-out is only as good as the background it is given, and "type *on a
plain white background*" is exactly the kind of hidden knowledge this app
exists to remove. So the picture card has a two-way picker - **A picture** or
**A character** - and character mode appends `styles.CUTOUT`: the whole subject
centred with space around it, alone on flat white, no scenery, no floor, no
shadow.

Two of the dropdowns have to go with it. A place and a plain background are
contradictory instructions and Flux settles that by drawing the place; a
lighting choice puts coloured light and cast shadows onto what needs to stay
flat white. So `CUTOUT_DROPS` is `("scene", "lighting")` - the page hides both,
and the server strips them too, because hiding a control is not the same as it
being impossible to send. Style and mood survive: cartoon, watercolour or pixel
art is still theirs, which is why `CUTOUT` deliberately says nothing about art
style.

Measured, same idea, same style choice, same requested scene:

| Mode | Prompt that reached ComfyUI | Cut-out |
|---|---|---|
| A picture | `…, set deep in a mossy green forest, in a bright, friendly cartoon style` | refused: background too busy |
| A character | `…, in a bright, friendly cartoon style, the whole subject visible and centred…` | 575×777 sticker, 46% transparent |

`cutout` is recorded in the sidecar, so "Make another like this" comes back as
a character too. And "✂️ Turn it into a sticker" now sits in the actions under
the finished picture, not only in the gallery viewer - a character picture
exists to be cut out, so making them go and find it again first was a step for
no reason.

---

## Three more things to make out of one they already have

The sticker, the grabbed frame, the voice-over and the sound effect established
the shape: a new file, the original untouched, a sidecar carrying a `kind` and
which of theirs it came from, and **no count against a daily limit**. These three
follow it. The limit counts the things they asked the machine to *invent*, and
none of these invents anything - a smoothed clip is their own clip with frames
between the frames, a huge picture is their own picture with the edges worked
out, a moving sticker is their own frames, fewer of them.

Two of them spend real GPU time even so, which is the new part.

### They go through the job registry, and they have no card

"Make it smooth" and "Make it huge" are renders. They take ten and six seconds
here, which is long enough to need a bar, and they must queue behind a video
rather than race it - so they call `registry.create` through `_started` like
every maker route, and `_require_idle` refuses a second one with the same 409.

What they do not have is a maker card to draw a result into: they start them
from the gallery viewer and what they make simply appears in the Gallery. So the
page grew `watchDerived()`, which borrows exactly two things from the card
machinery - the now-bar and the Go locks (`setBusy` with a card-shaped object
that is not one of the cards) - and answers with a toast carrying a "Show me"
that opens the new item. `TAB_FOR_KIND` sends these kinds to `mine`, so the
now-bar's own "Show me" goes to their gallery rather than to a maker tab, and
`/api/active` reattaches to one after a reload the same way.

There is deliberately no Stop for them. Ten seconds is not worth a button, and
`MAX_JOB_SECONDS` is the backstop if RIFE ever hangs.

`timings` gives them **their own families** rather than filing them with video
and image. An interpolation is a fraction of what rendering the clip cost and
an ESRGAN pass is a fraction of a Flux one; sharing a family would have each
teaching the other a seconds-per-megapixel rate that is wrong by an order of
magnitude. Their `units()` and `bucket()` read a `pixels` out of `job.extra` -
one frame of *their* file - because the sizes in `ORIENTATIONS` describe what
this app renders and say nothing about a clip they made at Quick or a photo off
their camera roll.

### What is capped, and why

- **Smooth / slow: 30 seconds and 800 frames.** Their clips are 5-15s at 24fps,
  so the seconds cap is generous; the *frames* cap is the one that matters,
  because a clip they have already smoothed once is 48fps and half its length
  would be twice the work.
- **Huge: the input is shrunk to 1.3 megapixels first** if it is bigger
  (`uploads.for_upscale`). Four times 1280x704 is 5120x2816, a 17MB PNG that
  opens on an iPad; four times a 2048x1536 photo off their camera roll is fifty
  megapixels, which is neither quick to write nor pleasant to open. Shrinking
  rather than refusing means the button works on their own photos, which is
  exactly what they will want it for.
- **The button is hidden** on a picture that is already huge (four times that
  is four hundred megapixels) and on either kind of sticker (the upscaler
  reads RGB and hands back RGB, so the see-through parts would silently
  disappear).

### The moving sticker

Up to two seconds of any video, as a looping animated WebP: 320px on the long
side, twelve frames a second, `loop=0`. No GPU and no model - their own frames,
fewer of them and smaller - so it is not behind the busy check either: it
finishes in a quarter of a second, while they are still looking at the sheet, and
refusing it because a video is rendering would be a rule with nothing behind
it.

- **WebP rather than GIF.** GIF is 256 colours and dithers a rendered video
  into mud. Everything they will open this in has done animated WebP for years.
- **The frame nearest each twelfth of a second is kept**, rather than every
  frame thinned afterwards. A 24fps clip then gives exactly every other frame
  and a 30fps one gives an even-enough twelve, with no special case for either:
  the clock is what matters, not the source's rate.
- **The sheet is the frame grabber's scrubber with one extra question.** The
  still underneath is the *first frame of the loop*, fetched from the server
  through `/frame?at=`, for the same reason the grabber fetches its own: what
  they see is where it starts. There is no moving preview, because making one
  would be making the thing.
- **`.webp` was already a known media suffix**, which is most of why this was
  cheap. `still()` returns the file itself, `thumb()` opens it with Pillow and
  gets frame one, `poster()` correctly answers 404 for an image and the page
  never asks. The gallery *tile* points straight at the file, so a moving
  sticker actually moves on the shelf - twenty-five 320px frames is
  kilobytes, not the sixteen-`<video>` problem that made every video tile a
  server-made still. Checked end to end: 25 frames, 83ms each, loop count 0,
  112KB, a 22KB JPEG thumbnail, `image/webp` off the file route.
- It lands on the **Stickers** shelf with its own badge (`🌀 Moving sticker`),
  and "Turn it into a sticker" is hidden on it - it is one already, and
  cutting it out would quietly throw away every frame but the first.

---

## Three ways to change a picture they already have

Flux 2 Klein 9B, and the first thing in this app that makes a *new* picture out
of an old one rather than a copy of it. "Change this picture", "What's outside
the frame?" and "Fix just this bit" all start in the gallery viewer, all take a
sentence, and all come back as ordinary pictures on the Pictures shelf.
("Turn it into..." is a fourth, further down: the same graph again, with the
sentence written by us instead of by them.)

**These are the exception to the rule the smooth/huge/sticker family
established.** Those do not count against a daily limit because none of them
invents anything. These do: a model draws a whole picture from their words, which
is exactly what the picture limit counts. `_require_budget("image", 1)` is on
all three, and `gallery.usage_today()` counts the three kinds into `pictures`
alongside `image` and `panel` - without that last part "change this picture"
would have been the way round a limit.

Everything else about them is the derived-render shape the last three built:
`_require_idle` and `_require_mine`, `_started` through the job registry, a
`kind` and an `edit_of` in the sidecar, `TAB_FOR_KIND` pointing at *the Gallery*,
and `watchDerived()` on the page - the now-bar, the Go locks and a toast with a
"Show me", because there is no maker card to draw a result into.

### Why it is an edit and not a better prompt

The reference is the whole point. Their picture is VAE-encoded and attached to
the conditioning with `ReferenceLatent`, so the model is *shown* what the
picture looks like while it redraws it. "Make it night-time with a big moon" on
their robot-and-sunflowers picture came back as the same robot in the same pose
in the same field with the same flowers, at night, with a moon. Asking Flux
schnell for "a friendly robot watering a sunflower at night" would have given a
different robot in a different field, and they would have noticed immediately.

### What each one is measured at

One 16GB card, shared with Ollama, and Klein 9B fp8 plus the Qwen3-8B encoder
is the tightest thing this app runs. `_started` releases both Ollama models
first, as it does for every render; ComfyUI offloads between the encode and the
sample.

| | Canvas | Wall clock | Peak VRAM |
|---|---|---|---|
| Change this picture | 1280x704 | 13s | **15217 MiB** of 16303 |
| What's outside the frame (a bit, all round) | 1600x896 | 14s | **15311 MiB** |
| Fix just this bit | 1280x704 | 12s | **15245 MiB** |
| (the first probe, cold, models not resident) | 1376x752 | 16s | 15293 MiB |
| (a 1600x880 outpaint probe) | 1600x880 | 6s | **15837 MiB** |

The last row is the one that sets the cap. `OUTPAINT_MAX_PIXELS` is 1.45
megapixels because 1.41 is the largest canvas that has actually rendered here
and half a gigabyte of headroom is not much - a quarter all round on their
landscape size is 1.43MP and needs no shrink, and anything past that shrinks
their picture to fit rather than finding out what an OOM looks like. "Make it
huge" afterwards is the answer to wanting the pixels back.

Warm, these are twelve to fourteen seconds. `timings` gives all three **one
family** (`edit`), keyed on the canvas in tenths of a megapixel: one model, one
set of four steps, and what it costs is the pixels it samples - so their first
"change this picture" teaches the outpaint how long it will take. Not the
picture family: Flux schnell is a different model at a different size and would
predict the wrong minute.

### The sizing, which is the one place the template was overruled

See the node map. Short version: the template scales the reference inside the
graph and that resamples a 1280x704 picture of theirs to 1376x752 for nothing.
`uploads.for_edit()` does it before the upload, on the same 16-pixel grid and
to the same ~1 megapixel, and leaves anything already there alone. So an edit
of a picture they made is the same size as the picture they made, "Animate this"
on the result is still pixel-exact, and `nearest_orientation()` gives the
sidecar an honest-enough shape for the one case where it really does change -
an outpaint, whose 1600x896 is not one of `ORIENTATIONS` and never will be.

Everything downstream already coped with that, which was worth checking rather
than assuming: the facts line reads width and height off the file, the thumb is
a cover crop of whatever it is given, and `uploads.prepare()` crops any gallery
source to the chosen shape at i2v time - a photo off their camera roll has been
going through exactly that path since uploads existed.

### What's outside the frame, and its one empty box

The only prompt box in the app that may be left empty. The picture *is* the
instruction here - "show me more of it" is a complete request - so
`_checked` runs on their words only when there are any, and what reaches the
model otherwise is `styles.OUTPAINT`, which is ours, registered in `prompts.py`
like the cut-out and banner wordings, and needs no filtering for the same
reason they do not. "Keeping everything already in the picture exactly as it
is" is the working half of it: without that, a bigger canvas reads to Klein as
licence to compose a new picture in the space.

An empty box also means an empty `idea`, and `registry.create` falls back to
the composed prompt when `idea` is blank - which would have shown our own
framing sentence in the viewer as the thing they asked for. The route passes
`"what's outside the frame"` instead.

#### Their picture is put back into the render afterwards

**The first version of this had their picture sitting inside the result as a
visible rectangle**, and "carried through the sampler untouched" was the wrong
claim. The pad node's mask does keep the middle out of the denoise, but the
whole canvas still comes home through `VAEDecode`, and that round trip moves
their picture: measured on a beach outpaint against the file they started from, a
per-channel mean of **+11, +10, -3** out of 255 - four times the drift an
inpaint shows. The model then continues the scene outwards from the *shifted*
middle, so the new border does not match the picture they are looking at either.
Two faults for the price of one: a tone step, and a hard line where the two
meet.

`uploads.rejoin_outpaint()` fixes it after the render, in the route's `after`
step, before the sidecar is written - so what lands in the gallery is one
ordinary picture. Three steps, and all three are needed:

1. **Their tone, over the whole canvas.** A per-channel mean-and-spread fit
   between the render's middle and their own file. The two are the same scene
   pixel for pixel, so the fit measures the round trip and nothing else; there
   is no content difference in it to be fooled by. On that render: a gain of
   1.09 and a lift of -31 on red, which took the middle from 9 off their picture
   to 3.8.
2. **The rest of the join, levelled.** A global fit cannot fix a sky that is a
   shade lighter above the old top edge than below it, which is exactly what a
   flat sky shows - and it was still plainly visible with step 1 alone. The
   low-frequency difference between their picture and the render's middle is
   spread outwards over the border and faded out over `OUTPAINT_REACH` (160px),
   which pins the broad tone of the new border to theirs at the join.
3. **Their own pixels, pasted back**, at full weight over every pixel of their
   picture and fading out over `OUTPAINT_FEATHER` (32px) into the border. So
   the middle is their file **byte for byte** - verified, max difference 0 - and
   there is nowhere a hard line could be.

**Pasting on its own made it worse**, which is worth knowing before anybody
simplifies this: their picture is duller than the render, so the paste without
the fit turned a soft step into a hard one.

`ImageColorMatch+`, `ColorMatch`, `ColorMatchV2`, `ImageColorMatchAdobe+` and
`easy imageColorMatch` all exist on this box and none of them is used. They are
custom nodes, where every other node in these graphs is core; they can only
match *globally*, which is step 1 and not step 2; and they cannot match to
something that only exists after the render - the paste. The arithmetic is
twenty lines of numpy and numpy is already a dependency.

The PNG's text chunks are carried across the rewrite, because
`gallery.recover_sidecar` reads the graph back out of them and saving the file
again would otherwise be the thing that lost it. `gallery.rewrite()` is a temp
file and `os.replace`, so there is no half-written picture to open, and the
join costs about half a second - which is why it is given a sliver of the
progress bar (`after_share`) rather than a graph's worth of it.

##### What it has been tried on

Six renders, every one of them looked at full size and with each new edge
cropped across the join at 2x, and measured as well: the mean of each row or
column, with a 41-pixel moving average taken out of it, so a *step* at the join
separates from the slope of the picture either side.

| | Their picture | Canvas | Worst step at a join |
|---|---|---|---|
| all round, a lot (beach, bright) | 1184 square | 1184x1184 | seamless |
| all round, a lot (underwater) | 1632x880 | 1632x880 | seamless |
| all round, **a bit** (sunflower field, pale even sky) | 1280x704 | 1600x896 | **1.4** of 255 |
| **left only**, a bit (the same) | 1280x704 | 1600x704 | **1.4**, and a smooth ramp, not a step |
| **up only**, a bit (the same) | 1280x704 | 1280x880 | **0.8** |
| all round, a lot (a dark night scene) | 1088x592 | 1632x880 | **1.1** |

Nothing visible on any of them, at any edge. The middle came back their file
**byte for byte** - max difference 0 - on all of them. For scale, the bright
band this replaced measured several units and was obvious across the room.

**The constants are right as they are.** `OUTPAINT_FEATHER` 32 and
`OUTPAINT_REACH` 160 were fitted on "a lot" all round and were the thing most
likely to want a second set of numbers for a small pad, because a quarter all
round on a 704-high picture pads the top by **96 pixels, narrower than the
reach** - so the levelling is still carried at about a third of its weight at
the very edge of the canvas instead of fading out inside the border. That is
the case the table's third row is, and it is clean; carrying their tone all the
way out is not a fault, because out there the border is only being compared
against itself. The feather's own cap (`room // 2`) never came near binding:
the narrowest pad any shape and amount can produce is about 80 pixels.

The one thing that does change with a single side is the *grain*. Their picture
carries fine detail that the invented border does not - measured, about 0.75
against 0.6 on the dark render - so the first row inside the join is slightly
busier than the last row outside it. It is not a tone step, nothing fades it
away without blurring the pixels they were promised, and at 2x it reads as their
photograph being sharper than its surroundings, which it is.

**The mask experiment was not needed and was deliberately not run.**
`feathering: 0` and `grow_mask_by: 6` are still what the file says, and the
workflow's `_note` is still true of it. The idea was that with the composite in
place the model no longer has to protect the middle, so a softer mask might
give it a better band to blend into. It is only worth spending a render on if a
join ever shows, and after the six above none has. **If one does**, that is the
first thing to try, and the earlier bright-band failure is not an argument
against it: that was the *model* being asked to keep the inside, and the inside
is ours now either way.

### Fix just this bit, and the second canvas

The drawing pad already opened on a gallery picture, so the mask mode is that
pad with everything that means "a picture" taken away: no colours, no stamps,
no brush sizes, one thick brush, the rubber, undo and "start again". What is
added is a words box under the canvas and a green **Go** in the bar.

**Two canvases are painted in step**, and that is the whole trick. The visible
one gets a see-through pink so they can see their picture through what they are
covering; an offscreen one gets solid white on black, and *that* is what the
server is sent. The overlay cannot be the mask - it has their picture underneath
it. Undo and "start again" move both, or a stroke they took back would still be
in what ComfyUI is given.

The mask is scaled server-side (`uploads.mask_for_edit`) to exactly the size
the picture was sized to, with **nearest-neighbour** and then a hard threshold.
Smooth resampling would make half-masked pixels, which is precisely what put a
grey band in the first outpaint render.

### "And put me in it", which works and has never been used

`image_flux2_klein_edit_two-api.json` chains a second `ReferenceLatent` for their
profile picture. The mechanism is proved: a render with two references put the
robot from one picture into the balloon valley of another, at the right scale,
with the valley untouched. What it has *not* been proved against is a real
face, because the only profile on this box has no avatar saved - so the
checkbox does not appear at all, gated on `me.avatar`. `_my_face_ref()` fails
soft: a face that will not upload costs the "with me" half and not the render.

**Be honest about what it will do when somebody does save a face.** It is the
same family-resemblance caveat as `characters.py`: Klein will draw a child who
looks like the reference, not that child. Say so before it disappoints them.

---

## Turn it into... (`app/restyles.py`)

The fourth thing to do with a picture they already have, and the only one of the
four that needs no sentence from them: a row of chips in the viewer - **a
cartoon, a painting, a pencil drawing, a comic, a clay model, toy bricks,
stained glass, make it real** - and the picture comes back drawn that way with
everything still in the same place. An optional words box takes their own twist
on top ("make it night-time with stars").

**The drawing pad is what this is really for.** Their house-and-cat drawing comes
back as a clay model *of itself*, a stained-glass window of itself, or a
photograph of a little model set with the same cat beside the same house. That
is a different feeling from making a picture of a house and a cat, and it is
the one that will get a reaction.

It is also the best character consistency in this app, and for free: the
reference *is* the character. `characters.py` repeats a sentence about how
somebody looks and gets a family resemblance; this hands Klein the picture, so
their orange cat with the crooked tail comes back as the same orange cat with the
crooked tail in clay, in glass and in graphite. Eight versions of one
character, all recognisably the same one.

### No new workflow, and how that was established

`build_restyle()` loads `image_flux2_klein_edit-api.json` - the same file
"Change this picture" uses - and patches one thing the edit route does not: the
filename prefix, `makery/style`. **There is no fifth Klein graph and there
should not be.** Klein is a reference/edit model and "redraw this as a
stained-glass window, keep the same scene" is exactly the instruction it was
distilled for.

The alternative was tried rather than reasoned about. A classic img2img -
`flux_schnell-api.json` with `EmptySD3LatentImage` swapped for a `VAEEncode` of
their picture and the KSampler's `denoise` turned down - was rendered at 0.65 and
0.8 on the robot-and-sunflowers picture asking for pixel art, and on the
drawing asking for a photograph. **All four came back with the style words
ignored entirely**: the robot was still a photoreal robot and the drawing was
still a drawing, slightly tidier. That is what four steps at CFG 1.0 does to a
style word it is not being *shown* - the prompt has no guidance term to push
with, and the structure it starts from decides the picture. Klein's
`ReferenceLatent` is shown the picture and told what to do with it, which is a
different mechanism and the right one.

Which also settles the strength question: there is nothing to offer. The Klein
graph samples an empty latent through `SamplerCustomAdvanced` and has no
`denoise` anywhere; the graph that has one is the graph that did not work. A
"a little / a lot" pair would have been two buttons over one behaviour.

### What each one actually looks like

One seed, three sources - a picture they generated (1280x704), a photo off the
camera roll (2048x1536) and a drawing off the pad (1024x768) - and eyes on
every render.

| Chip | How it came back |
|---|---|
| A cartoon | Clean bold-outline cartoon, composition exact. **On a photograph of an *object* it gives the object a face** - see below |
| A painting | The best of them. Real watercolour on paper, every sunflower where it was |
| A pencil drawing | Graphite and cross-hatching, faithful down to the chair legs |
| A comic | Ink outlines and halftone dots, nothing invented, no lettering |
| A clay model | Plasticine with thumbprints, on a clay backdrop. Excellent on a drawing |
| Toy bricks | Everything brick-built including the sky. Excellent once the wording stopped naming a table - see below |
| Stained glass | Leaded glass, lit from behind, gorgeous on a drawing |
| Make it real | A real photograph of a little model set: their cat, their house, their tree, their flowers. This is the one |

**Pixel art is deliberately not in the row**, and the user asked for it by
name. Three wordings were rendered. "Chunky 16-bit pixel art, big square
pixels" posterises a render passably and does **nothing at all** to a flat
drawing - it hands back the drawing. "An old video-game screen, low resolution,
big blocks of flat colour" is the best of the three and still only blocks up
the sky. "Drawn on a grid just 64 squares across" drew **literal graph paper**
over both the drawing and the render. A chip that spends one of their three
pictures for the day and gives back the picture they started with is a bug with
a button on it, so it is not there. If it is ever wanted, the honest way is a
post-process - downscale and nearest-neighbour back up - not a prompt.

Two things about the wording that cost a render each and are worth not
re-learning:

- **Do not tell Klein what not to draw.** Cartooning a photograph of a peach
  gave the peach two eyes and a smile. Adding "nothing grows a face, eyes or a
  mouth it did not already have" to `KEEP` made it *worse*: the same seed came
  back with eyelashes. There is no negative prompt in these graphs and CFG is
  1.0, so a forbidding sentence is only those words in the instruction. The
  behaviour is left as it is - it is charming, it only happens to objects with
  no face, and on anything with a real subject in it (a pet, a person, one of
  their drawings) it does not happen at all.
- **Do not name a setting the picture does not have.** "Rebuild this out of toy
  bricks, photographed on a table" put the robot on a desk beside a laptop and
  a pot plant, because it was told to. Dropping those four words put the
  sunflower field back, brick by brick.

### Where the line is, since deepfakes came up

"Not for deepfakes of course" was in the request that asked for this, and nothing here moves toward
one:

- **The chips are ours and there is no "make it look like <person>" among
  them.** They name a medium - paint, graphite, ink, clay, plastic, glass - and
  never a person, a celebrity or a style-by-artist-name.
- **Their own words still go through `safety.check_prompt`**, which has a
  `deepfake` category, exactly as on every other prompt route. The chip's
  sentence does not, for the same reason `styles.CUTOUT` does not: it is a
  fixed list we wrote.
- **The source is always one of their own gallery items** (`_require_mine`), and
  it is a whole picture, never a face pasted into another. The installed ReActor
  face-swap node stays unwired.
- **Restyling a photograph of a real person is fine and expected.** It is their
  own camera roll, and "turn the photo of Granny into a watercolour" is a
  painting of Granny, not a claim that Granny did something. The line is
  *identity transplant* - putting a real person's face onto a body or a scene
  that is not theirs - and nothing on this sheet can do it. ("...and put me in
  it" on the *edit* sheet is the nearest thing to it in this app, it uses their
  own saved face, and it is not on this sheet.)

### What it costs, and what it is made of

| | Canvas | Wall clock | Peak VRAM |
|---|---|---|---|
| A drawing → a clay model | 1024x768 | 12s | **15575 MiB** of 16303 |
| Their robot picture → stained glass | 1280x704 | 13s | **14931 MiB** |
| (a probe batch, back to back, three sources) | ~1MP | 6s each warm | 15825 MiB |

The same model and the same four steps as the three edits, so `timings` puts
it in the **same `edit` family** rather than one of its own - their first "change
this picture" already taught it what a megapixel costs here.

Everything else is the derived-render shape the edits established, and almost
none of it is new code: `_require_idle`, `_require_module("picture")`,
`_require_mine`, `_checked` on their words *only when they typed any*,
`_require_budget("image", 1)`, `_edit_source()` for the sizing and the upload,
`_started` through the job registry, `watchDerived()` on the page,
`TAB_FOR_KIND` pointing at *the Gallery*. The sidecar gets `kind: "restyle"`,
`restyle_of`, `turned_into` (which chip) and `twist` (their words), and
`usage_today()` counts `restyle` into `pictures` alongside the three edits -
without that it would have been the way round a daily limit.

**"Make it again, but..." reopens the sheet**, not a maker card: the same
picture, the same chip lit, their words back in the box and the same seed, so
changing one word gives a variation on the picture they are looking at.

`idea` is `restyles.asked_for()` - "turn it into a clay model, make it
night-time with stars" - rather than either their twist alone (which loses which
button made it) or the whole composed sentence (forty words they never wrote).

**One thing fixed on the way past.** `gallery.listing()` did not return
`edit_of`, so `item.edit_of` was `undefined` in the browser and "Make it again,
but..." never appeared on a changed picture at all, although the code for it
was there. `edit_of`, `restyle_of`, `turned_into` and `twist` are all in the
listing now.

## Sound effects

Twelve of them, **synthesised in numpy at import time and cached**, in
`app/sounds.py`. A folder of WAV files would be a licensing question, a
download and 40MB in the image; twelve short functions are none of those and
sound the same every time.

They are levelled to a common **RMS**, not a common peak: a sustained honk and
a short drum hit can share a peak and be nothing like as loud as each other.
Before that change the honk was 2.5× the loudness of everything around it.

Mixing reuses the voice-over path. `gallery._with_new_audio` was extracted out
of `add_voice` so that adding their voice and adding a boing are the same
operation with a different array - the video stream is remuxed, never
re-encoded, so both are instant and lossless. The video's own sound ducks to
55% under the effect, with the step smoothed into a fade or it clicks.

---

## Managing characters

**Saving one is offered where the picture appears.** "Save as a character" is
in the actions under a freshly made picture as well as in the gallery viewer:
the moment a picture turns up is when they know whether they want to keep
whoever is in it, and making them go and find it again later was a worse moment
to ask. The button takes itself away once used, and is not offered at all when
the cast is full.

Creating one has always been possible; looking after one was not. **Their cast is
a shelf at the top of the Gallery** - their own saved picture as the face, their
name under it - and a tap opens that character's own page, which is where
looking after them happens:

- **Rename**
- **How they look** - reword the sentence. This matters more than it sounds: it
  is what gets repeated into every prompt they appear in, so it is the one knob
  that changes what actually comes out. The model's first draft is usually good,
  but "spiky brown fur" when they meant *ginger* is exactly the kind of thing they
  should be able to fix without starting again.
- **Their stuff** - everything they are in, which is the page itself, and is
  also reachable from the cast row on any maker card
- **Goodbye** - armed, like every other delete here

There was a **My characters** sheet in between, listing the cast with those
four buttons on each row, reached by a button under the shelves. It is gone:
two lists of the same handful of people, one of them invisible until asked for,
and nothing on the page saying who they had made. The list is the shelf and the
row is the page.

The look is safety-checked on the way in, because unlike every other field on
that page it reaches ComfyUI verbatim.

Note that `character` only started being written into sidecars with this
change, so a character's page shows what they make from now on, plus their own
picture.

---

### Results play from the gallery, not the ComfyUI proxy

`/api/result/{job}` is a `StreamingResponse` proxied from ComfyUI's `/view`,
and a streamed body cannot answer a `Range` request. **iOS will not show a
`<video>` at all without ranges** - the player rendered as a crossed-out play
icon on the iPhone while the same file played fine on a laptop. The gallery
route is a `FileResponse`, which answers `Range: bytes=0-99` with `206` and
`Accept-Ranges: bytes` (Starlette 0.41), and the finished file is in the
gallery the moment the job is done. So `resultUrl()` builds
`/api/gallery/{filename}/file?v={job}` for anything with a filename and only
falls back to `/api/result/` without one.

### The helpers write for a nearly-twelve-year-old

The system prompts said "a 10-year-old child" and wrote like it - everything
was tiny, little and fluffy. They now say the reader is nearly twelve and reads
well,
and carry a tone line: vivid and specific with a bit of wit, not cutesy, no
"little" this and "tiny" that. Same safety rules. Measured on "a fox in a
library": *"A russet fox, ears perked, sits cross-legged on a worn oak table…
sunlight slants through high windows, casting warm gold on dust motes."*

### The video helper reads a picture's own words

Given a picture made here, `POST /api/script` looks up its sidecar and hands
the `idea` to `scripts.describe()` as *"It was made from this description:
…"*. The vision model sees the picture either way; the words name what it
might only guess at - the character, the style they chose. A photo they
uploaded has none, and that is fine. Verified: a picture of "a lighthouse at
dusk" with no words typed came back as *"a lighthouse with red and white
stripes glowing warmly at dusk"* and a prompt to match.

### The trash and reused filenames

ComfyUI reuses a name once its file is gone from the output directory, so the
trash can already hold an older `image_00007_.png` when a newer one is
deleted. `delete()` used `shutil.move`, which silently overwrote it - the one
thing a trash exists to prevent. It now renames the newer one with a
timestamp on collision, the way `restore()` already did going the other way.

### Every instruction, in one list (`app/prompts.py`)

Sixteen strings decide almost everything about what comes out - the tone of the
idea helpers, what the chat helper will discuss, the rules a comic panel is
drawn by, what the upload screen refuses - and they were readable only by
opening five different modules.

`prompts.py` does **not** move them. Each default still lives next to the code
that uses it, where it can be read in context; the registry names them, and
call sites pass their own constant as the fallback:

```python
payload = {"system": prompts.text("video_script", SYSTEM_PROMPT), ...}
```

So an unreadable override file, a missing key or a typo'd id all end with the
built-in running, which is the right way round for something in front of a
child. `text()` swallows everything and logs.

Two details worth keeping:

- **The chat prompt is a template, not an f-string.** It was built at import
  with the helper's name and the child's already substituted, which would have
  meant a parent editing it silently lost them. It is `{helper}` and `{who}`
  now, filled in by `chat.system_prompt()` at use, and the parent page says so.
- **Editing is off by default** (`prompt_editing`, a switch on that tab).
  Reading them is the point;
  a page that invites rewriting the safety instructions without the person
  having decided to is worse than no page. The route returns 403, not a
  disabled button, so it holds without the page.

## Frontend requirements

Target is **iPad Safari**, used by an 11-year-old.

- Large touch targets, large type, no small controls or hover-only affordances
- One prompt box per section, nothing else
- Visible progress while generating — video takes a while and they need to know
  it's working, not broken
- Errors in plain friendly language, never a stack trace or an HTTP status
- Downloads are same-origin via `/api/result/{id}?download=1` with the
  `download` attribute, which works in Safari
- **What they have typed survives a reload.** Every prompt box and the "what
  should they say" input are mirrored into `localStorage` on input and restored
  on load; clearing the box with the ✕ forgets it. The paths that fill a box
  *in code* - the helper, Surprise me, "Make another like this", "what happens
  next?" - fire no `input` event, so each one calls `card.rememberText()`
  itself. Every `localStorage` access is wrapped in try/catch: Safari throws in
  a private window rather than returning null.
- **`main` must keep `grid-template-columns: minmax(0, 1fr)`.** It is a grid,
  and an `auto` track is at least as wide as its widest item's *min-content*.
  The gallery's thumbnail strip does not shrink, so with an auto track it pushed
  the whole column past `max-width` and shoved every card sideways - the page
  looked "pushed to the right" at every width. `.card` and `.strip` carry
  `min-width: 0` for the same reason.
- The selection bar is `position: fixed`, not `sticky`. As a sticky element
  earlier in the flow it stuck to the *top* and sat on the first heading.
- Opening a sheet pins `body` with `position: fixed` and restores the scroll
  offset on close. `overflow: hidden` alone does not stop iOS Safari scrolling
  the page underneath.
- Every tappable thing has `touch-action: manipulation` (no double-tap zoom, no
  300ms delay) and `-webkit-user-select: none` (no callout on a long press).
- The return key dismisses the keyboard (the `enterkeyhint="done"` promise);
  Shift+Return still inserts a newline.
- The tab title carries the percentage while a job runs, and "✅ Ready!" for a
  few seconds when it finishes.
- The banner is a text-free Flux render with the title as real HTML over it:
  Flux schnell at 4 steps cannot spell. `favicon.png` and
  `apple-touch-icon.png` are crops of that same banner.

---

## Current state

Built and verified end to end against the live ComfyUI (0.36.0) and Ollama:

- `app/` — safety, comfy, workflows, jobs, main, styles, scripts, uploads, gallery
- `static/` — the two-card iPad frontend plus the gallery sheet
- `Dockerfile`, `docker-compose.yml`, `requirements.txt`

Verified on the server: image at both shapes (1280×704 and 832×1088), t2v, i2v
including the output→`/upload/image`→input round trip, photo upload with
orientation auto-detected from the file, 5s and 15s video, cancelling a running
render, the 409 when a second job is started, safety rejections on both their
input and the idea helper's output, style phrases reaching node 6 verbatim,
gallery listing / zip / single and bulk delete, path-traversal ids refused, and
the vhost over HTTPS on the existing wildcard cert.

The frontend is also exercised headlessly (jsdom for behaviour, headless Chrome
for layout) - see "Checking the frontend" below.

## Rebuilding while they are using it

Use **`./safe-rebuild`**, not `docker compose up -d --build`. Rebuilding
mid-render kills the job the app is tracking: ComfyUI finishes the file
regardless, so nothing is lost, but the progress bar vanishes from under
whoever was watching it and `_finish` never writes the sidecar. The script
waits for ComfyUI's queue to drain first, and runs `recover_missing()`
afterwards to pick up the notes for anything that landed while it was down.

Three real renders were interrupted this way before the script existed.

## Checking the frontend

**Syntax-check the scripts before every rebuild.** There is no node on this
host, but there is a node image, and a syntax error in `app.js` is their whole
page:

```bash
docker run --rm -v "$PWD/static:/s:ro" node:22-alpine \
  sh -c 'node --check /s/app.js && node --check /s/i18n.js && node --check /s/parent.js'
```

The HTML is worth a tag-balance check too - `html.parser` in a few lines, with
a stack - after any scripted edit that inserts a block. A stray `</div>` is how
the phone-alerts card ended up rendering on every parent tab.

There is no test suite, but two throwaway harnesses caught real bugs and are
worth rebuilding rather than reasoning about the CSS:

```bash
# behaviour: run the page in jsdom with fetch stubbed
docker run --rm -v "$PWD/static:/s:ro" -w /tmp node:20-alpine \
  sh -c "npm i -s jsdom && node your-script.mjs"

# layout: real Chrome, measure and screenshot at iPad widths
docker run --rm --network "$NETWORK_NAME" -v "$PWD/shots:/w" \
  --entrypoint sh zenika/alpine-chrome:with-puppeteer \
  -c 'cd /usr/src/app && cat /w/m.js > m.js && node m.js'
```

The layout one found the `main` grid-track bug by comparing
`document.documentElement.scrollWidth` against `innerWidth` and listing every
element whose rect exceeded the viewport. Reading the stylesheet had not.

A third shape of the same harness is worth rebuilding whenever the strings
change: walk every tab and sheet with the `lang` cookie set, scan every
visible text node and every `placeholder` / `aria-label` / `title` / `alt` for
words of another language, and run the identical walk against the live app
in English to prove nothing moved. See "The coverage check" under "Seven
languages" for what it found and what it deliberately ignores.

## How progress is reported

ComfyUI reports progress per node. Counting nodes equally is useless here: the
LTX graphs are ~50 nodes of which two `SamplerCustomAdvanced` passes take nearly
all the wall clock, so an unweighted bar jumps to 90% and then sits still for
minutes. `NODE_WEIGHTS` in [app/jobs.py](app/jobs.py) weights node classes by
roughly how long they take, which keeps the bar moving in step with the work.

The WebSocket is best-effort — it reconnects on its own, and the job runner also
polls `/history`, so a dropped socket costs progress updates but never a result.
Messages that arrive before the job has registered its `prompt_id` (the socket
beats our own `POST /prompt` response) are buffered for 30s and replayed.

## Open items

- **"Make another like this" sends a song to the video card.** `makeAnother()`
  picks between two cards on `item.media === "image"`, which was written before
  there was a music card, so a song's own words and dropdowns are refilled into
  the video card and quietly ignored. Noticed while adding "How many singers" -
  the choice *is* in the song's sidecar, and the reset button and Surprise me
  both read it correctly; it is only this one button that has nowhere to put
  it. Fixing it needs the lyrics box and the singing toggle refilled too.
- **Nothing caps the gallery itself.** The trash empties itself and the input
  dir is swept, but what they keep, they keep. At ~1-3MB an item that is a long
  way off mattering; a "you've used X GB" line in the card would be the first
  step if it ever does.
- **Chat is only as good as the model.** gemma4:12b is sensible and stays in
  character, but it is a 12B model on a home GPU: it will occasionally be
  confidently wrong about something factual. The system prompt steers it toward
  helping them make things rather than answering the world, and the transcript is
  on the parent page, but do not mistake it for a supervised product.
- **15s video is close to the edge.** A 15s render peaked at 15.5GB of the
  card's 16.3GB with ComfyUI's models resident. It works, but there is little
  headroom; if OOMs appear, cap the length rather than wondering why.
- Upload screening fails open when Ollama is down, and a NO from the model
  cannot be appealed from the page. Both are deliberate for a LAN app fed from
  their own camera roll; revisit if it is ever exposed further.
- **The nightly email has no retry across days.** If the relay is down for the
  whole ten-minute window, that day's email is simply lost - it is a summary,
  not a receipt, and a queue would be more machinery than the thing is worth.
- **The settings are one SQLite file now**, `state.db` in `STATE_DIR`, and the
  parent page is the only place any of them is changed. `.env` seeds the
  behavioural half once, on the first start, and is not read for it again. The
  old `.settings.json` is imported and renamed to `.settings.json.migrated` on
  that first start; the other state files are still JSON. See "Where settings
  live" for the whole of it, and "Backup and restore" for the file that holds
  all of it at once.
- **State is not kept in the gallery any more.** The settings, their characters,
  the chat transcript, the prompt overrides, the timings and their banner used to
  live in `GALLERY_DIR`, which is ComfyUI's *output* directory - shared, and
  named in the stack's own notes as something to `rm -rf` when a disk fills.
  `STATE_DIR` splits them out, defaulting to a Docker named volume. Unset, it
  *is* `GALLERY_DIR`, so an older install keeps working; set, `prepare_state()`
  moves what is in the old place across once at startup and logs each file.
  Moves rather than copies, so there is never a question about which copy is
  being read. `/state` is `chmod 1777` in the image because a new named volume
  inherits its ownership from the image and `RUN_AS` is the operator's choice.
- **"Film" is the one word for a video made of several clips**, everywhere they
  or a parent can read it. There are still two *kinds* underneath - `story`,
  which the model plans from their sentence and films part by part, and `movie`,
  which they assemble from clips they already have - because those strings are
  written into every sidecar already and renaming them would orphan everything
  they have made. They record how a file came about; they are not labels.
- **The spoken line is in the sidecar** (`said`). It is not part of `idea`,
  which is only their description, and by the time it is in the prompt it is
  inside a sentence we wrote - so "make it again but..." could not recover it
  without guessing, and came back with an empty speech box.
- **Nothing in this repo is instance-specific any more.** Everything a
  particular machine needs is in `.env` (gitignored), documented in
  `.env.example`, and everything a particular household *decides* is in
  `state.db`. The child's name is `KID_NAME` rather than spelled into the page
  title and the email subjects.
  `PARENT_PIN` used to be committed in `docker-compose.yml`; it is in `.env`
  now, though it is still in the git history of this repo. The child's *age*
  went the same way: "nearly twelve" was spelled into fourteen model
  instructions, and is now the profile's age (seeded once from `KID_AGE`)
  filled into `{age}` / `{age_old}` by
  `branding.about()`, which `prompts.text()` runs over the built-in and over a
  parent's edited version alike. It is a plain `str.replace` and not
  `str.format` because the comic instructions contain literal braces - they
  show the model the JSON to return.
- The `workflows/` exports carry their original sample prompts. Harmless - every
  one is overwritten at submit time - but they are what a render would fall back
  to if the node map drifted, which is why `_patch` raises instead of skipping.
  **One exception**: the ACE-Step export shipped with sample tags and lyrics
  that were wrong for a children's app to have sitting in a public repo, so
  those two *string values* were replaced by hand. Nothing structural was
  touched - same nodes, same inputs, verified by comparing the parsed shapes -
  and a re-export will bring the original text back, so check it.

## Three things that were quietly wrong

Found in a read-through and fixed; noting them because each looked fine.

- **Comic panels counted against nothing.** `/api/generate/comic` checked the
  picture allowance before starting, but the finished panels were filed as kind
  `panel` and `usage_today` only counted `image`. So a picture limit was a limit
  on the Picture tab only, and they could make comics all day. `usage_today` now
  reports a `pictures` total of `image + panel`, and that is what the allowance
  reads. The comic card shows the picture countdown too, or the number would sit
  on a tab they were not looking at.
- **The parent PIN had no guess throttle.** The grown-up box on the quiz overlay
  locks after five wrong tries; `_parent()` just compared the header, so the
  same four-digit PIN was ten thousand requests to `/api/parent/summary` away.
  It now shares that lockout and uses `hmac.compare_digest`. A *missing* header
  is not a guess - the page asks without one on first load - so only a wrong one
  counts.
- **"Save everything" blocked the event loop.** `gallery.zip_into` ran inline,
  so a multi-gigabyte zip froze their progress bar and every other request until
  it finished. It is in a thread now, like `join` and `add_voice` already were.

And one I caused: adding `.part-pick` to the picker selectors with a blind
"replace the first `.panels`" turned `.panels.is-on` into `.panels` in two
rules, so every comic panel-count button rendered as selected and permanently
pressed down. Repaired, and worth remembering as an argument for reading the
selector back after editing CSS by script.

And one the music card left behind: **"Make another like this" sent a song to
the video card.** `makeAnother` picked between two cards with
`item.media === "image"`, written when there were only two, so every song
landed on the video card - their lyrics nowhere, a shape a song has no use for,
and the length slider set from a different range. It picks by media across all
three now and refills the words box, the singing toggle (`[inst]` in the
sidecar means nobody sings on it) and the length.

Also: the fire-and-forget `digest.limit_notice` task had no reference held,
which is the documented way to have asyncio collect a task mid-run. There is a
`_background` set now.

---

## Conventions

- Do not hand-edit the files in `workflows/`. Load and patch them at runtime so
  they can be re-exported from ComfyUI and dropped in. **Two exceptions, both
  named in the workflow node map:** `video_smooth_rife-api.json` and
  `image_upscale_esrgan-api.json` were written from `GET /object_info` because
  no shipped template does either job, and each carries a `"_note"` saying so
  and naming the render that proved it. If you change one, re-render before you
  trust it - the point of the convention is that a graph matches what ComfyUI
  actually validates, and that is the part to keep.
- Keep every child-facing string friendly and blame-free.
- When adding a safety term, add it to `BLOCKLIST` in the right category. It
  goes on `SUBSTRING_TERMS` as well only if **both** of these hold: the word is
  likely to be glued to other text, *and* no ordinary word in any of the seven
  languages contains those letters. Nothing on that list is bounded at either
  end, so the second condition is what keeps it safe - "rape" was on it, and
  refused "grapes", "trapeze" and "scraped" until it was moved out. A short
  word that fails the second test can still be caught with a padding guard
  around it; `_RAPE_RE` in `app/safety.py` is the worked example.
- A term of three letters or fewer in one of the six non-English lists is
  matched only when that language is the one on the screen (`SHORT_TERM_CHARS`).
  Every language's list is otherwise run against every prompt, and there are not
  enough two-letter words to go round: French "nu" is Dutch for "now".
- Check a new term against ordinary words in the *other* six languages before
  adding it, not just its own. "What each list leaves out, and why" above has
  the collisions found so far and why each one is off.
