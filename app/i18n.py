"""Seven languages, one set of strings.

The first child to use this read English and French, and asked for more. The
page is switched between the seven from the child's own Settings tab, and the
switch has to reach the *server* too: a good third of what a child reads is
written here rather than in the browser - the closed sign, the "you have two
pictures left" line, what the progress bar says while a video renders, every
dropdown label, and every refusal.

How it works:

- **English is the source of truth and it stays in the code.** `t()` is keyed
  by the English string itself, so a call site reads as the sentence it
  produces and a missing translation shows the English rather than a blank or
  a key. One dict per language, and each is the only place that language
  lives. **Every other language was translated from the English**, not from
  the French: a chain of translations drifts, and the English is the sentence
  somebody wrote on purpose.
- **A handful of keys are symbolic** (`_SHAPE` below) - the ones whose
  languages differ in *shape* rather than in words, where one template cannot
  serve all seven. Those are the only entries `_SHAPE` holds, and English
  falls back to them.
- **Which language is a ContextVar**, set once per request by `WhoIsThis` in
  main.py from the `lang` cookie, exactly as it sets `gallery.WHO`. Nothing
  had to grow a language argument.
- `UI_LANG` in the environment is only the starting language for a browser
  that has never chosen. The cookie wins whenever it is there.

What is deliberately **not** translated: every phrase that goes to a model.
The dropdowns' style phrases, the character looks, the comic panel rules, the
restyle instructions - Flux and LTX understand English and measurably do not
understand any of the other six (see CLAUDE.md). A child writes in their own
language and `scripts.to_english` translates on the way to ComfyUI; only the
*labels* on those choices live here.
"""

from __future__ import annotations

import contextvars
import re

# The order is the order the chips are shown in: English and French first
# because those are the two this was first written for, then the rest
# alphabetically by their own name. Adding one means a dictionary here, one in static/i18n.js,
# a blocklist in safety.py and a stop-word list in scripts.py - all four, or
# the language is only half there.
LANGS = ("en", "fr", "de", "es", "it", "nl", "pt")

# What each one calls itself. A language's name is always written in that
# language: "Français" is what they are looking for on the chip, not "French".
NAMES = {
    "en": "English", "fr": "Français", "de": "Deutsch", "es": "Español",
    "it": "Italiano", "nl": "Nederlands", "pt": "Português",
}


def _clean(value: str) -> str:
    value = (value or "").strip().lower()[:2]
    return value if value in LANGS else ""


# The starting language for a browser that has never chosen one. A setting on
# the parent page - UI_LANG seeds it on the first start and is not read again.
# Their own chip in Settings still wins over it, and that is a cookie rather than
# a setting on purpose: two sisters on one iPad can read different languages,
# and neither of them has to find a grown-up.
def default_lang() -> str:
    from . import gallery

    return _clean(gallery.text("ui_lang")) or "en"

# Whose language this request is in. "" means nobody has said, so the
# household's starting language above.
LANG: contextvars.ContextVar[str] = contextvars.ContextVar("lang", default="")

COOKIE = "lang"


def lang() -> str:
    return LANG.get() or default_lang()


def from_cookie(value: str) -> str:
    """The language a `lang` cookie asks for, or "" for anything unreadable."""
    return _clean(value)


# --- the dictionaries -------------------------------------------------------

# Only the keys whose English is not the key itself: a sentence whose two
# languages put the pieces in a different order needs a template each.
_SHAPE = {
    "closed-until-day": "It opens again on {day} at {when}!",
    "closed-until-next-day": "It opens again {day} at {when}!",
    # The title, whose possessive is the part that does not translate. Two
    # entries, because two of the seven have a second form the name itself
    # asks for - French elides "de Ada" to "d'Ada", German writes "Max'
    # KI-Fabrik" where it writes "Adas KI-Fabrik" - and the rest say the same
    # thing whatever the name is. `branding.title_for` picks; the key is named
    # for the French case because that is the one it was written for.
    "factory-of-elided": "{name}'s AI Factory",
}

FR: dict[str, str] = {
    # --- the sign on the door ---------------------------------------------
    "Back soon!": "À tout de suite !",
    "It opens at {when}. See you then!": "Ça ouvre à {when}. À tout à l'heure !",
    "It opens again tomorrow at {when}. See you then!":
        "Ça rouvre demain à {when}. À demain !",
    "closed-until-day": "Ça rouvre {day} à {when} !",
    "closed-until-next-day": "Ça rouvre {day} à {when} !",
    "The factory is closed right now. ": "La fabrique est fermée pour le moment. ",
    "midnight": "minuit",
    "midday": "midi",
    "today": "aujourd'hui",
    "tomorrow": "demain",
    "Monday": "lundi", "Tuesday": "mardi", "Wednesday": "mercredi",
    "Thursday": "jeudi", "Friday": "vendredi", "Saturday": "samedi",
    "Sunday": "dimanche",
    "next Monday": "lundi prochain", "next Tuesday": "mardi prochain",
    "next Wednesday": "mercredi prochain", "next Thursday": "jeudi prochain",
    "next Friday": "vendredi prochain", "next Saturday": "samedi prochain",
    "next Sunday": "dimanche prochain",

    # --- refusals they read ------------------------------------------------
    "The factory is closed right now. Back soon!":
        "La fabrique est fermée pour le moment. À tout de suite !",
    "One at a time! Wait for the one you're making now to finish, "
    "or tap Stop if you've changed your mind.":
        "Une chose à la fois ! Attends que celle que tu fabriques soit finie, "
        "ou appuie sur Arrêter si tu as changé d'avis.",
    "That's all the pictures for today - great work! Come back tomorrow.":
        "C'est tout pour les images aujourd'hui - beau travail ! Reviens demain.",
    "That's all the videos for today - great work! Come back tomorrow.":
        "C'est tout pour les vidéos aujourd'hui - beau travail ! Reviens demain.",
    "That's all the songs for today - great work! Come back tomorrow.":
        "C'est tout pour les chansons aujourd'hui - beau travail ! Reviens demain.",
    "That's switched off right now.": "C'est éteint pour le moment.",
    "Making pictures is switched off right now. Ask a grown-up!":
        "Les images sont éteintes pour le moment. Demande à un adulte !",
    "Making videos is switched off right now. Ask a grown-up!":
        "Les vidéos sont éteintes pour le moment. Demande à un adulte !",
    "Making comics is switched off right now. Ask a grown-up!":
        "Les BD sont éteintes pour le moment. Demande à un adulte !",
    "Making songs is switched off right now. Ask a grown-up!":
        "Les chansons sont éteintes pour le moment. Demande à un adulte !",
    "The chat is switched off right now. Ask a grown-up!":
        "Le chat est éteint pour le moment. Demande à un adulte !",
    "The story maker is switched off right now. Ask a grown-up!":
        "Le créateur d'histoires est éteint pour le moment. Demande à un adulte !",

    # --- the story maker ----------------------------------------------------
    "Make the film and the song first!": "Fais d'abord le film et la chanson !",
    "Couldn't put those together. Make sure it's a film and a song!":
        "Impossible de les assembler. Vérifie que c'est bien un film et une chanson !",
    "Couldn't put those together. Try again!":
        "Impossible de les assembler. Réessaie !",

    # --- the warm-up sums ---------------------------------------------------
    "Let's warm up your brain first! {sums} and the factory opens.":
        "On échauffe ton cerveau d'abord ! {sums} et la fabrique ouvre.",
    "One quick sum": "Un petit calcul",
    "Two quick sums": "Deux petits calculs",
    "Three quick sums": "Trois petits calculs",
    "Four quick sums": "Quatre petits calculs",
    "Five quick sums": "Cinq petits calculs",
    "Six quick sums": "Six petits calculs",
    "Seven quick sums": "Sept petits calculs",
    "Eight quick sums": "Huit petits calculs",
    "Nine quick sums": "Neuf petits calculs",
    "Ten quick sums": "Dix petits calculs",

    # --- the word filter ----------------------------------------------------
    "Type something you'd like to make first!":
        "Écris d'abord ce que tu aimerais fabriquer !",
    "That's a bit long! Keep it under {max} characters.":
        "C'est un peu long ! Reste sous {max} caractères.",

    # --- what the progress bar says (jobs.py) -------------------------------
    "Getting ready...": "On se prépare...",
    "Something went wrong making that one. Try again!":
        "Quelque chose n'a pas marché pour celle-là. Réessaie !",
    "The art computer is busy with someone else. Waiting for your turn...":
        "L'ordinateur à dessins travaille pour quelqu'un d'autre. C'est bientôt ton tour...",
    "Stopped! Nothing was made. Try a different idea.":
        "Arrêté ! Rien n'a été fabriqué. Essaie une autre idée.",
    "Picture {n} of {total}...": "Image {n} sur {total}...",
    "Part {done} of {total} filmed...": "Partie {done} sur {total} filmée...",
    "Panel {done} of {total} drawn...": "Case {done} sur {total} dessinée...",
    "Putting it all together...": "On assemble le tout...",
    "Looking at every frame...": "On regarde chaque image...",
    "Drawing all the in-between bits...": "On dessine tout ce qu'il y a entre...",
    "Putting it back together!": "On recolle tout !",
    "Getting your picture ready...": "On prépare ton image...",
    "Making it bigger, bit by bit...": "On l'agrandit, petit à petit...",
    "Almost done!": "Presque fini !",
    "Looking at your picture...": "On regarde ton image...",
    "Painting what's outside...": "On peint ce qu'il y a autour...",
    "Changing it...": "On la change...",
    "Nearly there!": "On y est presque !",
    "Working out the tune...": "On trouve l'air...",

    # --- what kind of sound: a song, a little tune, a background
    #     hum. One card and one model; see app/music.py KINDS.
    "Working out the hum...": "On trouve l'ambiance...",
    "Words, a tune and somebody singing them.": "Des paroles, un air, et quelqu'un qui les chante.",
    "A short tune with nobody singing - good for the start of a video.": "Un air court sans personne qui chante - parfait pour le début d'une vidéo.",
    "A long, quiet sound to put behind something else. No tune, no beat.": "Un son long et calme à mettre derrière autre chose. Pas d'air, pas de rythme.",
    "Playing it... this takes a moment.": "On la joue... ça prend un instant.",
    "Mixing it down!": "On mixe tout ça !",
    "Reading your story...": "On lit ton histoire...",
    "Drawing the panels...": "On dessine les cases...",
    "Putting the page together!": "On monte la page !",
    "Working out your story...": "On imagine ton histoire...",
    "Filming it, bit by bit... this takes a while.":
        "On la filme, bout par bout... ça prend un moment.",
    "Joining it into one film!": "On assemble le film !",
    "Thinking up your picture...": "On imagine ton image...",
    "Painting it now...": "On la peint maintenant...",
    "Getting the video ready...": "On prépare la vidéo...",
    "Making your video... this part takes a few minutes.":
        "On fabrique ta vidéo... cette partie prend quelques minutes.",
    "Adding the details and the sound...": "On ajoute les détails et le son...",
    "Your comic is ready!": "Ta BD est prête !",
    "Your film is ready!": "Ton film est prêt !",
    "Your song is ready!": "Ta chanson est prête !",
    "Your tune is ready!": "Ton petit air est prêt !",
    "Your sound is ready!": "Ton ambiance est prête !",
    "Your video is ready!": "Ta vidéo est prête !",
    "Your picture is ready!": "Ton image est prête !",
    "All {n} pictures are ready - pick your favourite!":
        "Les {n} images sont prêtes - choisis ta préférée !",
    "Stopped! Here's the one you got.": "Arrêté ! Voici celle que tu as eue.",
    "Stopped! Here are the {n} you got.": "Arrêté ! Voici les {n} que tu as eues.",

    # --- the milestones -----------------------------------------------------
    "pictures": "images",
    "videos": "vidéos",
    "songs": "chansons",
    "comics": "BD",
    "things": "créations",

    # --- stickers, voices and sounds ----------------------------------------
    "That one can't be a sticker.": "Celle-là ne peut pas devenir un autocollant.",
    "That one's background is too busy to cut out. Stickers work best on a "
    "picture where the thing you want sits on its own - try asking for "
    "\"on a plain white background\"!":
        "Le fond de celle-là est trop chargé pour être découpé. Les "
        "autocollants marchent mieux quand la chose que tu veux est toute "
        "seule - essaie de demander « sur un fond blanc uni » !",
    "That one went all see-through! Try a picture where the thing you want "
    "stands out from behind it.":
        "Celle-là est devenue toute transparente ! Essaie une image où la "
        "chose que tu veux se détache bien du fond.",
    "Only pictures can be stickers!": "Seules les images peuvent devenir des autocollants !",
    "Couldn't cut that one out. Try again!": "Impossible de la découper. Réessaie !",
    "That one can't have a voice added.": "On ne peut pas ajouter de voix à celle-là.",
    "Couldn't add your voice. Try again!": "Impossible d'ajouter ta voix. Réessaie !",
    "That recording was empty. Try again!": "Cet enregistrement était vide. Réessaie !",
    "That recording is too long. Keep it short!":
        "Cet enregistrement est trop long. Fais court !",
    "That one can't have a sound added.": "On ne peut pas ajouter de son à celle-là.",
    "Couldn't add that sound. Try again!": "Impossible d'ajouter ce son. Réessaie !",
    "No such sound.": "Ce son n'existe pas.",

    # --- everything else they can be told ------------------------------------
    "That one's gone. Pick another!": "Celle-là n'est plus là. Choisis-en une autre !",
    "That picture isn't ready. Pick another!":
        "Cette image n'est pas prête. Choisis-en une autre !",
    "Couldn't fetch that picture. Try again!":
        "Impossible de récupérer cette image. Réessaie !",
    "That one's gone!": "Celle-là n'est plus là !",
    "That one's gone.": "Celle-là n'est plus là.",
    "That one's gone already!": "Celle-là a déjà disparu !",
    "That one's gone already.": "Celle-là a déjà disparu.",
    "That one's gone for good.": "Celle-là est partie pour de bon.",
    "That picture's gone. Pick another!":
        "Cette image n'est plus là. Choisis-en une autre !",
    "That one's gone. Make a new one!": "Celle-là n'est plus là. Fais-en une nouvelle !",
    "That one isn't ready yet.": "Celle-là n'est pas encore prête.",
    "The music maker isn't set up on this machine yet. Everything else still works!":
        "L'atelier musique n'est pas encore installé sur cet ordinateur. "
        "Tout le reste marche !",
    "A comic needs at least {min} pictures and you haven't got that many left "
    "today. Try a single picture!":
        "Une BD a besoin d'au moins {min} images, et il ne t'en reste pas "
        "autant aujourd'hui. Essaie une seule image !",
    "A film needs at least {min} videos and you haven't got that many left "
    "today. Try a single video!":
        "Un film a besoin d'au moins {min} vidéos, et il ne t'en reste pas "
        "autant aujourd'hui. Essaie une seule vidéo !",
    "Couldn't get that picture ready. Try again!":
        "Impossible de préparer cette image. Réessaie !",
    "Couldn't get those pictures ready. Try again!":
        "Impossible de préparer ces images. Réessaie !",
    "Couldn't get that video ready. Try again!":
        "Impossible de préparer cette vidéo. Réessaie !",
    "Couldn't get that ready. Try again!": "Impossible de préparer ça. Réessaie !",
    "Make or choose a picture first, then bring it here!":
        "Fais ou choisis d'abord une image, puis ramène-la ici !",
    "Pick a picture to animate, not a video!":
        "Choisis une image à animer, pas une vidéo !",
    "Pick a first picture and a last picture!":
        "Choisis une première image et une dernière image !",
    "Couldn't save that picture. Try again!":
        "Impossible d'enregistrer cette image. Réessaie !",
    "No picture for that one.": "Pas d'image pour celle-là.",
    "Don't know what to save.": "Je ne sais pas quoi enregistrer.",
    "Pick some things to save first!": "Choisis d'abord des choses à enregistrer !",
    "Those ones are gone!": "Celles-là ne sont plus là !",
    "Pick some things first!": "Choisis d'abord des choses !",
    "Pick some videos first!": "Choisis d'abord des vidéos !",
    "That's a lot! Try twenty or fewer.": "Ça fait beaucoup ! Essaie vingt ou moins.",
    "Pick videos to join - pictures can't go in a film!":
        "Choisis des vidéos à assembler - les images ne vont pas dans un film !",
    "Couldn't join those. Try again!": "Impossible de les assembler. Réessaie !",
    "Couldn't save that. Try again!": "Impossible d'enregistrer ça. Réessaie !",
    "Couldn't save them. Try again!": "Impossible de les enregistrer. Réessaie !",
    "Couldn't do that. Try again!": "Impossible de faire ça. Réessaie !",
    "Couldn't put that back. Try again!": "Impossible de la remettre. Réessaie !",
    "Couldn't delete that. Try again!": "Impossible de la supprimer. Réessaie !",
    "Couldn't delete that one. Try again!": "Impossible de supprimer celle-là. Réessaie !",
    "Only videos can be made smooth!":
        "Seules les vidéos peuvent devenir plus fluides !",
    "Couldn't read that video. Try another!":
        "Impossible de lire cette vidéo. Essaies-en une autre !",
    "Only pictures can be made huge!": "Seules les images peuvent devenir géantes !",
    "Couldn't read that picture. Try another!":
        "Impossible de lire cette image. Essaies-en une autre !",
    "There isn't enough video there to loop. Try starting a bit earlier!":
        "Il n'y a pas assez de vidéo à cet endroit pour faire une boucle. "
        "Commence un peu plus tôt !",
    "Only videos can be moving stickers!":
        "Seules les vidéos peuvent devenir des autocollants animés !",
    "Couldn't make that one move. Try again!":
        "Impossible de faire bouger celle-là. Réessaie !",
    "Tell me what should be there! Type it in the box and tap Go.":
        "Dis-moi ce qu'il faut mettre à la place ! Écris-le dans la case et appuie sur Go.",
    "Couldn't read what you painted. Try again!":
        "Impossible de lire ce que tu as peint. Réessaie !",
    "Type a word for the tag first!": "Écris d'abord un mot pour l'étiquette !",
    "Pick a picture first!": "Choisis d'abord une image !",
    "Who's that?": "C'est qui, ça ?",
    "I don't know who that is.": "Je ne sais pas qui c'est.",
    "I can't find that picture.": "Je ne trouve pas cette image.",
    "That one won't work as a picture of you.":
        "Celle-là ne marche pas comme portrait de toi.",
    "The factory is busy making your video! Chat to me when it's done.":
        "La fabrique est occupée à faire ta vidéo ! Parle-moi quand elle aura fini.",
    "That picture wouldn't go in the banner, sorry. Try another one!":
        "Cette image ne va pas dans la bannière, désolé. Essaies-en une autre !",
    "That one's too long to do this to. Try it on a shorter video!":
        "Celle-là est trop longue pour ça. Essaie sur une vidéo plus courte !",
    "Stickers can't be changed - they'd lose their see-through bits. "
    "Try it on one of your pictures!":
        "Les autocollants ne peuvent pas être changés - ils perdraient leurs "
        "parties transparentes. Essaie sur une de tes images !",
    "Only pictures can be changed. Pick one of your pictures!":
        "Seules les images peuvent être changées. Choisis une de tes images !",
    "Hi! I'm {name}. Ask me for an idea, or tell me what you'd like to make "
    "and I'll help you write it. ✨":
        "Salut ! Moi c'est {name}. Demande-moi une idée, ou dis-moi ce que tu "
        "veux fabriquer et je t'aide à l'écrire. ✨",
    "{name} is having a nap right now. Try again in a minute!":
        "{name} fait une petite sieste. Réessaie dans une minute !",
    "That's a long one! Say it in fewer words.":
        "Celui-là est long ! Dis-le en moins de mots.",
    "Type something first!": "Écris quelque chose d'abord !",
    "Let's use a different picture! That one isn't one we can animate here. "
    "Try a drawing, a toy, a pet, or a place.":
        "Prenons une autre image ! Celle-là, on ne peut pas l'animer ici. "
        "Essaie un dessin, un jouet, un animal, ou un endroit.",

    # --- the title across the top -------------------------------------------
    "My AI Factory": "Ma fabrique IA",
    "{name}'s AI Factory": "La fabrique IA de {name}",
    "factory-of-elided": "La fabrique IA d'{name}",

    # --- dropdown group headings --------------------------------------------
    "Style": "Style",
    "Where is it?": "C'est où ?",
    "Lighting": "Lumière",
    "Feeling": "Ambiance",
    "Colours": "Couleurs",
    "Seen from": "Vu de",
    "Camera": "Caméra",
    "Music": "Musique",
    "Background sounds": "Bruits de fond",
    "Kind of music": "Genre",
    "Mood": "Ambiance",
    "Main instrument": "Instrument",
    "Sung in": "Chanté en",
    "Who sings it": "Qui chante",
    "How many singers": "Combien de voix",
    # the empty option at the top of a dropdown
    "Any": "Au choix",
    "Match my words": "Mes mots",
    "Just one singer": "Une voix",
}


