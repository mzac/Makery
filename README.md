# Makery

A front-end for ComfyUI built for a child, not for an operator. No model
pickers, no samplers, no seeds — a box to type in, a big button, and a gallery
of everything they have made. It runs beside an existing ComfyUI and Ollama and
talks to them over the network; it renders nothing itself.

**Who it is for.** Somebody who already has ComfyUI and a GPU at home and would
like a child to be able to use them without first being taught what a sampler
is. It was written for a child with an iPad, which explains most of the design
decisions in it: tabs instead of a long page, one job at a time, and a grown-up
page that is a separate URL. No child's name is anywhere in the code — see
[Whose it is](#whose-it-is).

Self-hosted, Apache 2.0, and meant for a home network. There is no login on the
child's side and no account system; the parent page takes a PIN. Read
[Before you let a child at it](#before-you-let-a-child-at-it) before deciding
whether that is the right shape for your house.

## What it looks like

**Making something.** Eight tabs, one box to type in, one button, and the
dropdowns that turn a few words into a good prompt without having to know how
one is written. Every card says how long it will take on *this* machine, from
what the last few actually took.

![The Picture tab: a big box to type in, "Help me write it" and "Surprise me"
underneath it, the style, place and mood dropdowns below that, and a Make my
picture button](docs/making-a-picture.png)

**Everything they have made** is one page — newest first, or a shelf per kind —
with search, tags, favourites, a zip of the lot and a trash that keeps things
for a week.

![The Gallery tab: a grid of eight pictures in eight different styles, a video
and a song among them](docs/the-gallery.png)

**The parent page** is `/parent`, behind a PIN. Eight tabs: today at a glance
with the live machine figures, who uses it, the rules and the daily limits, the
alerts, their stuff, a sealed activity log, the settings, and every instruction
this app gives a model.

![The parent page, "Right now": a one-line "Everything's working", today's
counts, a thumbnail of each thing made today, the live processor, graphics and
memory readout, and what is using the disk](docs/the-parent-page.png)

**It was built for a tablet and it works on a phone.** Same page, same code —
the tabs reflow and everything stays thumb-sized.

<img src="docs/on-a-phone.png" width="300"
     alt="The same page at phone width, the eight tabs reflowed into two rows">

## What you need

Four things, and the first one is the one that takes an afternoon.

- **ComfyUI**, reachable over HTTP, with **[twelve model files on
  disk](#the-models-comfyui-needs)** — Flux schnell fp8 for pictures, the LTX
  2.5 set for video, Flux 2 Klein 9B for changing a picture, and two small ones
  for "make it smooth" and "make it huge". Four more, optional, for the Music
  tab. That is about 81 GB, plus 20 GB for music. **Nothing renders without
  them**, and the graphs load them *by name*, so the right weights under a
  different filename is a failed render rather than a warning. One custom node
  pack, for frame interpolation; everything else ships with ComfyUI. At startup
  this asks ComfyUI what it can see and names every missing file in the log.
- **Ollama**, for the idea helpers, the upload screening and the chat tab.
  Which model does which job is three dropdowns on the parent page, fed from
  whatever Ollama has already pulled — this app never downloads one. The idea
  helper's **must be a vision model** (`SCRIPT_MODEL` seeds it, default
  `qwen3-vl:4b-instruct`): the picture-aware help and the screening both send
  it an image. The chat tab's (`CHAT_MODEL`, default `gemma4:12b`) is optional,
  and Telegram's follows the idea helper unless it is given one of its own.
- **A GPU** that ComfyUI is already using. 16 GB is what this was built and
  measured on, and it is close to the floor — see [What the machine
  needs](#what-the-machine-needs). This app wants `gpus: all` only so NVML can
  read utilisation and VRAM for the progress readout; drop that line from the
  compose file and the numbers just go missing.
- **Docker** and **Docker Compose**, and a network ComfyUI and Ollama are
  already on. The image is `python:3.12-slim`; without Docker, Python 3.12 and
  `requirements.txt` are all it is.

The node names, input names and combo values in `workflows/` were last checked
against **ComfyUI 0.35.0** (Python 3.14, torch 2.14). Newer versions are
expected to work; an older one may not have the Flux 2 and LTX 2.5 nodes at all.

Starting from a machine with nothing on it? [Setting up the whole
stack](#setting-up-the-whole-stack) builds all of it — ComfyUI, Ollama, the
models, and a name to reach it by.

## Running it

```bash
cp .env.example .env
$EDITOR .env          # GALLERY_DIR and NETWORK_NAME at minimum
docker compose up -d --build
```

Then `http://<host>:8095`, or put it behind whatever proxy you already run.

The two settings that have no sensible default:

| | |
|---|---|
| `GALLERY_DIR` | ComfyUI's output directory for this app. It is read **directly** as the gallery — nothing is copied and there is no second source of truth. Point ComfyUI's `SaveImage`/`SaveVideo` prefix at it. |
| `NETWORK_NAME` | The Docker network ComfyUI and Ollama are on. `docker network ls`. |

Everything else has a working default and a comment explaining it in
[`.env.example`](.env.example), which is the reference.

**It will start without the models, and it will not render without them.** The
check runs a couple of seconds after startup, once ComfyUI is answering, and
writes one line naming every file the workflows want and ComfyUI cannot see. A
missing model is deliberately a line in the log rather than a refusal to run —
the picture half may be fine while the video half is still downloading — so
read the log after the first start rather than finding out by tapping Go:

```bash
docker compose logs makery | grep -i model
```

The Music tab is the one exception: it hides itself when its four files are
missing, instead of offering a button that cannot work.

## Before you let a child at it

Four things worth knowing before you decide, none of them reassuring.

**There is no authentication on the child's side.** No login, no password, no
session — anything that can reach the port can make a picture, browse the
gallery and delete from it. It is meant to live on a home network behind a
router. Nothing about it is safe to put on the internet.

**The parent PIN has a published default of `1234`.** It is in the source and
in `.env.example`, so it is public knowledge. It is there so that a fresh
install has a gate at all, not so that anybody relies on it, and the app warns
on every start until it is changed. Change it before a child works out that
1234 is the first thing anyone tries: `PARENT_PIN` in `.env`, or on the parent
page under Settings.

**The content filter is an input-side blocklist and nothing else.**
`safety.check_prompt()` reads the words that were typed — in all seven
languages, after accent-folding and a little leetspeak substitution — and
refuses a match with a friendly 400 before anything reaches ComfyUI. It does
not look at what comes back. The negative prompts written into every workflow
are **inert**: every graph here runs at CFG 1.0, where the term that would
subtract them is multiplied by zero. Uploaded photos are additionally shown to
a vision model, which fails *open* if Ollama is unreachable. A model can still
draw something nobody asked for, and nothing in this app will catch it.
[Safety](#safety) is the honest long version and is worth reading before the
first afternoon rather than after it.

**Profiles are a curtain, not a lock.** Two children get separate galleries,
separate limits and separate rules; they do not get separate accounts.
Switching profile is one tap with no PIN, and a direct media URL still opens
for anyone who has it. That was chosen on purpose for a shared iPad. If you
need a real lock, this is not it yet.

## What it can make

### The six makers

Each is its own tab, and a parent can switch any of them off. A maker with no
model available hides itself rather than answering "not set up" on every tap.

- **Pictures** from a sentence, one at a time or four to choose between, in
  landscape, portrait or square. Or "a character": the same idea drawn alone on
  a plain background, so it can be cut out.
- **Videos** with sound, 5–15 seconds. Four modes in one card: from words, from
  a picture, between **two pictures** (LTX's first-and-last-frame graph fills in
  the middle), or a **little film** — two to four clips where each starts from
  the last frame of the one before, joined into one. Quick / normal / sharper is
  the megapixel target, and *sharper* has a shorter length limit because it
  costs more VRAM.
- **Songs** with ACE-Step, 10 seconds to two minutes, with singing or without.
  Two boxes — what it should sound like, and the words that are sung — and one
  button that writes both from a single idea. The kind of music sets the tempo
  and the mood sets the key, because a lullaby is not a pop song with the word
  "lullaby" added. "Sung in" and "how many singers" (one, two taking turns, a
  group on the chorus, everyone together, call and answer) are dropdowns. The
  arrangement is the honest weak spot: what is verified is that each choice puts
  its tags in the encoder and its structure in the lyrics, and that the renders
  come back the right length. **Whether the model really hands the second verse
  to a second singer has not been checked by ear.**
- **Three kinds of sound, not one.** A chip at the top of the Music card picks
  between **a song**, **a little tune** (short, instrumental, 8–20s — a sting
  for the front of a video) and **a background hum** (long, no beat, 15–60s —
  something to leave playing behind something else). One model and one graph
  under all three, one daily allowance, and the two instrumental ones hide the
  words box and the vocal dropdowns rather than asking about them.
  A **sound effect** chip was measured and deliberately left out: the twelve in
  `app/sounds.py` are synthesised in numpy, exact and instant, and a diffusion
  model that might produce a door creak is worse than one that always does.
  So is anything made of **noise** — rain and a crowded market were both tried
  and both came back as music, with a tenth to a fiftieth of the high-frequency
  energy real rain has. There is **no text-to-speech** on this box at all, so
  no narration: everything speech-shaped in ComfyUI here is a cloud node with
  an API key behind it. See "What else ACE-Step can make, measured" in
  `CLAUDE.md` for the numbers behind every one of those calls.
- **The silence on the end is cut off.** ACE-Step is given a length and writes
  something shorter, leaving the rest of the file quiet — a median of three
  seconds and once over six. On a two-minute song nobody notices; on a
  ten-second tune it is half the file. `gallery.trim_tail` measures the tail
  and cuts it for the two instrumental kinds only, keeping a breath on the end,
  and does nothing at all unless a whole second is genuinely silent.
- **Comics**: a story becomes a 3, 4 or 6 panel strip with speech bubbles,
  drawn with one repeated character description so the panels look related.
- **Chat**, backed by whatever Ollama has. Deliberately not streamed: the whole
  reply is filtered before any of it is shown. Every turn is logged where a
  parent can read it, and the helper says so if asked.
- **A Story**, which is the other five put in order rather than a sixth thing
  the machine can do. One idea walked through five steps — write the story, draw
  the opening picture, film it in two to four parts starting from that picture,
  write a song as long as the film, and lay the song under it — with each result
  on the screen before the next step begins, so nobody spends three minutes of
  filming on a picture they have not seen. Every step is skippable and redoable,
  the whole thing survives a reload or a Stop, and it has **no allowance of its
  own**: the picture step spends a picture, the film step a video per part, the
  song step a song. The last step is a remux, not a render — the film's frames
  are copied across untouched and only the soundtrack is rebuilt, with the
  film's own sound kept quietly underneath the song unless you untick it. What
  comes out is a film with its own song, on the Films shelf with its own badge.

### Change a picture they already have

Four buttons in the gallery viewer, all Flux 2 Klein 9B with the child's own
picture as the reference — so they change the picture that exists rather than
drawing a new one that matches the words.

- **Turn it into…**: a row of chips — a cartoon, a painting, a pencil drawing,
  a comic, a clay model, toy bricks, stained glass, make it real — and the same
  picture comes back drawn that way, with everything still where it was. Add
  your own twist in the box, or don't. **A drawing off the drawing pad is what
  this is for**: a house and a cat drawn by hand come back as a clay model of
  themselves.
- **Change this picture**: "make it night-time", "give the fox a scarf". Same
  scene, same everything, that one thing different.
- **What's outside the frame?**: a side or all round, a bit or a lot, and it
  invents what was just out of shot. The original comes through untouched.
- **Fix just this bit**: paint over part of it in the drawing pad, say what
  should be there instead, and only that changes.

All four cost a picture from the daily limit, because a model really does draw
one. They are also the most expensive thing here in VRAM — see
[What the machine needs](#what-the-machine-needs). The rest below do not cost a
picture.

### Then do things to them

Favourite, name and tag; turn a picture into a sticker with its background cut
out; make a picture four times bigger; make a video smooth or slow it right
down; keep up to two seconds of one as a looping animated sticker; grab a frame
out of a video; record a voice-over that ducks the original sound rather than
replacing it; drop in one of twelve synthesised sound effects; join clips into a
movie with a title card; draw on a picture; print it; make a greetings card;
compare two side by side with a wipe slider. There is a bin under every fresh
result and on every tile; deleted things go to a trash for a week.

### The gallery

Their gallery is a page, not a sheet. Two views — *in groups*, a shelf per kind,
and *everything*, one grid newest first — plus search, tag chips, choosing
several at once, a zip, the trash, and a shelf of saved **characters** whose
pages list everything they appear in.

### Help with the hard part

"Help me write it" expands a few words into a full prompt — and given a picture,
*looks at it* and writes a prompt for animating what is actually there.
"Surprise me" invents an idea. "Mix it up" takes one used before and re-rolls
the look. Style, place, lighting, colour, mood and camera are dropdowns, in
alphabetical order, so a good prompt does not require knowing how to write one.

A **character** can be saved from a picture and put in later ones. Be clear
about what that gives you: a family resemblance, not the same character twice.
Flux cannot promise identity without extra models. What it reliably repeats is
the species, the colours and the clothes, which is enough for a story to read as
being about one person — and the character's own saved picture is kept, so
"Animate this" on *that* still starts from an identical frame.

### Seven languages

**Seven languages — the whole interface, in any of them.** English, French,
German, Spanish, Italian, Dutch and Portuguese. A row of chips in their Settings
tab switches the page: every button, every dropdown, the closed sign, the
progress bar, the refusals, and the helpers, which answer in whichever one is
on. The choice is a cookie, so whoever is at the screen makes it; the setting
on the parent page is only what a browser that has never chosen opens in, and
the parent page stays English itself. A child can also just type in any of the
seven and the helpers follow. The prompt that reaches the image model is
translated to English regardless, because that is measurably what it
understands; song lyrics are the exception and are never translated. The
blocklist covers all seven - which is the rule that decides how many there
are: a language the filter does not know would be a language nothing is
checked in.

### Who is using it

**Who is using it** — optional profiles, so two children are not one child.

Each profile has a name, a face, an age and its own copy of every rule a parent
can set: its own gallery, its own daily limits, its own makers, its own
timetable, its own sums, its own colour scheme. **One profile means no sign-in
screen at all** — the picker and the header chip are hidden entirely. A
**Family** shelf is the middle ground between "each child their own" and "share
everything": mark one picture, video or song "show the family" and it appears in
every profile's gallery, with the maker's name on it, while the rest stays
private.

**This is a curtain, not a lock.** Signed in as themselves, a sibling cannot
find, star, rename, trash or build on another child's work. But a direct media
URL still opens, and switching profiles is one tap with no PIN — the Netflix
model, chosen on purpose for a shared iPad. If you need a real lock, this is not
it yet.

### For the grown-ups

**For the grown-ups** — `/parent`, behind a PIN. Eight tabs:

| | |
|---|---|
| **Right now** | today's pictures at a glance, a one-line "is it working?", the live GPU and VRAM figures, and the pause switch |
| **Who uses it** | add, rename, re-face and remove profiles; the everybody-sees-everybody switch |
| **Rules** | daily limits on pictures, videos and songs with a one-tap top-up that expires at midnight; the weekly **timetable**; the warm-up sums; which makers exist |
| **Alerts** | the nightly email, the phone messages, the Telegram bot, and what happens after a refusal |
| **Their stuff** | the chat transcript, the trash and how long it keeps things, uploads the vision model refused (with an Allow button), and save-it-all zips |
| **Log** | everything the app has done, each entry sealed against the one before it, filterable by day, child and kind, and downloadable as CSV or JSONL |
| **Settings** | what it talks to, how it keeps time, the PIN, tidying up, how files are named, which Ollama model does which job, and **backup and restore** — one file with every setting, profile and face in it |
| **What it tells the AI** | **every instruction this app gives a model** — all twenty-one of them, with what each decides and whether it carries safety rules, so they can be read without opening the source. A switch on the tab makes them editable too |

### A weekly timetable

So the pause switch does not need flipping twice a day.
Up to four windows per day, `mon=16:00-18:30;…;sun=`, set on the parent page or
in `OPEN_HOURS`. Outside them the child sees *when* it opens, not just "back
soon"; a render already running is left to finish; and a one-tap override opens
it for the rest of today and expires at midnight. The pause switch still wins.

### Telling a grown-up what happened

**Messages to a phone**, through [Apprise](https://github.com/caronc/apprise):
Telegram, WhatsApp, Signal, ntfy, Discord, Matrix and about 150 more, one URL
per service in `NOTIFY_URLS`. Every picture as it is made (optionally with the
file attached), running out for the day, the daily summary, a wrong parent PIN,
or anything the word filter stopped — each switchable on the parent page. Tags
in front of a URL say what that place gets, so the pictures can go to Telegram
and the alerts to a phone:

```
NOTIFY_URLS="
  made,file=tgram://<bot token>/<chat id>
  limit,flagged=ntfy://ntfy.sh/mytopic
"
```

**An optional nightly email** with thumbnails of everything made that day and
the words under each, plus a second one the moment a daily limit runs out. It
goes out either through a plain SMTP relay or through Apprise, so the
"Apprise URL" box accepts anything Apprise speaks — Gmail with an app password,
SendGrid, SES.

**The Telegram bot can answer back**, if you turn it on (a switch on the
parent page, or
the switch on the parent page):

| | |
|---|---|
| `/today` | what has been made today, and what is left |
| `/more` | five more pictures today — `/more 10`, or `/more 5 videos` |
| `/last` | send me the newest thing |
| `/pause` / `/open` | close the factory, open it again |
| `/hours` | the timetable, and when it next opens |
| `/lock` / `/unlock` | bolt the parent page shut, even with the PIN; `/unlock` also clears every wrong-PIN lockout and says which |
| `/help` | what it can do |

Or a question in your own words, answered by Ollama from today's real numbers.
Only the chat IDs on that card — or, with the box left empty, the ones already
in `NOTIFY_URLS` — may use it; anyone else is ignored
without a reply. The model only reads: everything that changes the app is a
command you typed, and a question asked mid-render is answered without loading a
model at all, so it never costs a render.

## Using it

**The child's page** is `/`. Tabs across the top — Picture, Video, Comic, Music,
Story, Chat, Gallery, and a Settings tab holding their own face, their colour
scheme and a maker for the banner at the top of the page — and a bar that says
what is rendering and how far along, on every tab, with a "Show me" button. One
job at a time: a second start is refused rather than queued, so the progress bar
always means the thing being watched.

Three things can stand between a tap and a render, all enforced on the server
and not just hidden on the page:

- **the warm-up sums** — three arithmetic questions before the first make of the
  day, at a level and in the kinds a parent picks. No score is kept and there
  is no lockout, but a wrong answer means a fresh set. A closed factory asks
  for no sums.
- **the daily limits** — pictures, videos and songs counted between local
  midnights, per profile. The trash counts too, so deleting does not refund.
- **the pause switch and the timetable** — either closes it, and a render
  already running is left to finish.

With more than one profile there is a picker on the way in and a face in the
header. With one, none of that exists.

**What files are called** is a setting too, under *Settings*: a pattern per
kind of thing - `{kind}_{n:05}_` out of the box, which is exactly what ComfyUI
writes - built from `{date}`, `{time}`, `{kind}`, `{who}`, `{n}`, `{idea}` and
`{seed}`, with a live preview of the next name beside each box. `{n}` is
counted in the database rather than by looking at the folder, so a number is
never handed out twice however much is deleted. Files already in the gallery
keep the names they have.

**The parent page** is `/parent`, and the PIN is the only thing protecting it —
set it on that page, or as `PARENT_PIN` in `.env`. **There is no way to switch
it off.** An empty `PARENT_PIN` means the published default `1234` applies, not
that the gate goes away; it used to mean exactly that, and an unconfigured
install let everybody through, which made this the one setting whose unset
state was the insecure one. The app warns on every start until it is changed.
Five wrong PINs lock the box for ten minutes and can send you a message;
changing the PIN needs the current one typed in again, and has its own five.
The eight tabs are listed under [For the grown-ups](#for-the-grown-ups).

## Safety

Be clear about what is and is not filtered.

**What is:** `safety.check_prompt()`, an input-side blocklist in
`app/safety.py`, runs on every `/api/generate/*` route before anything reaches
ComfyUI, and returns a friendly 400 on a hit. Its categories are sexual
content, sexualised minors, graphic violence, weapons, drugs, hate, real named
people and scary imagery, in **all seven languages**, matched on word
boundaries after accent-folding and a little leetspeak substitution. Song
lyrics and chat replies get narrower lists of their own (`LYRIC_CATEGORIES`,
`CHAT_CATEGORIES`), because the full picture list refuses ordinary words in a
sentence — "blood" in "why is blood red?", "hanging" from a tree. Two switches
on the parent page apply the whole list to those. Chat replies are filtered in
full before any of the reply is shown, which is why chat does not stream.
Uploaded photos additionally go past the vision model, unless a parent turns
that off, and it fails *open* if Ollama is unreachable — it is the child's own
camera roll.

**What is not:** the negative prompts. Every workflow here runs at **CFG 1.0**,
where negative conditioning is mathematically ignored — the guidance term that
would subtract it is multiplied by zero. The negative prompts injected into
every job therefore have **no effect on the output today**. They are written out
in full so they start working if CFG is ever raised. Nothing screens the
*output* of an image or video model either. The blocklist is the only real
content filter, which is why **no route may skip it**.

**There is no setting that turns the blocklist off**, and no mode in which it
does not run.

**A refusal can close the factory.** Off by default. The parent page has three
levels — tell me only, close it for a photo the picture checker refused, or
close it for that *and* anything the word filter stops. The middle one is the
one worth having: the checker looked at an actual image and said no, where the
word filter also stops "gun" in a sentence about a water pistol. Either way the
grown-ups are told immediately, with the refused picture attached, and a closure
is reported whatever the notification switches say — they are the only people
who can open it again.

**And the part that is not a content question at all:** there is no login on
the child's side, and profiles are a curtain rather than a lock. See [Before
you let a child at it](#before-you-let-a-child-at-it).

## Settings, and where they live

Ninety variables, and only sixteen of them can still be answered from `.env`
once the app has started once. `.env.example` is laid out in the three parts
below and says the same thing in the same order, so either file can be read on
its own.

### `.env` is three different things

**Seven that only `.env` can answer.** Compose reads them to build the
container at all — the paths it mounts, the user it runs as, the network it
joins, the port it publishes and what to call the container. There is no app
yet at the moment they are read, so there is nowhere else they could come from.
Change one and rebuild.

| Group | Variables |
|---|---|
| Where things are | `GALLERY_DIR`, `STATE_VOLUME`, `COMFY_INPUT_DIR_HOST`, `RUN_AS` |
| Where it listens | `HOST_PORT`, `CONTAINER_NAME` |
| Which network | `NETWORK_NAME` |

**Nine the parent page can set too.** `.env` is the fallback and still
applies; a value set on the page wins, and clearing the box on the page puts
`.env` back. **Nothing here is ever copied into the database**, so upgrading
and changing nothing behaves exactly as it did before. The startup log says,
for each one, which of the two is in force — and never what it is.

| Variable | On the page | Live, or a restart? |
|---|---|---|
| `COMFY_URL` | Settings → What it talks to | **restart** — the app holds one WebSocket open to it for progress |
| `OLLAMA_URL` | Settings → What it talks to | live, from the next request |
| `LOG_LEVEL` | Settings → What it talks to | live, from the next log line |
| `TZ` | Settings → What it talks to | **restart** — see below |
| `PARENT_PIN` | Settings → The PIN on this page | live |
| `DIGEST_SMTP_PASS` | Alerts → Daily email → The relay password | live, from the next email |
| `DIGEST_URL` | Alerts → Daily email → Or one Apprise URL | live, from the next email |
| `NOTIFY_URLS` | Alerts → Messages to your phone → Where they go | live, from the next message |
| `TELEGRAM_BOT_TOKEN` | Alerts → Asking the bot things → The bot's own token | live; the bot starts listening within half a minute |

`TZ` is applied once, as the app starts, and deliberately not while it is
running. Every "today" in this app — the daily limits, the sums, whether
tonight's email has gone, the date in a filename — is measured against that
clock, and moving it under a day that is already half over would reset or
freeze that day's allowance. A restart is the honest way to move a clock.

**The five credentials are handled differently from every other box on that
page**, and this is the part worth reading before trusting it:

- **They are left out of the backup file.** They are not settings rows at all —
  they live in a store of their own that the export skips — because the backup
  is the file you are told to email to yourself, and a relay password, a bot
  token, two URLs with credentials in them and the PIN do not belong in it.
  **And a restore puts the live ones back** rather than clearing them, so
  restoring last week's file does not take the relay password off a working
  install. `DIGEST_URL` joined them late: it was an ordinary setting, and the
  example everything documents it with is
  `mailtos://you:apppassword@gmail.com`, so an installation that took that
  advice had a mail password in every backup it had made. One that already has
  one stored has it moved out of the settings on the next start, with nothing
  to do by hand and nothing left behind in the old place.
- **They are never shown back.** The page says whether one is set and where it
  came from, and offers Replace and Clear. There is no route that returns one.
- **They are taken back out of every log line**, including the request URLs
  httpx writes — which for the Telegram bot *is* the token — and out of the
  activity log, which records that a credential changed and never which one it
  became.
- **The PIN has extra rules**, because it is the lock on the page it is on:
  changing it needs the current one typed in again, it cannot be set to
  nothing, five wrong goes lock the box for ten minutes, and there is no button
  that removes it. See *Forgetting the PIN* below.

**Three boxes ask for the PIN**, and each keeps its own count of five wrong
goes and its own ten-minute lockout: the grown-up box on the sums, the parent
page itself, and changing the PIN. Separate counts, so that somebody guessing
at one cannot lock you out of another — a child who gets the sums overlay
wrong five times must not be able to shut their parent out of the settings
page.

They have to be separate, and the reason is worth knowing because it is the
kind of thing that looks fine and is not. A correct PIN used to clear the count
of wrong ones — a reasonable rule, meant for a parent who fumbles their own PIN
and then gets it right. But the parent page stores the PIN in the browser and
sends it with every request, and it polls every thirty seconds. So an open
parent tab was clearing that count all day with nobody at the keyboard — and
the count it cleared is the one guarding the grown-up box **on the child's own
page**. A tab left open on a laptop was quietly handing back guesses being
spent on the iPad.

Now only a PIN somebody actually *types* forgives the misses. The forgiving is
still there — mistype yours four times, get it right, and you are not locked
out — it just no longer happens on its own. Nothing anywhere lifts the word
filter, whoever gets in.

If you are locked out and you have the Telegram bot set up, `/unlock` clears
all three and tells you which ones it cleared.

#### Forgetting the PIN

A PIN set on the page lives in `state.db`, where `PARENT_PIN` in `.env` cannot
reach past it. To go back to the one in `.env` — or to the built-in `1234`, if
`.env` has none — remove the stored one, which takes a shell on the machine:

```bash
docker compose exec makery python -c \
  "from app import gallery, config; config.clear('parent_pin')"
```

That this needs the host is the point: it is the difference between a lock you
can lose the key to and a lock anybody already past it can take off.

**Seventy-four first-run defaults.** Everything else, and everything a
parent would change. Each one is read **once**, on the first start against an
empty database, to fill in a setting — and after that the parent page owns it
and `.env` is never consulted for it again. Editing one later and rebuilding
does nothing, which is the point: a setting that can be written from two places
is a setting nobody can answer a question about. They are kept in
`.env.example` anyway, values and all, because the list is also the answer to
"what can this thing be told to do?".

| Group | Variables | Where it is afterwards |
|---|---|---|
| Which makers exist | `ENABLE_PICTURE`, `ENABLE_VIDEO`, `ENABLE_COMIC`, `ENABLE_MUSIC`, `ENABLE_CHAT`, `ENABLE_STORY` | Rules → What they can make |
| When it is open | `OPEN_HOURS` | Rules → When it is open |
| The warm-up sums | `DAILY_QUIZ`, `QUIZ_QUESTIONS`, `QUIZ_BYPASS_MINUTES`, `QUIZ_LEVEL`, `QUIZ_OPS` | Rules → Sums first |
| The filter | `SCREEN_UPLOADS`, `CLOSE_ON_REFUSAL`, `CHAT_STRICT`, `MUSIC_STRICT`, `PROMPT_EDITING` | Rules → If the filter says no; What it tells the AI |
| How long things may be | `VIDEO_MIN_SECONDS`, `VIDEO_MAX_SECONDS`, `VIDEO_DEFAULT_SECONDS`, `VIDEO_MAX_SECONDS_SHARP`, `MUSIC_MIN_SECONDS`, `MUSIC_MAX_SECONDS`, `MUSIC_DEFAULT_SECONDS` | Rules → How long things can be |
| Tidying up | `TRASH_DAYS`, `INPUT_SWEEP_HOURS`, `MAX_CHARACTERS` | Settings → Tidying up |
| How many backups to keep | `BACKUP_KEEP` | Settings → Backup and restore |
| The activity log | `AUDIT_KEEP_DAYS`, `AUDIT_WORDS` | Log |
| The nightly email | `DIGEST_ENABLED`, `DIGEST_AT`, `DIGEST_MAX_ITEMS`, `DIGEST_LIMIT_NOTICE` | Alerts → Daily email |
| Which messages | `NOTIFY_ON_MADE`, `NOTIFY_ATTACH`, `NOTIFY_ON_LIMIT`, `NOTIFY_ON_DIGEST`, `NOTIFY_ON_FLAGGED`, `NOTIFY_ON_PIN`, `NOTIFY_MAX_MB` | Alerts → Messages to your phone |
| Who it is for | `KID_NAME`, `KID_AGE` (they make the *first profile*, and nothing else), `APP_TITLE` | Who uses it; Settings → Words and wording |
| Where the email goes | `DIGEST_TO`, `DIGEST_SMTP_HOST`, `DIGEST_SMTP_PORT`, `DIGEST_SMTP_STARTTLS`, `DIGEST_SMTP_USER`, `DIGEST_FROM`, `DIGEST_FROM_NAME`, `DIGEST_SUBJECT`, `DIGEST_LIMIT_SUBJECT` | Alerts → Daily email → Email server |
| The bot | `TELEGRAM_ASK`, `TELEGRAM_CHAT_IDS`, `TELEGRAM_TIMEOUT` | Alerts → Asking the bot things |
| Wording | `UI_LANG`, `KID_PRONOUN` | Settings → Words and wording |
| Which model does which job | `SCRIPT_MODEL`, `CHAT_MODEL`, `TELEGRAM_MODEL` | Settings → The helpers |
| How they are held | `SCRIPT_KEEP_ALIVE`, `CHAT_KEEP_ALIVE`, `COMFY_FREE_AFTER_JOB`, `CHAT_NAME`, `CHAT_KEEP_MESSAGES` | Settings → The helpers |
| What files are called | `FILENAME_PICTURE` … `FILENAME_OTHER` | Settings → How files are named |

`KID_NAME` and `KID_AGE` are in the lower half for the same reason as the
rest: they make the *first profile* on an empty installation and are never
read again. A name and an age belong to a profile afterwards, and the emails,
the page title and the bot all follow that profile.

**Upgrading from a version that read these?** Nothing to do. The old
`.settings.json` is imported on the first start and renamed to
`.settings.json.migrated` — never deleted — and anything it left to the
environment picks up the value in `.env`. The log says what came across. The
nine in the middle table are not migrated at all: nothing is copied out of
`.env` for them, so they keep answering from the file until somebody fills in
the box on the page.

### Where the settings actually live

One `state.db` in the `/state` volume, in WAL mode, keyed by `(scope, key)` —
scope is the household or a child's profile. Nothing the app *decides* is
written into `GALLERY_DIR`: not the settings, not the characters, the chat
transcript, the prompt overrides or the render timings. That volume is
deliberately somewhere other than ComfyUI's shared output directory, which is
the first thing anyone wipes when a disk fills up. Point `STATE_VOLUME` at a
host path if you would rather read it, and `chown` that path to `RUN_AS` first.

### Backing it up

The parent page, under **Settings**, has a *Backup and restore* card.

- **Download a backup** gives you one JSON file with every setting for every
  child, who the children are and what their faces look like, their characters,
  the words they have asked for before, the chat, the prompt overrides, the
  render timings and their banner. A few hundred kilobytes. Mail it to yourself.
- **It is not their gallery.** The pictures, videos and songs are the gigabytes,
  and they are already files on a disk you can copy — `GALLERY_DIR`.
- **Restoring** replaces all of the above with what is in the file. It is an
  armed two-tap, it takes a copy of what is there now first, and it never
  renumbers a child, so their pictures stay theirs.
- **One is made every night**, into `/state/backups`. How many are kept is a
  box on that card — the newest few of *each* kind, counted separately, so a
  run of nightly ones cannot push out the copy taken five minutes before a
  restore. They are listed on the same card with a Restore beside each.
- **There is not one credential in it.** The relay password, the bot token, the
  notify URLs and the PIN are deliberately not settings rows, so they are not
  in the file and a restore does not clear the ones this installation has.
- **The activity log rides along in it**, and a restore can only ever *add* to
  the log — see below.

### The log

The parent page's **Log** tab lists everything the app has done: what was made,
what was deleted and put back, what the filter stopped, every setting change
with its old and new value, who signed in, and wrong PINs. Filter it by day, by
child and by kind; download it as CSV or JSONL.

It lives in an append-only table in `state.db`, and **each entry is sealed
against the one before it**. *Check the chain* recomputes every seal and either
says "intact" or names the entry where it breaks and why. Nothing in the app
deletes or shortens it — there is no button and no route. To be plain about the
limit: anybody with a shell on the server can delete the database. The app
never will, and the chain shows if somebody did.

`AUDIT_KEEP_DAYS` is `0` — keep it for ever — and that is the default. Set a
number of days and the nightly sweep trims the oldest, writing an entry that
says it did so, so the gap has an explanation sealed behind it.

## Setting up the whole stack

This is for someone with a GPU and nothing else installed. If ComfyUI and
Ollama are already running, you only need [the models](#the-models-comfyui-needs)
and [Running it](#running-it) above.

### What the machine needs

- An **NVIDIA GPU**. 16 GB is what this was built and measured on, and it is
  close to the floor:
  - a 15-second video at *normal* peaks near 15.5 GB of a 16.3 GB card, which
    is why 15 seconds is the shipped ceiling and *sharper* has its own lower one
    (10 seconds by default);
  - the four Flux 2 Klein edit graphs are the tightest thing here — 15.2 to
    15.8 GB measured — which is why the outpaint canvas is capped at 1.45
    megapixels rather than finding out what an OOM looks like.

  A bigger card has room for more; `VIDEO_MAX_SECONDS` is the setting to raise,
  a few seconds at a time, watching the VRAM figure on the parent page.
- **~92 GB of disk for models** — about 81 GB for ComfyUI, about 11 GB for
  Ollama — plus another 20 GB if you want music, and room for what gets made. A
  5-second video is 1–3 MB and a 30-second song about 1 MB.
- **Docker**, **Docker Compose**, and the **NVIDIA Container Toolkit** so
  containers can see the card:

  ```bash
  # Debian/Ubuntu, after installing Docker itself
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
  sudo apt update && sudo apt install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
  docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi   # must print your card
  ```

### One compose file for ComfyUI and Ollama

Makery ships its own `docker-compose.yml` and **joins an existing
network** rather than defining these itself, so that it can sit beside a
ComfyUI you already have. If you have neither, this is a stack to start from.
Put it somewhere of its own — `~/ai-stack/compose.yaml` — and adjust the paths.

```yaml
services:
  comfyui:
    image: mmartial/comfyui-nvidia-docker:ubuntu24_cuda13.2-latest
    container_name: comfyui
    restart: unless-stopped
    gpus: all
    ports:
      - "8188:8188"
    environment:
      # The uid/gid everything under /basedir is owned by on the host. Make a
      # user for it (`sudo useradd -r comfyui`) and use its ids, or use your
      # own - but see "File ownership" below before choosing.
      WANTED_UID: 999
      WANTED_GID: 987
      BASE_DIRECTORY: /basedir
      USE_UV: "true"
      NVIDIA_VISIBLE_DEVICES: all
      NVIDIA_DRIVER_CAPABILITIES: all
    volumes:
      - ./comfyui/run:/comfy/mnt          # ComfyUI itself, and its venv
      - ./comfyui/basedir:/basedir        # models, input, output, custom nodes
    networks: [aistack]

  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: unless-stopped
    gpus: all
    ports:
      - "11434:11434"
    environment:
      OLLAMA_CONTEXT_LENGTH: "32768"
      OLLAMA_KEEP_ALIVE: "10m"
    volumes:
      - ollama:/root/.ollama
    networks: [aistack]

networks:
  aistack:
    driver: bridge

volumes:
  ollama: {}
```

```bash
docker compose up -d
docker network ls | grep aistack    # -> "<dirname>_aistack": that is NETWORK_NAME
```

The first ComfyUI start installs itself into `./comfyui/run` and takes several
minutes. `docker compose logs -f comfyui` until it serves on 8188.

### The models ComfyUI needs

Twelve files, about 81 GB, plus four more if you want the Music tab. The names
matter: they are what the graphs in `workflows/` load by name, and a mismatch is
a failed render rather than a warning. They go under `basedir/models/` in the
directories below.

The first seven are what the picture and video tabs need — without the rest
everything still works except the buttons named beside them.

| File | Directory | Size |
|---|---|---|
| `flux1-schnell-fp8.safetensors` | `checkpoints/` | 17.2 GB |
| `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` | `diffusion_models/` | 21.5 GB |
| `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | `text_encoders/` | 15.4 GB |
| `gemma4_e2b_it_int8_convrot.safetensors` | `text_encoders/` | 5.2 GB |
| `ltx-2.5-video-vae-bf16.safetensors` | `vae/` | 1.5 GB |
| `ltx-2.5-audio-vae-bf16.safetensors` | `vae/` | 0.4 GB |
| `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` | `latent_upscale_models/` | 1.0 GB |

Three more for **"Turn it into…"**, "Change this picture", "What's outside the
frame?" and "Fix just this bit" — Flux 2 Klein 9B, the distilled one, at four
steps, shared by all four graphs:

| File | Directory | Size |
|---|---|---|
| `flux-2-klein-9b-fp8.safetensors` | `diffusion_models/` | 9.4 GB |
| `qwen_3_8b_fp8mixed.safetensors` | `text_encoders/` | 8.7 GB |
| `flux2-vae.safetensors` | `vae/` | 0.3 GB |

And two small ones for the buttons under a finished picture or video:

| File | Directory | Size | For |
|---|---|---|---|
| `4x-UltraSharp.pth` | `upscale_models/` | 67 MB | "Make it huge" |
| `rife49.pth` | `custom_nodes/comfyui-frame-interpolation/ckpts/rife/` | 21 MB | "Make it smooth" / "Slow it down" |

And four more for the Music tab, which is optional — without them the tab
hides itself and everything else works:

| File | Directory | Size |
|---|---|---|
| `acestep_v1.5_xl_turbo_bf16.safetensors` | `diffusion_models/` | 10.0 GB |
| `qwen_4b_ace15.safetensors` | `text_encoders/` | 8.4 GB |
| `qwen_0.6b_ace15.safetensors` | `text_encoders/` | 1.2 GB |
| `ace_1.5_vae.safetensors` | `vae/` | 0.3 GB |

The easiest way to get exactly these is ComfyUI itself: open the **Flux schnell**,
**LTX 2.5**, **Flux 2 Klein image edit (9B, distilled)** and **ACE-Step 1.5**
templates from its own Templates browser and accept the model downloads it
offers. They land in the right directories under the right names.
Otherwise they are on Hugging Face — Flux schnell from Comfy-Org's repackaged
repository, the LTX 2.5 set from Lightricks and Comfy-Org — and you can drop
them in by hand.

**One custom node pack is needed, and only for one button.** `RIFE VFI` comes
from [ComfyUI-Frame-Interpolation](https://github.com/Fannovel16/ComfyUI-Frame-Interpolation)
and is what "Make it smooth" and "Slow it down" run on; without it those two
buttons fail and nothing else notices. Every other node these graphs use ships
with ComfyUI (`nodes` and `comfy_extras`) — checked one class at a time against
`GET /object_info` on 0.35.0, including the `LTXV*` family, `ResolutionSelector`,
`LatentUpscaleModelLoader`, and the whole Flux 2 set (`EmptyFlux2LatentImage`,
`Flux2Scheduler`, `ReferenceLatent`, `ImagePadForOutpaint`,
`VAEEncodeForInpaint`). If ComfyUI is old enough not to have them, update it
rather than installing anything.

Makery checks at startup: it asks ComfyUI what it has and logs a line
naming any file a workflow wants and ComfyUI cannot see, so a missing model is
something you read in the log rather than something a child discovers by
tapping Go.

### The models Ollama needs

```bash
docker exec ollama ollama pull qwen3-vl:4b-instruct   # 3.3 GB - required
docker exec ollama ollama pull gemma4:12b             # 7.6 GB - optional
```

- **`qwen3-vl:4b-instruct`** is the idea helper: the "help me write it"
  buttons, the French translation, the comic and film planning, and the
  screening of uploaded photos. It **must be a vision model** — three of those
  jobs send it an image, and a words-only one answers about a picture it was
  never shown. Any vision model Ollama has will do; this one is small and quick
  enough that a helper tap does not feel like a render.
- **`gemma4:12b`** is the Chat tab, and the Telegram answers if you turn those
  on. It is optional: without it the Chat tab hides itself. A smaller model
  works and is worth trying — 12b is 7.6 GB and cannot be resident while a
  video renders, so every chat message pays a load.

Both are pulled into the `ollama` volume and survive a rebuild.

**Pull first, then choose.** The parent page lists what Ollama reports, with
each model's size and whether it can see a picture, and a **Test** button that
runs one short question through it and shows the reply and how fast it came
back. `SCRIPT_MODEL`, `CHAT_MODEL` and `TELEGRAM_MODEL` in `.env` only seed
those three choices on the first start. A model that is chosen and then deleted
from Ollama is noticed at the next start: the log says so and the choice goes
back to what `.env` seeded, rather than failing on their first tap.

### Then Makery

Clone it, `cp .env.example .env`, and with the stack above the four settings
that matter are:

```ini
GALLERY_DIR=/home/you/ai-stack/comfyui/basedir/output/makery
NETWORK_NAME=ai-stack_aistack     # whatever `docker network ls` showed
COMFY_URL=http://comfyui:8188
OLLAMA_URL=http://ollama:11434
```

Make the gallery directory first, owned the way [File ownership](#file-ownership)
describes, or ComfyUI will make it as itself and the app will not be able to
delete from it:

```bash
mkdir -p comfyui/basedir/output/makery
sudo chown 999:987 comfyui/basedir/output/makery
sudo chmod 2775 comfyui/basedir/output/makery   # setgid, group-writable
```

Then `docker compose up -d --build`, and `http://<host>:8095`.

### File ownership

The container has to be able to **delete** from `GALLERY_DIR`, which ComfyUI
owns. Unlinking needs write permission on the *directory*, not the file, so the
usual arrangement is: the directory owned by ComfyUI's group, group-writable
and setgid, and `RUN_AS` set to a uid in that group — `RUN_AS=1001:987` where
987 is ComfyUI's gid. Get this wrong and everything works except deleting.

ComfyUI's own umask is usually 022, so the files it writes are `644`: readable
and deletable through a group-writable directory, but not editable in place.
That is fine — this app only ever reads and unlinks them.

If you point `STATE_VOLUME` at a host path, create it and `chown` it to `RUN_AS`
before the first start. Docker creates a missing bind-mount source as
`root:root 0755`, the container cannot write to it, and the app then quietly
keeps nothing.

### Putting it behind a name

Optional — it works on a port. If you want `make.example.net` instead, this is
an nginx vhost that handles the two things that matter, a **WebSocket** and a
**7-day read timeout**, because a render holds the connection for minutes:

```nginx
map $http_upgrade $connection_upgrade { default upgrade; '' close; }

server {
    listen 443 ssl;
    http2  on;
    server_name make.example.net;

    ssl_certificate     /etc/letsencrypt/live/example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example/privkey.pem;

    client_max_body_size 0;          # photos come straight off an iPad

    location / {
        # A variable, resolved per request against Docker's DNS: with a literal
        # hostname here, nginx refuses to start whenever the app is down.
        resolver 127.0.0.11 valid=30s;
        set $upstream http://makery:8000;
        proxy_pass $upstream$request_uri;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        proxy_buffering off;         # progress must arrive as it happens
        proxy_read_timeout 7d;       # a render is minutes, not seconds
        proxy_send_timeout 7d;
    }
}
```

Run nginx in the same compose file, on the same network, and `nginx -t` before
every reload.

**Use HTTPS if you can.** Two things need a secure context in Safari: recording
a voice-over, and taking a photo with the camera. On plain HTTP the buttons are
there and say why they cannot work.

### Without Docker

```bash
pip install -r requirements.txt
GALLERY_DIR=/path/to/comfyui/output/makery \
STATE_DIR=/path/to/makery-state \
COMFY_URL=http://127.0.0.1:8188 \
OLLAMA_URL=http://127.0.0.1:11434 \
uvicorn app.main:app --port 8000
```

`STATE_DIR` defaults to `GALLERY_DIR` if you leave it out, which works but puts
the settings in with the pictures.

### Whose it is

`KID_NAME` and `KID_AGE` make the **first profile** and nothing else. From
there the name reaches the page title, the movie title cards, the email
subjects and the parent page — but it reaches them *through the profile*, so
renaming them under "Who uses it" changes tonight's email subject too. Leave the
name empty and everything reads neutrally ("My AI Factory", "Your child made 3
pictures today"). What the whole thing is called can also be overridden
outright, under Settings → Words and wording. The pronoun — `she`/`he`/`they` — is a setting on
the parent page (`KID_PRONOUN` seeds it) and is only used in the parent-facing
text, where the sentences are *about* the child; everything the child reads is
already second person.

`KID_AGE` is the one that changes what comes *out*. The model instructions ask
for "a capable `{age_old}`" rather than spelling an age into each of them, so
this decides whether the ideas, stories and chat replies read as written for a
capable reader or for a toddler. Leave it empty and they all say "a child",
which works but is vaguer.

## The API

One FastAPI app, everything under `/api`, JSON in and JSON out, and **no
authentication at all except `X-Parent-Pin` on the parent routes** — see
[Before you let a child at it](#before-you-let-a-child-at-it). Roughly:

| | |
|---|---|
| `POST /api/generate/{image,t2v,i2v,flf,story,comic,music,banner}` | start a render → `{job_id}`. Every one of these runs the blocklist first |
| `GET /api/parent/log`, `/log/verify`, `/log/export` | the activity log, the chain check, and the download. Read-only: nothing shortens it |
| `GET /api/job/{id}`, `POST /api/job/{id}/cancel`, `GET /api/active` | progress, cancellation, and reattaching after a reload |
| `GET /api/result/{id}` | the finished file |
| `GET /api/gallery`, `/api/gallery/{id}/{file,thumb,poster,preview,last-frame}` | the output directory as a gallery |
| `POST /api/gallery/{id}/{edit,outpaint,inpaint,restyle,smooth,huge,sticker,loop,frame,voice,sound}` | everything made out of something already there |
| `PUT /api/gallery/{id}/{favourite,family,name}`, `POST /api/gallery/{tag,join,delete}`, `GET /api/gallery/{zip,trash}` | organising it |
| `POST /api/{script,surprise,remix,song-words}` | the Ollama idea helpers |
| `GET|POST /api/chat`, `GET|POST /api/quiz`, `GET /api/styles`, `/api/history`, `/api/characters`, `/api/profiles`, `/api/allowance`, `/api/health` | the rest of the child's page |
| `GET /api/parent/backup`, `POST /api/parent/restore` | the whole configuration as one JSON file, and back again |
| `/api/parent/*` | the grown-up page, behind `X-Parent-Pin`. There is always a PIN |

The full contract, with every request body and what each field means, is in
[`CLAUDE.md`](CLAUDE.md) under "Backend contract". It is not a public or
versioned API — it exists to serve the two pages in `static/`.

## Workflows

**The files in `workflows/` are data, not source.** Everything job-specific —
prompts, seeds, resolution, duration, output prefix — is patched at runtime by
`app/workflows.py` against node IDs documented in `CLAUDE.md`. If a re-export
renumbers a node, the patcher raises at startup rather than quietly rendering
the template's sample prompt instead of the child's.

Most of them are **API-format exports from ComfyUI**: re-export and drop in.
That is the convention, and `flux_schnell-api.json`, the three LTX 2.5 video
graphs and the ACE-Step one are all exactly that.

Six are the exception, and each carries a `_note` key at the top of the file
saying so, what it was built from, and the render that verified it:

- `image_flux2_klein_edit-api.json` and `..._edit_two-api.json` were converted
  from the two subgraphs of ComfyUI's own Flux 2 Klein image-edit template,
  keeping the model authors' settings, with the VAE and the reference sizing
  changed on purpose.
- `image_flux2_klein_inpaint-api.json`, `..._outpaint-api.json`,
  `image_upscale_esrgan-api.json` and `video_smooth_rife-api.json` were
  **built by hand from `GET /object_info`**, because no shipped template does
  those jobs. Input names, types and combo values were taken from what ComfyUI
  itself reported.

A key starting with an underscore is not a node; `_load()` skips it.

## Updating it

```bash
./safe-rebuild
```

`docker compose up -d --build` works, but rebuilding mid-render kills the job
the app is tracking. ComfyUI finishes the file regardless, so nothing is lost,
but the progress bar vanishes from under whoever was watching it and the sidecar
carrying the prompt is never written. `safe-rebuild` waits for ComfyUI's queue
to empty, rebuilds, and then recovers notes for any file that lost one.

## Layout

```
app/
  main.py        FastAPI routes and result streaming
  jobs.py        job registry, weighted progress, cancellation, chained graphs
  workflows.py   load the JSON graphs, patch nodes per job, resolution maths
  comfy.py       ComfyUI client: HTTP plus a shared progress WebSocket
  gallery.py     the output directory as a gallery; trash, stickers, audio
  naming.py      what a finished file is called, and the counter behind {n}
  store.py       one SQLite file: the settings, the counters and the log
  audit.py       what happened, each entry sealed against the one before it
  backup.py      one JSON file with everything a parent has decided in it
  safety.py      the prompt blocklist (all seven languages)
  scripts.py     the Ollama idea helpers
  chat.py        the chat tab, its filter and its transcript
  comic.py       stories into comic panels and film beats
  music.py       songs: the two boxes, the arrangements, the lyric filter
  restyles.py    the "Turn it into..." chips
  characters.py  characters that can be reused
  styles.py      the style / place / lighting / colour / mood phrases
  sounds.py      twelve sound effects, synthesised in numpy
  quiz.py        the daily warm-up sums
  profiles.py    a profile per child, and what each one owns
  schedule.py    the weekly timetable
  modules.py     which makers exist at all
  lockdown.py    what happens after a refusal
  timings.py     how long things took, so the next one can be predicted
  digest.py      the nightly email and its scheduler
  notify.py      messages to a phone, through Apprise
  telegram.py    the bot that answers back
  branding.py    whose instance this is, in one place
  themes.py      the colour schemes
  prompts.py     the registry of every model instruction, and its overrides
  uploads.py     photos and drawings from the tablet
  stats.py       NVML and /proc/stat for the live GPU/CPU readout
static/          the frontend: index.html, app.js, parent.html, parent.js, style.css
workflows/       ComfyUI graphs in API format - see above, and do not hand-edit
docs/            the screenshots at the top of this file, and nothing else
```

[`CLAUDE.md`](CLAUDE.md) is the long version, written for whoever maintains
this: the node maps, the resolution arithmetic, why the gallery needs the
permissions it does, the iOS traps, and the reasoning behind the decisions that
look odd.

## Licence

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

The files in `workflows/` are ComfyUI graphs kept as data rather than source,
and the models they load have licences of their own: check Flux schnell's,
Flux 2 Klein's, LTX 2.5's and ACE-Step's terms before using anything this
produces commercially.
