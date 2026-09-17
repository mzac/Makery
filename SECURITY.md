# Security

## What this project is, so a report can be judged against it

Makery is a self-hosted app for a home network. Several things that would be
vulnerabilities in a public web application are deliberate design decisions
here, and they are documented in the README under
[Before a child uses it](README.md#before-a-child-uses-it):

- **There is no authentication on the child's side.** No login, no session.
  Anything that can reach the port can make a picture, browse the gallery and
  delete from it. The app is meant to sit behind a home router and is not safe
  to expose to the internet.
- **The parent PIN has a published default of `1234`.** It is in the source
  and in `.env.example` on purpose, so that a fresh install has a gate at all.
  The app warns on every start until it is changed.
- **Profiles are a curtain, not a lock.** Switching profile takes one tap and
  no PIN, and a direct media URL opens for anyone holding it.
- **The content filter is input-side only.** It reads the words that were
  typed and refuses a match before anything reaches ComfyUI. It does not look
  at what the model produces, and the negative prompts in the workflows are
  inert at CFG 1.0.

Reports that amount to restating one of the above are not vulnerabilities, but
if you have found a way in that the README does not already admit to, please
do send it.

## In scope

- A way past `safety.check_prompt()` on any `/api/generate/*` route.
- A way to reach a `/api/parent/*` route without the PIN, or to defeat the
  five-guess lockout on any of the three boxes that take it.
- A path-traversal or arbitrary-read/write through a gallery id, a filename
  pattern, an upload, a backup filename or a restore.
- A credential (the PIN, the relay password, the Apprise URLs, the Telegram
  bot token) appearing in a backup file, a log line, the exported activity
  log or any API response.
- A way to forge a warm-up-sums pass, or to tamper with the activity log
  without the chain check noticing.
- Anything reachable by a child that can execute code on the host.

## Out of scope

- Anything that requires a shell on the machine already. A parent with root
  can delete the database; the app has never claimed otherwise.
- What the image, video, music or chat models choose to generate. Nothing here
  screens model output, and the README says so.
- Exposing the app to the internet and being compromised.
- The default PIN, on an installation where it has not been changed.

## Reporting

Use **[Report a vulnerability](https://github.com/mzac/Makery/security/advisories/new)**
on this repository's Security tab. That opens a private advisory, visible only
to you and the maintainer.

Please do not open a public issue for anything in the "In scope" list above.

Expect a first reply within a week. This is a hobby project maintained by one
person, so there is no formal SLA, no bounty, and no guarantee of a fix on any
particular timetable. What there is: a real answer, credit in the advisory if
you would like it, and the honest version of whether it can be fixed.

## Keeping an installation safe

- Change `PARENT_PIN`. The app tells you to on every start until you do.
- Keep it on the LAN. If you put it behind a proxy, put the proxy on the LAN
  too, and use HTTPS.
- Do not expose ComfyUI or Ollama to the internet either. Makery talks to them
  over a private Docker network and expects to be the only thing that does.
- Keep an eye on the **Log** tab. It records every wrong PIN, every refusal
  and every setting change, and the chain check will tell you if the log
  itself has been edited.