# German. The same keys in the same order under the same headings as
# FR above, so a line missing from one of them is a line out of step.
DE: dict[str, str] = {
    # --- the sign on the door ---------------------------------------------
    "Back soon!": "Bis gleich!",
    "It opens at {when}. See you then!": "Sie macht um {when} auf. Bis dann!",
    "It opens again tomorrow at {when}. See you then!":
        "Sie macht morgen um {when} wieder auf. Bis dann!",
    "closed-until-day": "Sie macht am {day} um {when} wieder auf!",
    "closed-until-next-day": "Sie macht {day} um {when} wieder auf!",
    "The factory is closed right now. ": "Die Fabrik ist gerade zu. ",
    "midnight": "Mitternacht",
    "midday": "12 Uhr mittags",
    "today": "heute",
    "tomorrow": "morgen",
    "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
    "Thursday": "Donnerstag", "Friday": "Freitag", "Saturday": "Samstag",
    "Sunday": "Sonntag",
    "next Monday": "nächsten Montag", "next Tuesday": "nächsten Dienstag",
    "next Wednesday": "nächsten Mittwoch",
    "next Thursday": "nächsten Donnerstag",
    "next Friday": "nächsten Freitag", "next Saturday": "nächsten Samstag",
    "next Sunday": "nächsten Sonntag",

    # --- refusals they read ------------------------------------------------
    "The factory is closed right now. Back soon!":
        "Die Fabrik ist gerade zu. Bis gleich!",
    "One at a time! Wait for the one you're making now to finish, or tap "
    "Stop if you've changed your mind.":
        "Eins nach dem anderen! Warte, bis das fertig ist, was du gerade "
        "machst, oder tipp auf Stopp, wenn du es dir anders überlegt hast.",
    "That's all the pictures for today - great work! Come back tomorrow.":
        "Das waren alle Bilder für heute - gut gemacht! Komm morgen wieder.",
    "That's all the videos for today - great work! Come back tomorrow.":
        "Das waren alle Videos für heute - gut gemacht! Komm morgen wieder.",
    "That's all the songs for today - great work! Come back tomorrow.":
        "Das waren alle Lieder für heute - gut gemacht! Komm morgen wieder.",
    "That's switched off right now.": "Das ist gerade ausgeschaltet.",
    "Making pictures is switched off right now. Ask a grown-up!":
        "Bilder machen ist gerade ausgeschaltet. Frag einen Erwachsenen!",
    "Making videos is switched off right now. Ask a grown-up!":
        "Videos machen ist gerade ausgeschaltet. Frag einen Erwachsenen!",
    "Making comics is switched off right now. Ask a grown-up!":
        "Comics machen ist gerade ausgeschaltet. Frag einen Erwachsenen!",
    "Making songs is switched off right now. Ask a grown-up!":
        "Lieder machen ist gerade ausgeschaltet. Frag einen Erwachsenen!",
    "The chat is switched off right now. Ask a grown-up!":
        "Der Chat ist gerade ausgeschaltet. Frag einen Erwachsenen!",

    # --- the warm-up sums ---------------------------------------------------
    "Let's warm up your brain first! {sums} and the factory opens.":
        "Erst das Gehirn aufwärmen! {sums} und die Fabrik macht auf.",
    "One quick sum": "Eine kleine Rechenaufgabe",
    "Two quick sums": "Zwei kleine Rechenaufgaben",
    "Three quick sums": "Drei kleine Rechenaufgaben",
    "Four quick sums": "Vier kleine Rechenaufgaben",
    "Five quick sums": "Fünf kleine Rechenaufgaben",
    "Six quick sums": "Sechs kleine Rechenaufgaben",
    "Seven quick sums": "Sieben kleine Rechenaufgaben",
    "Eight quick sums": "Acht kleine Rechenaufgaben",
    "Nine quick sums": "Neun kleine Rechenaufgaben",
    "Ten quick sums": "Zehn kleine Rechenaufgaben",

    # --- the word filter ----------------------------------------------------
    "Type something you'd like to make first!":
        "Schreib erst auf, was du machen möchtest!",
    "That's a bit long! Keep it under {max} characters.":
        "Das ist ein bisschen lang! Bleib unter {max} Zeichen.",

    # --- what the progress bar says (jobs.py) -------------------------------
    "Getting ready...": "Es wird vorbereitet...",
    "Something went wrong making that one. Try again!":
        "Dabei ist was schiefgegangen. Probier nochmal!",
    "The art computer is busy with someone else. Waiting for your turn...":
        "Der Mal-Computer ist gerade für jemand anderen da. Du bist gleich "
        "dran...",
    "Stopped! Nothing was made. Try a different idea.":
        "Gestoppt! Es wurde nichts gemacht. Probier eine andere Idee.",
    "Picture {n} of {total}...": "Bild {n} von {total}...",
    "Part {done} of {total} filmed...": "Teil {done} von {total} gefilmt...",
    "Panel {done} of {total} drawn...":
        "Kästchen {done} von {total} gezeichnet...",
    "Putting it all together...": "Alles wird zusammengesetzt...",
    "Looking at every frame...": "Jedes Einzelbild wird angeschaut...",
    "Drawing all the in-between bits...":
        "Alles dazwischen wird gezeichnet...",
    "Putting it back together!": "Alles wird wieder zusammengeklebt!",
    "Getting your picture ready...": "Dein Bild wird vorbereitet...",
    "Making it bigger, bit by bit...": "Es wird Stück für Stück größer...",
    "Almost done!": "Fast fertig!",
    "Looking at your picture...": "Dein Bild wird angeschaut...",
    "Painting what's outside...": "Es wird gemalt, was außenrum ist...",
    "Changing it...": "Es wird geändert...",
    "Nearly there!": "Gleich geschafft!",
    "Working out the tune...": "Die Melodie wird ausgedacht...",

    # --- what kind of sound: a song, a little tune, a background
    #     hum. One card and one model; see app/music.py KINDS.
    "Working out the hum...": "Der Klang wird ausgedacht...",
    "Words, a tune and somebody singing them.": "Text, eine Melodie und jemand, der sie singt.",
    "A short tune with nobody singing - good for the start of a video.": "Eine kurze Melodie ohne Gesang - gut für den Anfang eines Videos.",
    "A long, quiet sound to put behind something else. No tune, no beat.": "Ein langer, ruhiger Klang für den Hintergrund. Keine Melodie, kein Takt.",
    "Playing it... this takes a moment.":
        "Es wird gespielt... das dauert einen Moment.",
    "Mixing it down!": "Alles wird abgemischt!",
    "Reading your story...": "Deine Geschichte wird gelesen...",
    "Drawing the panels...": "Die Kästchen werden gezeichnet...",
    "Putting the page together!": "Die Seite wird zusammengebaut!",
    "Working out your story...": "Deine Geschichte wird ausgedacht...",
    "Filming it, bit by bit... this takes a while.":
        "Es wird Stück für Stück gefilmt... das dauert eine Weile.",
    "Joining it into one film!": "Alles wird zu einem Film!",
    "Thinking up your picture...": "Dein Bild wird ausgedacht...",
    "Painting it now...": "Jetzt wird gemalt...",
    "Getting the video ready...": "Das Video wird vorbereitet...",
    "Making your video... this part takes a few minutes.":
        "Dein Video wird gemacht... dieser Teil dauert ein paar Minuten.",
    "Adding the details and the sound...":
        "Die Details und der Ton kommen dazu...",
    "Your comic is ready!": "Dein Comic ist fertig!",
    "Your film is ready!": "Dein Film ist fertig!",
    "Your song is ready!": "Dein Lied ist fertig!",
    "Your tune is ready!": "Deine Melodie ist fertig!",
    "Your sound is ready!": "Dein Klang ist fertig!",
    "Your video is ready!": "Dein Video ist fertig!",
    "Your picture is ready!": "Dein Bild ist fertig!",
    "All {n} pictures are ready - pick your favourite!":
        "Alle {n} Bilder sind fertig - such dein Lieblingsbild aus!",
    "Stopped! Here's the one you got.":
        "Gestoppt! Das hier ist fertig geworden.",
    "Stopped! Here are the {n} you got.":
        "Gestoppt! Diese {n} sind fertig geworden.",

    # --- the milestones -----------------------------------------------------
    "pictures": "Bilder",
    "videos": "Videos",
    "songs": "Lieder",
    "comics": "Comics",
    "things": "Sachen",

    # --- stickers, voices and sounds ----------------------------------------
    "That one can't be a sticker.": "Daraus kann kein Sticker werden.",
    "That one's background is too busy to cut out. Stickers work best on a "
    "picture where the thing you want sits on its own - try asking for \"on "
    "a plain white background\"!":
        "Der Hintergrund ist zu voll zum Ausschneiden. Sticker klappen am "
        "besten bei einem Bild, wo das Ding ganz allein steht - probier mal "
        "„vor einem weißen Hintergrund“!",
    "That one went all see-through! Try a picture where the thing you want "
    "stands out from behind it.":
        "Das ist ganz durchsichtig geworden! Probier ein Bild, wo sich das "
        "Ding gut vom Hintergrund abhebt.",
    "Only pictures can be stickers!": "Nur Bilder können Sticker werden!",
    "Couldn't cut that one out. Try again!":
        "Konnte das nicht ausschneiden. Probier nochmal!",
    "That one can't have a voice added.": "Da kann keine Stimme dazu.",
    "Couldn't add your voice. Try again!":
        "Konnte deine Stimme nicht dazutun. Probier nochmal!",
    "That recording was empty. Try again!":
        "Die Aufnahme war leer. Probier nochmal!",
    "That recording is too long. Keep it short!":
        "Die Aufnahme ist zu lang. Mach es kurz!",
    "That one can't have a sound added.": "Da kann kein Geräusch dazu.",
    "Couldn't add that sound. Try again!":
        "Konnte das Geräusch nicht dazutun. Probier nochmal!",
    "No such sound.": "Das Geräusch gibt es nicht.",

    # --- everything else they can be told ------------------------------------
    "That one's gone. Pick another!": "Das ist weg. Such ein anderes aus!",
    "That picture isn't ready. Pick another!":
        "Das Bild ist nicht fertig. Such ein anderes aus!",
    "Couldn't fetch that picture. Try again!":
        "Konnte das Bild nicht holen. Probier nochmal!",
    "That one's gone!": "Das ist weg!",
    "That one's gone.": "Das ist weg.",
    "That one's gone already!": "Das ist schon weg!",
    "That one's gone already.": "Das ist schon weg.",
    "That one's gone for good.": "Das ist für immer weg.",
    "That picture's gone. Pick another!":
        "Das Bild ist weg. Such ein anderes aus!",
    "That one's gone. Make a new one!": "Das ist weg. Mach ein neues!",
    "That one isn't ready yet.": "Das ist noch nicht fertig.",
    "The music maker isn't set up on this machine yet. Everything else still "
    "works!":
        "Die Musik-Werkstatt ist auf diesem Computer noch nicht "
        "eingerichtet. Alles andere geht trotzdem!",
    "A comic needs at least {min} pictures and you haven't got that many "
    "left today. Try a single picture!":
        "Ein Comic braucht mindestens {min} Bilder, und so viele hast du "
        "heute nicht mehr übrig. Probier ein einzelnes Bild!",
    "A film needs at least {min} videos and you haven't got that many left "
    "today. Try a single video!":
        "Ein Film braucht mindestens {min} Videos, und so viele hast du "
        "heute nicht mehr übrig. Probier ein einzelnes Video!",
    "Couldn't get that picture ready. Try again!":
        "Konnte das Bild nicht fertig machen. Probier nochmal!",
    "Couldn't get those pictures ready. Try again!":
        "Konnte die Bilder nicht fertig machen. Probier nochmal!",
    "Couldn't get that video ready. Try again!":
        "Konnte das Video nicht fertig machen. Probier nochmal!",
    "Couldn't get that ready. Try again!":
        "Konnte das nicht fertig machen. Probier nochmal!",
    "Make or choose a picture first, then bring it here!":
        "Mach oder such erst ein Bild aus, dann bring es hierher!",
    "Pick a picture to animate, not a video!":
        "Such ein Bild zum Bewegen aus, kein Video!",
    "Pick a first picture and a last picture!":
        "Such ein erstes und ein letztes Bild aus!",
    "Couldn't save that picture. Try again!":
        "Konnte das Bild nicht speichern. Probier nochmal!",
    "No picture for that one.": "Dazu gibt es kein Bild.",
    "Don't know what to save.": "Weiß nicht, was gespeichert werden soll.",
    "Pick some things to save first!": "Such erst Sachen zum Speichern aus!",
    "Those ones are gone!": "Die sind weg!",
    "Pick some things first!": "Such erst ein paar Sachen aus!",
    "Pick some videos first!": "Such erst ein paar Videos aus!",
    "That's a lot! Try twenty or fewer.":
        "Das ist viel! Probier zwanzig oder weniger.",
    "Pick videos to join - pictures can't go in a film!":
        "Such Videos zum Zusammensetzen aus - Bilder passen nicht in einen "
        "Film!",
    "Couldn't join those. Try again!":
        "Konnte die nicht zusammensetzen. Probier nochmal!",
    "Couldn't save that. Try again!":
        "Konnte das nicht speichern. Probier nochmal!",
    "Couldn't save them. Try again!":
        "Konnte sie nicht speichern. Probier nochmal!",
    "Couldn't do that. Try again!":
        "Konnte das nicht machen. Probier nochmal!",
    "Couldn't put that back. Try again!":
        "Konnte das nicht zurückholen. Probier nochmal!",
    "Couldn't delete that. Try again!":
        "Konnte das nicht löschen. Probier nochmal!",
    "Couldn't delete that one. Try again!":
        "Konnte das da nicht löschen. Probier nochmal!",
    "Only videos can be made smooth!":
        "Nur Videos können flüssig gemacht werden!",
    "Couldn't read that video. Try another!":
        "Konnte das Video nicht lesen. Probier ein anderes!",
    "Only pictures can be made huge!":
        "Nur Bilder können riesig gemacht werden!",
    "Couldn't read that picture. Try another!":
        "Konnte das Bild nicht lesen. Probier ein anderes!",
    "There isn't enough video there to loop. Try starting a bit earlier!":
        "Da ist nicht genug Video für eine Schleife. Fang ein bisschen "
        "früher an!",
    "Only videos can be moving stickers!":
        "Nur Videos können Wackel-Sticker werden!",
    "Couldn't make that one move. Try again!":
        "Konnte das nicht bewegen. Probier nochmal!",
    "Tell me what should be there! Type it in the box and tap Go.":
        "Sag mir, was da sein soll! Schreib es ins Feld und tipp auf Los.",
    "Couldn't read what you painted. Try again!":
        "Konnte nicht lesen, was du gemalt hast. Probier nochmal!",
    "Type a word for the tag first!": "Schreib erst ein Wort für das Etikett!",
    "Pick a picture first!": "Such erst ein Bild aus!",
    "Who's that?": "Wer ist das?",
    "I don't know who that is.": "Ich weiß nicht, wer das ist.",
    "I can't find that picture.": "Ich finde das Bild nicht.",
    "That one won't work as a picture of you.":
        "Das klappt nicht als Bild von dir.",
    "The factory is busy making your video! Chat to me when it's done.":
        "Die Fabrik macht gerade dein Video! Chatte mit mir, wenn es fertig "
        "ist.",
    "That picture wouldn't go in the banner, sorry. Try another one!":
        "Das Bild wollte nicht in den Kopf der Seite, sorry. Probier ein "
        "anderes!",
    "That one's too long to do this to. Try it on a shorter video!":
        "Das ist zu lang dafür. Probier es mit einem kürzeren Video!",
    "Stickers can't be changed - they'd lose their see-through bits. Try it "
    "on one of your pictures!":
        "Sticker kann man nicht ändern - sie würden ihre durchsichtigen "
        "Stellen verlieren. Probier es mit einem deiner Bilder!",
    "Only pictures can be changed. Pick one of your pictures!":
        "Nur Bilder können geändert werden. Such eins von deinen Bildern aus!",
    "Hi! I'm {name}. Ask me for an idea, or tell me what you'd like to make "
    "and I'll help you write it. ✨":
        "Hallo! Ich bin {name}. Frag mich nach einer Idee, oder sag mir, was "
        "du machen willst, dann helfe ich dir beim Schreiben. ✨",
    "{name} is having a nap right now. Try again in a minute!":
        "{name} macht gerade ein Nickerchen. Probier es in einer Minute "
        "nochmal!",
    "That's a long one! Say it in fewer words.":
        "Das ist lang! Sag es mit weniger Wörtern.",
    "Type something first!": "Schreib erst was!",
    "Let's use a different picture! That one isn't one we can animate here. "
    "Try a drawing, a toy, a pet, or a place.":
        "Nehmen wir ein anderes Bild! Das können wir hier nicht bewegen. "
        "Probier eine Zeichnung, ein Spielzeug, ein Haustier oder einen Ort.",

    # --- the title across the top -------------------------------------------
    "My AI Factory": "Meine KI-Fabrik",
    "{name}'s AI Factory": "{name}s KI-Fabrik",
    "factory-of-elided": "{name}' KI-Fabrik",

    # --- dropdown group headings --------------------------------------------
    "Style": "Stil",
    "Where is it?": "Wo ist es?",
    "Lighting": "Licht",
    "Feeling": "Stimmung",
    "Colours": "Farben",
    "Seen from": "Blick von",
    "Camera": "Kamera",
    "Music": "Musik",
    "Background sounds": "Geräusche",
    "Kind of music": "Musikart",
    "Mood": "Stimmung",
    "Main instrument": "Instrument",
    "Sung in": "Gesungen auf",
    "Who sings it": "Wer singt",
    "How many singers": "Wie viele Stimmen",
    # the empty option at the top of a dropdown
    "Any": "Egal",
    "Match my words": "Meine Wörter",
    "Just one singer": "Eine Stimme",
}

# Spanish. The same keys in the same order under the same headings as
# FR above, so a line missing from one of them is a line out of step.
ES: dict[str, str] = {
    # --- the sign on the door ---------------------------------------------
    "Back soon!": "¡Vuelvo pronto!",
    "It opens at {when}. See you then!": "Abre a las {when}. ¡Nos vemos!",
    "It opens again tomorrow at {when}. See you then!":
        "Abre otra vez mañana a las {when}. ¡Nos vemos!",
    "closed-until-day": "¡Abre otra vez el {day} a las {when}!",
    "closed-until-next-day": "¡Abre otra vez {day} a las {when}!",
    "The factory is closed right now. ":
        "La fábrica está cerrada ahora mismo. ",
    "midnight": "12 de la noche",
    "midday": "12 del mediodía",
    "today": "hoy",
    "tomorrow": "mañana",
    "Monday": "lunes", "Tuesday": "martes", "Wednesday": "miércoles",
    "Thursday": "jueves", "Friday": "viernes", "Saturday": "sábado",
    "Sunday": "domingo",
    "next Monday": "el lunes que viene", "next Tuesday": "el martes que viene",
    "next Wednesday": "el miércoles que viene",
    "next Thursday": "el jueves que viene",
    "next Friday": "el viernes que viene",
    "next Saturday": "el sábado que viene",
    "next Sunday": "el domingo que viene",

    # --- refusals they read ------------------------------------------------
    "The factory is closed right now. Back soon!":
        "La fábrica está cerrada ahora mismo. ¡Vuelvo pronto!",
    "One at a time! Wait for the one you're making now to finish, or tap "
    "Stop if you've changed your mind.":
        "¡De una en una! Espera a que acabe la que estás haciendo ahora, o "
        "toca Parar si has cambiado de idea.",
    "That's all the pictures for today - great work! Come back tomorrow.":
        "Ya no quedan imágenes por hoy - ¡buen trabajo! Vuelve mañana.",
    "That's all the videos for today - great work! Come back tomorrow.":
        "Ya no quedan vídeos por hoy - ¡buen trabajo! Vuelve mañana.",
    "That's all the songs for today - great work! Come back tomorrow.":
        "Ya no quedan canciones por hoy - ¡buen trabajo! Vuelve mañana.",
    "That's switched off right now.": "Eso está apagado ahora mismo.",
    "Making pictures is switched off right now. Ask a grown-up!":
        "Ahora mismo no se pueden hacer imágenes. ¡Pregunta a un adulto!",
    "Making videos is switched off right now. Ask a grown-up!":
        "Ahora mismo no se pueden hacer vídeos. ¡Pregunta a un adulto!",
    "Making comics is switched off right now. Ask a grown-up!":
        "Ahora mismo no se pueden hacer cómics. ¡Pregunta a un adulto!",
    "Making songs is switched off right now. Ask a grown-up!":
        "Ahora mismo no se pueden hacer canciones. ¡Pregunta a un adulto!",
    "The chat is switched off right now. Ask a grown-up!":
        "El chat está apagado ahora mismo. ¡Pregunta a un adulto!",

    # --- the warm-up sums ---------------------------------------------------
    "Let's warm up your brain first! {sums} and the factory opens.":
        "¡Primero vamos a calentar el cerebro! {sums} y la fábrica abre.",
    "One quick sum": "Una suma rápida",
    "Two quick sums": "Dos sumas rápidas",
    "Three quick sums": "Tres sumas rápidas",
    "Four quick sums": "Cuatro sumas rápidas",
    "Five quick sums": "Cinco sumas rápidas",
    "Six quick sums": "Seis sumas rápidas",
    "Seven quick sums": "Siete sumas rápidas",
    "Eight quick sums": "Ocho sumas rápidas",
    "Nine quick sums": "Nueve sumas rápidas",
    "Ten quick sums": "Diez sumas rápidas",

    # --- the word filter ----------------------------------------------------
    "Type something you'd like to make first!":
        "¡Escribe antes algo que quieras hacer!",
    "That's a bit long! Keep it under {max} characters.":
        "¡Eso es un poco largo! Que no pase de {max} letras.",

    # --- what the progress bar says (jobs.py) -------------------------------
    "Getting ready...": "Preparando...",
    "Something went wrong making that one. Try again!":
        "Algo ha salido mal al hacerlo. ¡Prueba otra vez!",
    "The art computer is busy with someone else. Waiting for your turn...":
        "La máquina de dibujar está ocupada con otra persona. Esperando tu "
        "turno...",
    "Stopped! Nothing was made. Try a different idea.":
        "¡Parado! No se hizo nada. Prueba con otra idea.",
    "Picture {n} of {total}...": "Imagen {n} de {total}...",
    "Part {done} of {total} filmed...": "Parte {done} de {total} grabada...",
    "Panel {done} of {total} drawn...": "Viñeta {done} de {total} dibujada...",
    "Putting it all together...": "Montándolo todo...",
    "Looking at every frame...": "Mirando todos los fotogramas...",
    "Drawing all the in-between bits...":
        "Dibujando todo lo que va en medio...",
    "Putting it back together!": "¡Montándolo otra vez!",
    "Getting your picture ready...": "Preparando tu imagen...",
    "Making it bigger, bit by bit...": "Haciéndola más grande, poco a poco...",
    "Almost done!": "¡Casi está!",
    "Looking at your picture...": "Mirando tu imagen...",
    "Painting what's outside...": "Pintando lo que hay fuera...",
    "Changing it...": "Cambiándola...",
    "Nearly there!": "¡Ya casi!",
    "Working out the tune...": "Buscando la melodía...",

    # --- what kind of sound: a song, a little tune, a background
    #     hum. One card and one model; see app/music.py KINDS.
    "Working out the hum...": "Buscando el sonido...",
    "Words, a tune and somebody singing them.": "Letra, melodía y alguien que la cante.",
    "A short tune with nobody singing - good for the start of a video.": "Una melodía corta sin nadie cantando - va muy bien al principio de un vídeo.",
    "A long, quiet sound to put behind something else. No tune, no beat.": "Un sonido largo y tranquilo para poner detrás de otra cosa. Sin melodía y sin ritmo.",
    "Playing it... this takes a moment.":
        "Tocándola... esto tarda un poquito.",
    "Mixing it down!": "¡Mezclándolo todo!",
    "Reading your story...": "Leyendo tu historia...",
    "Drawing the panels...": "Dibujando las viñetas...",
    "Putting the page together!": "¡Montando la página!",
    "Working out your story...": "Pensando tu historia...",
    "Filming it, bit by bit... this takes a while.":
        "Grabándolo poco a poco... esto tarda un rato.",
    "Joining it into one film!": "¡Uniéndolo todo en una película!",
    "Thinking up your picture...": "Imaginando tu imagen...",
    "Painting it now...": "Pintándola ya...",
    "Getting the video ready...": "Preparando el vídeo...",
    "Making your video... this part takes a few minutes.":
        "Haciendo tu vídeo... esta parte tarda unos minutos.",
    "Adding the details and the sound...":
        "Añadiendo los detalles y el sonido...",
    "Your comic is ready!": "¡Tu cómic está listo!",
    "Your film is ready!": "¡Tu película está lista!",
    "Your song is ready!": "¡Tu canción está lista!",
    "Your tune is ready!": "¡Tu melodía está lista!",
    "Your sound is ready!": "¡Tu sonido está listo!",
    "Your video is ready!": "¡Tu vídeo está listo!",
    "Your picture is ready!": "¡Tu imagen está lista!",
    "All {n} pictures are ready - pick your favourite!":
        "Ya están las {n} imágenes - ¡elige tu favorita!",
    "Stopped! Here's the one you got.": "¡Parado! Aquí tienes la que salió.",
    "Stopped! Here are the {n} you got.":
        "¡Parado! Aquí tienes las {n} que salieron.",

    # --- the milestones -----------------------------------------------------
    "pictures": "imágenes",
    "videos": "vídeos",
    "songs": "canciones",
    "comics": "cómics",
    "things": "cosas",

    # --- stickers, voices and sounds ----------------------------------------
    "That one can't be a sticker.": "Esa no puede ser una pegatina.",
    "That one's background is too busy to cut out. Stickers work best on a "
    "picture where the thing you want sits on its own - try asking for \"on "
    "a plain white background\"!":
        "El fondo de esa tiene demasiadas cosas para recortarla. Las "
        "pegatinas salen mejor con una imagen donde lo que quieres está "
        "solito - ¡prueba a pedir \"sobre un fondo blanco liso\"!",
    "That one went all see-through! Try a picture where the thing you want "
    "stands out from behind it.":
        "¡Esa se ha quedado transparente del todo! Prueba con una imagen "
        "donde lo que quieres destaque del fondo.",
    "Only pictures can be stickers!":
        "¡Solo las imágenes pueden ser pegatinas!",
    "Couldn't cut that one out. Try again!":
        "No se ha podido recortar. ¡Prueba otra vez!",
    "That one can't have a voice added.": "A eso no se le puede poner voz.",
    "Couldn't add your voice. Try again!":
        "No se ha podido poner tu voz. ¡Prueba otra vez!",
    "That recording was empty. Try again!":
        "Esa grabación estaba vacía. ¡Prueba otra vez!",
    "That recording is too long. Keep it short!":
        "Esa grabación es muy larga. ¡Que sea cortita!",
    "That one can't have a sound added.": "A eso no se le puede poner sonido.",
    "Couldn't add that sound. Try again!":
        "No se ha podido poner ese sonido. ¡Prueba otra vez!",
    "No such sound.": "Ese sonido no existe.",

    # --- everything else they can be told ------------------------------------
    "That one's gone. Pick another!": "Esa ya no está. ¡Elige otra!",
    "That picture isn't ready. Pick another!":
        "Esa imagen no está lista. ¡Elige otra!",
    "Couldn't fetch that picture. Try again!":
        "No se ha podido traer esa imagen. ¡Prueba otra vez!",
    "That one's gone!": "¡Esa ya no está!",
    "That one's gone.": "Esa ya no está.",
    "That one's gone already!": "¡Esa ya no estaba!",
    "That one's gone already.": "Esa ya no estaba.",
    "That one's gone for good.": "Esa se ha ido para siempre.",
    "That picture's gone. Pick another!":
        "Esa imagen ya no está. ¡Elige otra!",
    "That one's gone. Make a new one!": "Esa ya no está. ¡Haz una nueva!",
    "That one isn't ready yet.": "Esa todavía no está lista.",
    "The music maker isn't set up on this machine yet. Everything else still "
    "works!":
        "Lo de hacer música todavía no está puesto en esta máquina. ¡Todo lo "
        "demás funciona!",
    "A comic needs at least {min} pictures and you haven't got that many "
    "left today. Try a single picture!":
        "Un cómic necesita por lo menos {min} imágenes y hoy no te quedan "
        "tantas. ¡Prueba con una sola imagen!",
    "A film needs at least {min} videos and you haven't got that many left "
    "today. Try a single video!":
        "Una película necesita por lo menos {min} vídeos y hoy no te quedan "
        "tantos. ¡Prueba con un solo vídeo!",
    "Couldn't get that picture ready. Try again!":
        "No se ha podido preparar esa imagen. ¡Prueba otra vez!",
    "Couldn't get those pictures ready. Try again!":
        "No se han podido preparar esas imágenes. ¡Prueba otra vez!",
    "Couldn't get that video ready. Try again!":
        "No se ha podido preparar ese vídeo. ¡Prueba otra vez!",
    "Couldn't get that ready. Try again!":
        "No se ha podido preparar. ¡Prueba otra vez!",
    "Make or choose a picture first, then bring it here!":
        "¡Haz o elige primero una imagen y luego tráela aquí!",
    "Pick a picture to animate, not a video!":
        "¡Elige una imagen para animar, no un vídeo!",
    "Pick a first picture and a last picture!":
        "¡Elige una imagen para el principio y otra para el final!",
    "Couldn't save that picture. Try again!":
        "No se ha podido guardar esa imagen. ¡Prueba otra vez!",
    "No picture for that one.": "Esa no tiene imagen.",
    "Don't know what to save.": "No sé qué guardar.",
    "Pick some things to save first!": "¡Elige primero qué quieres guardar!",
    "Those ones are gone!": "¡Esas ya no están!",
    "Pick some things first!": "¡Elige primero algunas cosas!",
    "Pick some videos first!": "¡Elige primero algunos vídeos!",
    "That's a lot! Try twenty or fewer.":
        "¡Eso es un montón! Prueba con veinte o menos.",
    "Pick videos to join - pictures can't go in a film!":
        "Elige vídeos para unir - ¡las imágenes no pueden ir en una película!",
    "Couldn't join those. Try again!":
        "No se han podido unir. ¡Prueba otra vez!",
    "Couldn't save that. Try again!":
        "No se ha podido guardar. ¡Prueba otra vez!",
    "Couldn't save them. Try again!":
        "No se han podido guardar. ¡Prueba otra vez!",
    "Couldn't do that. Try again!": "No se ha podido hacer. ¡Prueba otra vez!",
    "Couldn't put that back. Try again!":
        "No se ha podido devolver. ¡Prueba otra vez!",
    "Couldn't delete that. Try again!":
        "No se ha podido borrar. ¡Prueba otra vez!",
    "Couldn't delete that one. Try again!":
        "No se ha podido borrar esa. ¡Prueba otra vez!",
    "Only videos can be made smooth!":
        "¡Solo los vídeos se pueden hacer más fluidos!",
    "Couldn't read that video. Try another!":
        "No se ha podido leer ese vídeo. ¡Prueba con otro!",
    "Only pictures can be made huge!":
        "¡Solo las imágenes se pueden hacer enormes!",
    "Couldn't read that picture. Try another!":
        "No se ha podido leer esa imagen. ¡Prueba con otra!",
    "There isn't enough video there to loop. Try starting a bit earlier!":
        "Ahí no hay bastante vídeo para hacer el bucle. ¡Prueba a empezar un "
        "poco antes!",
    "Only videos can be moving stickers!":
        "¡Solo los vídeos pueden ser pegatinas animadas!",
    "Couldn't make that one move. Try again!":
        "No se ha podido hacer que se mueva. ¡Prueba otra vez!",
    "Tell me what should be there! Type it in the box and tap Go.":
        "¡Dime qué quieres que haya ahí! Escríbelo en la caja y toca Vamos.",
    "Couldn't read what you painted. Try again!":
        "No se ha podido leer lo que has pintado. ¡Prueba otra vez!",
    "Type a word for the tag first!":
        "¡Escribe primero una palabra para la etiqueta!",
    "Pick a picture first!": "¡Elige primero una imagen!",
    "Who's that?": "¿Quién es?",
    "I don't know who that is.": "No sé quién es.",
    "I can't find that picture.": "No encuentro esa imagen.",
    "That one won't work as a picture of you.":
        "Esa no vale como imagen tuya.",
    "The factory is busy making your video! Chat to me when it's done.":
        "¡La fábrica está ocupada haciendo tu vídeo! Chatea conmigo cuando "
        "acabe.",
    "That picture wouldn't go in the banner, sorry. Try another one!":
        "Esa imagen no se ha podido poner arriba, lo siento. ¡Prueba con "
        "otra!",
    "That one's too long to do this to. Try it on a shorter video!":
        "Ese es muy largo para hacerle esto. ¡Pruébalo con un vídeo más "
        "corto!",
    "Stickers can't be changed - they'd lose their see-through bits. Try it "
    "on one of your pictures!":
        "Las pegatinas no se pueden cambiar - perderían sus partes "
        "transparentes. ¡Pruébalo con una de tus imágenes!",
    "Only pictures can be changed. Pick one of your pictures!":
        "Solo se pueden cambiar las imágenes. ¡Elige una de tus imágenes!",
    "Hi! I'm {name}. Ask me for an idea, or tell me what you'd like to make "
    "and I'll help you write it. ✨":
        "¡Hola! Soy {name}. Pídeme una idea, o cuéntame qué te gustaría "
        "hacer y te ayudo a escribirlo. ✨",
    "{name} is having a nap right now. Try again in a minute!":
        "{name} está echándose una siesta ahora mismo. ¡Prueba otra vez en "
        "un minuto!",
    "That's a long one! Say it in fewer words.":
        "¡Eso es muy largo! Dilo con menos palabras.",
    "Type something first!": "¡Escribe algo primero!",
    "Let's use a different picture! That one isn't one we can animate here. "
    "Try a drawing, a toy, a pet, or a place.":
        "¡Vamos a usar otra imagen! Esa no es de las que podemos animar "
        "aquí. Prueba con un dibujo, un juguete, una mascota o un sitio.",

    # --- the title across the top -------------------------------------------
    "My AI Factory": "Mi fábrica de IA",
    "{name}'s AI Factory": "La fábrica de IA de {name}",
    "factory-of-elided": "La fábrica de IA de {name}",

    # --- dropdown group headings --------------------------------------------
    "Style": "Estilo",
    "Where is it?": "¿Dónde está?",
    "Lighting": "Luz",
    "Feeling": "Ambiente",
    "Colours": "Colores",
    "Seen from": "Visto desde",
    "Camera": "Cámara",
    "Music": "Música",
    "Background sounds": "Sonidos de fondo",
    "Kind of music": "Tipo de música",
    "Mood": "Ánimo",
    "Main instrument": "Instrumento principal",
    "Sung in": "Cantada en",
    "Who sings it": "Quién la canta",
    "How many singers": "Cuántas voces",
    # the empty option at the top of a dropdown
    "Any": "Cualquiera",
    "Match my words": "Como la letra",
    "Just one singer": "Una sola voz",
}

# Italian. The same keys in the same order under the same headings as
# FR above, so a line missing from one of them is a line out of step.
IT: dict[str, str] = {
    # --- the sign on the door ---------------------------------------------
    "Back soon!": "Torniamo presto!",
    "It opens at {when}. See you then!": "Apre alle {when}. A dopo!",
    "It opens again tomorrow at {when}. See you then!":
        "Riapre domani alle {when}. A domani!",
    "closed-until-day": "Riapre {day} alle {when}!",
    "closed-until-next-day": "Riapre {day} alle {when}!",
    "The factory is closed right now. ": "La fabbrica adesso è chiusa. ",
    "midnight": "24:00",
    "midday": "12:00",
    "today": "oggi",
    "tomorrow": "domani",
    "Monday": "lunedì", "Tuesday": "martedì", "Wednesday": "mercoledì",
    "Thursday": "giovedì", "Friday": "venerdì", "Saturday": "sabato",
    "Sunday": "domenica",
    "next Monday": "lunedì prossimo", "next Tuesday": "martedì prossimo",
    "next Wednesday": "mercoledì prossimo",
    "next Thursday": "giovedì prossimo",
    "next Friday": "venerdì prossimo", "next Saturday": "sabato prossimo",
    "next Sunday": "domenica prossima",

    # --- refusals they read ------------------------------------------------
    "The factory is closed right now. Back soon!":
        "La fabbrica adesso è chiusa. Torniamo presto!",
    "One at a time! Wait for the one you're making now to finish, or tap "
    "Stop if you've changed your mind.":
        "Una alla volta! Aspetta che finisca quella che stai facendo, oppure "
        "tocca Stop se hai cambiato idea.",
    "That's all the pictures for today - great work! Come back tomorrow.":
        "Basta immagini per oggi - bel lavoro! Torna domani.",
    "That's all the videos for today - great work! Come back tomorrow.":
        "Basta video per oggi - bel lavoro! Torna domani.",
    "That's all the songs for today - great work! Come back tomorrow.":
        "Basta canzoni per oggi - bel lavoro! Torna domani.",
    "That's switched off right now.": "Adesso è spento.",
    "Making pictures is switched off right now. Ask a grown-up!":
        "Adesso non si possono fare immagini. Chiedi a un grande!",
    "Making videos is switched off right now. Ask a grown-up!":
        "Adesso non si possono fare video. Chiedi a un grande!",
    "Making comics is switched off right now. Ask a grown-up!":
        "Adesso non si possono fare fumetti. Chiedi a un grande!",
    "Making songs is switched off right now. Ask a grown-up!":
        "Adesso non si possono fare canzoni. Chiedi a un grande!",
    "The chat is switched off right now. Ask a grown-up!":
        "La chat adesso è spenta. Chiedi a un grande!",

    # --- the warm-up sums ---------------------------------------------------
    "Let's warm up your brain first! {sums} and the factory opens.":
        "Prima riscaldiamo il cervello! {sums} e la fabbrica apre.",
    "One quick sum": "Un conto veloce",
    "Two quick sums": "Due conti veloci",
    "Three quick sums": "Tre conti veloci",
    "Four quick sums": "Quattro conti veloci",
    "Five quick sums": "Cinque conti veloci",
    "Six quick sums": "Sei conti veloci",
    "Seven quick sums": "Sette conti veloci",
    "Eight quick sums": "Otto conti veloci",
    "Nine quick sums": "Nove conti veloci",
    "Ten quick sums": "Dieci conti veloci",

    # --- the word filter ----------------------------------------------------
    "Type something you'd like to make first!":
        "Prima scrivi qualcosa che vuoi fare!",
    "That's a bit long! Keep it under {max} characters.":
        "È un po' lungo! Stai sotto i {max} caratteri.",

    # --- what the progress bar says (jobs.py) -------------------------------
    "Getting ready...": "Mi preparo...",
    "Something went wrong making that one. Try again!":
        "Qualcosa è andato storto. Riprova!",
    "The art computer is busy with someone else. Waiting for your turn...":
        "Il computer dei disegni è occupato con un altro. Aspetto il tuo "
        "turno...",
    "Stopped! Nothing was made. Try a different idea.":
        "Fermato! Non è venuto fuori niente. Prova un'altra idea.",
    "Picture {n} of {total}...": "Immagine {n} di {total}...",
    "Part {done} of {total} filmed...": "Parte {done} di {total} girata...",
    "Panel {done} of {total} drawn...":
        "Vignetta {done} di {total} disegnata...",
    "Putting it all together...": "Metto insieme tutto...",
    "Looking at every frame...": "Guardo ogni fotogramma...",
    "Drawing all the in-between bits...": "Disegno tutti i pezzi in mezzo...",
    "Putting it back together!": "Rimetto tutto insieme!",
    "Getting your picture ready...": "Preparo la tua immagine...",
    "Making it bigger, bit by bit...":
        "La faccio più grande, pezzo per pezzo...",
    "Almost done!": "Quasi fatto!",
    "Looking at your picture...": "Guardo la tua immagine...",
    "Painting what's outside...": "Dipingo quello che c'è fuori...",
    "Changing it...": "La sto cambiando...",
    "Nearly there!": "Ci siamo quasi!",
    "Working out the tune...": "Trovo la melodia...",

    # --- what kind of sound: a song, a little tune, a background
    #     hum. One card and one model; see app/music.py KINDS.
    "Working out the hum...": "Trovo il suono...",
    "Words, a tune and somebody singing them.": "Parole, una melodia e qualcuno che le canta.",
    "A short tune with nobody singing - good for the start of a video.": "Una melodia breve senza nessuno che canta - perfetta per l'inizio di un video.",
    "A long, quiet sound to put behind something else. No tune, no beat.": "Un suono lungo e tranquillo da mettere dietro a qualcos'altro. Niente melodia, niente ritmo.",
    "Playing it... this takes a moment.": "La suono... ci vuole un momento.",
    "Mixing it down!": "Sistemo il suono!",
    "Reading your story...": "Leggo la tua storia...",
    "Drawing the panels...": "Disegno le vignette...",
    "Putting the page together!": "Compongo la pagina!",
    "Working out your story...": "Penso alla tua storia...",
    "Filming it, bit by bit... this takes a while.":
        "Lo giro pezzo per pezzo... ci vuole un po'.",
    "Joining it into one film!": "Unisco tutto in un film!",
    "Thinking up your picture...": "Penso alla tua immagine...",
    "Painting it now...": "Adesso la dipingo...",
    "Getting the video ready...": "Preparo il video...",
    "Making your video... this part takes a few minutes.":
        "Faccio il tuo video... questa parte richiede qualche minuto.",
    "Adding the details and the sound...": "Aggiungo i dettagli e il suono...",
    "Your comic is ready!": "Il tuo fumetto è pronto!",
    "Your film is ready!": "Il tuo film è pronto!",
    "Your song is ready!": "La tua canzone è pronta!",
    "Your tune is ready!": "La tua melodia è pronta!",
    "Your sound is ready!": "Il tuo suono è pronto!",
    "Your video is ready!": "Il tuo video è pronto!",
    "Your picture is ready!": "La tua immagine è pronta!",
    "All {n} pictures are ready - pick your favourite!":
        "Tutte e {n} le immagini sono pronte - scegli la tua preferita!",
    "Stopped! Here's the one you got.": "Fermato! Ecco quella che è venuta.",
    "Stopped! Here are the {n} you got.":
        "Fermato! Ecco le {n} che sono venute.",

    # --- the milestones -----------------------------------------------------
    "pictures": "immagini",
    "videos": "video",
    "songs": "canzoni",
    "comics": "fumetti",
    "things": "cose",

    # --- stickers, voices and sounds ----------------------------------------
    "That one can't be a sticker.": "Quella non può diventare un adesivo.",
    "That one's background is too busy to cut out. Stickers work best on a "
    "picture where the thing you want sits on its own - try asking for \"on "
    "a plain white background\"!":
        "Lo sfondo di quella è troppo pieno per ritagliarla. Gli adesivi "
        "vengono meglio con un'immagine dove la cosa che vuoi sta da sola - "
        "prova a chiedere \"su uno sfondo bianco semplice\"!",
    "That one went all see-through! Try a picture where the thing you want "
    "stands out from behind it.":
        "Quella è venuta tutta trasparente! Prova un'immagine dove la cosa "
        "che vuoi si stacca bene dallo sfondo.",
    "Only pictures can be stickers!":
        "Solo le immagini possono diventare adesivi!",
    "Couldn't cut that one out. Try again!":
        "Non sono riuscito a ritagliarla. Riprova!",
    "That one can't have a voice added.":
        "A quella non si può aggiungere la voce.",
    "Couldn't add your voice. Try again!":
        "Non sono riuscito ad aggiungere la tua voce. Riprova!",
    "That recording was empty. Try again!":
        "Quella registrazione era vuota. Riprova!",
    "That recording is too long. Keep it short!":
        "Quella registrazione è troppo lunga. Falla corta!",
    "That one can't have a sound added.":
        "A quella non si può aggiungere un suono.",
    "Couldn't add that sound. Try again!":
        "Non sono riuscito ad aggiungere quel suono. Riprova!",
    "No such sound.": "Quel suono non esiste.",

    # --- everything else they can be told ------------------------------------
    "That one's gone. Pick another!": "Quella non c'è più. Scegline un'altra!",
    "That picture isn't ready. Pick another!":
        "Quell'immagine non è pronta. Scegline un'altra!",
    "Couldn't fetch that picture. Try again!":
        "Non sono riuscito a prendere quell'immagine. Riprova!",
    "That one's gone!": "Quella non c'è più!",
    "That one's gone.": "Quella non c'è più.",
    "That one's gone already!": "Quella è già sparita!",
    "That one's gone already.": "Quella è già sparita.",
    "That one's gone for good.": "Quella è sparita per sempre.",
    "That picture's gone. Pick another!":
        "Quell'immagine non c'è più. Scegline un'altra!",
    "That one's gone. Make a new one!": "Quella non c'è più. Fanne una nuova!",
    "That one isn't ready yet.": "Quella non è ancora pronta.",
    "The music maker isn't set up on this machine yet. Everything else still "
    "works!":
        "Il creatore di canzoni non è ancora pronto su questo computer. "
        "Tutto il resto funziona!",
    "A comic needs at least {min} pictures and you haven't got that many "
    "left today. Try a single picture!":
        "Un fumetto ha bisogno di almeno {min} immagini e oggi non te ne "
        "restano abbastanza. Prova con una sola immagine!",
    "A film needs at least {min} videos and you haven't got that many left "
    "today. Try a single video!":
        "Un film ha bisogno di almeno {min} video e oggi non te ne restano "
        "abbastanza. Prova con un solo video!",
    "Couldn't get that picture ready. Try again!":
        "Non sono riuscito a preparare quell'immagine. Riprova!",
    "Couldn't get those pictures ready. Try again!":
        "Non sono riuscito a preparare quelle immagini. Riprova!",
    "Couldn't get that video ready. Try again!":
        "Non sono riuscito a preparare quel video. Riprova!",
    "Couldn't get that ready. Try again!":
        "Non sono riuscito a prepararla. Riprova!",
    "Make or choose a picture first, then bring it here!":
        "Prima fai o scegli un'immagine, poi portala qui!",
    "Pick a picture to animate, not a video!":
        "Scegli un'immagine da animare, non un video!",
    "Pick a first picture and a last picture!":
        "Scegli un'immagine di inizio e una di fine!",
    "Couldn't save that picture. Try again!":
        "Non sono riuscito a salvare quell'immagine. Riprova!",
    "No picture for that one.": "Per quella non c'è nessuna immagine.",
    "Don't know what to save.": "Non so cosa salvare.",
    "Pick some things to save first!": "Prima scegli le cose da salvare!",
    "Those ones are gone!": "Quelle non ci sono più!",
    "Pick some things first!": "Prima scegli qualcosa!",
    "Pick some videos first!": "Prima scegli dei video!",
    "That's a lot! Try twenty or fewer.":
        "Sono tantissime! Prova con venti o meno.",
    "Pick videos to join - pictures can't go in a film!":
        "Scegli dei video da unire - le immagini non vanno in un film!",
    "Couldn't join those. Try again!": "Non sono riuscito a unirli. Riprova!",
    "Couldn't save that. Try again!": "Non sono riuscito a salvarla. Riprova!",
    "Couldn't save them. Try again!": "Non sono riuscito a salvarle. Riprova!",
    "Couldn't do that. Try again!": "Non ci sono riuscito. Riprova!",
    "Couldn't put that back. Try again!":
        "Non sono riuscito a rimetterla a posto. Riprova!",
    "Couldn't delete that. Try again!":
        "Non sono riuscito a cancellarla. Riprova!",
    "Couldn't delete that one. Try again!":
        "Non sono riuscito a cancellare quella. Riprova!",
    "Only videos can be made smooth!":
        "Solo i video si possono rendere fluidi!",
    "Couldn't read that video. Try another!":
        "Non sono riuscito a leggere quel video. Provane un altro!",
    "Only pictures can be made huge!":
        "Solo le immagini si possono ingrandire!",
    "Couldn't read that picture. Try another!":
        "Non sono riuscito a leggere quell'immagine. Provane un'altra!",
    "There isn't enough video there to loop. Try starting a bit earlier!":
        "Lì non c'è abbastanza video per fare il giro. Prova a partire un "
        "po' prima!",
    "Only videos can be moving stickers!":
        "Solo i video possono diventare adesivi che si muovono!",
    "Couldn't make that one move. Try again!":
        "Non sono riuscito a farla muovere. Riprova!",
    "Tell me what should be there! Type it in the box and tap Go.":
        "Dimmi cosa ci deve essere! Scrivilo nel riquadro e tocca Vai.",
    "Couldn't read what you painted. Try again!":
        "Non sono riuscito a leggere quello che hai colorato. Riprova!",
    "Type a word for the tag first!":
        "Prima scrivi una parola per l'etichetta!",
    "Pick a picture first!": "Prima scegli un'immagine!",
    "Who's that?": "Chi è?",
    "I don't know who that is.": "Non so chi sia.",
    "I can't find that picture.": "Non trovo quell'immagine.",
    "That one won't work as a picture of you.":
        "Quella non va bene come immagine di te.",
    "The factory is busy making your video! Chat to me when it's done.":
        "La fabbrica sta facendo il tuo video! Parliamo quando ha finito.",
    "That picture wouldn't go in the banner, sorry. Try another one!":
        "Quell'immagine non ci sta in cima, scusa. Provane un'altra!",
    "That one's too long to do this to. Try it on a shorter video!":
        "Quello è troppo lungo per farci questa cosa. Prova con un video più "
        "corto!",
    "Stickers can't be changed - they'd lose their see-through bits. Try it "
    "on one of your pictures!":
        "Gli adesivi non si possono cambiare - perderebbero le parti "
        "trasparenti. Prova con una delle tue immagini!",
    "Only pictures can be changed. Pick one of your pictures!":
        "Solo le immagini si possono cambiare. Scegli una delle tue immagini!",
    "Hi! I'm {name}. Ask me for an idea, or tell me what you'd like to make "
    "and I'll help you write it. ✨":
        "Ciao! Sono {name}. Chiedimi un'idea, oppure dimmi cosa vuoi fare e "
        "ti aiuto a scriverlo. ✨",
    "{name} is having a nap right now. Try again in a minute!":
        "{name} sta facendo un pisolino. Riprova tra un minuto!",
    "That's a long one! Say it in fewer words.":
        "Che lungo! Dillo con meno parole.",
    "Type something first!": "Prima scrivi qualcosa!",
    "Let's use a different picture! That one isn't one we can animate here. "
    "Try a drawing, a toy, a pet, or a place.":
        "Usiamo un'altra immagine! Quella qui non la possiamo animare. Prova "
        "con un disegno, un giocattolo, un animale o un posto.",

    # --- the title across the top -------------------------------------------
    "My AI Factory": "La mia fabbrica IA",
    "{name}'s AI Factory": "La fabbrica IA di {name}",
    "factory-of-elided": "La fabbrica IA di {name}",

    # --- dropdown group headings --------------------------------------------
    "Style": "Stile",
    "Where is it?": "Dov'è?",
    "Lighting": "Luce",
    "Feeling": "Sensazione",
    "Colours": "Colori",
    "Seen from": "Visto da",
    "Camera": "Telecamera",
    "Music": "Musica",
    "Background sounds": "Suoni di sottofondo",
    "Kind of music": "Tipo di musica",
    "Mood": "Atmosfera",
    "Main instrument": "Strumento principale",
    "Sung in": "Cantata in",
    "Who sings it": "Chi canta",
    "How many singers": "Quanti cantanti",
    # the empty option at the top of a dropdown
    "Any": "A scelta",
    "Match my words": "Le mie parole",
    "Just one singer": "Una voce",
}

# Dutch. The same keys in the same order under the same headings as
# FR above, so a line missing from one of them is a line out of step.
NL: dict[str, str] = {
    # --- the sign on the door ---------------------------------------------
    "Back soon!": "Tot straks!",
    "It opens at {when}. See you then!": "Hij gaat om {when} open. Tot dan!",
    "It opens again tomorrow at {when}. See you then!":
        "Morgen om {when} gaat hij weer open. Tot dan!",
    "closed-until-day": "Hij gaat {day} om {when} weer open!",
    "closed-until-next-day": "Hij gaat {day} om {when} weer open!",
    "The factory is closed right now. ": "De fabriek is nu dicht. ",
    "midnight": "middernacht",
    "midday": "twaalf uur 's middags",
    "today": "vandaag",
    "tomorrow": "morgen",
    "Monday": "maandag", "Tuesday": "dinsdag", "Wednesday": "woensdag",
    "Thursday": "donderdag", "Friday": "vrijdag", "Saturday": "zaterdag",
    "Sunday": "zondag",
    "next Monday": "volgende week maandag",
    "next Tuesday": "volgende week dinsdag",
    "next Wednesday": "volgende week woensdag",
    "next Thursday": "volgende week donderdag",
    "next Friday": "volgende week vrijdag",
    "next Saturday": "volgende week zaterdag",
    "next Sunday": "volgende week zondag",

    # --- refusals they read ------------------------------------------------
    "The factory is closed right now. Back soon!":
        "De fabriek is nu dicht. Tot straks!",
    "One at a time! Wait for the one you're making now to finish, or tap "
    "Stop if you've changed your mind.":
        "Eentje tegelijk! Wacht tot die van nu klaar is, of tik op Stop als "
        "je van gedachten bent veranderd.",
    "That's all the pictures for today - great work! Come back tomorrow.":
        "Dat waren alle plaatjes voor vandaag - goed gedaan! Kom morgen "
        "terug.",
    "That's all the videos for today - great work! Come back tomorrow.":
        "Dat waren alle video's voor vandaag - goed gedaan! Kom morgen terug.",
    "That's all the songs for today - great work! Come back tomorrow.":
        "Dat waren alle liedjes voor vandaag - goed gedaan! Kom morgen terug.",
    "That's switched off right now.": "Dat staat nu uit.",
    "Making pictures is switched off right now. Ask a grown-up!":
        "Plaatjes maken staat nu uit. Vraag een volwassene!",
    "Making videos is switched off right now. Ask a grown-up!":
        "Video's maken staat nu uit. Vraag een volwassene!",
    "Making comics is switched off right now. Ask a grown-up!":
        "Strips maken staat nu uit. Vraag een volwassene!",
    "Making songs is switched off right now. Ask a grown-up!":
        "Liedjes maken staat nu uit. Vraag een volwassene!",
    "The chat is switched off right now. Ask a grown-up!":
        "De chat staat nu uit. Vraag een volwassene!",

    # --- the warm-up sums ---------------------------------------------------
    "Let's warm up your brain first! {sums} and the factory opens.":
        "Eerst je hersens opwarmen! {sums} en de fabriek gaat open.",
    "One quick sum": "Eén snel sommetje",
    "Two quick sums": "Twee snelle sommetjes",
    "Three quick sums": "Drie snelle sommetjes",
    "Four quick sums": "Vier snelle sommetjes",
    "Five quick sums": "Vijf snelle sommetjes",
    "Six quick sums": "Zes snelle sommetjes",
    "Seven quick sums": "Zeven snelle sommetjes",
    "Eight quick sums": "Acht snelle sommetjes",
    "Nine quick sums": "Negen snelle sommetjes",
    "Ten quick sums": "Tien snelle sommetjes",

    # --- the word filter ----------------------------------------------------
    "Type something you'd like to make first!": "Typ eerst wat je wilt maken!",
    "That's a bit long! Keep it under {max} characters.":
        "Dat is wat lang! Hou het onder {max} tekens.",

    # --- what the progress bar says (jobs.py) -------------------------------
    "Getting ready...": "Aan het klaarzetten...",
    "Something went wrong making that one. Try again!":
        "Er ging iets mis bij het maken. Probeer het nog eens!",
    "The art computer is busy with someone else. Waiting for your turn...":
        "De tekencomputer is met iemand anders bezig. Wachten tot jij aan de "
        "beurt bent...",
    "Stopped! Nothing was made. Try a different idea.":
        "Gestopt! Er is niets gemaakt. Probeer een ander idee.",
    "Picture {n} of {total}...": "Plaatje {n} van {total}...",
    "Part {done} of {total} filmed...": "Deel {done} van {total} gefilmd...",
    "Panel {done} of {total} drawn...": "Vakje {done} van {total} getekend...",
    "Putting it all together...": "Alles in elkaar aan het zetten...",
    "Looking at every frame...": "Naar elk beeldje aan het kijken...",
    "Drawing all the in-between bits...":
        "Alle tussenstukjes aan het tekenen...",
    "Putting it back together!": "Weer in elkaar aan het zetten!",
    "Getting your picture ready...": "Je plaatje aan het klaarmaken...",
    "Making it bigger, bit by bit...":
        "Stukje bij beetje groter aan het maken...",
    "Almost done!": "Bijna klaar!",
    "Looking at your picture...": "Naar je plaatje aan het kijken...",
    "Painting what's outside...": "Aan het schilderen wat erbuiten ligt...",
    "Changing it...": "Aan het veranderen...",
    "Nearly there!": "Bijna zover!",
    "Working out the tune...": "Het wijsje aan het bedenken...",

    # --- what kind of sound: a song, a little tune, a background
    #     hum. One card and one model; see app/music.py KINDS.
    "Working out the hum...": "Het geluid aan het bedenken...",
    "Words, a tune and somebody singing them.": "Woorden, een wijsje en iemand die ze zingt.",
    "A short tune with nobody singing - good for the start of a video.": "Een kort wijsje zonder zang - leuk voor het begin van een video.",
    "A long, quiet sound to put behind something else. No tune, no beat.": "Een lang, rustig geluid om achter iets anders te zetten. Geen wijsje, geen ritme.",
    "Playing it... this takes a moment.": "Aan het spelen... dit duurt even.",
    "Mixing it down!": "Alles aan het mixen!",
    "Reading your story...": "Je verhaal aan het lezen...",
    "Drawing the panels...": "De vakjes aan het tekenen...",
    "Putting the page together!": "De pagina in elkaar aan het zetten!",
    "Working out your story...": "Je verhaal aan het uitwerken...",
    "Filming it, bit by bit... this takes a while.":
        "Stukje voor stukje aan het filmen... dat duurt even.",
    "Joining it into one film!": "Er één film van aan het maken!",
    "Thinking up your picture...": "Je plaatje aan het bedenken...",
    "Painting it now...": "Nu aan het schilderen...",
    "Getting the video ready...": "De video aan het klaarmaken...",
    "Making your video... this part takes a few minutes.":
        "Je video aan het maken... dit stuk duurt een paar minuten.",
    "Adding the details and the sound...": "De details en het geluid erbij...",
    "Your comic is ready!": "Je strip is klaar!",
    "Your film is ready!": "Je film is klaar!",
    "Your song is ready!": "Je liedje is klaar!",
    "Your tune is ready!": "Je deuntje is klaar!",
    "Your sound is ready!": "Je geluid is klaar!",
    "Your video is ready!": "Je video is klaar!",
    "Your picture is ready!": "Je plaatje is klaar!",
    "All {n} pictures are ready - pick your favourite!":
        "Alle {n} plaatjes zijn klaar - kies je favoriet!",
    "Stopped! Here's the one you got.": "Gestopt! Dit is wat je kreeg.",
    "Stopped! Here are the {n} you got.":
        "Gestopt! Dit zijn de {n} die je kreeg.",

    # --- the milestones -----------------------------------------------------
    "pictures": "plaatjes",
    "videos": "video's",
    "songs": "liedjes",
    "comics": "strips",
    "things": "dingen",

    # --- stickers, voices and sounds ----------------------------------------
    "That one can't be a sticker.": "Daar kan geen sticker van.",
    "That one's background is too busy to cut out. Stickers work best on a "
    "picture where the thing you want sits on its own - try asking for \"on "
    "a plain white background\"!":
        "De achtergrond is te druk om uit te knippen. Stickers lukken het "
        "best bij een plaatje waar het ding alleen staat - vraag eens om "
        "\"op een effen witte achtergrond\"!",
    "That one went all see-through! Try a picture where the thing you want "
    "stands out from behind it.":
        "Die werd helemaal doorzichtig! Probeer een plaatje waar het ding "
        "goed opvalt tegen de achtergrond.",
    "Only pictures can be stickers!":
        "Alleen plaatjes kunnen stickers worden!",
    "Couldn't cut that one out. Try again!":
        "Uitknippen lukte niet. Probeer het nog eens!",
    "That one can't have a voice added.": "Daar kan geen stem bij.",
    "Couldn't add your voice. Try again!":
        "Je stem erbij zetten lukte niet. Probeer het nog eens!",
    "That recording was empty. Try again!":
        "Die opname was leeg. Probeer het nog eens!",
    "That recording is too long. Keep it short!":
        "Die opname is te lang. Hou het kort!",
    "That one can't have a sound added.": "Daar kan geen geluid bij.",
    "Couldn't add that sound. Try again!":
        "Dat geluid erbij zetten lukte niet. Probeer het nog eens!",
    "No such sound.": "Dat geluid bestaat niet.",

    # --- everything else they can be told ------------------------------------
    "That one's gone. Pick another!": "Die is weg. Kies een andere!",
    "That picture isn't ready. Pick another!":
        "Dat plaatje is nog niet klaar. Kies een ander!",
    "Couldn't fetch that picture. Try again!":
        "Dat plaatje ophalen lukte niet. Probeer het nog eens!",
    "That one's gone!": "Die is weg!",
    "That one's gone.": "Die is weg.",
    "That one's gone already!": "Die is al weg!",
    "That one's gone already.": "Die is al weg.",
    "That one's gone for good.": "Die is voorgoed weg.",
    "That picture's gone. Pick another!":
        "Dat plaatje is weg. Kies een ander!",
    "That one's gone. Make a new one!": "Die is weg. Maak een nieuwe!",
    "That one isn't ready yet.": "Die is nog niet klaar.",
    "The music maker isn't set up on this machine yet. Everything else still "
    "works!":
        "De muziekmaker staat op deze computer nog niet klaar. De rest werkt "
        "gewoon!",
    "A comic needs at least {min} pictures and you haven't got that many "
    "left today. Try a single picture!":
        "Een strip heeft minstens {min} plaatjes nodig en zoveel heb je "
        "vandaag niet meer over. Probeer één plaatje!",
    "A film needs at least {min} videos and you haven't got that many left "
    "today. Try a single video!":
        "Een film heeft minstens {min} video's nodig en zoveel heb je "
        "vandaag niet meer over. Probeer één video!",
    "Couldn't get that picture ready. Try again!":
        "Dat plaatje klaarmaken lukte niet. Probeer het nog eens!",
    "Couldn't get those pictures ready. Try again!":
        "Die plaatjes klaarmaken lukte niet. Probeer het nog eens!",
    "Couldn't get that video ready. Try again!":
        "Die video klaarmaken lukte niet. Probeer het nog eens!",
    "Couldn't get that ready. Try again!":
        "Dat klaarmaken lukte niet. Probeer het nog eens!",
    "Make or choose a picture first, then bring it here!":
        "Maak of kies eerst een plaatje en neem het dan mee hierheen!",
    "Pick a picture to animate, not a video!":
        "Kies een plaatje om te laten bewegen, geen video!",
    "Pick a first picture and a last picture!":
        "Kies een eerste en een laatste plaatje!",
    "Couldn't save that picture. Try again!":
        "Dat plaatje opslaan lukte niet. Probeer het nog eens!",
    "No picture for that one.": "Daar hoort geen plaatje bij.",
    "Don't know what to save.": "Ik weet niet wat ik moet opslaan.",
    "Pick some things to save first!": "Kies eerst wat je wilt opslaan!",
    "Those ones are gone!": "Die zijn weg!",
    "Pick some things first!": "Kies eerst een paar dingen!",
    "Pick some videos first!": "Kies eerst een paar video's!",
    "That's a lot! Try twenty or fewer.":
        "Dat is veel! Probeer er twintig of minder.",
    "Pick videos to join - pictures can't go in a film!":
        "Kies video's om aan elkaar te plakken - plaatjes kunnen niet in een "
        "film!",
    "Couldn't join those. Try again!":
        "Die aan elkaar plakken lukte niet. Probeer het nog eens!",
    "Couldn't save that. Try again!":
        "Dat opslaan lukte niet. Probeer het nog eens!",
    "Couldn't save them. Try again!":
        "Die opslaan lukte niet. Probeer het nog eens!",
    "Couldn't do that. Try again!": "Dat lukte niet. Probeer het nog eens!",
    "Couldn't put that back. Try again!":
        "Terugzetten lukte niet. Probeer het nog eens!",
    "Couldn't delete that. Try again!":
        "Weggooien lukte niet. Probeer het nog eens!",
    "Couldn't delete that one. Try again!":
        "Die weggooien lukte niet. Probeer het nog eens!",
    "Only videos can be made smooth!":
        "Alleen video's kunnen vloeiend worden!",
    "Couldn't read that video. Try another!":
        "Die video lezen lukte niet. Probeer een andere!",
    "Only pictures can be made huge!":
        "Alleen plaatjes kunnen reuzegroot worden!",
    "Couldn't read that picture. Try another!":
        "Dat plaatje lezen lukte niet. Probeer een ander!",
    "There isn't enough video there to loop. Try starting a bit earlier!":
        "Daar zit niet genoeg video om rond te gaan. Begin eens wat eerder!",
    "Only videos can be moving stickers!":
        "Alleen video's kunnen bewegende stickers worden!",
    "Couldn't make that one move. Try again!":
        "Die laten bewegen lukte niet. Probeer het nog eens!",
    "Tell me what should be there! Type it in the box and tap Go.":
        "Zeg wat er moet komen! Typ het in het vakje en tik op Start.",
    "Couldn't read what you painted. Try again!":
        "Wat je verfde was niet te lezen. Probeer het nog eens!",
    "Type a word for the tag first!": "Typ eerst een woord voor het label!",
    "Pick a picture first!": "Kies eerst een plaatje!",
    "Who's that?": "Wie is dat?",
    "I don't know who that is.": "Ik weet niet wie dat is.",
    "I can't find that picture.": "Ik kan dat plaatje niet vinden.",
    "That one won't work as a picture of you.":
        "Die werkt niet als plaatje van jou.",
    "The factory is busy making your video! Chat to me when it's done.":
        "De fabriek is druk met je video! Chat met me als hij klaar is.",
    "That picture wouldn't go in the banner, sorry. Try another one!":
        "Dat plaatje paste niet in de balk bovenaan, sorry. Probeer een "
        "ander!",
    "That one's too long to do this to. Try it on a shorter video!":
        "Die is te lang om dit mee te doen. Probeer een kortere video!",
    "Stickers can't be changed - they'd lose their see-through bits. Try it "
    "on one of your pictures!":
        "Stickers kun je niet veranderen - dan raken ze hun doorzichtige "
        "stukjes kwijt. Probeer het op een van je plaatjes!",
    "Only pictures can be changed. Pick one of your pictures!":
        "Alleen plaatjes kun je veranderen. Kies een van je plaatjes!",
    "Hi! I'm {name}. Ask me for an idea, or tell me what you'd like to make "
    "and I'll help you write it. ✨":
        "Hoi! Ik ben {name}. Vraag me om een idee, of vertel wat je wilt "
        "maken en ik help je het op te schrijven. ✨",
    "{name} is having a nap right now. Try again in a minute!":
        "{name} doet even een dutje. Probeer het zo nog eens!",
    "That's a long one! Say it in fewer words.":
        "Dat is een lange! Zeg het in minder woorden.",
    "Type something first!": "Typ eerst iets!",
    "Let's use a different picture! That one isn't one we can animate here. "
    "Try a drawing, a toy, a pet, or a place.":
        "Kies een ander plaatje! Die kunnen we hier niet laten bewegen. "
        "Probeer een tekening, speelgoed, een huisdier of een plek.",

    # --- the title across the top -------------------------------------------
    "My AI Factory": "Mijn AI-fabriek",
    "{name}'s AI Factory": "De AI-fabriek van {name}",
    "factory-of-elided": "De AI-fabriek van {name}",

    # --- dropdown group headings --------------------------------------------
    "Style": "Stijl",
    "Where is it?": "Waar is het?",
    "Lighting": "Licht",
    "Feeling": "Gevoel",
    "Colours": "Kleuren",
    "Seen from": "Gezien vanaf",
    "Camera": "Camera",
    "Music": "Muziek",
    "Background sounds": "Achtergrondgeluid",
    "Kind of music": "Soort muziek",
    "Mood": "Sfeer",
    "Main instrument": "Hoofdinstrument",
    "Sung in": "Gezongen in",
    "Who sings it": "Wie zingt",
    "How many singers": "Hoeveel zangers",
    # the empty option at the top of a dropdown
    "Any": "Alles mag",
    "Match my words": "Zoals ik typ",
    "Just one singer": "Eén zanger",
}

# Portuguese. The same keys in the same order under the same headings as
# FR above, so a line missing from one of them is a line out of step.
PT: dict[str, str] = {
    # --- the sign on the door ---------------------------------------------
    "Back soon!": "Já volta!",
    "It opens at {when}. See you then!": "Abre às {when}. Até lá!",
    "It opens again tomorrow at {when}. See you then!":
        "Volta a abrir amanhã às {when}. Até lá!",
    "closed-until-day": "Volta a abrir {day} às {when}!",
    "closed-until-next-day": "Volta a abrir {day} às {when}!",
    "The factory is closed right now. ":
        "A fábrica está fechada neste momento. ",
    "midnight": "meia-noite",
    "midday": "12:00",
    "today": "hoje",
    "tomorrow": "amanhã",
    "Monday": "segunda-feira",
    "Tuesday": "terça-feira",
    "Wednesday": "quarta-feira",
    "Thursday": "quinta-feira", "Friday": "sexta-feira", "Saturday": "sábado",
    "Sunday": "domingo",
    "next Monday": "na próxima segunda-feira",
    "next Tuesday": "na próxima terça-feira",
    "next Wednesday": "na próxima quarta-feira",
    "next Thursday": "na próxima quinta-feira",
    "next Friday": "na próxima sexta-feira",
    "next Saturday": "no próximo sábado",
    "next Sunday": "no próximo domingo",

    # --- refusals they read ------------------------------------------------
    "The factory is closed right now. Back soon!":
        "A fábrica está fechada neste momento. Já volta!",
    "One at a time! Wait for the one you're making now to finish, or tap "
    "Stop if you've changed your mind.":
        "Uma coisa de cada vez! Espera que acabe a que estás a fazer agora, "
        "ou toca em Parar se mudaste de ideias.",
    "That's all the pictures for today - great work! Come back tomorrow.":
        "Acabaram as imagens por hoje - bom trabalho! Volta amanhã.",
    "That's all the videos for today - great work! Come back tomorrow.":
        "Acabaram os vídeos por hoje - bom trabalho! Volta amanhã.",
    "That's all the songs for today - great work! Come back tomorrow.":
        "Acabaram as canções por hoje - bom trabalho! Volta amanhã.",
    "That's switched off right now.": "Isso está desligado neste momento.",
    "Making pictures is switched off right now. Ask a grown-up!":
        "Fazer imagens está desligado neste momento. Pede a um adulto!",
    "Making videos is switched off right now. Ask a grown-up!":
        "Fazer vídeos está desligado neste momento. Pede a um adulto!",
    "Making comics is switched off right now. Ask a grown-up!":
        "Fazer BD está desligado neste momento. Pede a um adulto!",
    "Making songs is switched off right now. Ask a grown-up!":
        "Fazer canções está desligado neste momento. Pede a um adulto!",
    "The chat is switched off right now. Ask a grown-up!":
        "O chat está desligado neste momento. Pede a um adulto!",

    # --- the warm-up sums ---------------------------------------------------
    "Let's warm up your brain first! {sums} and the factory opens.":
        "Vamos aquecer o cérebro primeiro! {sums} e a fábrica abre.",
    "One quick sum": "Uma conta rápida",
    "Two quick sums": "Duas contas rápidas",
    "Three quick sums": "Três contas rápidas",
    "Four quick sums": "Quatro contas rápidas",
    "Five quick sums": "Cinco contas rápidas",
    "Six quick sums": "Seis contas rápidas",
    "Seven quick sums": "Sete contas rápidas",
    "Eight quick sums": "Oito contas rápidas",
    "Nine quick sums": "Nove contas rápidas",
    "Ten quick sums": "Dez contas rápidas",

    # --- the word filter ----------------------------------------------------
    "Type something you'd like to make first!":
        "Escreve primeiro o que gostavas de fazer!",
    "That's a bit long! Keep it under {max} characters.":
        "Isso é um bocadinho longo! Fica-te por menos de {max} caracteres.",

    # --- what the progress bar says (jobs.py) -------------------------------
    "Getting ready...": "A preparar...",
    "Something went wrong making that one. Try again!":
        "Alguma coisa correu mal com essa. Tenta outra vez!",
    "The art computer is busy with someone else. Waiting for your turn...":
        "O computador dos desenhos está ocupado com outra pessoa. À espera "
        "da tua vez...",
    "Stopped! Nothing was made. Try a different idea.":
        "Parado! Não se fez nada. Experimenta outra ideia.",
    "Picture {n} of {total}...": "Imagem {n} de {total}...",
    "Part {done} of {total} filmed...": "Parte {done} de {total} filmada...",
    "Panel {done} of {total} drawn...":
        "Quadradinho {done} de {total} desenhado...",
    "Putting it all together...": "A juntar tudo...",
    "Looking at every frame...": "A ver cada imagem...",
    "Drawing all the in-between bits...":
        "A desenhar tudo o que fica pelo meio...",
    "Putting it back together!": "A colar tudo outra vez!",
    "Getting your picture ready...": "A preparar a tua imagem...",
    "Making it bigger, bit by bit...": "A aumentá-la, bocado a bocado...",
    "Almost done!": "Quase pronto!",
    "Looking at your picture...": "A olhar para a tua imagem...",
    "Painting what's outside...": "A pintar o que está à volta...",
    "Changing it...": "A mudá-la...",
    "Nearly there!": "Está quase!",
    "Working out the tune...": "A encontrar a melodia...",

    # --- what kind of sound: a song, a little tune, a background
    #     hum. One card and one model; see app/music.py KINDS.
    "Working out the hum...": "A encontrar o som...",
    "Words, a tune and somebody singing them.": "Letra, uma melodia e alguém a cantá-la.",
    "A short tune with nobody singing - good for the start of a video.": "Uma melodia curta sem ninguém a cantar - boa para o início de um vídeo.",
    "A long, quiet sound to put behind something else. No tune, no beat.": "Um som longo e calmo para pôr atrás de outra coisa. Sem melodia e sem ritmo.",
    "Playing it... this takes a moment.": "A tocá-la... demora um bocadinho.",
    "Mixing it down!": "A misturar tudo!",
    "Reading your story...": "A ler a tua história...",
    "Drawing the panels...": "A desenhar os quadradinhos...",
    "Putting the page together!": "A montar a página!",
    "Working out your story...": "A imaginar a tua história...",
    "Filming it, bit by bit... this takes a while.":
        "A filmá-la, parte a parte... demora um bocado.",
    "Joining it into one film!": "A juntar tudo num só filme!",
    "Thinking up your picture...": "A imaginar a tua imagem...",
    "Painting it now...": "A pintá-la agora...",
    "Getting the video ready...": "A preparar o vídeo...",
    "Making your video... this part takes a few minutes.":
        "A fazer o teu vídeo... esta parte demora uns minutos.",
    "Adding the details and the sound...": "A juntar os pormenores e o som...",
    "Your comic is ready!": "A tua BD está pronta!",
    "Your film is ready!": "O teu filme está pronto!",
    "Your song is ready!": "A tua canção está pronta!",
    "Your tune is ready!": "A tua melodia está pronta!",
    "Your sound is ready!": "O teu som está pronto!",
    "Your video is ready!": "O teu vídeo está pronto!",
    "Your picture is ready!": "A tua imagem está pronta!",
    "All {n} pictures are ready - pick your favourite!":
        "As {n} imagens estão prontas - escolhe a tua preferida!",
    "Stopped! Here's the one you got.": "Parado! Aqui está a que ficou feita.",
    "Stopped! Here are the {n} you got.":
        "Parado! Aqui estão as {n} que ficaram feitas.",

    # --- the milestones -----------------------------------------------------
    "pictures": "imagens",
    "videos": "vídeos",
    "songs": "canções",
    "comics": "BD",
    "things": "coisas",

    # --- stickers, voices and sounds ----------------------------------------
    "That one can't be a sticker.": "Essa não pode ser um autocolante.",
    "That one's background is too busy to cut out. Stickers work best on a "
    "picture where the thing you want sits on its own - try asking for \"on "
    "a plain white background\"!":
        "O fundo dessa é cheio demais para recortar. Os autocolantes "
        "funcionam melhor numa imagem em que a coisa que queres está sozinha "
        "- experimenta pedir “sobre um fundo branco liso”!",
    "That one went all see-through! Try a picture where the thing you want "
    "stands out from behind it.":
        "Essa ficou toda transparente! Experimenta uma imagem em que a coisa "
        "que queres se destaque bem do fundo.",
    "Only pictures can be stickers!": "Só as imagens podem ser autocolantes!",
    "Couldn't cut that one out. Try again!":
        "Não deu para a recortar. Tenta outra vez!",
    "That one can't have a voice added.": "Não se pode juntar voz a essa.",
    "Couldn't add your voice. Try again!":
        "Não deu para juntar a tua voz. Tenta outra vez!",
    "That recording was empty. Try again!":
        "Essa gravação estava vazia. Tenta outra vez!",
    "That recording is too long. Keep it short!":
        "Essa gravação é comprida demais. Faz curtinho!",
    "That one can't have a sound added.": "Não se pode juntar som a essa.",
    "Couldn't add that sound. Try again!":
        "Não deu para juntar esse som. Tenta outra vez!",
    "No such sound.": "Esse som não existe.",

    # --- everything else they can be told ------------------------------------
    "That one's gone. Pick another!": "Essa já não existe. Escolhe outra!",
    "That picture isn't ready. Pick another!":
        "Essa imagem não está pronta. Escolhe outra!",
    "Couldn't fetch that picture. Try again!":
        "Não deu para ir buscar essa imagem. Tenta outra vez!",
    "That one's gone!": "Essa já não existe!",
    "That one's gone.": "Essa já não existe.",
    "That one's gone already!": "Essa já desapareceu!",
    "That one's gone already.": "Essa já desapareceu.",
    "That one's gone for good.": "Essa foi-se de vez.",
    "That picture's gone. Pick another!":
        "Essa imagem já não existe. Escolhe outra!",
    "That one's gone. Make a new one!": "Essa já não existe. Faz uma nova!",
    "That one isn't ready yet.": "Essa ainda não está pronta.",
    "The music maker isn't set up on this machine yet. Everything else still "
    "works!":
        "A oficina da música ainda não está instalada neste computador. Tudo "
        "o resto funciona!",
    "A comic needs at least {min} pictures and you haven't got that many "
    "left today. Try a single picture!":
        "Uma BD precisa de pelo menos {min} imagens e hoje já não te restam "
        "tantas. Experimenta uma imagem sozinha!",
    "A film needs at least {min} videos and you haven't got that many left "
    "today. Try a single video!":
        "Um filme precisa de pelo menos {min} vídeos e hoje já não te restam "
        "tantos. Experimenta um vídeo sozinho!",
    "Couldn't get that picture ready. Try again!":
        "Não deu para preparar essa imagem. Tenta outra vez!",
    "Couldn't get those pictures ready. Try again!":
        "Não deu para preparar essas imagens. Tenta outra vez!",
    "Couldn't get that video ready. Try again!":
        "Não deu para preparar esse vídeo. Tenta outra vez!",
    "Couldn't get that ready. Try again!":
        "Não deu para preparar isso. Tenta outra vez!",
    "Make or choose a picture first, then bring it here!":
        "Faz ou escolhe primeiro uma imagem e depois trá-la para aqui!",
    "Pick a picture to animate, not a video!":
        "Escolhe uma imagem para ganhar vida, não um vídeo!",
    "Pick a first picture and a last picture!":
        "Escolhe uma primeira imagem e uma última imagem!",
    "Couldn't save that picture. Try again!":
        "Não deu para guardar essa imagem. Tenta outra vez!",
    "No picture for that one.": "Não há imagem para essa.",
    "Don't know what to save.": "Não sei o que guardar.",
    "Pick some things to save first!":
        "Escolhe primeiro umas coisas para guardar!",
    "Those ones are gone!": "Essas já não existem!",
    "Pick some things first!": "Escolhe primeiro umas coisas!",
    "Pick some videos first!": "Escolhe primeiro uns vídeos!",
    "That's a lot! Try twenty or fewer.":
        "Isso é muito! Experimenta vinte ou menos.",
    "Pick videos to join - pictures can't go in a film!":
        "Escolhe vídeos para juntar - as imagens não entram num filme!",
    "Couldn't join those. Try again!":
        "Não deu para os juntar. Tenta outra vez!",
    "Couldn't save that. Try again!":
        "Não deu para guardar isso. Tenta outra vez!",
    "Couldn't save them. Try again!":
        "Não deu para as guardar. Tenta outra vez!",
    "Couldn't do that. Try again!":
        "Não deu para fazer isso. Tenta outra vez!",
    "Couldn't put that back. Try again!":
        "Não deu para pôr isso de volta. Tenta outra vez!",
    "Couldn't delete that. Try again!":
        "Não deu para apagar isso. Tenta outra vez!",
    "Couldn't delete that one. Try again!":
        "Não deu para apagar essa. Tenta outra vez!",
    "Only videos can be made smooth!": "Só os vídeos podem ficar fluidos!",
    "Couldn't read that video. Try another!":
        "Não deu para ler esse vídeo. Experimenta outro!",
    "Only pictures can be made huge!": "Só as imagens podem ficar gigantes!",
    "Couldn't read that picture. Try another!":
        "Não deu para ler essa imagem. Experimenta outra!",
    "There isn't enough video there to loop. Try starting a bit earlier!":
        "Não há vídeo que chegue aí para fazer uma volta. Experimenta "
        "começar um bocadinho antes!",
    "Only videos can be moving stickers!":
        "Só os vídeos podem ser autocolantes animados!",
    "Couldn't make that one move. Try again!":
        "Não deu para pôr essa a mexer. Tenta outra vez!",
    "Tell me what should be there! Type it in the box and tap Go.":
        "Diz-me o que deve ficar ali! Escreve na caixa e toca em Vai.",
    "Couldn't read what you painted. Try again!":
        "Não deu para ler o que pintaste. Tenta outra vez!",
    "Type a word for the tag first!":
        "Escreve primeiro uma palavra para a etiqueta!",
    "Pick a picture first!": "Escolhe primeiro uma imagem!",
    "Who's that?": "Quem é?",
    "I don't know who that is.": "Não sei quem é.",
    "I can't find that picture.": "Não encontro essa imagem.",
    "That one won't work as a picture of you.":
        "Essa não serve como imagem de ti.",
    "The factory is busy making your video! Chat to me when it's done.":
        "A fábrica está ocupada a fazer o teu vídeo! Fala comigo quando "
        "acabar.",
    "That picture wouldn't go in the banner, sorry. Try another one!":
        "Essa imagem não dá para a faixa do topo, desculpa. Experimenta "
        "outra!",
    "That one's too long to do this to. Try it on a shorter video!":
        "Essa é comprida demais para isto. Experimenta num vídeo mais curto!",
    "Stickers can't be changed - they'd lose their see-through bits. Try it "
    "on one of your pictures!":
        "Os autocolantes não podem ser mudados - perdiam as partes "
        "transparentes. Experimenta numa das tuas imagens!",
    "Only pictures can be changed. Pick one of your pictures!":
        "Só as imagens podem ser mudadas. Escolhe uma das tuas imagens!",
    "Hi! I'm {name}. Ask me for an idea, or tell me what you'd like to make "
    "and I'll help you write it. ✨":
        "Olá! Eu sou {name}. Pede-me uma ideia, ou diz-me o que queres fazer "
        "que eu ajudo-te a escrever. ✨",
    "{name} is having a nap right now. Try again in a minute!":
        "{name} está a dormir uma soneca. Tenta outra vez daqui a um minuto!",
    "That's a long one! Say it in fewer words.":
        "Essa é comprida! Diz em menos palavras.",
    "Type something first!": "Escreve alguma coisa primeiro!",
    "Let's use a different picture! That one isn't one we can animate here. "
    "Try a drawing, a toy, a pet, or a place.":
        "Vamos usar outra imagem! Essa não é das que conseguimos pôr a mexer "
        "aqui. Experimenta um desenho, um brinquedo, um animal ou um sítio.",

    # --- the title across the top -------------------------------------------
    "My AI Factory": "A Minha Fábrica IA",
    "{name}'s AI Factory": "A Fábrica IA de {name}",
    "factory-of-elided": "A Fábrica IA de {name}",

    # --- dropdown group headings --------------------------------------------
    "Style": "Estilo",
    "Where is it?": "Onde é?",
    "Lighting": "Luz",
    "Feeling": "Ambiente",
    "Colours": "Cores",
    "Seen from": "Visto de",
    "Camera": "Câmara",
    "Music": "Música",
    "Background sounds": "Sons de fundo",
    "Kind of music": "Género",
    "Mood": "Ambiente",
    "Main instrument": "Instrumento",
    "Sung in": "Cantado em",
    "Who sings it": "Quem canta",
    "How many singers": "Quantas vozes",
    # the empty option at the top of a dropdown
    "Any": "À escolha",
    "Match my words": "Como escrevi",
    "Just one singer": "Uma só voz",
}

# The label on every dropdown choice, by (group id, choice id), one table per
# language.
#
# Deliberately not in the choice tuples in styles.py / music.py: those lists
# grow, and six translation columns beside them are six more things for anybody
# adding a choice to get wrong. An id with nothing here shows its English
# label, so a new choice turns up working and untranslated rather than blank.
CHOICES_FR: dict[tuple[str, str], str] = {
    ("style", "cartoon"): "Dessin animé",
    ("style", "anime"): "Anime",
    ("style", "pixar"): "Film en 3D",
    ("style", "storybook"): "Livre d'images",
    ("style", "watercolour"): "Aquarelle",
    ("style", "oil"): "Peinture à l'huile",
    ("style", "sketch"): "Croquis au crayon",
    ("style", "pixel"): "Pixel art",
    ("style", "comic"): "BD",
    ("style", "clay"): "Pâte à modeler",
    ("style", "papercraft"): "Papier découpé",
    ("style", "photo"): "Photo",

    ("scene", "forest"): "Forêt",
    ("scene", "beach"): "Plage",
    ("scene", "city"): "Ville",
    ("scene", "farm"): "Ferme",
    ("scene", "mountains"): "Montagnes",
    ("scene", "mountaintop"): "Sommet",
    ("scene", "snow"): "Neige",
    ("scene", "desert"): "Désert",
    ("scene", "oasis"): "Oasis",
    ("scene", "jungle"): "Jungle",
    ("scene", "jungletemple"): "Temple dans la jungle",
    ("scene", "savannah"): "Savane",
    ("scene", "rainstreet"): "Rue sous la pluie",
    ("scene", "market"): "Marché animé",
    ("scene", "lighthouse"): "Phare",
    ("scene", "treehouse"): "Cabane dans un arbre",
    ("scene", "playground"): "Aire de jeux",
    ("scene", "library"): "Bibliothèque",
    ("scene", "volcano"): "Dans un volcan",
    ("scene", "arctic"): "Arctique",
    ("scene", "waterfall"): "Cascade",
    ("scene", "space"): "Espace",
    ("scene", "moon"): "Sur la Lune",
    ("scene", "underwater"): "Sous l'eau",
    ("scene", "castle"): "Château",
    ("scene", "candyland"): "Pays des bonbons",
    ("scene", "clouds"): "Dans les nuages",
    ("scene", "cloudcastle"): "Château de nuages",
    ("scene", "floatingisland"): "Île volante",
    ("scene", "snowglobe"): "Dans une boule à neige",
    ("scene", "giantskitchen"): "Cuisine du géant",
    ("scene", "robotcity"): "Ville des robots",
    ("scene", "dragoncave"): "Grotte du dragon",
    ("scene", "dinosaurvalley"): "Vallée des dinosaures",
    ("scene", "bedroom"): "Chambre douillette",
    ("scene", "kitchentable"): "Table de la cuisine",
    ("scene", "gardenshed"): "Cabane de jardin",
    ("scene", "backseat"): "En voiture",
    ("scene", "backyard"): "Jardin",

    ("lighting", "sunny"): "Grand soleil",
    ("lighting", "sunset"): "Coucher de soleil",
    ("lighting", "moonlight"): "Clair de lune",
    ("lighting", "candle"): "Bougie",
    ("lighting", "neon"): "Néons",
    ("lighting", "rainbow"): "Lumière arc-en-ciel",
    ("lighting", "misty"): "Matin de brume",
    ("lighting", "stars"): "Nuit étoilée",
    ("lighting", "fire"): "Feu de bois",

    ("mood", "cosy"): "Douillette",
    ("mood", "magical"): "Magique",
    ("mood", "silly"): "Rigolote",
    ("mood", "epic"): "Épique",
    ("mood", "peaceful"): "Paisible",
    ("mood", "adventure"): "Aventureuse",
    ("mood", "dreamy"): "Rêveuse",
    ("mood", "mysterious"): "Mystérieuse",
    ("mood", "brave"): "Courageuse",
    ("mood", "sleepy"): "Endormie",
    ("mood", "proud"): "Fière",
    ("mood", "nervous"): "Inquiète",
    ("mood", "giggly"): "Pouffante",
    ("mood", "dramatic"): "Dramatique",
    ("mood", "spookyfun"): "Frissons pour rire",
    ("mood", "lonely"): "Solitaire",
    ("mood", "triumphant"): "Triomphante",
    ("mood", "curious"): "Curieuse",
    ("mood", "grumpy"): "Grognon",
    ("mood", "wild"): "Déchaînée",
    ("mood", "excited"): "Tout excitée",
    ("mood", "shy"): "Timide",
    ("mood", "confident"): "Sûre d'elle",
    ("mood", "sneaky"): "Sournoise",
    ("mood", "hopeful"): "Pleine d'espoir",
    ("mood", "determined"): "Déterminée",
    ("mood", "surprised"): "Surprise",
    ("mood", "mischievous"): "Espiègle",

    ("colours", "bright"): "Vives et franches",
    ("colours", "pastel"): "Pastels doux",
    ("colours", "rainbow"): "Arc-en-ciel",
    ("colours", "warm"): "Chaudes",
    ("colours", "cool"): "Froides",
    ("colours", "neon"): "Fluo",
    ("colours", "earthy"): "Terreuses",
    ("colours", "mono"): "Noir et blanc",
    ("colours", "sepia"): "Vieille photo",
    ("colours", "gold"): "Or et argent",
    ("colours", "icyblue"): "Bleus glacés",
    ("colours", "sunset"): "Orangés du soir",
    ("colours", "candypink"): "Rose bonbon",
    ("colours", "forestgreen"): "Verts de forêt",
    ("colours", "goldpurple"): "Or et violet",
    ("colours", "monored"): "Nuances de rouge",
    ("colours", "blueyellow"): "Bleu et jaune",
    ("colours", "jewel"): "Couleurs de bijoux",
    ("colours", "autumn"): "Couleurs d'automne",
    ("colours", "spring"): "Couleurs de printemps",
    ("colours", "christmas"): "Couleurs de Noël",
    ("colours", "halloween"): "Couleurs d'Halloween",

    ("seenfrom", "closeup"): "De tout près",
    ("seenfrom", "far"): "De loin",
    ("seenfrom", "above"): "D'en haut",
    ("seenfrom", "below"): "D'en bas",
    ("seenfrom", "side"): "De côté",
    ("seenfrom", "behind"): "De derrière",
    ("seenfrom", "eye"): "À hauteur des yeux",

    ("camera", "slowzoom"): "Zoom lent",
    ("camera", "pullback"): "Recul",
    ("camera", "pan"): "Panoramique lent",
    ("camera", "orbit"): "Tour autour",
    ("camera", "follow"): "Qui suit",
    ("camera", "closeup"): "Gros plan",
    ("camera", "wide"): "Plan large",
    ("camera", "drone"): "Vue d'en haut",
    ("camera", "still"): "Sans bouger",
    ("camera", "tiltup"): "Vers le haut",
    ("camera", "flyover"): "Survol",
    ("camera", "timelapse"): "Accéléré",

    ("music", "ukulele"): "Ukulélé joyeux",
    ("music", "piano"): "Piano tout doux",
    ("music", "orchestra"): "Grand et épique",
    ("music", "chiptune"): "Jeu vidéo",
    ("music", "jazz"): "Jazzy",
    ("music", "dreamy"): "Rêveuse",
    ("music", "marching"): "Fanfare",
    ("music", "spooky"): "Mystérieuse",
    ("music", "rock"): "Rock entraînant",
    ("music", "lullaby"): "Berceuse",
    ("music", "circus"): "Cirque",
    ("music", "none"): "Aucune",

    ("sounds", "none"): "Aucun",
    ("sounds", "birds"): "Oiseaux et vent",
    ("sounds", "waves"): "Vagues de l'océan",
    ("sounds", "rain"): "Pluie",
    ("sounds", "forest"): "Forêt",
    ("sounds", "city"): "Ville animée",
    ("sounds", "fire"): "Feu qui crépite",
    ("sounds", "crowd"): "Foule qui applaudit",
    ("sounds", "kitchen"): "Bruits de cuisine",
    ("sounds", "space"): "Bourdonnement profond",
    ("sounds", "quiet"): "Silence",
    ("sounds", "thunder"): "Tonnerre au loin",
    ("sounds", "playground"): "Cour de récré",
    ("sounds", "splash"): "Éclaboussures",

    ("genre", "pop"): "Pop",

    # --- what kind of sound: a song, a little tune, a background
    #     hum. One card and one model; see app/music.py KINDS.
    ("kind", "song"): "Une chanson",
    ("kind", "jingle"): "Un petit air",
    ("kind", "ambience"): "Une ambiance",
    ("genre", "rock"): "Rock",
    ("genre", "dance"): "Dance",
    ("genre", "hiphop"): "Hip-hop",
    ("genre", "folk"): "Folk",
    ("genre", "orchestra"): "Orchestre",
    ("genre", "jazz"): "Jazz",
    ("genre", "lullaby"): "Berceuse",
    ("genre", "marching"): "Fanfare",
    ("genre", "chiptune"): "Jeu vidéo",
    ("genre", "country"): "Country",
    ("genre", "reggae"): "Reggae",

    ("mood", "happy"): "Joyeuse",
    ("mood", "exciting"): "Palpitante",
    ("mood", "spooky"): "Frissonnante",
    ("mood", "calm"): "Calme",
    ("mood", "sad"): "Songeuse",

    ("instrument", "piano"): "Piano",
    ("instrument", "guitar"): "Guitare",
    ("instrument", "drums"): "Batterie",
    ("instrument", "violin"): "Violon",
    ("instrument", "flute"): "Flûte",
    ("instrument", "synth"): "Synthé",
    ("instrument", "ukulele"): "Ukulélé",
    ("instrument", "trumpet"): "Trompette",
    ("instrument", "steeldrum"): "Steel drums",
    ("instrument", "harp"): "Harpe",

    ("language", "en"): "English",
    ("language", "fr"): "Français",

    ("voice", "girl"): "Une fille",
    ("voice", "boy"): "Un garçon",
    ("voice", "woman"): "Une femme",
    ("voice", "man"): "Un homme",
    ("voice", "choir"): "Toute une chorale",
    ("voice", "robot"): "Un robot",

    ("singers", "duet"): "Deux à tour de rôle",
    ("singers", "group"): "Un groupe se joint",
    ("singers", "everyone"): "Tous ensemble",
    ("singers", "call"): "Question-réponse",

    # "Turn it into..." - the chips in the viewer
    ("restyle", "cartoon"): "🖍️ Un dessin animé",
    ("restyle", "painting"): "🎨 Une peinture",
    ("restyle", "pencil"): "✏️ Un dessin au crayon",
    ("restyle", "comic"): "💥 Une BD",
    ("restyle", "clay"): "🧸 De la pâte à modeler",
    ("restyle", "bricks"): "🧱 Des briques",
    ("restyle", "glass"): "🪟 Un vitrail",
    ("restyle", "real"): "📷 Pour de vrai",

    # Their colour schemes
    ("theme", "midnight"): "Minuit",
    ("theme", "bubblegum"): "Chewing-gum",
    ("theme", "ocean"): "Océan",
    ("theme", "forest"): "Forêt",
    ("theme", "sunset"): "Coucher de soleil",
    ("theme", "daylight"): "Grand jour",

    # The sound effects sheet
    ("sound", "boing"): "Boing",
    ("sound", "pop"): "Pop",
    ("sound", "ding"): "Ding !",
    ("sound", "sparkle"): "Paillettes",
    ("sound", "whoosh"): "Whoosh",
    ("sound", "splash"): "Plouf",
    ("sound", "drum"): "Tambour",
    ("sound", "zap"): "Zap",
    ("sound", "honk"): "Pouet",
    ("sound", "fanfare"): "Ta-daa !",
    ("sound", "cheer"): "Bravos",
    ("sound", "thud"): "Boum",

    # The thirty-one styles added after the French work was done, which
    # had been showing their English labels ever since. Appended rather
    # than folded into the list above, so that list is still the one
    # that was written and checked at the time.
    ("style", "chalk"): "Dessin à la craie",
    ("style", "crayon"): "Dessin aux crayons",
    ("style", "charcoal"): "Dessin au fusain",
    ("style", "inkwash"): "Encre et lavis",
    ("style", "stainedglass"): "Vitrail",
    ("style", "woodcut"): "Gravure sur bois",
    ("style", "popart"): "Pop art",
    ("style", "ukiyoe"): "Estampe japonaise",
    ("style", "graffiti"): "Graffiti",
    ("style", "bricks"): "Briques de jeu",
    ("style", "felt"): "Feutrine",
    ("style", "knitted"): "Laine tricotée",
    ("style", "origami"): "Origami",
    ("style", "sand"): "Sculpture de sable",
    ("style", "balloon"): "Ballon sculpté",
    ("style", "gingerbread"): "Pain d'épices",
    ("style", "retrogame"): "Vieux jeu vidéo",
    ("style", "stopmotion"): "Stop-motion",
    ("style", "cartoon80s"): "Dessin animé 80",
    ("style", "sticker"): "Autocollant",
    ("style", "emoji"): "Émoji",
    ("style", "lowpoly"): "3D à facettes",
    ("style", "vectorflat"): "Vectoriel à plat",
    ("style", "vintagephoto"): "Photo d'autrefois",
    ("style", "polaroid"): "Polaroïd",
    ("style", "macro"): "Gros plan macro",
    ("style", "bwfilm"): "Film noir et blanc",
    ("style", "coloringpage"): "Coloriage",
    ("style", "doodle"): "Gribouillage",
    ("style", "blueprint"): "Plan d'architecte",
    ("style", "treasuremap"): "Carte au trésor",
}

# German.
CHOICES_DE: dict[tuple[str, str], str] = {
    ("style", "cartoon"): "Zeichentrick",
    ("style", "anime"): "Anime",
    ("style", "pixar"): "3D-Film",
    ("style", "storybook"): "Bilderbuch",
    ("style", "watercolour"): "Aquarell",
    ("style", "oil"): "Ölgemälde",
    ("style", "sketch"): "Bleistiftskizze",
    ("style", "pixel"): "Pixel-Art",
    ("style", "comic"): "Comic",
    ("style", "clay"): "Knetfiguren",
    ("style", "papercraft"): "Papierbasteln",
    ("style", "photo"): "Foto",
    ("style", "chalk"): "Kreidebild",
    ("style", "crayon"): "Wachsmalstift",
    ("style", "charcoal"): "Kohlezeichnung",
    ("style", "inkwash"): "Tuschezeichnung",
    ("style", "stainedglass"): "Kirchenfenster",
    ("style", "woodcut"): "Holzschnitt",
    ("style", "popart"): "Pop-Art",
    ("style", "ukiyoe"): "Japanischer Druck",
    ("style", "graffiti"): "Graffiti",
    ("style", "bricks"): "Bausteine",
    ("style", "felt"): "Filz",
    ("style", "knitted"): "Gestrickt",
    ("style", "origami"): "Origami",
    ("style", "sand"): "Sandskulptur",
    ("style", "balloon"): "Luftballontier",
    ("style", "gingerbread"): "Lebkuchen",
    ("style", "retrogame"): "Retro-Videospiel",
    ("style", "stopmotion"): "Stop-Motion",
    ("style", "cartoon80s"): "80er-Zeichentrick",
    ("style", "sticker"): "Sticker",
    ("style", "emoji"): "Emoji",
    ("style", "lowpoly"): "Low-Poly-3D",
    ("style", "vectorflat"): "Vektorgrafik",
    ("style", "vintagephoto"): "Altes Foto",
    ("style", "polaroid"): "Polaroid",
    ("style", "macro"): "Makro-Nahaufnahme",
    ("style", "bwfilm"): "Schwarz-Weiß-Film",
    ("style", "coloringpage"): "Ausmalbild",
    ("style", "doodle"): "Gekritzel",
    ("style", "blueprint"): "Bauplan",
    ("style", "treasuremap"): "Schatzkarte",

    ("scene", "forest"): "Wald",
    ("scene", "beach"): "Strand",
    ("scene", "city"): "Stadt",
    ("scene", "farm"): "Bauernhof",
    ("scene", "mountains"): "Berge",
    ("scene", "mountaintop"): "Berggipfel",
    ("scene", "snow"): "Schnee",
    ("scene", "desert"): "Wüste",
    ("scene", "oasis"): "Oase",
    ("scene", "jungle"): "Dschungel",
    ("scene", "jungletemple"): "Tempel im Dschungel",
    ("scene", "savannah"): "Savanne",
    ("scene", "rainstreet"): "Straße im Regen",
    ("scene", "market"): "Voller Markt",
    ("scene", "lighthouse"): "Leuchtturm",
    ("scene", "treehouse"): "Baumhaus",
    ("scene", "playground"): "Spielplatz",
    ("scene", "library"): "Bücherei",
    ("scene", "volcano"): "Im Vulkan",
    ("scene", "arctic"): "Arktis",
    ("scene", "waterfall"): "Wasserfall",
    ("scene", "space"): "Weltall",
    ("scene", "moon"): "Auf dem Mond",
    ("scene", "underwater"): "Unter Wasser",
    ("scene", "castle"): "Schloss",
    ("scene", "candyland"): "Bonbonland",
    ("scene", "clouds"): "In den Wolken",
    ("scene", "cloudcastle"): "Wolkenschloss",
    ("scene", "floatingisland"): "Schwebende Insel",
    ("scene", "snowglobe"): "In einer Schneekugel",
    ("scene", "giantskitchen"): "Riesenküche",
    ("scene", "robotcity"): "Roboterstadt",
    ("scene", "dragoncave"): "Drachenhöhle",
    ("scene", "dinosaurvalley"): "Dinotal",
    ("scene", "bedroom"): "Gemütliches Zimmer",
    ("scene", "kitchentable"): "Küchentisch",
    ("scene", "gardenshed"): "Gartenhaus",
    ("scene", "backseat"): "Autofahrt",
    ("scene", "backyard"): "Garten",

    ("lighting", "sunny"): "Sonniger Tag",
    ("lighting", "sunset"): "Goldene Abendsonne",
    ("lighting", "moonlight"): "Mondlicht",
    ("lighting", "candle"): "Kerzenlicht",
    ("lighting", "neon"): "Neonlicht",
    ("lighting", "rainbow"): "Regenbogenlicht",
    ("lighting", "misty"): "Nebliger Morgen",
    ("lighting", "stars"): "Sternennacht",
    ("lighting", "fire"): "Feuerschein",

    ("mood", "cosy"): "Gemütlich",
    ("mood", "magical"): "Magisch",
    ("mood", "silly"): "Albern",
    ("mood", "epic"): "Episch",
    ("mood", "peaceful"): "Friedlich",
    ("mood", "adventure"): "Abenteuerlich",
    ("mood", "dreamy"): "Verträumt",
    ("mood", "mysterious"): "Geheimnisvoll",
    ("mood", "brave"): "Mutig",
    ("mood", "sleepy"): "Schläfrig",
    ("mood", "proud"): "Stolz",
    ("mood", "nervous"): "Nervös",
    ("mood", "giggly"): "Kicherig",
    ("mood", "dramatic"): "Dramatisch",
    ("mood", "spookyfun"): "Gruselig-lustig",
    ("mood", "lonely"): "Einsam",
    ("mood", "triumphant"): "Triumphierend",
    ("mood", "curious"): "Neugierig",
    ("mood", "grumpy"): "Grummelig",
    ("mood", "wild"): "Wild",
    ("mood", "excited"): "Ganz aufgeregt",
    ("mood", "shy"): "Schüchtern",
    ("mood", "confident"): "Selbstsicher",
    ("mood", "sneaky"): "Heimlich",
    ("mood", "hopeful"): "Hoffnungsvoll",
    ("mood", "determined"): "Entschlossen",
    ("mood", "surprised"): "Überrascht",
    ("mood", "mischievous"): "Frech",
    ("mood", "happy"): "Fröhlich",
    ("mood", "exciting"): "Spannend",
    ("mood", "spooky"): "Gruselig",
    ("mood", "calm"): "Ruhig",
    ("mood", "sad"): "Nachdenklich",

    ("colours", "bright"): "Kräftig und bunt",
    ("colours", "pastel"): "Sanfte Pastelltöne",
    ("colours", "rainbow"): "Regenbogen",
    ("colours", "warm"): "Warm",
    ("colours", "cool"): "Kühl",
    ("colours", "neon"): "Neon",
    ("colours", "earthy"): "Erdtöne",
    ("colours", "mono"): "Schwarz-Weiß",
    ("colours", "sepia"): "Altes Foto",
    ("colours", "gold"): "Gold und Silber",
    ("colours", "icyblue"): "Eisblau",
    ("colours", "sunset"): "Abendorange",
    ("colours", "candypink"): "Bonbonrosa",
    ("colours", "forestgreen"): "Waldgrün",
    ("colours", "goldpurple"): "Gold und Lila",
    ("colours", "monored"): "Rottöne",
    ("colours", "blueyellow"): "Nur Blau und Gelb",
    ("colours", "jewel"): "Edelsteinfarben",
    ("colours", "autumn"): "Herbstfarben",
    ("colours", "spring"): "Frühlingsfarben",
    ("colours", "christmas"): "Weihnachtsfarben",
    ("colours", "halloween"): "Halloween-Farben",

    ("seenfrom", "closeup"): "Ganz nah",
    ("seenfrom", "far"): "Von weit weg",
    ("seenfrom", "above"): "Von oben",
    ("seenfrom", "below"): "Von unten",
    ("seenfrom", "side"): "Von der Seite",
    ("seenfrom", "behind"): "Von hinten",
    ("seenfrom", "eye"): "Auf Augenhöhe",

    ("camera", "slowzoom"): "Langsam ranzoomen",
    ("camera", "pullback"): "Zurückfahren",
    ("camera", "pan"): "Langsam schwenken",
    ("camera", "orbit"): "Drumherum",
    ("camera", "follow"): "Hinterher",
    ("camera", "closeup"): "Nahaufnahme",
    ("camera", "wide"): "Weite Einstellung",
    ("camera", "drone"): "Von oben",
    ("camera", "still"): "Ganz still",
    ("camera", "tiltup"): "Nach oben",
    ("camera", "flyover"): "Drüberfliegen",
    ("camera", "timelapse"): "Im Zeitraffer",

    ("music", "ukulele"): "Fröhliche Ukulele",
    ("music", "piano"): "Sanftes Klavier",
    ("music", "orchestra"): "Groß und episch",
    ("music", "chiptune"): "Videospiel",
    ("music", "jazz"): "Jazzig",
    ("music", "dreamy"): "Verträumt",
    ("music", "marching"): "Blaskapelle",
    ("music", "spooky"): "Geheimnisvoll",
    ("music", "rock"): "Flotter Rock",
    ("music", "lullaby"): "Schlaflied",
    ("music", "circus"): "Zirkus",
    ("music", "none"): "Keine",

    ("sounds", "none"): "Keine",
    ("sounds", "birds"): "Vögel und Wind",
    ("sounds", "waves"): "Meereswellen",
    ("sounds", "rain"): "Regen",
    ("sounds", "forest"): "Wald",
    ("sounds", "city"): "Belebte Stadt",
    ("sounds", "fire"): "Knisterndes Feuer",
    ("sounds", "crowd"): "Jubelnde Menge",
    ("sounds", "kitchen"): "Küchengeklapper",
    ("sounds", "space"): "Tiefes Brummen",
    ("sounds", "quiet"): "Stille",
    ("sounds", "thunder"): "Ferner Donner",
    ("sounds", "playground"): "Schulhof",
    ("sounds", "splash"): "Wasserplatschen",

    ("genre", "pop"): "Pop",

    # --- what kind of sound: a song, a little tune, a background
    #     hum. One card and one model; see app/music.py KINDS.
    ("kind", "song"): "Ein Lied",
    ("kind", "jingle"): "Eine Melodie",
    ("kind", "ambience"): "Ein Hintergrundklang",
    ("genre", "rock"): "Rock",
    ("genre", "dance"): "Dance",
    ("genre", "hiphop"): "Hip-Hop",
    ("genre", "folk"): "Folk",
    ("genre", "orchestra"): "Orchester",
    ("genre", "jazz"): "Jazz",
    ("genre", "lullaby"): "Schlaflied",
    ("genre", "marching"): "Blaskapelle",
    ("genre", "chiptune"): "Videospiel",
    ("genre", "country"): "Country",
    ("genre", "reggae"): "Reggae",

    ("instrument", "piano"): "Klavier",
    ("instrument", "guitar"): "Gitarre",
    ("instrument", "drums"): "Schlagzeug",
    ("instrument", "violin"): "Geige",
    ("instrument", "flute"): "Flöte",
    ("instrument", "synth"): "Synth",
    ("instrument", "ukulele"): "Ukulele",
    ("instrument", "trumpet"): "Trompete",
    ("instrument", "steeldrum"): "Steeldrums",
    ("instrument", "harp"): "Harfe",

    ("voice", "girl"): "Ein Mädchen",
    ("voice", "boy"): "Ein Junge",
    ("voice", "woman"): "Eine Frau",
    ("voice", "man"): "Ein Mann",
    ("voice", "choir"): "Ein ganzer Chor",
    ("voice", "robot"): "Ein Roboter",

    ("singers", "duet"): "Zwei im Wechsel",
    ("singers", "group"): "Eine Gruppe dazu",
    ("singers", "everyone"): "Alle zusammen",
    ("singers", "call"): "Ruf und Antwort",

    ("language", "en"): "English",
    ("language", "fr"): "Français",

    ("sound", "boing"): "Boing",
    ("sound", "pop"): "Plopp",
    ("sound", "ding"): "Ding!",
    ("sound", "sparkle"): "Glitzern",
    ("sound", "whoosh"): "Wusch",
    ("sound", "splash"): "Platsch",
    ("sound", "drum"): "Trommel",
    ("sound", "zap"): "Zap",
    ("sound", "honk"): "Tut",
    ("sound", "fanfare"): "Ta-daa!",
    ("sound", "cheer"): "Jubel",
    ("sound", "thud"): "Bumm",

    ("theme", "midnight"): "Mitternacht",
    ("theme", "bubblegum"): "Kaugummi",
    ("theme", "ocean"): "Ozean",
    ("theme", "forest"): "Wald",
    ("theme", "sunset"): "Sonnenuntergang",
    ("theme", "daylight"): "Heller Tag",

    ("restyle", "cartoon"): "🖍️ Zeichentrick",
    ("restyle", "painting"): "🎨 Gemälde",
    ("restyle", "pencil"): "✏️ Bleistiftzeichnung",
    ("restyle", "comic"): "💥 Comic",
    ("restyle", "clay"): "🧸 Knetfigur",
    ("restyle", "bricks"): "🧱 Bausteine",
    ("restyle", "glass"): "🪟 Kirchenfenster",
    ("restyle", "real"): "📷 Echt machen",
}

# Spanish.
CHOICES_ES: dict[tuple[str, str], str] = {
    ("style", "cartoon"): "Dibujos animados",
    ("style", "anime"): "Anime",
    ("style", "pixar"): "Película 3D",
    ("style", "storybook"): "Cuento ilustrado",
    ("style", "watercolour"): "Acuarela",
    ("style", "oil"): "Óleo",
    ("style", "sketch"): "Boceto a lápiz",
    ("style", "pixel"): "Pixel art",
    ("style", "comic"): "Cómic",
    ("style", "clay"): "Plastilina",
    ("style", "papercraft"): "Papel recortado",
    ("style", "photo"): "Fotografía",
    ("style", "chalk"): "Dibujo con tiza",
    ("style", "crayon"): "Dibujo con ceras",
    ("style", "charcoal"): "Dibujo a carboncillo",
    ("style", "inkwash"): "Tinta y aguada",
    ("style", "stainedglass"): "Vidriera",
    ("style", "woodcut"): "Grabado en madera",
    ("style", "popart"): "Pop art",
    ("style", "ukiyoe"): "Grabado japonés",
    ("style", "graffiti"): "Grafiti",
    ("style", "bricks"): "Bloques de juguete",
    ("style", "felt"): "Fieltro",
    ("style", "knitted"): "Lana tejida",
    ("style", "origami"): "Origami",
    ("style", "sand"): "Escultura de arena",
    ("style", "balloon"): "Figura de globos",
    ("style", "gingerbread"): "Galleta de jengibre",
    ("style", "retrogame"): "Videojuego antiguo",
    ("style", "stopmotion"): "Stop-motion",
    ("style", "cartoon80s"): "Dibujos de los 80",
    ("style", "sticker"): "Pegatina",
    ("style", "emoji"): "Emoji",
    ("style", "lowpoly"): "3D low-poly",
    ("style", "vectorflat"): "Vector plano",
    ("style", "vintagephoto"): "Foto antigua",
    ("style", "polaroid"): "Polaroid",
    ("style", "macro"): "Macro de cerca",
    ("style", "bwfilm"): "Película en blanco y negro",
    ("style", "coloringpage"): "Para colorear",
    ("style", "doodle"): "Garabato",
    ("style", "blueprint"): "Plano técnico",
    ("style", "treasuremap"): "Mapa del tesoro",

    ("scene", "forest"): "Bosque",
    ("scene", "beach"): "Playa",
    ("scene", "city"): "Ciudad",
    ("scene", "farm"): "Granja",
    ("scene", "mountains"): "Montañas",
    ("scene", "mountaintop"): "Cima de una montaña",
    ("scene", "snow"): "Nevado",
    ("scene", "desert"): "Desierto",
    ("scene", "oasis"): "Oasis en el desierto",
    ("scene", "jungle"): "Selva",
    ("scene", "jungletemple"): "Templo en la selva",
    ("scene", "savannah"): "Sabana",
    ("scene", "rainstreet"): "Calle con lluvia",
    ("scene", "market"): "Mercado con gente",
    ("scene", "lighthouse"): "Faro",
    ("scene", "treehouse"): "Casa en un árbol",
    ("scene", "playground"): "Parque infantil",
    ("scene", "library"): "Biblioteca",
    ("scene", "volcano"): "Dentro de un volcán",
    ("scene", "arctic"): "El Ártico",
    ("scene", "waterfall"): "Cascada",
    ("scene", "space"): "El espacio",
    ("scene", "moon"): "En la luna",
    ("scene", "underwater"): "Bajo el agua",
    ("scene", "castle"): "Castillo",
    ("scene", "candyland"): "País de los caramelos",
    ("scene", "clouds"): "Entre las nubes",
    ("scene", "cloudcastle"): "Castillo de nubes",
    ("scene", "floatingisland"): "Isla flotante",
    ("scene", "snowglobe"): "Dentro de una bola de nieve",
    ("scene", "giantskitchen"): "Cocina de un gigante",
    ("scene", "robotcity"): "Ciudad de robots",
    ("scene", "dragoncave"): "Cueva del dragón",
    ("scene", "dinosaurvalley"): "Valle de dinosaurios",
    ("scene", "bedroom"): "Habitación acogedora",
    ("scene", "kitchentable"): "Mesa de la cocina",
    ("scene", "gardenshed"): "Caseta del jardín",
    ("scene", "backseat"): "Viaje en coche",
    ("scene", "backyard"): "Patio de casa",

    ("lighting", "sunny"): "Día de sol",
    ("lighting", "sunset"): "Atardecer dorado",
    ("lighting", "moonlight"): "Luz de luna",
    ("lighting", "candle"): "Luz de vela",
    ("lighting", "neon"): "Brillo de neón",
    ("lighting", "rainbow"): "Luz de arcoíris",
    ("lighting", "misty"): "Mañana con niebla",
    ("lighting", "stars"): "Noche estrellada",
    ("lighting", "fire"): "Luz de fuego",

    ("mood", "cosy"): "Acogedor",
    ("mood", "magical"): "Mágico",
    ("mood", "silly"): "Gracioso",
    ("mood", "epic"): "Épico",
    ("mood", "peaceful"): "Tranquilo",
    ("mood", "adventure"): "Aventurero",
    ("mood", "dreamy"): "Soñador",
    ("mood", "mysterious"): "Misterioso",
    ("mood", "brave"): "Valiente",
    ("mood", "sleepy"): "Adormilado",
    ("mood", "proud"): "Orgulloso",
    ("mood", "nervous"): "Nervioso",
    ("mood", "giggly"): "Risueño",
    ("mood", "dramatic"): "Dramático",
    ("mood", "spookyfun"): "Terror divertido",
    ("mood", "lonely"): "Solitario",
    ("mood", "triumphant"): "Triunfal",
    ("mood", "curious"): "Curioso",
    ("mood", "grumpy"): "Gruñón",
    ("mood", "wild"): "Salvaje",
    ("mood", "excited"): "Emocionado",
    ("mood", "shy"): "Tímido",
    ("mood", "confident"): "Seguro de sí",
    ("mood", "sneaky"): "Astuto",
    ("mood", "hopeful"): "Esperanzado",
    ("mood", "determined"): "Decidido",
    ("mood", "surprised"): "Sorprendido",
    ("mood", "mischievous"): "Travieso",
    ("mood", "happy"): "Alegre",
    ("mood", "exciting"): "Emocionante",
    ("mood", "spooky"): "De miedo",
    ("mood", "calm"): "Tranquila",
    ("mood", "sad"): "Pensativa",

    ("colours", "bright"): "Vivos y fuertes",
    ("colours", "pastel"): "Pasteles suaves",
    ("colours", "rainbow"): "Arcoíris",
    ("colours", "warm"): "Cálidos",
    ("colours", "cool"): "Fríos",
    ("colours", "neon"): "Neón",
    ("colours", "earthy"): "Tonos tierra",
    ("colours", "mono"): "Blanco y negro",
    ("colours", "sepia"): "Foto antigua",
    ("colours", "gold"): "Oro y plata",
    ("colours", "icyblue"): "Azules de hielo",
    ("colours", "sunset"): "Naranjas de atardecer",
    ("colours", "candypink"): "Rosa chicle",
    ("colours", "forestgreen"): "Verdes de bosque",
    ("colours", "goldpurple"): "Oro y morado",
    ("colours", "monored"): "Tonos de rojo",
    ("colours", "blueyellow"): "Solo azul y amarillo",
    ("colours", "jewel"): "Tonos joya",
    ("colours", "autumn"): "Colores de otoño",
    ("colours", "spring"): "Colores de primavera",
    ("colours", "christmas"): "Colores de Navidad",
    ("colours", "halloween"): "Colores de Halloween",

    ("seenfrom", "closeup"): "De cerca",
    ("seenfrom", "far"): "De lejos",
    ("seenfrom", "above"): "Desde arriba",
    ("seenfrom", "below"): "Desde abajo",
    ("seenfrom", "side"): "De lado",
    ("seenfrom", "behind"): "Por detrás",
    ("seenfrom", "eye"): "A la altura de los ojos",

    ("camera", "slowzoom"): "Zoom lento",
    ("camera", "pullback"): "Alejarse",
    ("camera", "pan"): "Barrido lento",
    ("camera", "orbit"): "Dar vueltas alrededor",
    ("camera", "follow"): "Ir siguiéndolo",
    ("camera", "closeup"): "De cerca",
    ("camera", "wide"): "Plano abierto",
    ("camera", "drone"): "Desde arriba",
    ("camera", "still"): "Sin moverse",
    ("camera", "tiltup"): "Mirar hacia arriba",
    ("camera", "flyover"): "Pasar volando",
    ("camera", "timelapse"): "Acelerado",

    ("music", "ukulele"): "Ukelele alegre",
    ("music", "piano"): "Piano suave",
    ("music", "orchestra"): "Grande y épica",
    ("music", "chiptune"): "Videojuego",
    ("music", "jazz"): "Con jazz",
    ("music", "dreamy"): "Soñadora",
    ("music", "marching"): "Banda de música",
    ("music", "spooky"): "Misteriosa",
    ("music", "rock"): "Rock animado",
    ("music", "lullaby"): "Nana",
    ("music", "circus"): "Circo",
    ("music", "none"): "Sin música",

    ("sounds", "none"): "Sin sonido",
    ("sounds", "birds"): "Pájaros y viento",
    ("sounds", "waves"): "Olas del mar",
    ("sounds", "rain"): "Lluvia",
    ("sounds", "forest"): "Bosque",
    ("sounds", "city"): "Ciudad con ruido",
    ("sounds", "fire"): "Fuego crepitando",
    ("sounds", "crowd"): "Gente aplaudiendo",
    ("sounds", "kitchen"): "Ruido de cocina",
    ("sounds", "space"): "Zumbido grave",
    ("sounds", "quiet"): "Silencio",
    ("sounds", "thunder"): "Truenos a lo lejos",
    ("sounds", "playground"): "Parque infantil",
    ("sounds", "splash"): "Chapoteo de agua",

    ("genre", "pop"): "Pop",

    # --- what kind of sound: a song, a little tune, a background
    #     hum. One card and one model; see app/music.py KINDS.
    ("kind", "song"): "Una canción",
    ("kind", "jingle"): "Una melodía",
    ("kind", "ambience"): "Un sonido de fondo",
    ("genre", "rock"): "Rock",
    ("genre", "dance"): "Dance",
    ("genre", "hiphop"): "Hip hop",
    ("genre", "folk"): "Folk",
    ("genre", "orchestra"): "Orquesta",
    ("genre", "jazz"): "Jazz",
    ("genre", "lullaby"): "Nana",
    ("genre", "marching"): "Banda de música",
    ("genre", "chiptune"): "Videojuego",
    ("genre", "country"): "Country",
    ("genre", "reggae"): "Reggae",

    ("instrument", "piano"): "Piano",
    ("instrument", "guitar"): "Guitarra",
    ("instrument", "drums"): "Batería",
    ("instrument", "violin"): "Violín",
    ("instrument", "flute"): "Flauta",
    ("instrument", "synth"): "Sintetizador",
    ("instrument", "ukulele"): "Ukelele",
    ("instrument", "trumpet"): "Trompeta",
    ("instrument", "steeldrum"): "Tambores metálicos",
    ("instrument", "harp"): "Arpa",

    ("voice", "girl"): "Una niña",
    ("voice", "boy"): "Un niño",
    ("voice", "woman"): "Una mujer",
    ("voice", "man"): "Un hombre",
    ("voice", "choir"): "Un coro entero",
    ("voice", "robot"): "Un robot",

    ("singers", "duet"): "Dos por turnos",
    ("singers", "group"): "Un grupo se une",
    ("singers", "everyone"): "Todos juntos",
    ("singers", "call"): "Pregunta y respuesta",

    ("language", "en"): "English",
    ("language", "fr"): "Français",

    ("sound", "boing"): "Boing",
    ("sound", "pop"): "Pop",
    ("sound", "ding"): "¡Ding!",
    ("sound", "sparkle"): "Chispas",
    ("sound", "whoosh"): "Fiu",
    ("sound", "splash"): "Chof",
    ("sound", "drum"): "Tambor",
    ("sound", "zap"): "Zas",
    ("sound", "honk"): "Bocina",
    ("sound", "fanfare"): "¡Ta-chán!",
    ("sound", "cheer"): "Aplausos",
    ("sound", "thud"): "Pum",

    ("theme", "midnight"): "Medianoche",
    ("theme", "bubblegum"): "Chicle",
    ("theme", "ocean"): "Océano",
    ("theme", "forest"): "Bosque",
    ("theme", "sunset"): "Atardecer",
    ("theme", "daylight"): "Luz de día",

    ("restyle", "cartoon"): "🖍️ Un dibujo animado",
    ("restyle", "painting"): "🎨 Un cuadro",
    ("restyle", "pencil"): "✏️ Un dibujo a lápiz",
    ("restyle", "comic"): "💥 Un cómic",
    ("restyle", "clay"): "🧸 Una figura de plastilina",
    ("restyle", "bricks"): "🧱 Bloques de juguete",
    ("restyle", "glass"): "🪟 Una vidriera",
    ("restyle", "real"): "📷 Hazla real",
}

# Italian.
CHOICES_IT: dict[tuple[str, str], str] = {
    ("style", "cartoon"): "Cartone animato",
    ("style", "anime"): "Anime",
    ("style", "pixar"): "Film in 3D",
    ("style", "storybook"): "Libro illustrato",
    ("style", "watercolour"): "Acquerello",
    ("style", "oil"): "Pittura a olio",
    ("style", "sketch"): "Schizzo a matita",
    ("style", "pixel"): "Pixel art",
    ("style", "comic"): "Fumetto",
    ("style", "clay"): "Plastilina",
    ("style", "papercraft"): "Carta ritagliata",
    ("style", "photo"): "Fotografia",
    ("style", "chalk"): "Disegno col gesso",
    ("style", "crayon"): "Disegno a pastelli",
    ("style", "charcoal"): "Disegno a carboncino",
    ("style", "inkwash"): "Inchiostro e acquerello",
    ("style", "stainedglass"): "Vetrata colorata",
    ("style", "woodcut"): "Stampa su legno",
    ("style", "popart"): "Pop art",
    ("style", "ukiyoe"): "Stampa giapponese",
    ("style", "graffiti"): "Graffiti",
    ("style", "bricks"): "Mattoncini",
    ("style", "felt"): "Feltro",
    ("style", "knitted"): "Lana a maglia",
    ("style", "origami"): "Origami",
    ("style", "sand"): "Scultura di sabbia",
    ("style", "balloon"): "Palloncino modellato",
    ("style", "gingerbread"): "Pan di zenzero",
    ("style", "retrogame"): "Videogioco retrò",
    ("style", "stopmotion"): "Stop-motion",
    ("style", "cartoon80s"): "Cartone anni '80",
    ("style", "sticker"): "Adesivo",
    ("style", "emoji"): "Emoji",
    ("style", "lowpoly"): "3D low-poly",
    ("style", "vectorflat"): "Vettoriale piatto",
    ("style", "vintagephoto"): "Foto d'epoca",
    ("style", "polaroid"): "Polaroid",
    ("style", "macro"): "Macro ravvicinata",
    ("style", "bwfilm"): "Film in bianco e nero",
    ("style", "coloringpage"): "Da colorare",
    ("style", "doodle"): "Scarabocchio",
    ("style", "blueprint"): "Disegno tecnico",
    ("style", "treasuremap"): "Mappa del tesoro",

    ("scene", "forest"): "Foresta",
    ("scene", "beach"): "Spiaggia",
    ("scene", "city"): "Città",
    ("scene", "farm"): "Fattoria",
    ("scene", "mountains"): "Montagne",
    ("scene", "mountaintop"): "Cima della montagna",
    ("scene", "snow"): "Sulla neve",
    ("scene", "desert"): "Deserto",
    ("scene", "oasis"): "Oasi nel deserto",
    ("scene", "jungle"): "Giungla",
    ("scene", "jungletemple"): "Tempio nella giungla",
    ("scene", "savannah"): "Savana",
    ("scene", "rainstreet"): "Strada sotto la pioggia",
    ("scene", "market"): "Mercato affollato",
    ("scene", "lighthouse"): "Faro",
    ("scene", "treehouse"): "Casa sull'albero",
    ("scene", "playground"): "Parco giochi",
    ("scene", "library"): "Biblioteca",
    ("scene", "volcano"): "Dentro un vulcano",
    ("scene", "arctic"): "L'Artide",
    ("scene", "waterfall"): "Cascata",
    ("scene", "space"): "Spazio",
    ("scene", "moon"): "Sulla Luna",
    ("scene", "underwater"): "Sott'acqua",
    ("scene", "castle"): "Castello",
    ("scene", "candyland"): "Paese dei dolci",
    ("scene", "clouds"): "Tra le nuvole",
    ("scene", "cloudcastle"): "Castello di nuvole",
    ("scene", "floatingisland"): "Isola volante",
    ("scene", "snowglobe"): "Dentro una palla di neve",
    ("scene", "giantskitchen"): "Cucina del gigante",
    ("scene", "robotcity"): "Città dei robot",
    ("scene", "dragoncave"): "Grotta del drago",
    ("scene", "dinosaurvalley"): "Valle dei dinosauri",
    ("scene", "bedroom"): "Stanza accogliente",
    ("scene", "kitchentable"): "Tavolo di cucina",
    ("scene", "gardenshed"): "Capanno in giardino",
    ("scene", "backseat"): "In macchina",
    ("scene", "backyard"): "In giardino",

    ("lighting", "sunny"): "Giornata di sole",
    ("lighting", "sunset"): "Tramonto dorato",
    ("lighting", "moonlight"): "Chiaro di luna",
    ("lighting", "candle"): "Luce di candela",
    ("lighting", "neon"): "Luce al neon",
    ("lighting", "rainbow"): "Luce arcobaleno",
    ("lighting", "misty"): "Mattina di nebbia",
    ("lighting", "stars"): "Notte stellata",
    ("lighting", "fire"): "Luce del fuoco",

    ("mood", "cosy"): "Accogliente",
    ("mood", "magical"): "Magica",
    ("mood", "silly"): "Buffa",
    ("mood", "epic"): "Epica",
    ("mood", "peaceful"): "Tranquilla",
    ("mood", "adventure"): "Avventurosa",
    ("mood", "dreamy"): "Sognante",
    ("mood", "mysterious"): "Misteriosa",
    ("mood", "brave"): "Coraggiosa",
    ("mood", "sleepy"): "Assonnata",
    ("mood", "proud"): "Orgogliosa",
    ("mood", "nervous"): "Agitata",
    ("mood", "giggly"): "Ridacchiante",
    ("mood", "dramatic"): "Drammatica",
    ("mood", "spookyfun"): "Paura per finta",
    ("mood", "lonely"): "Solitaria",
    ("mood", "triumphant"): "Trionfante",
    ("mood", "curious"): "Curiosa",
    ("mood", "grumpy"): "Burbera",
    ("mood", "wild"): "Scatenata",
    ("mood", "excited"): "Emozionata",
    ("mood", "shy"): "Timida",
    ("mood", "confident"): "Sicura di sé",
    ("mood", "sneaky"): "Furtiva",
    ("mood", "hopeful"): "Piena di speranza",
    ("mood", "determined"): "Determinata",
    ("mood", "surprised"): "Sorpresa",
    ("mood", "mischievous"): "Birichina",
    ("mood", "happy"): "Allegra",
    ("mood", "exciting"): "Emozionante",
    ("mood", "spooky"): "Paurosa",
    ("mood", "calm"): "Calma",
    ("mood", "sad"): "Pensierosa",

    ("colours", "bright"): "Vivaci e decisi",
    ("colours", "pastel"): "Pastelli delicati",
    ("colours", "rainbow"): "Arcobaleno",
    ("colours", "warm"): "Caldi",
    ("colours", "cool"): "Freddi",
    ("colours", "neon"): "Neon",
    ("colours", "earthy"): "Colori della terra",
    ("colours", "mono"): "Bianco e nero",
    ("colours", "sepia"): "Foto vecchia",
    ("colours", "gold"): "Oro e argento",
    ("colours", "icyblue"): "Azzurri ghiacciati",
    ("colours", "sunset"): "Arancioni del tramonto",
    ("colours", "candypink"): "Rosa caramella",
    ("colours", "forestgreen"): "Verdi del bosco",
    ("colours", "goldpurple"): "Oro e viola",
    ("colours", "monored"): "Sfumature di rosso",
    ("colours", "blueyellow"): "Solo blu e giallo",
    ("colours", "jewel"): "Colori gioiello",
    ("colours", "autumn"): "Colori d'autunno",
    ("colours", "spring"): "Colori di primavera",
    ("colours", "christmas"): "Colori di Natale",
    ("colours", "halloween"): "Colori di Halloween",

    ("seenfrom", "closeup"): "Da vicino",
    ("seenfrom", "far"): "Da lontano",
    ("seenfrom", "above"): "Dall'alto",
    ("seenfrom", "below"): "Dal basso",
    ("seenfrom", "side"): "Di lato",
    ("seenfrom", "behind"): "Da dietro",
    ("seenfrom", "eye"): "Altezza occhi",

    ("camera", "slowzoom"): "Zoom lento",
    ("camera", "pullback"): "Si allontana",
    ("camera", "pan"): "Panoramica lenta",
    ("camera", "orbit"): "Gira attorno",
    ("camera", "follow"): "Segue",
    ("camera", "closeup"): "Da vicino",
    ("camera", "wide"): "Campo largo",
    ("camera", "drone"): "Dall'alto",
    ("camera", "still"): "Sta ferma",
    ("camera", "tiltup"): "Guarda in su",
    ("camera", "flyover"): "Vola sopra",
    ("camera", "timelapse"): "Accelera",

    ("music", "ukulele"): "Ukulele allegro",
    ("music", "piano"): "Piano dolce",
    ("music", "orchestra"): "Grande ed epica",
    ("music", "chiptune"): "Videogioco",
    ("music", "jazz"): "Jazz",
    ("music", "dreamy"): "Sognante",
    ("music", "marching"): "Banda",
    ("music", "spooky"): "Misteriosa",
    ("music", "rock"): "Rock allegro",
    ("music", "lullaby"): "Ninna nanna",
    ("music", "circus"): "Circo",
    ("music", "none"): "Niente",

    ("sounds", "none"): "Niente",
    ("sounds", "birds"): "Uccelli e vento",
    ("sounds", "waves"): "Onde del mare",
    ("sounds", "rain"): "Pioggia",
    ("sounds", "forest"): "Foresta",
    ("sounds", "city"): "Città affollata",
    ("sounds", "fire"): "Fuoco che scoppietta",
    ("sounds", "crowd"): "Folla che applaude",
    ("sounds", "kitchen"): "Rumori di cucina",
    ("sounds", "space"): "Ronzio profondo",
    ("sounds", "quiet"): "Silenzio",
    ("sounds", "thunder"): "Tuono lontano",
    ("sounds", "playground"): "Parco giochi",
    ("sounds", "splash"): "Schizzi d'acqua",

    ("genre", "pop"): "Pop",

    # --- what kind of sound: a song, a little tune, a background
    #     hum. One card and one model; see app/music.py KINDS.
    ("kind", "song"): "Una canzone",
    ("kind", "jingle"): "Una melodia",
    ("kind", "ambience"): "Un suono di sottofondo",
    ("genre", "rock"): "Rock",
    ("genre", "dance"): "Dance",
    ("genre", "hiphop"): "Hip hop",
    ("genre", "folk"): "Folk",
    ("genre", "orchestra"): "Orchestra",
    ("genre", "jazz"): "Jazz",
    ("genre", "lullaby"): "Ninna nanna",
    ("genre", "marching"): "Banda",
    ("genre", "chiptune"): "Videogioco",
    ("genre", "country"): "Country",
    ("genre", "reggae"): "Reggae",

    ("instrument", "piano"): "Piano",
    ("instrument", "guitar"): "Chitarra",
    ("instrument", "drums"): "Batteria",
    ("instrument", "violin"): "Violino",
    ("instrument", "flute"): "Flauto",
    ("instrument", "synth"): "Synth",
    ("instrument", "ukulele"): "Ukulele",
    ("instrument", "trumpet"): "Tromba",
    ("instrument", "steeldrum"): "Steel drum",
    ("instrument", "harp"): "Arpa",

    ("voice", "girl"): "Una bambina",
    ("voice", "boy"): "Un bambino",
    ("voice", "woman"): "Una donna",
    ("voice", "man"): "Un uomo",
    ("voice", "choir"): "Un coro intero",
    ("voice", "robot"): "Un robot",

    ("singers", "duet"): "Due a turno",
    ("singers", "group"): "Un gruppo si unisce",
    ("singers", "everyone"): "Tutti insieme",
    ("singers", "call"): "Domanda e risposta",

    ("language", "en"): "English",
    ("language", "fr"): "Français",

    ("sound", "boing"): "Boing",
    ("sound", "pop"): "Pop",
    ("sound", "ding"): "Ding!",
    ("sound", "sparkle"): "Scintillio",
    ("sound", "whoosh"): "Whoosh",
    ("sound", "splash"): "Splash",
    ("sound", "drum"): "Tamburo",
    ("sound", "zap"): "Zap",
    ("sound", "honk"): "Clacson",
    ("sound", "fanfare"): "Ta-daa!",
    ("sound", "cheer"): "Applausi",
    ("sound", "thud"): "Tonfo",

    ("theme", "midnight"): "Mezzanotte",
    ("theme", "bubblegum"): "Chewing gum",
    ("theme", "ocean"): "Oceano",
    ("theme", "forest"): "Foresta",
    ("theme", "sunset"): "Tramonto",
    ("theme", "daylight"): "Pieno giorno",

    ("restyle", "cartoon"): "🖍️ Un cartone",
    ("restyle", "painting"): "🎨 Un dipinto",
    ("restyle", "pencil"): "✏️ Un disegno a matita",
    ("restyle", "comic"): "💥 Un fumetto",
    ("restyle", "clay"): "🧸 Un modellino di plastilina",
    ("restyle", "bricks"): "🧱 Mattoncini",
    ("restyle", "glass"): "🪟 Una vetrata",
    ("restyle", "real"): "📷 Per davvero",
}

# Dutch.
CHOICES_NL: dict[tuple[str, str], str] = {
    ("style", "cartoon"): "Tekenfilm",
    ("style", "anime"): "Anime",
    ("style", "pixar"): "3D-film",
    ("style", "storybook"): "Prentenboek",
    ("style", "watercolour"): "Waterverf",
    ("style", "oil"): "Olieverf",
    ("style", "sketch"): "Potloodschets",
    ("style", "pixel"): "Pixelart",
    ("style", "comic"): "Stripboek",
    ("style", "clay"): "Klei",
    ("style", "papercraft"): "Papierkunst",
    ("style", "photo"): "Foto",
    ("style", "chalk"): "Krijttekening",
    ("style", "crayon"): "Waskrijt",
    ("style", "charcoal"): "Houtskool",
    ("style", "inkwash"): "Inkttekening",
    ("style", "stainedglass"): "Glas-in-lood",
    ("style", "woodcut"): "Houtsnede",
    ("style", "popart"): "Popart",
    ("style", "ukiyoe"): "Japanse houtsnede",
    ("style", "graffiti"): "Graffiti",
    ("style", "bricks"): "Bouwsteentjes",
    ("style", "felt"): "Vilt",
    ("style", "knitted"): "Gebreide wol",
    ("style", "origami"): "Origami",
    ("style", "sand"): "Zandsculptuur",
    ("style", "balloon"): "Ballonfiguur",
    ("style", "gingerbread"): "Peperkoek",
    ("style", "retrogame"): "Retrogame",
    ("style", "stopmotion"): "Stop-motion",
    ("style", "cartoon80s"): "80s-tekenfilm",
    ("style", "sticker"): "Sticker",
    ("style", "emoji"): "Emoji",
    ("style", "lowpoly"): "Low-poly 3D",
    ("style", "vectorflat"): "Vectortekening",
    ("style", "vintagephoto"): "Oude foto",
    ("style", "polaroid"): "Polaroid",
    ("style", "macro"): "Macro-opname",
    ("style", "bwfilm"): "Zwart-witfilm",
    ("style", "coloringpage"): "Kleurplaat",
    ("style", "doodle"): "Krabbel",
    ("style", "blueprint"): "Bouwtekening",
    ("style", "treasuremap"): "Schatkaart",

    ("scene", "forest"): "Bos",
    ("scene", "beach"): "Strand",
    ("scene", "city"): "Stad",
    ("scene", "farm"): "Boerderij",
    ("scene", "mountains"): "Bergen",
    ("scene", "mountaintop"): "Bergtop",
    ("scene", "snow"): "Sneeuw",
    ("scene", "desert"): "Woestijn",
    ("scene", "oasis"): "Oase",
    ("scene", "jungle"): "Jungle",
    ("scene", "jungletemple"): "Jungletempel",
    ("scene", "savannah"): "Savanne",
    ("scene", "rainstreet"): "Straat in de regen",
    ("scene", "market"): "Drukke markt",
    ("scene", "lighthouse"): "Vuurtoren",
    ("scene", "treehouse"): "Boomhut",
    ("scene", "playground"): "Speeltuin",
    ("scene", "library"): "Bibliotheek",
    ("scene", "volcano"): "In een vulkaan",
    ("scene", "arctic"): "De Noordpool",
    ("scene", "waterfall"): "Waterval",
    ("scene", "space"): "De ruimte",
    ("scene", "moon"): "Op de maan",
    ("scene", "underwater"): "Onder water",
    ("scene", "castle"): "Kasteel",
    ("scene", "candyland"): "Snoepland",
    ("scene", "clouds"): "In de wolken",
    ("scene", "cloudcastle"): "Wolkenkasteel",
    ("scene", "floatingisland"): "Zwevend eiland",
    ("scene", "snowglobe"): "In een sneeuwbol",
    ("scene", "giantskitchen"): "Reuzenkeuken",
    ("scene", "robotcity"): "Robotstad",
    ("scene", "dragoncave"): "Drakenhol",
    ("scene", "dinosaurvalley"): "Dinovallei",
    ("scene", "bedroom"): "Knusse kamer",
    ("scene", "kitchentable"): "Keukentafel",
    ("scene", "gardenshed"): "Tuinschuur",
    ("scene", "backseat"): "Autoritje",
    ("scene", "backyard"): "Achtertuin",

    ("lighting", "sunny"): "Zonnige dag",
    ("lighting", "sunset"): "Zonsondergang",
    ("lighting", "moonlight"): "Maanlicht",
    ("lighting", "candle"): "Kaarslicht",
    ("lighting", "neon"): "Neongloed",
    ("lighting", "rainbow"): "Regenbooglicht",
    ("lighting", "misty"): "Mistige ochtend",
    ("lighting", "stars"): "Sterrennacht",
    ("lighting", "fire"): "Vuurlicht",

    ("mood", "cosy"): "Knus",
    ("mood", "magical"): "Magisch",
    ("mood", "silly"): "Gek",
    ("mood", "epic"): "Episch",
    ("mood", "peaceful"): "Vredig",
    ("mood", "adventure"): "Avontuurlijk",
    ("mood", "dreamy"): "Dromerig",
    ("mood", "mysterious"): "Geheimzinnig",
    ("mood", "brave"): "Dapper",
    ("mood", "sleepy"): "Slaperig",
    ("mood", "proud"): "Trots",
    ("mood", "nervous"): "Zenuwachtig",
    ("mood", "giggly"): "Giechelig",
    ("mood", "dramatic"): "Dramatisch",
    ("mood", "spookyfun"): "Eng maar leuk",
    ("mood", "lonely"): "Eenzaam",
    ("mood", "triumphant"): "Triomfantelijk",
    ("mood", "curious"): "Nieuwsgierig",
    ("mood", "grumpy"): "Chagrijnig",
    ("mood", "wild"): "Wild",
    ("mood", "excited"): "Enthousiast",
    ("mood", "shy"): "Verlegen",
    ("mood", "confident"): "Zelfverzekerd",
    ("mood", "sneaky"): "Stiekem",
    ("mood", "hopeful"): "Hoopvol",
    ("mood", "determined"): "Vastberaden",
    ("mood", "surprised"): "Verrast",
    ("mood", "mischievous"): "Ondeugend",
    ("mood", "happy"): "Vrolijk",
    ("mood", "exciting"): "Spannend",
    ("mood", "spooky"): "Eng",
    ("mood", "calm"): "Rustig",
    ("mood", "sad"): "Peinzend",

    ("colours", "bright"): "Fel en krachtig",
    ("colours", "pastel"): "Zachte pastels",
    ("colours", "rainbow"): "Regenboog",
    ("colours", "warm"): "Warm",
    ("colours", "cool"): "Koel",
    ("colours", "neon"): "Neon",
    ("colours", "earthy"): "Aards",
    ("colours", "mono"): "Zwart-wit",
    ("colours", "sepia"): "Oude foto",
    ("colours", "gold"): "Goud en zilver",
    ("colours", "icyblue"): "IJsblauw",
    ("colours", "sunset"): "Oranje avondlucht",
    ("colours", "candypink"): "Snoeproze",
    ("colours", "forestgreen"): "Bosgroen",
    ("colours", "goldpurple"): "Goud en paars",
    ("colours", "monored"): "Tinten rood",
    ("colours", "blueyellow"): "Alleen blauw en geel",
    ("colours", "jewel"): "Juweelkleuren",
    ("colours", "autumn"): "Herfstkleuren",
    ("colours", "spring"): "Lentekleuren",
    ("colours", "christmas"): "Kerstkleuren",
    ("colours", "halloween"): "Halloweenkleuren",

    ("seenfrom", "closeup"): "Van dichtbij",
    ("seenfrom", "far"): "Van ver weg",
    ("seenfrom", "above"): "Van boven",
    ("seenfrom", "below"): "Van onderen",
    ("seenfrom", "side"): "Van opzij",
    ("seenfrom", "behind"): "Van achteren",
    ("seenfrom", "eye"): "Op ooghoogte",

    ("camera", "slowzoom"): "Langzaam inzoomen",
    ("camera", "pullback"): "Terugtrekken",
    ("camera", "pan"): "Langzaam zwenken",
    ("camera", "orbit"): "Eromheen draaien",
    ("camera", "follow"): "Meelopen",
    ("camera", "closeup"): "Van dichtbij",
    ("camera", "wide"): "Breed beeld",
    ("camera", "drone"): "Van boven",
    ("camera", "still"): "Stilstaan",
    ("camera", "tiltup"): "Omhoog kijken",
    ("camera", "flyover"): "Eroverheen vliegen",
    ("camera", "timelapse"): "Versnellen",

    ("music", "ukulele"): "Vrolijke ukelele",
    ("music", "piano"): "Zachte piano",
    ("music", "orchestra"): "Groots en episch",
    ("music", "chiptune"): "Videogame",
    ("music", "jazz"): "Jazzy",
    ("music", "dreamy"): "Dromerig",
    ("music", "marching"): "Fanfare",
    ("music", "spooky"): "Geheimzinnig",
    ("music", "rock"): "Stevige rock",
    ("music", "lullaby"): "Slaapliedje",
    ("music", "circus"): "Circus",
    ("music", "none"): "Geen",

    ("sounds", "none"): "Geen",
    ("sounds", "birds"): "Vogels en wind",
    ("sounds", "waves"): "Zeegolven",
    ("sounds", "rain"): "Regen",
    ("sounds", "forest"): "Bos",
    ("sounds", "city"): "Drukke stad",
    ("sounds", "fire"): "Knapperend vuur",
    ("sounds", "crowd"): "Juichend publiek",
    ("sounds", "kitchen"): "Keukengerinkel",
    ("sounds", "space"): "Diep gebrom",
    ("sounds", "quiet"): "Stil",
    ("sounds", "thunder"): "Donder in de verte",
    ("sounds", "playground"): "Speeltuin",
    ("sounds", "splash"): "Spetterend water",

    ("genre", "pop"): "Pop",

    # --- what kind of sound: a song, a little tune, a background
    #     hum. One card and one model; see app/music.py KINDS.
    ("kind", "song"): "Een liedje",
    ("kind", "jingle"): "Een deuntje",
    ("kind", "ambience"): "Een achtergrondgeluid",
    ("genre", "rock"): "Rock",
    ("genre", "dance"): "Dance",
    ("genre", "hiphop"): "Hiphop",
    ("genre", "folk"): "Folk",
    ("genre", "orchestra"): "Orkest",
    ("genre", "jazz"): "Jazz",
    ("genre", "lullaby"): "Slaapliedje",
    ("genre", "marching"): "Fanfare",
    ("genre", "chiptune"): "Videogame",
    ("genre", "country"): "Country",
    ("genre", "reggae"): "Reggae",

    ("instrument", "piano"): "Piano",
    ("instrument", "guitar"): "Gitaar",
    ("instrument", "drums"): "Drums",
    ("instrument", "violin"): "Viool",
    ("instrument", "flute"): "Fluit",
    ("instrument", "synth"): "Synth",
    ("instrument", "ukulele"): "Ukelele",
    ("instrument", "trumpet"): "Trompet",
    ("instrument", "steeldrum"): "Steeldrums",
    ("instrument", "harp"): "Harp",

    ("voice", "girl"): "Een meisje",
    ("voice", "boy"): "Een jongen",
    ("voice", "woman"): "Een vrouw",
    ("voice", "man"): "Een man",
    ("voice", "choir"): "Een heel koor",
    ("voice", "robot"): "Een robot",

    ("singers", "duet"): "Twee om de beurt",
    ("singers", "group"): "Een groep doet mee",
    ("singers", "everyone"): "Allemaal samen",
    ("singers", "call"): "Vraag en antwoord",

    ("language", "en"): "English",
    ("language", "fr"): "Français",

    ("sound", "boing"): "Boing",
    ("sound", "pop"): "Plop",
    ("sound", "ding"): "Ding!",
    ("sound", "sparkle"): "Glitter",
    ("sound", "whoosh"): "Woesj",
    ("sound", "splash"): "Plons",
    ("sound", "drum"): "Trommel",
    ("sound", "zap"): "Zap",
    ("sound", "honk"): "Toeter",
    ("sound", "fanfare"): "Ta-daa!",
    ("sound", "cheer"): "Gejuich",
    ("sound", "thud"): "Bonk",

    ("theme", "midnight"): "Middernacht",
    ("theme", "bubblegum"): "Kauwgom",
    ("theme", "ocean"): "Oceaan",
    ("theme", "forest"): "Bos",
    ("theme", "sunset"): "Zonsondergang",
    ("theme", "daylight"): "Daglicht",

    ("restyle", "cartoon"): "🖍️ Een tekenfilm",
    ("restyle", "painting"): "🎨 Een schilderij",
    ("restyle", "pencil"): "✏️ Een potloodtekening",
    ("restyle", "comic"): "💥 Een strip",
    ("restyle", "clay"): "🧸 Een kleifiguur",
    ("restyle", "bricks"): "🧱 Bouwsteentjes",
    ("restyle", "glass"): "🪟 Glas-in-lood",
    ("restyle", "real"): "📷 Echt maken",
}

# Portuguese.
CHOICES_PT: dict[tuple[str, str], str] = {
    ("style", "cartoon"): "Desenho animado",
    ("style", "anime"): "Anime",
    ("style", "pixar"): "Filme em 3D",
    ("style", "storybook"): "Livro ilustrado",
    ("style", "watercolour"): "Aguarela",
    ("style", "oil"): "Pintura a óleo",
    ("style", "sketch"): "Esboço a lápis",
    ("style", "pixel"): "Pixel art",
    ("style", "comic"): "BD",
    ("style", "clay"): "Plasticina",
    ("style", "papercraft"): "Papel recortado",
    ("style", "photo"): "Fotografia",
    ("style", "chalk"): "Desenho a giz",
    ("style", "crayon"): "Lápis de cera",
    ("style", "charcoal"): "Desenho a carvão",
    ("style", "inkwash"): "Tinta-da-china",
    ("style", "stainedglass"): "Vitral",
    ("style", "woodcut"): "Gravura em madeira",
    ("style", "popart"): "Pop art",
    ("style", "ukiyoe"): "Gravura japonesa",
    ("style", "graffiti"): "Graffiti",
    ("style", "bricks"): "Blocos de brincar",
    ("style", "felt"): "Feltro",
    ("style", "knitted"): "Lã tricotada",
    ("style", "origami"): "Origami",
    ("style", "sand"): "Escultura de areia",
    ("style", "balloon"): "Animal de balões",
    ("style", "gingerbread"): "Bolacha de gengibre",
    ("style", "retrogame"): "Jogo antigo",
    ("style", "stopmotion"): "Stop-motion",
    ("style", "cartoon80s"): "Desenho dos anos 80",
    ("style", "sticker"): "Autocolante",
    ("style", "emoji"): "Emoji",
    ("style", "lowpoly"): "3D low-poly",
    ("style", "vectorflat"): "Vetor plano",
    ("style", "vintagephoto"): "Foto antiga",
    ("style", "polaroid"): "Polaroid",
    ("style", "macro"): "Grande plano macro",
    ("style", "bwfilm"): "Filme a preto e branco",
    ("style", "coloringpage"): "Página para colorir",
    ("style", "doodle"): "Rabisco",
    ("style", "blueprint"): "Planta técnica",
    ("style", "treasuremap"): "Mapa do tesouro",

    ("scene", "forest"): "Floresta",
    ("scene", "beach"): "Praia",
    ("scene", "city"): "Cidade",
    ("scene", "farm"): "Quinta",
    ("scene", "mountains"): "Montanhas",
    ("scene", "mountaintop"): "Topo da montanha",
    ("scene", "snow"): "Neve",
    ("scene", "desert"): "Deserto",
    ("scene", "oasis"): "Oásis no deserto",
    ("scene", "jungle"): "Selva",
    ("scene", "jungletemple"): "Templo na selva",
    ("scene", "savannah"): "Savana",
    ("scene", "rainstreet"): "Rua à chuva",
    ("scene", "market"): "Mercado animado",
    ("scene", "lighthouse"): "Farol",
    ("scene", "treehouse"): "Casa na árvore",
    ("scene", "playground"): "Parque infantil",
    ("scene", "library"): "Biblioteca",
    ("scene", "volcano"): "Dentro de um vulcão",
    ("scene", "arctic"): "O Ártico",
    ("scene", "waterfall"): "Cascata",
    ("scene", "space"): "Espaço",
    ("scene", "moon"): "Na Lua",
    ("scene", "underwater"): "Debaixo de água",
    ("scene", "castle"): "Castelo",
    ("scene", "candyland"): "Terra dos doces",
    ("scene", "clouds"): "Nas nuvens",
    ("scene", "cloudcastle"): "Castelo de nuvens",
    ("scene", "floatingisland"): "Ilha voadora",
    ("scene", "snowglobe"): "Dentro de um globo de neve",
    ("scene", "giantskitchen"): "Cozinha do gigante",
    ("scene", "robotcity"): "Cidade dos robôs",
    ("scene", "dragoncave"): "Gruta do dragão",
    ("scene", "dinosaurvalley"): "Vale dos dinossauros",
    ("scene", "bedroom"): "Quarto acolhedor",
    ("scene", "kitchentable"): "Mesa da cozinha",
    ("scene", "gardenshed"): "Casinha do jardim",
    ("scene", "backseat"): "De carro",
    ("scene", "backyard"): "Quintal",

    ("lighting", "sunny"): "Dia de sol",
    ("lighting", "sunset"): "Pôr do sol dourado",
    ("lighting", "moonlight"): "Luar",
    ("lighting", "candle"): "Luz de vela",
    ("lighting", "neon"): "Brilho de néon",
    ("lighting", "rainbow"): "Luz de arco-íris",
    ("lighting", "misty"): "Manhã de nevoeiro",
    ("lighting", "stars"): "Noite estrelada",
    ("lighting", "fire"): "Luz de fogueira",

    ("mood", "cosy"): "Aconchegante",
    ("mood", "magical"): "Mágico",
    ("mood", "silly"): "Maluco",
    ("mood", "epic"): "Épico",
    ("mood", "peaceful"): "Tranquilo",
    ("mood", "adventure"): "Aventureiro",
    ("mood", "dreamy"): "Sonhador",
    ("mood", "mysterious"): "Misterioso",
    ("mood", "brave"): "Corajoso",
    ("mood", "sleepy"): "Sonolento",
    ("mood", "proud"): "Orgulhoso",
    ("mood", "nervous"): "Nervoso",
    ("mood", "giggly"): "Risonho",
    ("mood", "dramatic"): "Dramático",
    ("mood", "spookyfun"): "Assustador a brincar",
    ("mood", "lonely"): "Solitário",
    ("mood", "triumphant"): "Triunfante",
    ("mood", "curious"): "Curioso",
    ("mood", "grumpy"): "Resmungão",
    ("mood", "wild"): "Selvagem",
    ("mood", "excited"): "Entusiasmado",
    ("mood", "shy"): "Tímido",
    ("mood", "confident"): "Confiante",
    ("mood", "sneaky"): "Matreiro",
    ("mood", "hopeful"): "Esperançoso",
    ("mood", "determined"): "Determinado",
    ("mood", "surprised"): "Surpreendido",
    ("mood", "mischievous"): "Traquina",
    ("mood", "happy"): "Alegre",
    ("mood", "exciting"): "Empolgante",
    ("mood", "spooky"): "Arrepiante",
    ("mood", "calm"): "Calmo",
    ("mood", "sad"): "Pensativo",

    ("colours", "bright"): "Vivas e fortes",
    ("colours", "pastel"): "Pastéis suaves",
    ("colours", "rainbow"): "Arco-íris",
    ("colours", "warm"): "Quentes",
    ("colours", "cool"): "Frias",
    ("colours", "neon"): "Néon",
    ("colours", "earthy"): "Terrosas",
    ("colours", "mono"): "Preto e branco",
    ("colours", "sepia"): "Foto antiga",
    ("colours", "gold"): "Ouro e prata",
    ("colours", "icyblue"): "Azuis gelados",
    ("colours", "sunset"): "Laranjas do poente",
    ("colours", "candypink"): "Rosa-bombom",
    ("colours", "forestgreen"): "Verdes da floresta",
    ("colours", "goldpurple"): "Ouro e roxo",
    ("colours", "monored"): "Tons de vermelho",
    ("colours", "blueyellow"): "Só azul e amarelo",
    ("colours", "jewel"): "Tons de joia",
    ("colours", "autumn"): "Cores de outono",
    ("colours", "spring"): "Cores de primavera",
    ("colours", "christmas"): "Cores de Natal",
    ("colours", "halloween"): "Cores de Halloween",

    ("seenfrom", "closeup"): "De muito perto",
    ("seenfrom", "far"): "De longe",
    ("seenfrom", "above"): "De cima",
    ("seenfrom", "below"): "De baixo",
    ("seenfrom", "side"): "De lado",
    ("seenfrom", "behind"): "De trás",
    ("seenfrom", "eye"): "À altura dos olhos",

    ("camera", "slowzoom"): "Zoom lento",
    ("camera", "pullback"): "A afastar",
    ("camera", "pan"): "Panorâmica lenta",
    ("camera", "orbit"): "À volta",
    ("camera", "follow"): "A seguir",
    ("camera", "closeup"): "Grande plano",
    ("camera", "wide"): "Plano aberto",
    ("camera", "drone"): "Vista de cima",
    ("camera", "still"): "Sem mexer",
    ("camera", "tiltup"): "A olhar para cima",
    ("camera", "flyover"): "A sobrevoar",
    ("camera", "timelapse"): "Acelerado",

    ("music", "ukulele"): "Ukulele alegre",
    ("music", "piano"): "Piano suave",
    ("music", "orchestra"): "Grande e épica",
    ("music", "chiptune"): "Videojogo",
    ("music", "jazz"): "Jazzy",
    ("music", "dreamy"): "Sonhadora",
    ("music", "marching"): "Fanfarra",
    ("music", "spooky"): "Misteriosa",
    ("music", "rock"): "Rock animado",
    ("music", "lullaby"): "Canção de embalar",
    ("music", "circus"): "Circo",
    ("music", "none"): "Nenhuma",

    ("sounds", "none"): "Nenhum",
    ("sounds", "birds"): "Pássaros e vento",
    ("sounds", "waves"): "Ondas do mar",
    ("sounds", "rain"): "Chuva",
    ("sounds", "forest"): "Floresta",
    ("sounds", "city"): "Cidade movimentada",
    ("sounds", "fire"): "Fogueira a crepitar",
    ("sounds", "crowd"): "Multidão a aplaudir",
    ("sounds", "kitchen"): "Barulho de cozinha",
    ("sounds", "space"): "Zumbido profundo",
    ("sounds", "quiet"): "Silêncio",
    ("sounds", "thunder"): "Trovoada ao longe",
    ("sounds", "playground"): "Recreio",
    ("sounds", "splash"): "Chapinhar na água",

    ("genre", "pop"): "Pop",

    # --- what kind of sound: a song, a little tune, a background
    #     hum. One card and one model; see app/music.py KINDS.
    ("kind", "song"): "Uma canção",
    ("kind", "jingle"): "Uma melodia",
    ("kind", "ambience"): "Um som de fundo",
    ("genre", "rock"): "Rock",
    ("genre", "dance"): "Dance",
    ("genre", "hiphop"): "Hip-hop",
    ("genre", "folk"): "Folk",
    ("genre", "orchestra"): "Orquestra",
    ("genre", "jazz"): "Jazz",
    ("genre", "lullaby"): "Canção de embalar",
    ("genre", "marching"): "Fanfarra",
    ("genre", "chiptune"): "Videojogo",
    ("genre", "country"): "Country",
    ("genre", "reggae"): "Reggae",

    ("instrument", "piano"): "Piano",
    ("instrument", "guitar"): "Guitarra",
    ("instrument", "drums"): "Bateria",
    ("instrument", "violin"): "Violino",
    ("instrument", "flute"): "Flauta",
    ("instrument", "synth"): "Sintetizador",
    ("instrument", "ukulele"): "Ukulele",
    ("instrument", "trumpet"): "Trompete",
    ("instrument", "steeldrum"): "Steel drums",
    ("instrument", "harp"): "Harpa",

    ("voice", "girl"): "Uma menina",
    ("voice", "boy"): "Um menino",
    ("voice", "woman"): "Uma mulher",
    ("voice", "man"): "Um homem",
    ("voice", "choir"): "Um coro inteiro",
    ("voice", "robot"): "Um robô",

    ("singers", "duet"): "Dois à vez",
    ("singers", "group"): "Um grupo junta-se",
    ("singers", "everyone"): "Todos juntos",
    ("singers", "call"): "Pergunta e resposta",

    ("language", "en"): "English",
    ("language", "fr"): "Français",

    ("sound", "boing"): "Boing",
    ("sound", "pop"): "Pop",
    ("sound", "ding"): "Ding!",
    ("sound", "sparkle"): "Brilhos",
    ("sound", "whoosh"): "Whoosh",
    ("sound", "splash"): "Chape!",
    ("sound", "drum"): "Tambor",
    ("sound", "zap"): "Zap",
    ("sound", "honk"): "Buzina",
    ("sound", "fanfare"): "Ta-dã!",
    ("sound", "cheer"): "Palmas",
    ("sound", "thud"): "Bum",

    ("theme", "midnight"): "Meia-noite",
    ("theme", "bubblegum"): "Chiclete",
    ("theme", "ocean"): "Oceano",
    ("theme", "forest"): "Floresta",
    ("theme", "sunset"): "Pôr do sol",
    ("theme", "daylight"): "Dia claro",

    ("restyle", "cartoon"): "🖍️ Um desenho animado",
    ("restyle", "painting"): "🎨 Uma pintura",
    ("restyle", "pencil"): "✏️ Um desenho a lápis",
    ("restyle", "comic"): "💥 Uma BD",
    ("restyle", "clay"): "🧸 Plasticina",
    ("restyle", "bricks"): "🧱 Blocos de brincar",
    ("restyle", "glass"): "🪟 Um vitral",
    ("restyle", "real"): "📷 Como se fosse real",
}

_CHOICES = {
    "fr": CHOICES_FR, "de": CHOICES_DE, "es": CHOICES_ES,
    "it": CHOICES_IT, "nl": CHOICES_NL, "pt": CHOICES_PT,
}


_DICTS = {"en": _SHAPE, "fr": FR, "de": DE, "es": ES, "it": IT, "nl": NL,
          "pt": PT}


def t(key: str, **fmt) -> str:
    """The key in the language of this request, with {placeholders} filled.

    The key *is* the English text, so a missing translation reads correctly
    rather than showing a key or a blank. `str.replace` and not `str.format`:
    a stray brace in a translated sentence should not raise in front of a
    child.
    """
    out = _DICTS.get(lang(), {}).get(key)
    if out is None:
        out = _SHAPE.get(key, key)
    for name, value in fmt.items():
        out = out.replace("{" + name + "}", str(value))
    return _spaces(out) if lang() in _SPACED else out


# French puts a space in front of ! ? : and ;, and it has to be one that does
# not break, or the mark wraps onto the next line on its own. Done here rather
# than in every entry above, so the dictionary stays readable.
#
# It is French and nothing else. Spanish opens its questions instead (¿...?)
# and that is written into the entries, because it is a *character* rather
# than spacing; German, Dutch, Italian and Portuguese set their marks tight
# against the word the way English does. One rule for all seven would put a
# gap in front of every exclamation mark on six pages that do not want one.
_SPACED = {"fr"}

_TIGHT = re.compile(r" ([!?;:»])")


def _spaces(text: str) -> str:
    return _TIGHT.sub(" \\1", text).replace("« ", "« ")


def label(group: str, choice: str, english: str) -> str:
    """One dropdown choice's label. English for anything not translated yet.

    A choice added to `styles.py` later turns up on the page working and
    untranslated rather than blank, in all six - which is the whole reason
    these labels are keyed by id here instead of sitting in a column beside
    the choice, where six of them would be six more things to get wrong.
    """
    here = lang()
    if here == "en":
        return english
    return _CHOICES.get(here, {}).get((group, choice), english)
