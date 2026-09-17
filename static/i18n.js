/* Two languages, one set of strings - the browser half.

   The server half is app/i18n.py, and both work the same way: the key *is*
   the English text, so a call site reads as the sentence it produces and a
   missing translation shows the English rather than a blank or a key name.
   English therefore stays in app.js and in index.html, where it can be read
   in place; French lives here and nowhere else.

   Three ways in:

   - `t("Make my picture")` in app.js, for everything the script writes.
   - `data-i18n="..."` on static markup, whose English is the key - applied by
     `I18N.apply()` before the first paint, so nothing flashes.
   - `data-i18n-attr="placeholder:...;aria-label:..."` for the attributes,
     same idea.

   A handful of keys are symbolic rather than English - the ones whose two
   languages differ in *shape* rather than in words, where one template cannot
   serve both. Those, and only those, are in `EN`.

   Which language: the `lang` cookie, which their Settings tab writes, mirrored
   into localStorage so this file can decide before the first paint (the
   cookie is authoritative and the two agree except across devices; /api/app
   corrects it). Loaded before app.js, which is why `t` is on `window`. */

window.I18N = (function () {
  "use strict";

  // Only the keys that are not their own English.
  var EN = {
    // The wizard's sentence, which is a picture prompt and not prose: English
    // puts the colour in front of the noun and the article in front of that,
    // French puts the colour after it and keeps the article on the choice.
    "wiz-sentence": "a friendly {colour}{bare}{wearing}, a cheerful cartoon " +
                    "portrait, head and shoulders, big friendly eyes",
    "wiz-wearing": " wearing {list}",
    "wiz-and": " and ",
    // The chip says "purple"; the sentence needs "purple " in front of the
    // noun in English and "en violet" after it in French, so the colour has a
    // label and a fragment rather than one string doing both.
    "wiz-colour": "{colour} ",
    "closes-in": "The factory closes at {at} - about {mins} minutes left.",
  };

  var FR = {
    // --- the shell ------------------------------------------------------
    "My AI Factory": "Ma fabrique IA",
    "AI Factory": "Fabrique IA",
    "What would you like to do?": "Qu'est-ce que tu veux faire ?",
    "That's me - tap to swap": "C'est moi - appuie pour changer",
    "Show me": "Montre-moi",
    "Working...": "Ça travaille...",

    // --- what's happening, in full (the sheet behind the now-bar) --------
    "Tap to see what's happening": "Appuie pour voir ce qui se passe",
    "⏳ What’s happening?": "⏳ Il se passe quoi ?",
    // One per kind, because the article agrees with what is being made.
    "Making a picture": "Je fabrique une image",
    "Making a comic": "Je fabrique une BD",
    "Making a video": "Je fabrique une vidéo",
    "Making a film": "Je fabrique un film",
    "Making a song": "Je fabrique une chanson",
    "Making a video smoother": "Je rends une vidéo plus fluide",
    "Making a video slow": "Je passe une vidéo au ralenti",
    "Making a picture huge": "J'agrandis une image",
    "Changing a picture": "Je change une image",
    "Seeing outside a picture": "Je regarde autour d'une image",
    "Fixing part of a picture": "Je répare un bout d'une image",
    "Turning a picture into something else": "Je transforme une image",
    "Making something": "Je fabrique quelque chose",
    // The quality picker's words without their emoji, for the row of facts.
    "Quick": "Rapide",
    "Normal": "Normal",
    "Sharper": "Plus net",
    "{n} of {m}": "{n} sur {m}",
    "usually takes {time}": "prend d'habitude {time}",
    "Something else is being made first.": "Quelque chose d'autre passe avant.",
    "There are {n} things being made first.": "Il y a {n} choses qui passent avant.",
    "Done! ✨": "C'est fini ! ✨",
    "Look at it!": "Regarde !",
    "Really stop?": "Vraiment arrêter ?",
    "wiz-sentence": "{thing} {colour}très sympathique{wearing}, portrait de " +
                    "dessin animé joyeux, tête et épaules, de grands yeux rieurs",
    "wiz-wearing": " qui porte {list}",
    "wiz-and": " et ",
    "wiz-colour": "en {colour} ",

    // Tabs. Short on purpose: seven of them share one row at 390px.
    "Picture": "Image",
    "Video": "Vidéo",
    "Comic": "BD",
    "Music": "Musique",
    "Chat": "Chat",
    "Gallery": "Galerie",
    "Settings": "Réglages",

    // --- "your picture is ready" ----------------------------------------
    "Your picture is ready! ✨": "Ton image est prête ! ✨",
    "Your video is ready! ✨": "Ta vidéo est prête ! ✨",
    "Your comic is ready! ✨": "Ta BD est prête ! ✨",
    "Your film is ready! ✨": "Ton film est prêt ! ✨",
    "Your song is ready! ✨": "Ta chanson est prête ! ✨",
    "Your smooth video is ready! ✨": "Ta vidéo fluide est prête ! ✨",
    "Your slow-motion video is ready! ✨": "Ton ralenti est prêt ! ✨",
    "Your big picture is ready! ✨": "Ta grande image est prête ! ✨",
    "Your bigger picture is ready! ✨": "Ton image agrandie est prête ! ✨",
    "Your changed picture is ready! ✨": "Ton image changée est prête ! ✨",

    // --- the Gallery ------------------------------------------------------
    "Everything you've made is saved here.": "Tout ce que tu fabriques est gardé ici.",
    "Nothing here yet! Make a picture, a video or a comic and it'll turn up here.":
      "Rien pour l'instant ! Fais une image, une vidéo ou une BD et ça arrivera ici.",
    "Nothing of yours yet - but there's something on the family shelf!":
      "Rien de toi pour l'instant - mais il y a quelque chose sur l'étagère de la famille !",
    "You've made 1 thing so far.": "Tu as fabriqué 1 chose pour l'instant.",
    "You've made {n} things so far.": "Tu as fabriqué {n} choses pour l'instant.",
    "🧑‍🎤 My characters": "🧑‍🎤 Mes personnages",
    "Show": "Voir",
    "How to show your gallery": "Comment voir ta galerie",
    "Everything": "Tout",
    "In groups": "En groupes",
    "Order": "Ordre",
    "What order to show them in": "Dans quel ordre les montrer",
    "Newest": "Récent",
    "Oldest": "Ancien",
    "⭐ Favourites": "⭐ Favoris",
    "By kind": "Par type",
    "🔎 Find something you made": "🔎 Trouve une de tes créations",
    "Search your gallery": "Chercher dans ta galerie",
    "Clear the search": "Effacer la recherche",
    "Choose": "Choisir",
    "Cancel": "Annuler",
    "👨‍👩‍👧 Family": "👨‍👩‍👧 Famille",
    "🎨 Pictures": "🎨 Images",
    "📖 Comics": "📖 BD",
    "🧩 Comic pictures": "🧩 Images de BD",
    "✂️ Stickers": "✂️ Autocollants",
    "📷 Photos & drawings": "📷 Photos et dessins",
    "🎬 Videos": "🎬 Vidéos",
    "🎵 Songs": "🎵 Chansons",
    "Nothing matches that. Try another word!":
      "Rien ne correspond. Essaie un autre mot !",
    "Nothing here yet! Go and make something.":
      "Rien pour l'instant ! Va fabriquer quelque chose.",
    "🗑️ Recently deleted": "🗑️ Supprimé récemment",
    "Things stay here for {days} days, then they're gone for good. Tap one to put it back.":
      "Les choses restent ici {days} jours, puis elles partent pour de bon. " +
      "Appuie sur l'une d'elles pour la remettre.",
    "Nothing chosen yet": "Rien de choisi",
    "Tap the ones you want": "Appuie sur celles que tu veux",
    "1 chosen": "1 choisie",
    "{n} chosen": "{n} choisies",
    "Choose all": "Tout choisir",
    "Choose none": "Ne rien choisir",
    "🎬 Join into a film": "🎬 Assembler en film",
    "🔍 Compare them": "🔍 Les comparer",
    "🏷️ Add a tag": "🏷️ Ajouter une étiquette",
    "⬇︎ Save": "⬇︎ Enregistrer",
    "🗑️ Delete": "🗑️ Supprimer",
    "Deleted": "Supprimé",
    "{n} things deleted": "{n} choses supprimées",
    "Undo": "Annuler",
    "Put back!": "Remise !",
    "All put back!": "Toutes remises !",
    "Really delete?": "Vraiment supprimer ?",
    "Really delete it?": "Vraiment la supprimer ?",
    "Really delete all {n}?": "Vraiment supprimer les {n} ?",
    "Really delete forever?": "Supprimer pour toujours ?",
    "Really clear it?": "Vraiment tout effacer ?",
    "Really say goodbye?": "Vraiment lui dire au revoir ?",

    // --- the maker cards -------------------------------------------------
    "Make a picture": "Faire une image",
    "Make a video": "Faire une vidéo",
    "Make a comic": "Faire une BD",
    "Make a song": "Faire une chanson",
    "↺ Start again": "↺ Recommencer",
    "Clear everything on this card and start again":
      "Effacer tout sur cette carte et recommencer",
    "What should the picture be?": "Qu'est-ce que l'image doit montrer ?",
    "What should the video be?": "Qu'est-ce que la vidéo doit montrer ?",
    "What's your story?": "C'est quoi, ton histoire ?",
    "What should the song be about?": "La chanson parle de quoi ?",
    "What should the top of your page look like?":
      "Le haut de ta page, ça ressemble à quoi ?",
    "A fluffy dragon eating pancakes on the moon":
      "Un dragon tout doux qui mange des crêpes sur la Lune",
    "A puppy surfing a giant wave at sunset":
      "Un chiot qui surfe une vague géante au coucher du soleil",
    "It flaps its wings and flies up into the clouds":
      "Il bat des ailes et s'envole dans les nuages",
    "The cat walks across the room and curls up in the sunny spot":
      "Le chat traverse la pièce et se roule en boule au soleil",
    "A little robot looking for its lost cat in a big city":
      "Un petit robot qui cherche son chat perdu dans une grande ville",
    "A hedgehog who wants to learn to swim":
      "Un hérisson qui veut apprendre à nager",
    "A dragon who is scared of pancakes": "Un dragon qui a peur des crêpes",
    "A row of hot air balloons over a green valley":
      "Une rangée de ballons au-dessus d'une vallée verte",
    "Clear what you typed": "Effacer ce que tu as écrit",
    "✨ Help me write it": "✨ Aide-moi à l'écrire",
    "👀 Look at my picture and help me write it":
      "👀 Regarde mon image et aide-moi à l'écrire",
    "✨ Write me a song": "✨ Écris-moi une chanson",
    "🎉 Surprise me": "🎉 Surprends-moi",
    "🎲 Mix it up": "🎲 Mélange tout",
    "📜 Things I've asked for before": "📜 Ce que j'ai déjà demandé",
    "📷 Start from a photo": "📷 Partir d'une photo",
    "🖼️ Pick one from my gallery": "🖼️ Choisir dans ma galerie",
    "Who's in it?": "Qui est dedans ?",
    "Nobody": "Personne",
    "📄 Everything with {name} in it": "📄 Tout ce où il y a {name}",
    "Make": "Faire",
    "What kind of picture": "Quel genre d'image",
    "A picture": "Une image",
    "A character": "Un personnage",
    "Drawn on its own with nothing behind it, so you can cut it out as a sticker or keep them as a character.":
      "Dessiné tout seul, sans rien derrière, pour pouvoir le découper en " +
      "autocollant ou le garder comme personnage.",
    "Shape": "Forme",
    "Picture shape": "Forme de l'image",
    "Video shape": "Forme de la vidéo",
    "Landscape": "Paysage",
    "Portrait": "Portrait",
    "Square": "Carré",
    "landscape": "paysage",
    "portrait": "portrait",
    "square": "carré",
    "How many": "Combien",
    "How many pictures": "Combien d'images",
    "How many panels": "Combien de cases",
    "Just one": "Une seule",
    "Four to pick from": "Quatre au choix",
    "3 pictures": "3 images",
    "4 pictures": "4 images",
    "6 pictures": "6 images",
    "Look": "Aspect",
    "Look and sound": "Aspect et son",
    "Sound": "Son",
    "Clear these": "Effacer tout ça",
    "Any": "Au choix",
    "Make my picture": "Fais mon image",
    "Make {n} pictures": "Fais {n} images",
    "Make my video": "Fais ma vidéo",
    "Make my film": "Fais mon film",
    "Animate it": "Anime-la",
    "Make my comic": "Fais ma BD",
    "Make my song": "Fais ma chanson",
    "Make my music": "Fais ma musique",
    "Make one": "Fais-en une",
    "Stop": "Arrêter",
    "Tell a story and it gets drawn as a comic strip you can print.":
      "Raconte une histoire et elle sera dessinée en BD, prête à imprimer.",

    // video card
    "Start from": "Partir de",
    "What to start the video from": "D'où part la vidéo",
    "✏️ Words": "✏️ Des mots",
    "🖼️ A picture": "🖼️ Une image",
    "🎞️ Two pictures": "🎞️ Deux images",
    "📽️ A little film": "📽️ Un petit film",
    "Make a picture up above and tap <strong>Animate this</strong>, or use a photo from your iPad.":
      "Fais une image plus haut et appuie sur <strong>Anime ça</strong>, ou " +
      "prends une photo de ton iPad.",
    "The picture you picked": "L'image que tu as choisie",
    "This picture is ready to animate!": "Cette image est prête à être animée !",
    "Use a different one": "En prendre une autre",
    "📷 Take or choose a photo": "📷 Prends ou choisis une photo",
    "✏️ Draw one": "✏️ Dessines-en une",
    "Pick where the video starts and where it ends. The middle gets made up.":
      "Choisis où la vidéo commence et où elle finit. Le milieu est inventé.",
    "Starts on": "Commence sur",
    "Ends on": "Finit sur",
    "🖼️ Pick from the gallery": "🖼️ Choisir dans la galerie",
    "🖼️ Pick a different one": "🖼️ En choisir une autre",
    "🗣️ What should they say?": "🗣️ Qu'est-ce qu'ils disent ?",
    "(you can leave this empty)": "(tu peux laisser vide)",
    "Look at the Earth from up here!": "Regarde la Terre d'ici !",
    "Clear what they say": "Effacer ce qu'ils disent",
    "🔊 Videos have sound — they'll say this out loud, so keep it short.":
      "🔊 Les vidéos ont du son — ils diront ça à voix haute, alors fais court.",
    "Quality": "Qualité",
    "Video quality": "Qualité de la vidéo",
    "⚡ Quick": "⚡ Rapide",
    "👍 Normal": "👍 Normal",
    "✨ Sharper": "✨ Plus net",
    "Sharper means more detail, but it takes a good deal longer to make, and the longest a sharper video can be is":
      "Plus net veut dire plus de détails, mais c'est bien plus long à " +
      "fabriquer, et une vidéo plus nette ne peut pas dépasser",
    "seconds.": "secondes.",
    "How long": "Durée",
    "Video length in seconds": "Durée de la vidéo en secondes",
    "How long the song is, in seconds": "Durée de la chanson, en secondes",
    "{n} seconds": "{n} secondes",
    "Longer videos take longer to make.":
      "Les vidéos plus longues prennent plus de temps à fabriquer.",
    "Longer songs take longer to make.":
      "Les chansons plus longues prennent plus de temps à fabriquer.",
    "How many parts": "Combien de parties",
    "2 parts": "2 parties",
    "3 parts": "3 parties",
    "4 parts": "4 parties",
    "Each part carries on from the last one, then they're joined into one film. It takes a while, and it uses up one video for each part.":
      "Chaque partie continue la précédente, puis tout est assemblé en un " +
      "film. Ça prend un moment, et ça utilise une vidéo par partie.",
    "🔊 Add a sound": "🔊 Ajouter un son",
    "None": "Aucun",
    "When?": "Quand ?",
    "At the start": "Au début",
    "In the middle": "Au milieu",
    "At the end": "À la fin",

    // music card
    "Singing": "Chant",
    "Singing or not": "Chanté ou pas",
    "With singing": "Avec du chant",
    "Just music": "Juste la musique",
    "Words": "Paroles",
    "Clear the words": "Effacer les paroles",
    "[Verse]\nI met a dragon on the stairs\nHe said he doesn't like éclairs\n\n[Chorus]\nPancakes, pancakes, run away!":
      "[Couplet]\nJ'ai vu un dragon dans l'escalier\nIl m'a dit qu'il n'aime pas les éclairs\n\n[Refrain]\nDes crêpes, des crêpes, sauve qui peut !",
    "Put <strong>[Verse]</strong> or <strong>[Chorus]</strong> on a line of their own to mark the parts. Leave it empty and you'll get music with nobody singing.":
      "Mets <strong>[Couplet]</strong> ou <strong>[Refrain]</strong> sur une " +
      "ligne à eux pour marquer les parties. Laisse vide et tu auras de la " +
      "musique sans personne qui chante.",

    // --- the helpers -----------------------------------------------------
    "Type a few words about your idea first!":
      "Écris d'abord quelques mots sur ton idée !",
    "Thinking of ideas...": "Je cherche des idées...",
    "Looking at your picture...": "Je regarde ton image...",
    "This takes a moment the first time.": "C'est un peu long la première fois.",
    "Here you go! Change anything you like.":
      "Et voilà ! Change tout ce que tu veux.",
    "Here's an idea for it - change anything you like.":
      "Voilà une idée - change tout ce que tu veux.",
    "Writing your song...": "J'écris ta chanson...",
    "Here are some words! Change any line you like - they don't have to rhyme.":
      "Voilà des paroles ! Change les lignes que tu veux - ça n'a pas besoin de rimer.",
    "🎲 Thinking of something...": "🎲 Je réfléchis...",
    "🎲 Writing a song...": "🎲 J'écris une chanson...",
    "Dreaming up an idea...": "J'invente une idée...",
    "Here's a whole song! Change any line you like.":
      "Voilà une chanson entière ! Change les lignes que tu veux.",
    "Here's an idea! Change anything you like.":
      "Voilà une idée ! Change tout ce que tu veux.",
    "One of your old ideas with a brand new look. Change anything you like!":
      "Une de tes anciennes idées avec un tout nouveau look. Change ce que tu veux !",
    "A brand new idea. Change anything you like!":
      "Une toute nouvelle idée. Change ce que tu veux !",
    "🎲 Shuffling...": "🎲 Je mélange...",
    "Same as before - change anything you like, then go!":
      "Comme avant - change ce que tu veux, puis c'est parti !",
    "Change a word or two and you'll get this same one, but different. “Make another like this” starts from scratch instead.":
      "Change un mot ou deux et tu auras la même, mais différente. " +
      "« Fais-en une autre comme ça » repart de zéro.",
    "Your drawing is ready! Tap the helper to get a script for it, or say what should happen.":
      "Ton dessin est prêt ! Appuie sur l'aide pour avoir un texte, ou dis ce qui doit se passer.",
    "This starts where that video stopped. What happens next?":
      "Ça commence là où cette vidéo s'est arrêtée. Qu'est-ce qui se passe après ?",

    // --- while it renders -------------------------------------------------
    "Sending it off...": "J'envoie tout ça...",
    "Getting started...": "Ça démarre...",
    "Starting": "Départ",
    "Making another one...": "J'en fais une autre...",
    "Getting it ready...": "Je prépare ça...",
    "Working out your story...": "J'imagine ton histoire...",
    "Reading your story...": "Je lis ton histoire...",
    "Putting your comic together...": "J'assemble ta BD...",
    "Stopping...": "J'arrête...",
    "Stopped! Nothing was made. Try a different idea.":
      "Arrêté ! Rien n'a été fabriqué. Essaie une autre idée.",
    "Couldn't stop it — it may finish anyway.":
      "Impossible de l'arrêter — elle va peut-être finir quand même.",
    "Something went wrong. Let's try that again!":
      "Quelque chose n'a pas marché. On réessaie !",
    "Pick a picture first — make one above, or use a photo!":
      "Choisis d'abord une image — fais-en une plus haut, ou prends une photo !",
    "Pick a picture to start on and one to end on!":
      "Choisis une image pour commencer et une pour finir !",
    "Type something you'd like to make first!":
      "Écris d'abord ce que tu aimerais fabriquer !",
    "Sending your photo...": "J'envoie ta photo...",
    "It's in your gallery! Now pick what to do with it ✨":
      "C'est dans ta galerie ! Choisis ce que tu veux en faire ✨",
    "✅ Ready!": "✅ Prêt !",
    "Took {time}.": "Ça a pris {time}.",
    "{n} seconds long": "{n} secondes",
    "{n} second": "{n} seconde",
    "{n} secs": "{n} s",
    "about {n} seconds": "environ {n} secondes",
    "about a minute": "environ une minute",
    "about {n} minutes": "environ {n} minutes",
    "{time} so far": "{time} déjà",
    // The live strip beside the bar, and on its own line in the status sheet.
    "{used} of {total} GB": "{used} sur {total} Go",
    "about {time} to go": "encore environ {time}",
    "⏱️ I haven't made one of these yet — I'll time this one.":
      "⏱️ Je n'en ai jamais fait comme ça — je vais chronométrer celle-là.",
    "⏱️ Takes {time} on this computer.":
      "⏱️ Ça prend {time} sur cet ordinateur.",
    "⏱️ Probably takes {time}.": "⏱️ Ça prend sans doute {time}.",

    // --- the allowance and the clock --------------------------------------
    "🌙 That's all the pictures for today. See you tomorrow!":
      "🌙 C'est tout pour les images aujourd'hui. À demain !",
    "🌙 That's all the videos for today. See you tomorrow!":
      "🌙 C'est tout pour les vidéos aujourd'hui. À demain !",
    "🌙 That's all the songs for today. See you tomorrow!":
      "🌙 C'est tout pour les chansons aujourd'hui. À demain !",
    "✨ {n} pictures left today, so that's how many you'll get.":
      "✨ Il te reste {n} images aujourd'hui, c'est donc ce que tu auras.",
    "✨ {n} videos left today, so that's how many you'll get.":
      "✨ Il te reste {n} vidéos aujourd'hui, c'est donc ce que tu auras.",
    "✨ {n} songs left today, so that's how many you'll get.":
      "✨ Il te reste {n} chansons aujourd'hui, c'est donc ce que tu auras.",
    "✨ 1 picture left today, so that's how many you'll get.":
      "✨ Il te reste 1 image aujourd'hui, c'est donc ce que tu auras.",
    "✨ 1 video left today, so that's how many you'll get.":
      "✨ Il te reste 1 vidéo aujourd'hui, c'est donc ce que tu auras.",
    "✨ 1 song left today, so that's how many you'll get.":
      "✨ Il te reste 1 chanson aujourd'hui, c'est donc ce que tu auras.",
    "✨ One more picture today - make it a good one!":
      "✨ Encore une image aujourd'hui - fais-en une belle !",
    "✨ One more video today - make it a good one!":
      "✨ Encore une vidéo aujourd'hui - fais-en une belle !",
    "✨ One more song today - make it a good one!":
      "✨ Encore une chanson aujourd'hui - fais-en une belle !",
    "✨ {n} more pictures today": "✨ Encore {n} images aujourd'hui",
    "✨ {n} more videos today": "✨ Encore {n} vidéos aujourd'hui",
    "✨ {n} more songs today": "✨ Encore {n} chansons aujourd'hui",
    "The factory closes at {at} - any minute now!":
      "La fabrique ferme à {at} - d'une minute à l'autre !",
    "closes-in": "La fabrique ferme à {at} - il reste environ {mins} minutes.",
    "The factory is closed right now": "La fabrique est fermée pour le moment",
    "Back soon!": "À tout de suite !",

    // --- the warm-up sums --------------------------------------------------
    "Warm up your brain!": "Échauffe ton cerveau !",
    "Get these right and the factory opens for today.":
      "Réussis-les et la fabrique ouvre pour aujourd'hui.",
    "Get it right and the factory opens for today.":
      "Réussis-le et la fabrique ouvre pour aujourd'hui.",
    "Get all {n} right and the factory opens for today.":
      "Réussis les {n} et la fabrique ouvre pour aujourd'hui.",
    "Check my answers": "Vérifie mes réponses",
    "Fill them all in first!": "Remplis-les tous d'abord !",
    "All right! Off you go.": "Tout juste ! C'est parti.",
    "So close - one of those wasn't right. Here are some new ones!":
      "Tout près - il y en avait un de faux. En voilà des nouveaux !",
    "Not quite! Here are some new ones.": "Pas tout à fait ! En voilà des nouveaux.",
    "Something went wrong. Try again!": "Quelque chose n'a pas marché. Réessaie !",
    "I'm a grown-up": "Je suis un adulte",
    "Grown-up PIN": "Code des adultes",
    "Let me in": "Laisse-moi entrer",

    // --- the viewer --------------------------------------------------------
    "Pick a picture": "Choisis une image",
    "Pick where it starts": "Choisis où ça commence",
    "Pick where it ends": "Choisis où ça finit",
    "Done": "Terminé",
    "← Back": "← Retour",
    "What is it called?": "Ça s'appelle comment ?",
    "✏️ Give it a name": "✏️ Donne-lui un nom",
    "What you asked for": "Ce que tu as demandé",
    "What {name} asked for": "Ce que {name} a demandé",
    "{name} made this": "{name} a fait ça",
    "The words": "Les paroles",
    "Something you made": "Une de tes créations",
    "Something deleted": "Quelque chose de supprimé",
    "(music only - nobody sings on this one.)":
      "(juste la musique - personne ne chante sur celle-là.)",
    "(read back out of the file - this is the whole prompt, including the bits the dropdowns added.)":
      "(relu dans le fichier - c'est la description entière, avec ce que les " +
      "menus ont ajouté.)",
    "A drawing you made. Tap Animate this to bring it to life!":
      "Un dessin que tu as fait. Appuie sur Anime ça pour le faire bouger !",
    "A card you made. Print it, or share it!":
      "Une carte que tu as faite. Imprime-la, ou partage-la !",
    "A photo you added. Tap Animate this to bring it to life!":
      "Une photo que tu as ajoutée. Appuie sur Anime ça pour la faire bouger !",
    "This one's notes are lost - it was made before the app kept them, or straight from ComfyUI.":
      "Les notes de celle-là sont perdues - elle a été faite avant que " +
      "l'appli les garde, ou directement dans ComfyUI.",
    "☆ Favourite": "☆ Favori",
    "⭐ Favourite": "⭐ Favori",
    "⭐ Starred": "⭐ Préférée",
    "⭐ Starred!": "⭐ Préférée !",
    "☆ This one’s best": "☆ C'est la meilleure",
    "👨‍👩‍👧 Show the family": "👨‍👩‍👧 Montrer à la famille",
    "👨‍👩‍👧 Hide from the family": "👨‍👩‍👧 Cacher à la famille",
    "Everyone can see this one now! 👨‍👩‍👧":
      "Tout le monde peut la voir maintenant ! 👨‍👩‍👧",
    "Back to just you.": "De nouveau rien qu'à toi.",
    "🔁 Make another like this": "🔁 Fais-en une autre comme ça",
    "🎯 Make it again, but…": "🎯 Refais-la, mais…",
    "✨ Animate this": "✨ Anime ça",
    "🧑‍🎤 Save as a character": "🧑‍🎤 Garder comme personnage",
    "🎤 Say something over it": "🎤 Parle par-dessus",
    "✂️ Turn it into a sticker": "✂️ Transforme-la en autocollant",
    "✂️ Cutting it out...": "✂️ Je la découpe...",
    "🔍 Make it huge": "🔍 Rends-la géante",
    "🎨 Turn it into…": "🎨 Transforme-la en…",
    "🪄 Change this picture": "🪄 Change cette image",
    "🔭 What's outside the frame?": "🔭 Qu'y a-t-il autour ?",
    "🩹 Fix just this bit": "🩹 Répare juste ce bout",
    "🖼️ Put it at the top": "🖼️ Mets-la en haut",
    "👤 That one's me": "👤 C'est moi, celle-là",
    "🔊 Add a sound effect": "🔊 Ajoute un bruit",
    "📸 Grab a picture from it": "📸 Prends une image dedans",
    "✨ Make it smooth": "✨ Rends-la fluide",
    "🐌 Slow it down": "🐌 Ralentis-la",
    "🌀 Make a moving sticker": "🌀 Fais un autocollant animé",
    "✏️ Draw on it": "✏️ Dessine dessus",
    "🖨️ Print it": "🖨️ Imprime-la",
    "💌 Make a card": "💌 Fais une carte",
    "▶️ What happens next?": "▶️ Et après ?",
    "📤 Share": "📤 Partager",
    "⬇︎ Save it": "⬇︎ Enregistre-la",
    "↩️ Put it back": "↩️ Remets-la",
    "🗑️ Delete for good": "🗑️ Supprimer pour de bon",
    "In the trash": "À la corbeille",
    "Gone - it's in the trash.": "Partie - elle est à la corbeille.",
    "＋ Add a tag": "＋ Ajouter une étiquette",
    "What tag?": "Quelle étiquette ?",
    "What tag should these get?": "Quelle étiquette pour celles-ci ?",
    "\n\nAlready used: ": "\n\nDéjà utilisées : ",
    "{n} thing tagged “#{tag}”": "{n} chose étiquetée « #{tag} »",
    "{n} things tagged “#{tag}”": "{n} choses étiquetées « #{tag} »",
    "Couldn't open your gallery right now. Try again!":
      "Impossible d'ouvrir ta galerie pour l'instant. Réessaie !",
    "That one's turned off just now.": "Ça, c'est éteint en ce moment.",

    // --- what kind of thing a tile is --------------------------------------
    "📖 Comic": "📖 BD",
    "🧩 Panel": "🧩 Case",
    "📷 Photo": "📷 Photo",
    "🎬 Film": "🎬 Film",
    "🎤 My voice": "🎤 Ma voix",
    "🔊 Sound": "🔊 Bruit",
    "✂️ Sticker": "✂️ Autocollant",
    "📸 From a video": "📸 Tiré d'une vidéo",
    "🎵 Song": "🎵 Chanson",

    // --- what kind of sound: a song, a little tune, a background
    //     hum. One card and one model; see app/music.py KINDS.
    "What kind": "Quel genre",
    "What kind of sound to make": "Quel genre de son fabriquer",
    "Make my tune": "Fais mon petit air",
    "Make my sound": "Fais mon ambiance",
    "🎲 Thinking of a sound...": "🎲 Je cherche un son...",
    "Your tune is ready! ✨": "Ton petit air est prêt ! ✨",
    "Your sound is ready! ✨": "Ton ambiance est prête ! ✨",
    "Making a little tune": "Je fabrique un petit air",
    "Making a background hum": "Je fabrique une ambiance",
    "🎺 Little tune": "🎺 Petit air",
    "🌊 Background hum": "🌊 Ambiance",
    "✨ Smooth": "✨ Fluide",
    "🐌 Slow motion": "🐌 Ralenti",
    "🌀 Moving sticker": "🌀 Autocollant animé",
    "🔍 Huge": "🔍 Géante",
    "🪄 Changed": "🪄 Changée",
    "🔭 More of it": "🔭 Plus grande",
    "🩹 Fixed a bit": "🩹 Réparée",
    "🎨 A new style": "🎨 Nouveau style",
    "✏️ Drawing": "✏️ Dessin",
    "💌 Card": "💌 Carte",
    "▶ Video": "▶ Vidéo",

    // --- the result row ----------------------------------------------------
    "The picture you made": "L'image que tu as faite",
    "One of the pictures you made": "Une des images que tu as faites",
    "Your comic": "Ta BD",
    "🎲 Try again": "🎲 Réessaie",
    "⬇︎ Save picture": "⬇︎ Enregistre l'image",
    "⬇︎ Save video": "⬇︎ Enregistre la vidéo",
    "⬇︎ Save song": "⬇︎ Enregistre la chanson",
    "⬇︎ Save my film": "⬇︎ Enregistre mon film",
    "⬇︎ Save my comic": "⬇︎ Enregistre ma BD",
    "⬇︎ Save them all": "⬇︎ Enregistre-les toutes",
    "Keep this one": "Je garde celle-là",
    "✓ Kept": "✓ Gardée",
    "Delete this one": "Supprimer celle-là",
    "It's a sticker! ✂️": "C'est un autocollant ! ✂️",
    "It's ready! ✨": "C'est prêt ! ✨",
    "It's ready! 🔍": "C'est prêt ! 🔍",
    "Your very first picture! 🎉": "Ta toute première image ! 🎉",
    "Your very first video! 🎉": "Ta toute première vidéo ! 🎉",
    "Your very first comic! 🎉": "Ta toute première BD ! 🎉",
    "Your very first film! 🎉": "Ton tout premier film ! 🎉",
    "That's {n} pictures! 🎉": "Ça fait {n} images ! 🎉",
    "That's {n} videos! 🎉": "Ça fait {n} vidéos ! 🎉",
    "That's {n} comics! 🎉": "Ça fait {n} BD ! 🎉",
    "That's {n} films! 🎉": "Ça fait {n} films ! 🎉",

    // --- characters ---------------------------------------------------------
    "Character": "Personnage",
    "What's this character called?": "Il s'appelle comment, ce personnage ?",
    "Having a good look at {name}...": "Je regarde bien {name}...",
    "{name} can be in your next one! 🧑‍🎤":
      "{name} peut être dans la prochaine ! 🧑‍🎤",
    "That's {n} characters already! Say goodbye to one first, in the Gallery.":
      "Ça fait déjà {n} personnages ! Dis d'abord au revoir à l'un d'eux, dans la Galerie.",
    "Forget “{idea}”": "Oublier « {idea} »",
    "✏️ Rename": "✏️ Renommer",
    "🎨 How they look": "🎨 À quoi il ressemble",
    "👋 Say goodbye to them": "👋 Lui dire au revoir",
    "Nothing with them in it yet! Choose them under “Who’s in it?” and make something.":
      "Rien avec lui pour l'instant ! Choisis-le dans « Qui est dedans ? » et fabrique quelque chose.",
    "What should they be called?": "Il s'appelle comment ?",
    "One sentence saying what they look like. This gets used in every picture they're in, so be specific about colours and clothes.":
      "Une phrase qui dit à quoi il ressemble. Elle sert dans toutes les " +
      "images où il est, alors sois précise sur les couleurs et les habits.",
    "Said goodbye to {name}. Their pictures are still in the Gallery.":
      "Au revoir, {name}. Ses images sont toujours dans la Galerie.",
    "Couldn't load them just now.": "Impossible de les charger pour l'instant.",

    // --- the film and card makers -------------------------------------------
    "Make a film": "Faire un film",
    "{n} videos, in the order you chose them. It'll open with a title card - give it a name!":
      "{n} vidéos, dans l'ordre où tu les as choisies. Ça commence par un " +
      "carton-titre - donne-lui un nom !",
    "🎬 What's your film called?": "🎬 Ton film s'appelle comment ?",
    "The Great Pancake Adventure": "La Grande Aventure des Crêpes",
    "My Film": "Mon film",
    "{title} presents": "{title} présente",
    "Joining your film... this takes a little while.":
      "J'assemble ton film... ça prend un petit moment.",
    "Done! It's at the top of your videos.":
      "Fini ! C'est en haut de tes vidéos.",
    "Make a card": "Faire une carte",
    "Save my card": "Enregistre ma carte",
    "💌 What should it say?": "💌 Qu'est-ce qu'elle doit dire ?",
    "Happy birthday Grandma!": "Joyeux anniversaire Mamie !",
    "Card colour": "Couleur de carte",
    "Card colour {n}": "Couleur de carte {n}",
    "Made for you!": "Pour toi !",
    "made at {title}": "fait à {title}",
    "Saving your card...": "J'enregistre ta carte...",
    "Saved! It's in Photos & drawings - open it to print or share.":
      "Enregistrée ! Elle est dans Photos et dessins - ouvre-la pour l'imprimer ou la partager.",
    "My comic": "Ma BD",

    // --- their voice, sounds, frames, loops -----------------------------------
    "🎤 Say something": "🎤 Dis quelque chose",
    "✕ Close": "✕ Fermer",
    "Tap the big button and talk. Your voice goes on top of your video.":
      "Appuie sur le gros bouton et parle. Ta voix se met sur ta vidéo.",
    "Start talking": "Commence à parler",
    "Keep the video's own sound too (it goes quieter while you talk)":
      "Garder aussi le son de la vidéo (il baisse pendant que tu parles)",
    "✨ Put it on my video": "✨ Mets-la sur ma vidéo",
    "🔁 Record it again": "🔁 Recommence l'enregistrement",
    "🗑️ Throw the recording away": "🗑️ Jette l'enregistrement",
    "Or use a sound you already have": "Ou prends un son que tu as déjà",
    "This browser can't record here - that needs https. Pick a sound from your files below instead.":
      "Ce navigateur ne peut pas enregistrer ici - il faut du https. " +
      "Prends plutôt un son dans tes fichiers, en dessous.",
    "You haven't put it on your video yet!":
      "Tu ne l'as pas encore mise sur ta vidéo !",
    "Your iPad needs to say yes to the microphone first. Tap the big button again and choose Allow.":
      "Ton iPad doit d'abord dire oui au micro. Appuie encore sur le gros " +
      "bouton et choisis Autoriser.",
    "I can't find a microphone on this device. You can pick a sound from your files below instead.":
      "Je ne trouve pas de micro sur cet appareil. Tu peux prendre un son " +
      "dans tes fichiers, en dessous.",
    "The microphone didn't start ({why}). You can pick a sound from your files below instead.":
      "Le micro n'a pas démarré ({why}). Tu peux prendre un son dans tes " +
      "fichiers, en dessous.",
    "Putting your voice on it...": "Je mets ta voix dessus...",
    "Your voice is on it! 🎤": "Ta voix est dessus ! 🎤",
    "Pick a sound, slide to where you want it, then put it on.":
      "Choisis un bruit, glisse là où tu le veux, puis mets-le.",
    "When the sound happens": "Quand le bruit arrive",
    "Couldn't load the sounds.": "Impossible de charger les bruits.",
    "Putting it on...": "Je le mets...",
    "Sound added! 🔊": "Bruit ajouté ! 🔊",
    "📸 Grab a picture": "📸 Prendre une image",
    "Slide to the bit you like. The picture underneath is exactly what you'll keep.":
      "Glisse jusqu'au moment que tu aimes. L'image en dessous est " +
      "exactement celle que tu gardes.",
    "Which bit?": "Quel moment ?",
    "Which moment to keep": "Quel moment garder",
    "The picture you are about to keep": "L'image que tu vas garder",
    "✨ Keep this picture": "✨ Garde cette image",
    "Keeping it...": "Je la garde...",
    "Kept it as a picture! 📸": "Gardée comme image ! 📸",
    "Pick the bit you want and it'll loop for ever - a sticker that moves.":
      "Choisis le bout que tu veux et ça tournera en boucle pour toujours - " +
      "un autocollant qui bouge.",
    "Start here": "Commence ici",
    "Where the loop starts": "Où la boucle commence",
    "How long?": "Combien de temps ?",
    "How long the loop is": "La durée de la boucle",
    "1 second": "1 seconde",
    "2 seconds": "2 secondes",
    "Where your moving sticker starts": "Où ton autocollant animé commence",
    "✨ Make my sticker": "✨ Fais mon autocollant",
    "Making it...": "Je le fais...",
    "It moves! 🌀": "Ça bouge ! 🌀",

    // --- the three edits ----------------------------------------------------
    "Say what you'd like different and it'll make the same picture again with that changed.":
      "Dis ce que tu veux de différent et la même image sera refaite avec ce changement.",
    "The picture you're changing": "L'image que tu changes",
    "What should be different?": "Qu'est-ce qui doit changer ?",
    "make it night-time\ngive the fox a scarf":
      "mets-la la nuit\nmets une écharpe au renard",
    "make it night-time": "mets-la la nuit",
    "make it snowy": "mets de la neige",
    "add a rainbow": "ajoute un arc-en-ciel",
    "make it look like a painting": "fais-en une peinture",
    "put a hat on it": "mets-lui un chapeau",
    "make everything tiny": "rends tout minuscule",
    "...and put me in it 👤": "...et mets-moi dedans 👤",
    "✨ Go": "✨ C'est parti",
    "Tell me what should be different!": "Dis-moi ce qui doit changer !",
    "Changing your picture... 🪄": "Je change ton image... 🪄",
    "Pick a kind of picture and it'll draw this one again that way, with everything still where it is.":
      "Choisis un genre d'image et celle-ci sera redessinée comme ça, avec " +
      "tout à la même place.",
    "The picture you're turning into something else":
      "L'image que tu transformes en autre chose",
    "What to turn it into": "En quoi la transformer",
    "Anything else? (you don't have to say)":
      "Autre chose ? (tu n'es pas obligée de le dire)",
    "you don't have to say - or add your own twist: make it night-time":
      "tu n'es pas obligée - ou ajoute ton idée : mets-la la nuit",
    "Pick what to turn it into!": "Choisis en quoi la transformer !",
    "Drawing it again... 🎨": "Je la redessine... 🎨",
    "Pick a side and it'll invent what was just out of the picture.":
      "Choisis un côté et ce qui était juste en dehors de l'image sera inventé.",
    "The picture you're growing": "L'image que tu agrandis",
    "Which way?": "De quel côté ?",
    "Which way to grow": "De quel côté agrandir",
    "All round": "Tout autour",
    "⬅️ Left": "⬅️ Gauche",
    "➡️ Right": "➡️ Droite",
    "⬆️ Up": "⬆️ Haut",
    "⬇️ Down": "⬇️ Bas",
    "How much?": "Combien ?",
    "How much bigger": "Combien plus grand",
    "A bit": "Un peu",
    "A lot": "Beaucoup",
    "What's out there? (you don't have to say)":
      "Qu'y a-t-il là-bas ? (tu n'es pas obligée de le dire)",
    "you don't have to say - or try: a beach, more trees":
      "tu n'es pas obligée - ou essaie : une plage, plus d'arbres",
    "Looking outside the frame... 🔭": "Je regarde autour de l'image... 🔭",
    "Say what should be there instead, then tap Go.":
      "Dis ce qu'il faut mettre à la place, puis appuie sur C'est parti.",
    "Paint over the bit you want changed first!":
      "Peins d'abord par-dessus le bout que tu veux changer !",
    "Fixing that bit... 🩹": "Je répare ce bout... 🩹",
    "Slowing it right down... it comes out quiet 🐌":
      "Je la ralentis à fond... elle sortira sans le son 🐌",
    "Smoothing it out... ✨": "Je la rends fluide... ✨",
    "Making it huge... 🔍": "Je la rends géante... 🔍",
    "Cutting it out...": "Je la découpe...",

    // --- compare ------------------------------------------------------------
    "🔍 Which one?": "🔍 Laquelle ?",
    "Slide across to see one and then the other.":
      "Glisse pour voir l'une puis l'autre.",
    "The first one": "La première",
    "The second one": "La deuxième",
    "Slide between the two pictures": "Glisse entre les deux images",

    // --- the drawing pad ----------------------------------------------------
    "Draw something": "Dessine quelque chose",
    "Use my drawing": "Prends mon dessin",
    "Colour": "Couleur",
    "Colour {n}": "Couleur {n}",
    "Stamps": "Tampons",
    "Stamp {emoji}": "Tampon {emoji}",
    "Thin brush": "Pinceau fin",
    "Medium brush": "Pinceau moyen",
    "Thick brush": "Pinceau épais",
    "🧽 Rubber": "🧽 Gomme",
    "↶ Undo": "↶ Annuler",
    "Start again": "Recommencer",
    "What should be there instead?": "Qu'est-ce qu'il faut mettre à la place ?",
    "what should be there instead? e.g. a red party hat":
      "qu'est-ce qu'il faut mettre à la place ? par exemple un chapeau rouge",
    "Draw with your finger or a pencil. When you're done, tap <strong>Use my drawing</strong>.":
      "Dessine avec ton doigt ou un stylet. Quand tu as fini, appuie sur " +
      "<strong>Prends mon dessin</strong>.",
    "Paint over the bit you want changed, say what should be there, then tap <strong>Go</strong>.":
      "Peins par-dessus le bout à changer, dis ce qu'il faut mettre, puis " +
      "appuie sur <strong>C'est parti</strong>.",

    // --- the chat tab -------------------------------------------------------
    "Chat with": "Discute avec",
    "Ask for an idea, or tell me what you’re making. Your grown-ups can read everything said here.":
      "Demande une idée, ou raconte ce que tu fabriques. Tes adultes peuvent " +
      "lire tout ce qui se dit ici.",
    "Your chat": "Ta discussion",
    "Say something": "Dis quelque chose",
    "Say something…": "Dis quelque chose…",
    "Send it": "Envoie",
    "Start a new chat": "Commencer une nouvelle discussion",
    "Started a new chat. Your grown-ups can still see the old one.":
      "Nouvelle discussion. Tes adultes peuvent encore voir l'ancienne.",
    "The chat helper isn't set up on this machine yet. Everything else still works!":
      "L'aide-chat n'est pas encore installée sur cet ordinateur. Tout le reste marche !",
    "Give me an idea for a picture": "Donne-moi une idée de dessin",
    "What can I make here?": "Qu'est-ce que je peux fabriquer ici ?",
    // The third starter exists to show them they can write in the other
    // language, so on a French page it is the English one.
    "Donne-moi une idée de dessin": "Give me a drawing idea",
    "🎨 Make a picture of this": "🎨 Fais une image de ça",
    "🎬 Make a video of this": "🎬 Fais une vidéo de ça",
    "📋 Copy": "📋 Copier",
    "✓ Copied": "✓ Copié",
    "✕ Couldn't copy": "✕ Copie impossible",
    "That's what {name} said. Change anything you like, or tap “Help me write it” to turn it into a proper description.":
      "C'est ce que {name} a dit. Change ce que tu veux, ou appuie sur " +
      "« Aide-moi à l'écrire » pour en faire une vraie description.",
    "the helper": "l'aide",

    // --- Settings -----------------------------------------------------------
    "You": "Toi",
    "You're {name}!": "Tu es {name} !",
    "🪄 Make a picture of me": "🪄 Fais une image de moi",
    "😃 Pick a face instead": "😃 Choisis plutôt une tête",
    "↩️ Back to the face": "↩️ Revenir à la tête",
    "Pick a face": "Choisis une tête",
    "Colours": "Couleurs",
    "Language": "Langue",
    "Which language": "Quelle langue",
    "The top of your page": "Le haut de ta page",
    "What is across the top of your page now":
      "Ce qu'il y a en haut de ta page en ce moment",
    "↩️ Put the first one back": "↩️ Remets celle du début",
    "Put back the one it came with.": "J'ai remis celle du début.",
    "Couldn't change it back.": "Impossible de la remettre.",
    "Making new ones is switched off right now, but you can still use any picture from <strong>Gallery</strong> — open one and tap <strong>Put it at the top</strong>.":
      "Faire de nouvelles bannières est éteint pour le moment, mais tu peux " +
      "encore prendre n'importe quelle image dans la <strong>Galerie</strong> " +
      "— ouvre-en une et appuie sur <strong>Mets-la en haut</strong>.",
    "It's a long thin strip, so wide things work best — a row of something, a view, a pattern. Your name goes on top of it, so leave the middle fairly quiet.":
      "C'est une longue bande fine, donc ce qui est large marche mieux — une " +
      "rangée de quelque chose, un paysage, un motif. Ton nom se met dessus, " +
      "alors laisse le milieu assez calme.",
    "🖼️ Putting it up...": "🖼️ Je la mets en haut...",
    "That's the top of your page now! 🖼️":
      "C'est le haut de ta page maintenant ! 🖼️",
    "That one wouldn't go up there.": "Celle-là ne va pas là-haut.",
    "Kept it on this device, but it wouldn't save.":
      "Gardé sur cet appareil, mais ça n'a pas pu être enregistré.",
    "Tap your face. A grown-up adds and changes these on the parent page.":
      "Appuie sur ta tête. Un adulte les ajoute et les change sur la page des parents.",
    "👤 Making it you...": "👤 Je fais que c'est toi...",
    "That's you now! 👤": "C'est toi maintenant ! 👤",
    "I'm a grown-up — the parent page": "Je suis un adulte — la page des parents",

    // --- who is making things today -----------------------------------------
    "Who's making things today?": "Qui fabrique aujourd'hui ?",

    // --- the picture-of-me wizard -------------------------------------------
    "Make a picture of me": "Une image de moi",
    "1. What are you?": "1. Tu es quoi ?",
    "What are you?": "Tu es quoi ?",
    "Or type your own": "Ou écris le tien",
    "…or type your own": "…ou écris le tien",
    "2. What colour?": "2. De quelle couleur ?",
    "What colour?": "De quelle couleur ?",
    "3. Anything else?": "3. Autre chose ?",
    "Anything else?": "Autre chose ?",
    "Anything else": "Autre chose",
    "…a wizard hat, freckles, a scarf":
      "…un chapeau de sorcier, des taches de rousseur, une écharpe",
    "Let's make it! ✨": "On la fait ! ✨",
    "It makes four at once so you can pick your favourite. Then tap <strong>👤 That one's me</strong> under the one you like.":
      "Ça en fait quatre d'un coup pour que tu choisisses ta préférée. Puis " +
      "appuie sur <strong>👤 C'est moi, celle-là</strong> sous celle que tu aimes.",
    "Pick what you are to get started!": "Choisis ce que tu es pour commencer !",
    "Pick what you are first!": "Choisis d'abord ce que tu es !",
    "Making pictures is switched off right now.":
      "Faire des images est éteint pour le moment.",
    "Tap Go and pick your favourite! ✨":
      "Appuie sur le bouton et choisis ta préférée ! ✨",
    // The wizard's choices. The sentence they compose is a prompt, so the
    // article travels with the word in French, where gender does too.
    "a fox": "un renard", "a cat": "un chat", "a dog": "un chien",
    "a dragon": "un dragon", "a robot": "un robot", "an owl": "une chouette",
    "a unicorn": "une licorne", "a penguin": "un pingouin",
    "an astronaut": "un astronaute", "a wizard": "un magicien",
    "a superhero": "un superhéros", "a pirate": "un pirate",
    "a mermaid": "une sirène", "a knight": "un chevalier",
    "a panda": "un panda", "an octopus": "une pieuvre",
    // "en violet" rather than "violet": the colour then agrees with nothing,
    // so one word does for a fox and for a mermaid alike.
    "purple": "violet", "blue": "bleu", "green": "vert",
    "orange": "orange", "pink": "rose", "red": "rouge",
    "yellow": "jaune", "rainbow": "arc-en-ciel", "silver": "argenté",
    "golden": "doré",
    "a wizard hat": "un chapeau de sorcier",
    "big round glasses": "de grandes lunettes rondes",
    "a stripy scarf": "une écharpe rayée",
    "a cape": "une cape", "headphones": "un casque",
    "a flower crown": "une couronne de fleurs", "a bow tie": "un nœud papillon",
    "freckles": "des taches de rousseur",

    // --- when it is shut -----------------------------------------------------
    "just now": "à l'instant",
    "{n} minute ago": "il y a {n} minute",
    "{n} minutes ago": "il y a {n} minutes",
    "{n} hour ago": "il y a {n} heure",
    "{n} hours ago": "il y a {n} heures",
    "{n} KB": "{n} ko",
    "{n} MB": "{n} Mo",

    // The close button on every sheet. Static markup, so it is a
    // data-i18n and not a t() - and it was English in every language
    // until the coverage walk went looking for exactly this.
    "✕ Close": "✕ Fermer",

    // --- the story maker -----------------------------------------------------
    "Song": "Chanson",
    // The bar says these for the second between the tap and the first poll;
    // after that they come from the server, already in their language.
    "Thinking up your picture...": "On imagine ton image...",
    "Working out the tune...": "On trouve l'air...",
    "Story": "Histoire",
    "Story maker": "Créateur d'histoires",
    "One idea, all the way to a little film with its own song. One step at a time.":
      "Une idée, jusqu'à un petit film avec sa propre chanson. Une étape à la fois.",
    "Idea": "Idée",
    "Film": "Film",
    "Together": "Ensemble",
    "A fox who builds a rocket out of junk in the garden":
      "Un renard qui construit une fusée avec des vieux trucs du jardin",
    "How long each part is": "La durée de chaque partie",
    "The film's sound": "Le son du film",
    "Keep the film's own sound under the song":
      "Garder le son du film sous la chanson",
    "That's my story!": "C'est mon histoire !",
    "Skip this bit": "Passer cette étape",
    "Next →": "Suite →",
    "First, what happens? A beginning, a middle and an end.":
      "D'abord, qu'est-ce qui se passe ? Un début, un milieu et une fin.",
    "🎨 Draw the opening picture": "🎨 Dessine la première image",
    "Now the very first thing we see. You can keep trying until you like it.":
      "Maintenant la toute première chose qu'on voit. Tu peux réessayer jusqu'à ce qu'elle te plaise.",
    "🎬 Film it!": "🎬 Filme-la !",
    "Each part carries on from the last frame of the one before.":
      "Chaque partie repart de la dernière image de celle d'avant.",
    "🎵 Write a song for it": "🎵 Écris une chanson pour l'histoire",
    "Words about your story, as long as your film.":
      "Des paroles sur ton histoire, aussi longues que ton film.",
    "✨ Put it all together": "✨ Assemble le tout",
    "Your song, under your film. This is the last bit!":
      "Ta chanson, sous ton film. C'est la dernière étape !",
    "the opening picture": "la première image",
    "the song": "la chanson",
    "One bit is switched off right now: {what}. The rest still works!":
      "Une étape est éteinte pour le moment : {what}. Le reste marche quand même !",
    "Two bits are switched off right now: {what} and {other}. The rest still works!":
      "Deux étapes sont éteintes pour le moment : {what} et {other}. Le reste marche quand même !",
    "Writing the words...": "J'écris les paroles...",
    "Putting your story together...": "J'assemble ton histoire...",
    "Your story is ready!": "Ton histoire est prête !",
    "🔁 Make another": "🔁 Refais-en une autre",
    "⬇︎ Save my story": "⬇︎ Garder mon histoire",
    "🎭 Start a new story": "🎭 Commence une nouvelle histoire",
    "Make the film and the song first!":
      "Fais d'abord le film et la chanson !",
    "🎭 Story film": "🎭 Film-histoire",
  };


  // German. The same keys in the same order under the same headings
  // as FR above, so a line missing from one of them is a line out of step.
  var DE = {
    // --- the shell ------------------------------------------------------
    "My AI Factory": "Meine KI-Fabrik",
    "AI Factory": "KI-Fabrik",
    "What would you like to do?": "Was möchtest du machen?",
    "That's me - tap to swap": "Das bin ich - tipp zum Wechseln",
    "Show me": "Zeig mal",
    "Working...": "Ich arbeite...",
    "wiz-sentence":
      "{thing}, {colour}ganz freundlich{wearing}, ein fröhliches " +
      "Cartoon-Porträt, Kopf und Schultern, große freundliche Augen",
    "wiz-wearing": " mit {list}",
    "wiz-and": " und ",
    "wiz-colour": "in {colour}, ",

    // Tabs. Short on purpose: seven of them share one row at 390px.
    "Picture": "Bild",
    "Video": "Video",
    "Comic": "Comic",
    "Music": "Musik",
    "Chat": "Chat",
    "Gallery": "Galerie",
    "Settings": "Optionen",

    // --- "your picture is ready" ----------------------------------------
    "Your picture is ready! ✨": "Dein Bild ist fertig! ✨",
    "Your video is ready! ✨": "Dein Video ist fertig! ✨",
    "Your comic is ready! ✨": "Dein Comic ist fertig! ✨",
    "Your film is ready! ✨": "Dein Film ist fertig! ✨",
    "Your song is ready! ✨": "Dein Lied ist fertig! ✨",
    "Your smooth video is ready! ✨": "Dein flüssiges Video ist fertig! ✨",
    "Your slow-motion video is ready! ✨": "Deine Zeitlupe ist fertig! ✨",
    "Your big picture is ready! ✨": "Dein großes Bild ist fertig! ✨",
    "Your bigger picture is ready! ✨": "Dein Riesenbild ist fertig! ✨",
    "Your changed picture is ready! ✨": "Dein geändertes Bild ist fertig! ✨",

    // --- the Gallery ------------------------------------------------------
    "Everything you've made is saved here.":
      "Alles, was du machst, wird hier aufbewahrt.",
    "Nothing here yet! Make a picture, a video or a comic and it'll turn up here.":
      "Noch nichts da! Mach ein Bild, ein Video oder einen Comic, dann " +
      "taucht es hier auf.",
    "Nothing of yours yet - but there's something on the family shelf!":
      "Von dir noch nichts - aber im Familien-Regal liegt was!",
    "You've made 1 thing so far.": "Du hast bis jetzt 1 Sache gemacht.",
    "You've made {n} things so far.": "Du hast bis jetzt {n} Sachen gemacht.",
    "🧑‍🎤 My characters": "🧑‍🎤 Meine Figuren",
    "Show": "Zeigen",
    "How to show your gallery": "Wie deine Galerie gezeigt wird",
    "Everything": "Alles",
    "In groups": "In Gruppen",
    "Order": "Sortierung",
    "What order to show them in": "In welcher Reihenfolge sie gezeigt werden",
    "Newest": "Neueste",
    "Oldest": "Älteste",
    "⭐ Favourites": "⭐ Favoriten",
    "By kind": "Nach Art",
    "🔎 Find something you made": "🔎 Finde etwas von dir",
    "Search your gallery": "Deine Galerie durchsuchen",
    "Clear the search": "Suche löschen",
    "Choose": "Auswählen",
    "Cancel": "Abbrechen",
    "👨‍👩‍👧 Family": "👨‍👩‍👧 Familie",
    "🎨 Pictures": "🎨 Bilder",
    "📖 Comics": "📖 Comics",
    "🧩 Comic pictures": "🧩 Comic-Bilder",
    "✂️ Stickers": "✂️ Sticker",
    "📷 Photos & drawings": "📷 Fotos & Zeichnungen",
    "🎬 Videos": "🎬 Videos",
    "🎵 Songs": "🎵 Lieder",
    "Nothing matches that. Try another word!":
      "Dazu gibt es nichts. Probier ein anderes Wort!",
    "Nothing here yet! Go and make something.":
      "Noch nichts da! Geh und mach was.",
    "🗑️ Recently deleted": "🗑️ Zuletzt gelöscht",
    "Things stay here for {days} days, then they're gone for good. Tap one to put it back.":
      "Sachen bleiben {days} Tage hier, dann sind sie für immer weg. Tipp " +
      "eine an, um sie zurückzuholen.",
    "Nothing chosen yet": "Noch nichts ausgewählt",
    "Tap the ones you want": "Tipp die an, die du willst",
    "1 chosen": "1 ausgewählt",
    "{n} chosen": "{n} ausgewählt",
    "Choose all": "Alle auswählen",
    "Choose none": "Nichts auswählen",
    "🎬 Join into a film": "🎬 Zu einem Film machen",
    "🔍 Compare them": "🔍 Vergleichen",
    "🏷️ Add a tag": "🏷️ Etikett anhängen",
    "⬇︎ Save": "⬇︎ Speichern",
    "🗑️ Delete": "🗑️ Löschen",
    "Deleted": "Gelöscht",
    "{n} things deleted": "{n} Sachen gelöscht",
    "Undo": "Rückgängig",
    "Put back!": "Zurückgeholt!",
    "All put back!": "Alle zurückgeholt!",
    "Really delete?": "Wirklich löschen?",
    "Really delete it?": "Das wirklich löschen?",
    "Really delete all {n}?": "Wirklich alle {n} löschen?",
    "Really delete forever?": "Für immer löschen?",
    "Really clear it?": "Wirklich alles löschen?",
    "Really say goodbye?": "Wirklich Tschüss sagen?",

    // --- the maker cards -------------------------------------------------
    "Make a picture": "Bild machen",
    "Make a video": "Video machen",
    "Make a comic": "Comic machen",
    "Make a song": "Lied machen",
    "↺ Start again": "↺ Von vorn",
    "Clear everything on this card and start again":
      "Alles auf dieser Karte löschen und von vorn anfangen",
    "What should the picture be?": "Was soll auf dem Bild sein?",
    "What should the video be?": "Was soll im Video passieren?",
    "What's your story?": "Wie geht deine Geschichte?",
    "What should the song be about?": "Worum geht es in dem Lied?",
    "What should the top of your page look like?":
      "Wie soll der Kopf deiner Seite aussehen?",
    "A fluffy dragon eating pancakes on the moon":
      "Ein flauschiger Drache isst Pfannkuchen auf dem Mond",
    "A puppy surfing a giant wave at sunset":
      "Ein Hundebaby surft bei Sonnenuntergang auf einer Riesenwelle",
    "It flaps its wings and flies up into the clouds":
      "Er schlägt mit den Flügeln und fliegt hoch in die Wolken",
    "The cat walks across the room and curls up in the sunny spot":
      "Die Katze läuft durchs Zimmer und rollt sich im Sonnenfleck zusammen",
    "A little robot looking for its lost cat in a big city":
      "Ein kleiner Roboter sucht seine Katze in einer großen Stadt",
    "A hedgehog who wants to learn to swim":
      "Ein Igel, der schwimmen lernen will",
    "A dragon who is scared of pancakes":
      "Ein Drache, der Angst vor Pfannkuchen hat",
    "A row of hot air balloons over a green valley":
      "Eine Reihe Heißluftballons über einem grünen Tal",
    "Clear what you typed": "Löschen, was du geschrieben hast",
    "✨ Help me write it": "✨ Hilf mir beim Schreiben",
    "👀 Look at my picture and help me write it":
      "👀 Schau dir mein Bild an und hilf mir",
    "✨ Write me a song": "✨ Schreib mir ein Lied",
    "🎉 Surprise me": "🎉 Überrasch mich",
    "🎲 Mix it up": "🎲 Misch alles",
    "📜 Things I've asked for before": "📜 Was ich schon gefragt habe",
    "📷 Start from a photo": "📷 Mit einem Foto anfangen",
    "🖼️ Pick one from my gallery": "🖼️ Eins aus meiner Galerie",
    "Who's in it?": "Wer ist dabei?",
    "Nobody": "Niemand",
    "📄 Everything with {name} in it": "📄 Alles mit {name} drin",
    "Make": "Machen",
    "What kind of picture": "Was für ein Bild",
    "A picture": "Ein Bild",
    "A character": "Eine Figur",
    "Drawn on its own with nothing behind it, so you can cut it out as a sticker or keep them as a character.":
      "Ganz allein gezeichnet, ohne etwas dahinter - so kannst du es als " +
      "Sticker ausschneiden oder als Figur behalten.",
    "Shape": "Form",
    "Picture shape": "Form des Bildes",
    "Video shape": "Form des Videos",
    "Landscape": "Quer",
    "Portrait": "Hoch",
    "Square": "Quadrat",
    "landscape": "quer",
    "portrait": "hoch",
    "square": "quadratisch",
    "How many": "Wie viele",
    "How many pictures": "Wie viele Bilder",
    "How many panels": "Wie viele Kästchen",
    "Just one": "Nur eins",
    "Four to pick from": "Vier zur Auswahl",
    "3 pictures": "3 Bilder",
    "4 pictures": "4 Bilder",
    "6 pictures": "6 Bilder",
    "Look": "Aussehen",
    "Look and sound": "Bild und Ton",
    "Sound": "Ton",
    "Clear these": "Alles löschen",
    "Any": "Egal",
    "Make my picture": "Bild machen!",
    "Make {n} pictures": "{n} Bilder machen",
    "Make my video": "Video machen!",
    "Make my film": "Film machen!",
    "Animate it": "Beweg es!",
    "Make my comic": "Comic machen!",
    "Make my song": "Lied machen!",
    "Make my music": "Musik machen!",
    "Make one": "Mach eins!",
    "Stop": "Stopp",
    "Tell a story and it gets drawn as a comic strip you can print.":
      "Erzähl eine Geschichte und sie wird als Comic gezeichnet, zum " +
      "Ausdrucken.",

    // video card
    "Start from": "Anfangen mit",
    "What to start the video from": "Womit das Video anfängt",
    "✏️ Words": "✏️ Wörter",
    "🖼️ A picture": "🖼️ Ein Bild",
    "🎞️ Two pictures": "🎞️ Zwei Bilder",
    "📽️ A little film": "📽️ Ein kleiner Film",
    "Make a picture up above and tap <strong>Animate this</strong>, or use a photo from your iPad.":
      "Mach oben ein Bild und tipp auf <strong>Beweg das</strong>, oder " +
      "nimm ein Foto von deinem iPad.",
    "The picture you picked": "Das Bild, das du ausgesucht hast",
    "This picture is ready to animate!": "Dieses Bild ist bereit zum Bewegen!",
    "Use a different one": "Ein anderes nehmen",
    "📷 Take or choose a photo": "📷 Foto machen oder aussuchen",
    "✏️ Draw one": "✏️ Selbst malen",
    "Pick where the video starts and where it ends. The middle gets made up.":
      "Such aus, wo das Video anfängt und wo es aufhört. Die Mitte wird " +
      "erfunden.",
    "Starts on": "Fängt an mit",
    "Ends on": "Hört auf mit",
    "🖼️ Pick from the gallery": "🖼️ Aus der Galerie",
    "🖼️ Pick a different one": "🖼️ Ein anderes nehmen",
    "🗣️ What should they say?": "🗣️ Was sollen sie sagen?",
    "(you can leave this empty)": "(du kannst das leer lassen)",
    "Look at the Earth from up here!": "Schau mal, die Erde von hier oben!",
    "Clear what they say": "Löschen, was sie sagen",
    "🔊 Videos have sound — they'll say this out loud, so keep it short.":
      "🔊 Videos haben Ton — das wird laut gesagt, also mach es kurz.",
    "Quality": "Qualität",
    "Video quality": "Qualität des Videos",
    "⚡ Quick": "⚡ Schnell",
    "👍 Normal": "👍 Normal",
    "✨ Sharper": "✨ Schärfer",
    "Sharper means more detail, but it takes a good deal longer to make, and the longest a sharper video can be is":
      "Schärfer heißt mehr Details, dauert aber viel länger, und ein " +
      "schärferes Video darf höchstens",
    "seconds.": "Sekunden lang sein.",
    "How long": "Wie lang",
    "Video length in seconds": "Länge des Videos in Sekunden",
    "How long the song is, in seconds": "Länge des Liedes in Sekunden",
    "{n} seconds": "{n} Sekunden",
    "Longer videos take longer to make.": "Längere Videos dauern länger.",
    "Longer songs take longer to make.": "Längere Lieder dauern länger.",
    "How many parts": "Wie viele Teile",
    "2 parts": "2 Teile",
    "3 parts": "3 Teile",
    "4 parts": "4 Teile",
    "Each part carries on from the last one, then they're joined into one film. It takes a while, and it uses up one video for each part.":
      "Jeder Teil macht da weiter, wo der letzte aufgehört hat, dann wird " +
      "alles zu einem Film. Das dauert eine Weile und braucht ein Video " +
      "pro Teil.",
    "🔊 Add a sound": "🔊 Geräusch dazu",
    "None": "Keins",
    "When?": "Wann?",
    "At the start": "Am Anfang",
    "In the middle": "In der Mitte",
    "At the end": "Am Ende",

    // music card
    "Singing": "Gesang",
    "Singing or not": "Mit Gesang oder ohne",
    "With singing": "Mit Gesang",
    "Just music": "Nur Musik",
    "Words": "Text",
    "Clear the words": "Text löschen",
    "[Verse]\nI met a dragon on the stairs\nHe said he doesn't like éclairs\n\n[Chorus]\nPancakes, pancakes, run away!":
      "[Strophe]\nIch traf einen Drachen im Treppenhaus\nEr mag keine " +
      "Kekse, er lacht sie aus\n\n[Refrain]\nPfannkuchen, Pfannkuchen, " +
      "lauf schnell raus!",
    "Put <strong>[Verse]</strong> or <strong>[Chorus]</strong> on a line of their own to mark the parts. Leave it empty and you'll get music with nobody singing.":
      "Schreib <strong>[Strophe]</strong> oder <strong>[Refrain]</strong> " +
      "in eine eigene Zeile, um die Teile zu markieren. Lass es leer, dann " +
      "gibt es Musik, bei der niemand singt.",

    // --- the helpers -----------------------------------------------------
    "Type a few words about your idea first!":
      "Schreib erst ein paar Wörter zu deiner Idee!",
    "Thinking of ideas...": "Ich suche Ideen...",
    "Looking at your picture...": "Ich schaue mir dein Bild an...",
    "This takes a moment the first time.": "Beim ersten Mal dauert das kurz.",
    "Here you go! Change anything you like.":
      "Bitte schön! Ändere alles, was du willst.",
    "Here's an idea for it - change anything you like.":
      "Hier eine Idee - ändere alles, was du willst.",
    "Writing your song...": "Ich schreibe dein Lied...",
    "Here are some words! Change any line you like - they don't have to rhyme.":
      "Hier ist ein Text! Ändere jede Zeile, die du willst - es muss sich " +
      "nicht reimen.",
    "🎲 Thinking of something...": "🎲 Ich überlege...",
    "🎲 Writing a song...": "🎲 Ich schreibe ein Lied...",
    "Dreaming up an idea...": "Ich erfinde eine Idee...",
    "Here's a whole song! Change any line you like.":
      "Hier ist ein ganzes Lied! Ändere jede Zeile, die du willst.",
    "Here's an idea! Change anything you like.":
      "Hier ist eine Idee! Ändere alles, was du willst.",
    "One of your old ideas with a brand new look. Change anything you like!":
      "Eine alte Idee von dir in ganz neuem Look. Ändere, was du willst!",
    "A brand new idea. Change anything you like!":
      "Eine ganz neue Idee. Ändere, was du willst!",
    "🎲 Shuffling...": "🎲 Ich mische...",
    "Same as before - change anything you like, then go!":
      "Wie vorher - ändere, was du willst, und dann los!",
    "Change a word or two and you'll get this same one, but different. “Make another like this” starts from scratch instead.":
      "Ändere ein, zwei Wörter und du bekommst dasselbe, nur anders. „Noch " +
      "so eins“ fängt dagegen von vorn an.",
    "Your drawing is ready! Tap the helper to get a script for it, or say what should happen.":
      "Deine Zeichnung ist fertig! Tipp auf die Hilfe für einen Text, oder " +
      "sag, was passieren soll.",
    "This starts where that video stopped. What happens next?":
      "Das fängt da an, wo das Video aufgehört hat. Was passiert jetzt?",

    // --- while it renders -------------------------------------------------
    "Sending it off...": "Ich schicke es los...",
    "Getting started...": "Es geht los...",
    "Starting": "Start",
    "Making another one...": "Ich mache noch eins...",
    "Getting it ready...": "Ich mache alles bereit...",
    "Working out your story...": "Ich denke mir deine Geschichte aus...",
    "Reading your story...": "Ich lese deine Geschichte...",
    "Putting your comic together...": "Ich baue deinen Comic zusammen...",
    "Stopping...": "Ich höre auf...",
    "Stopped! Nothing was made. Try a different idea.":
      "Gestoppt! Es wurde nichts gemacht. Probier eine andere Idee.",
    "Couldn't stop it — it may finish anyway.":
      "Konnte es nicht stoppen — vielleicht wird es trotzdem fertig.",
    "Something went wrong. Let's try that again!":
      "Da ist was schiefgegangen. Probieren wir es nochmal!",
    "Pick a picture first — make one above, or use a photo!":
      "Such erst ein Bild aus — mach oben eins, oder nimm ein Foto!",
    "Pick a picture to start on and one to end on!":
      "Such ein Bild für den Anfang und eins für das Ende aus!",
    "Type something you'd like to make first!":
      "Schreib erst auf, was du machen möchtest!",
    "Sending your photo...": "Ich schicke dein Foto...",
    "It's in your gallery! Now pick what to do with it ✨":
      "Es ist in deiner Galerie! Jetzt such aus, was du damit machst ✨",
    "✅ Ready!": "✅ Fertig!",
    "Took {time}.": "Hat {time} gedauert.",
    "{n} seconds long": "{n} Sekunden lang",
    "{n} second": "{n} Sekunde",
    "{n} secs": "{n} Sek.",
    "about {n} seconds": "etwa {n} Sekunden",
    "about a minute": "etwa eine Minute",
    "about {n} minutes": "etwa {n} Minuten",
    "{time} so far": "{time} bisher",
    "about {time} to go": "noch etwa {time}",
    "⏱️ I haven't made one of these yet — I'll time this one.":
      "⏱️ So eins habe ich noch nie gemacht — ich stoppe die Zeit.",
    "⏱️ Takes {time} on this computer.":
      "⏱️ Dauert {time} auf diesem Computer.",
    "⏱️ Probably takes {time}.": "⏱️ Dauert wohl {time}.",

    // --- the allowance and the clock --------------------------------------
    "🌙 That's all the pictures for today. See you tomorrow!":
      "🌙 Das waren alle Bilder für heute. Bis morgen!",
    "🌙 That's all the videos for today. See you tomorrow!":
      "🌙 Das waren alle Videos für heute. Bis morgen!",
    "🌙 That's all the songs for today. See you tomorrow!":
      "🌙 Das waren alle Lieder für heute. Bis morgen!",
    "✨ {n} pictures left today, so that's how many you'll get.":
      "✨ Heute sind noch {n} Bilder übrig, so viele bekommst du.",
    "✨ {n} videos left today, so that's how many you'll get.":
      "✨ Heute sind noch {n} Videos übrig, so viele bekommst du.",
    "✨ {n} songs left today, so that's how many you'll get.":
      "✨ Heute sind noch {n} Lieder übrig, so viele bekommst du.",
    "✨ 1 picture left today, so that's how many you'll get.":
      "✨ Heute ist noch 1 Bild übrig, das bekommst du.",
    "✨ 1 video left today, so that's how many you'll get.":
      "✨ Heute ist noch 1 Video übrig, das bekommst du.",
    "✨ 1 song left today, so that's how many you'll get.":
      "✨ Heute ist noch 1 Lied übrig, das bekommst du.",
    "✨ One more picture today - make it a good one!":
      "✨ Heute noch ein Bild - mach ein schönes!",
    "✨ One more video today - make it a good one!":
      "✨ Heute noch ein Video - mach ein schönes!",
    "✨ One more song today - make it a good one!":
      "✨ Heute noch ein Lied - mach ein schönes!",
    "✨ {n} more pictures today": "✨ Heute noch {n} Bilder",
    "✨ {n} more videos today": "✨ Heute noch {n} Videos",
    "✨ {n} more songs today": "✨ Heute noch {n} Lieder",
    "The factory closes at {at} - any minute now!":
      "Die Fabrik macht um {at} zu - jeden Moment!",
    "closes-in": "Die Fabrik macht um {at} zu - noch etwa {mins} Minuten.",
    "The factory is closed right now": "Die Fabrik ist gerade zu",
    "Back soon!": "Bis gleich!",

    // --- the warm-up sums --------------------------------------------------
    "Warm up your brain!": "Wärm dein Gehirn auf!",
    "Get these right and the factory opens for today.":
      "Mach die Aufgaben richtig und die Fabrik macht für heute auf.",
    "Get it right and the factory opens for today.":
      "Mach die Aufgabe richtig und die Fabrik macht für heute auf.",
    "Get all {n} right and the factory opens for today.":
      "Mach alle {n} richtig und die Fabrik macht für heute auf.",
    "Check my answers": "Antworten prüfen",
    "Fill them all in first!": "Füll erst alle aus!",
    "All right! Off you go.": "Alles richtig! Los geht's.",
    "So close - one of those wasn't right. Here are some new ones!":
      "Fast - eine war falsch. Hier sind neue!",
    "Not quite! Here are some new ones.": "Nicht ganz! Hier sind neue.",
    "Something went wrong. Try again!":
      "Da ist was schiefgegangen. Probier nochmal!",
    "I'm a grown-up": "Ich bin erwachsen",
    "Grown-up PIN": "Erwachsenen-PIN",
    "Let me in": "Lass mich rein",

    // --- the viewer --------------------------------------------------------
    "Pick a picture": "Such ein Bild aus",
    "Pick where it starts": "Such den Anfang aus",
    "Pick where it ends": "Such das Ende aus",
    "Done": "Fertig",
    "← Back": "← Zurück",
    "What is it called?": "Wie heißt es?",
    "✏️ Give it a name": "✏️ Gib ihm einen Namen",
    "What you asked for": "Was du gewünscht hast",
    "What {name} asked for": "Was {name} gewünscht hat",
    "{name} made this": "{name} hat das gemacht",
    "The words": "Der Text",
    "Something you made": "Etwas von dir",
    "Something deleted": "Etwas Gelöschtes",
    "(music only - nobody sings on this one.)":
      "(nur Musik - hier singt niemand.)",
    "(read back out of the file - this is the whole prompt, including the bits the dropdowns added.)":
      "(aus der Datei gelesen - das ist die ganze Beschreibung, mit allem, " +
      "was die Menüs dazugetan haben.)",
    "A drawing you made. Tap Animate this to bring it to life!":
      "Eine Zeichnung von dir. Tipp auf Beweg das, damit sie lebendig wird!",
    "A card you made. Print it, or share it!":
      "Eine Karte von dir. Druck sie aus oder verschick sie!",
    "A photo you added. Tap Animate this to bring it to life!":
      "Ein Foto von dir. Tipp auf Beweg das, damit es lebendig wird!",
    "This one's notes are lost - it was made before the app kept them, or straight from ComfyUI.":
      "Die Notizen dazu sind weg - es entstand, bevor die App sie " +
      "aufbewahrt hat, oder direkt in ComfyUI.",
    "☆ Favourite": "☆ Favorit",
    "⭐ Favourite": "⭐ Favorit",
    "⭐ Starred": "⭐ Markiert",
    "⭐ Starred!": "⭐ Markiert!",
    "☆ This one’s best": "☆ Das ist das beste",
    "👨‍👩‍👧 Show the family": "👨‍👩‍👧 Der Familie zeigen",
    "👨‍👩‍👧 Hide from the family": "👨‍👩‍👧 Vor der Familie verstecken",
    "Everyone can see this one now! 👨‍👩‍👧":
      "Jetzt können es alle sehen! 👨‍👩‍👧",
    "Back to just you.": "Wieder nur für dich.",
    "🔁 Make another like this": "🔁 Noch so eins",
    "🎯 Make it again, but…": "🎯 Nochmal, aber…",
    "✨ Animate this": "✨ Beweg das",
    "🧑‍🎤 Save as a character": "🧑‍🎤 Als Figur behalten",
    "🎤 Say something over it": "🎤 Was dazu sagen",
    "✂️ Turn it into a sticker": "✂️ Sticker daraus machen",
    "✂️ Cutting it out...": "✂️ Ich schneide aus...",
    "🔍 Make it huge": "🔍 Riesig machen",
    "🎨 Turn it into…": "🎨 Mach daraus…",
    "🪄 Change this picture": "🪄 Bild ändern",
    "🔭 What's outside the frame?": "🔭 Was ist außenrum?",
    "🩹 Fix just this bit": "🩹 Nur das hier ändern",
    "🖼️ Put it at the top": "🖼️ Nach oben auf die Seite",
    "👤 That one's me": "👤 Das bin ich",
    "🔊 Add a sound effect": "🔊 Geräusch dazu",
    "📸 Grab a picture from it": "📸 Bild daraus greifen",
    "✨ Make it smooth": "✨ Flüssig machen",
    "🐌 Slow it down": "🐌 Langsamer machen",
    "🌀 Make a moving sticker": "🌀 Wackel-Sticker machen",
    "✏️ Draw on it": "✏️ Draufmalen",
    "🖨️ Print it": "🖨️ Ausdrucken",
    "💌 Make a card": "💌 Karte machen",
    "▶️ What happens next?": "▶️ Und dann?",
    "📤 Share": "📤 Teilen",
    "⬇︎ Save it": "⬇︎ Speichern",
    "↩️ Put it back": "↩️ Zurückholen",
    "🗑️ Delete for good": "🗑️ Für immer löschen",
    "In the trash": "Im Papierkorb",
    "Gone - it's in the trash.": "Weg - es ist im Papierkorb.",
    "＋ Add a tag": "＋ Etikett anhängen",
    "What tag?": "Welches Etikett?",
    "What tag should these get?": "Welches Etikett für die hier?",
    "\n\nAlready used: ": "\n\nSchon benutzt: ",
    "{n} thing tagged “#{tag}”": "{n} Sache mit „#{tag}“",
    "{n} things tagged “#{tag}”": "{n} Sachen mit „#{tag}“",
    "Couldn't open your gallery right now. Try again!":
      "Deine Galerie geht gerade nicht auf. Probier nochmal!",
    "That one's turned off just now.": "Das ist gerade ausgeschaltet.",

    // --- what kind of thing a tile is --------------------------------------
    "📖 Comic": "📖 Comic",
    "🧩 Panel": "🧩 Kästchen",
    "📷 Photo": "📷 Foto",
    "🎬 Film": "🎬 Film",
    "🎤 My voice": "🎤 Meine Stimme",
    "🔊 Sound": "🔊 Geräusch",
    "✂️ Sticker": "✂️ Sticker",
    "📸 From a video": "📸 Aus einem Video",
    "🎵 Song": "🎵 Lied",

    // --- what kind of sound: a song, a little tune, a background
    //     hum. One card and one model; see app/music.py KINDS.
    "What kind": "Welche Art",
    "What kind of sound to make": "Welche Art von Ton gemacht wird",
    "Make my tune": "Melodie machen!",
    "Make my sound": "Klang machen!",
    "🎲 Thinking of a sound...": "🎲 Ich denke mir einen Klang aus...",
    "Your tune is ready! ✨": "Deine Melodie ist fertig! ✨",
    "Your sound is ready! ✨": "Dein Klang ist fertig! ✨",
    "Making a little tune": "Ich mache eine Melodie",
    "Making a background hum": "Ich mache einen Hintergrundklang",
    "🎺 Little tune": "🎺 Melodie",
    "🌊 Background hum": "🌊 Hintergrundklang",
    "✨ Smooth": "✨ Flüssig",
    "🐌 Slow motion": "🐌 Zeitlupe",
    "🌀 Moving sticker": "🌀 Wackel-Sticker",
    "🔍 Huge": "🔍 Riesig",
    "🪄 Changed": "🪄 Geändert",
    "🔭 More of it": "🔭 Mehr davon",
    "🩹 Fixed a bit": "🩹 Ausgebessert",
    "🎨 A new style": "🎨 Neuer Stil",
    "✏️ Drawing": "✏️ Zeichnung",
    "💌 Card": "💌 Karte",
    "▶ Video": "▶ Video",

    // --- the result row ----------------------------------------------------
    "The picture you made": "Das Bild, das du gemacht hast",
    "One of the pictures you made": "Eins deiner Bilder",
    "Your comic": "Dein Comic",
    "🎲 Try again": "🎲 Nochmal",
    "⬇︎ Save picture": "⬇︎ Bild speichern",
    "⬇︎ Save video": "⬇︎ Video speichern",
    "⬇︎ Save song": "⬇︎ Lied speichern",
    "⬇︎ Save my film": "⬇︎ Film speichern",
    "⬇︎ Save my comic": "⬇︎ Comic speichern",
    "⬇︎ Save them all": "⬇︎ Alle speichern",
    "Keep this one": "Das behalten",
    "✓ Kept": "✓ Behalten",
    "Delete this one": "Das löschen",
    "It's a sticker! ✂️": "Ein Sticker! ✂️",
    "It's ready! ✨": "Fertig! ✨",
    "It's ready! 🔍": "Fertig! 🔍",
    "Your very first picture! 🎉": "Dein allererstes Bild! 🎉",
    "Your very first video! 🎉": "Dein allererstes Video! 🎉",
    "Your very first comic! 🎉": "Dein allererster Comic! 🎉",
    "Your very first film! 🎉": "Dein allererster Film! 🎉",
    "That's {n} pictures! 🎉": "Das sind {n} Bilder! 🎉",
    "That's {n} videos! 🎉": "Das sind {n} Videos! 🎉",
    "That's {n} comics! 🎉": "Das sind {n} Comics! 🎉",
    "That's {n} films! 🎉": "Das sind {n} Filme! 🎉",

    // --- characters ---------------------------------------------------------
    "Character": "Figur",
    "What's this character called?": "Wie heißt diese Figur?",
    "Having a good look at {name}...": "Ich schaue mir {name} genau an...",
    "{name} can be in your next one! 🧑‍🎤":
      "{name} kann beim nächsten Mal dabei sein! 🧑‍🎤",
    "That's {n} characters already! Say goodbye to one first, in the Gallery.":
      "Das sind schon {n} Figuren! Sag erst einer in der Galerie Tschüss.",
    "Forget “{idea}”": "„{idea}“ vergessen",
    "✏️ Rename": "✏️ Umbenennen",
    "🎨 How they look": "🎨 Wie sie aussieht",
    "👋 Say goodbye to them": "👋 Tschüss sagen",
    "Nothing with them in it yet! Choose them under “Who’s in it?” and make something.":
      "Noch nichts mit ihr! Such sie unter „Wer ist dabei?“ aus und mach " +
      "etwas.",
    "What should they be called?": "Wie soll sie heißen?",
    "One sentence saying what they look like. This gets used in every picture they're in, so be specific about colours and clothes.":
      "Ein Satz dazu, wie sie aussieht. Der wird in jedem Bild mit ihr " +
      "benutzt, also sei genau bei Farben und Kleidung.",
    "Said goodbye to {name}. Their pictures are still in the Gallery.":
      "Tschüss, {name}. Die Bilder sind noch in der Galerie.",
    "Couldn't load them just now.": "Konnte sie gerade nicht laden.",

    // --- the film and card makers -------------------------------------------
    "Make a film": "Film machen",
    "{n} videos, in the order you chose them. It'll open with a title card - give it a name!":
      "{n} Videos, in der Reihenfolge, die du gewählt hast. Am Anfang " +
      "steht ein Titelbild - gib ihm einen Namen!",
    "🎬 What's your film called?": "🎬 Wie heißt dein Film?",
    "The Great Pancake Adventure": "Das große Pfannkuchen-Abenteuer",
    "My Film": "Mein Film",
    "{title} presents": "{title} präsentiert",
    "Joining your film... this takes a little while.":
      "Ich setze deinen Film zusammen... das dauert ein bisschen.",
    "Done! It's at the top of your videos.":
      "Fertig! Es steht ganz oben bei deinen Videos.",
    "Make a card": "Karte machen",
    "Save my card": "Karte speichern",
    "💌 What should it say?": "💌 Was soll draufstehen?",
    "Happy birthday Grandma!": "Alles Gute zum Geburtstag, Oma!",
    "Card colour": "Kartenfarbe",
    "Card colour {n}": "Kartenfarbe {n}",
    "Made for you!": "Für dich gemacht!",
    "made at {title}": "gemacht in {title}",
    "Saving your card...": "Ich speichere deine Karte...",
    "Saved! It's in Photos & drawings - open it to print or share.":
      "Gespeichert! Sie ist bei Fotos & Zeichnungen - mach sie auf zum " +
      "Drucken oder Teilen.",
    "My comic": "Mein Comic",

    // --- their voice, sounds, frames, loops -----------------------------------
    "🎤 Say something": "🎤 Sag was",
    "✕ Close": "✕ Schließen",
    "Tap the big button and talk. Your voice goes on top of your video.":
      "Tipp auf den großen Knopf und sprich. Deine Stimme kommt auf dein " +
      "Video.",
    "Start talking": "Losreden",
    "Keep the video's own sound too (it goes quieter while you talk)":
      "Den Ton vom Video behalten (er wird leiser, während du sprichst)",
    "✨ Put it on my video": "✨ Auf mein Video legen",
    "🔁 Record it again": "🔁 Nochmal aufnehmen",
    "🗑️ Throw the recording away": "🗑️ Aufnahme wegwerfen",
    "Or use a sound you already have":
      "Oder nimm ein Geräusch, das du schon hast",
    "This browser can't record here - that needs https. Pick a sound from your files below instead.":
      "Dieser Browser kann hier nicht aufnehmen - dafür braucht es https. " +
      "Nimm stattdessen unten ein Geräusch aus deinen Dateien.",
    "You haven't put it on your video yet!":
      "Du hast sie noch nicht auf dein Video gelegt!",
    "Your iPad needs to say yes to the microphone first. Tap the big button again and choose Allow.":
      "Dein iPad muss erst Ja zum Mikrofon sagen. Tipp nochmal auf den " +
      "großen Knopf und wähle Erlauben.",
    "I can't find a microphone on this device. You can pick a sound from your files below instead.":
      "Ich finde kein Mikrofon auf diesem Gerät. Du kannst stattdessen " +
      "unten ein Geräusch aus deinen Dateien nehmen.",
    "The microphone didn't start ({why}). You can pick a sound from your files below instead.":
      "Das Mikrofon ist nicht angegangen ({why}). Du kannst stattdessen " +
      "unten ein Geräusch aus deinen Dateien nehmen.",
    "Putting your voice on it...": "Ich lege deine Stimme darauf...",
    "Your voice is on it! 🎤": "Deine Stimme ist drauf! 🎤",
    "Pick a sound, slide to where you want it, then put it on.":
      "Such ein Geräusch aus, schieb es dahin, wo du es willst, und leg es " +
      "drauf.",
    "When the sound happens": "Wann das Geräusch kommt",
    "Couldn't load the sounds.": "Konnte die Geräusche nicht laden.",
    "Putting it on...": "Ich lege es drauf...",
    "Sound added! 🔊": "Geräusch dazu! 🔊",
    "📸 Grab a picture": "📸 Bild greifen",
    "Slide to the bit you like. The picture underneath is exactly what you'll keep.":
      "Schieb bis zu der Stelle, die du magst. Das Bild darunter ist genau " +
      "das, was du behältst.",
    "Which bit?": "Welche Stelle?",
    "Which moment to keep": "Welchen Moment behalten",
    "The picture you are about to keep": "Das Bild, das du behalten wirst",
    "✨ Keep this picture": "✨ Dieses Bild behalten",
    "Keeping it...": "Ich behalte es...",
    "Kept it as a picture! 📸": "Als Bild behalten! 📸",
    "Pick the bit you want and it'll loop for ever - a sticker that moves.":
      "Such das Stück aus, das du willst, und es läuft für immer in der " +
      "Schleife - ein Sticker, der sich bewegt.",
    "Start here": "Hier anfangen",
    "Where the loop starts": "Wo die Schleife anfängt",
    "How long?": "Wie lang?",
    "How long the loop is": "Wie lang die Schleife ist",
    "1 second": "1 Sekunde",
    "2 seconds": "2 Sekunden",
    "Where your moving sticker starts": "Wo dein Wackel-Sticker anfängt",
    "✨ Make my sticker": "✨ Sticker machen!",
    "Making it...": "Ich mache es...",
    "It moves! 🌀": "Es bewegt sich! 🌀",

    // --- the three edits ----------------------------------------------------
    "Say what you'd like different and it'll make the same picture again with that changed.":
      "Sag, was anders sein soll, und dasselbe Bild wird nochmal gemacht, " +
      "nur mit dieser Änderung.",
    "The picture you're changing": "Das Bild, das du änderst",
    "What should be different?": "Was soll anders sein?",
    "make it night-time\ngive the fox a scarf":
      "mach Nacht daraus\ngib dem Fuchs einen Schal",
    "make it night-time": "mach Nacht daraus",
    "make it snowy": "lass es schneien",
    "add a rainbow": "füg einen Regenbogen dazu",
    "make it look like a painting": "mach ein Gemälde daraus",
    "put a hat on it": "setz ihm einen Hut auf",
    "make everything tiny": "mach alles winzig",
    "...and put me in it 👤": "...und mich mit rein 👤",
    "✨ Go": "✨ Los",
    "Tell me what should be different!": "Sag mir, was anders sein soll!",
    "Changing your picture... 🪄": "Ich ändere dein Bild... 🪄",
    "Pick a kind of picture and it'll draw this one again that way, with everything still where it is.":
      "Such eine Bildart aus und dieses Bild wird so nochmal gezeichnet, " +
      "mit allem an derselben Stelle.",
    "The picture you're turning into something else":
      "Das Bild, das du in etwas anderes verwandelst",
    "What to turn it into": "In was es verwandelt wird",
    "Anything else? (you don't have to say)":
      "Noch was? (musst du nicht sagen)",
    "you don't have to say - or add your own twist: make it night-time":
      "musst du nicht sagen - oder häng deine Idee dran: mach Nacht daraus",
    "Pick what to turn it into!": "Such aus, in was es verwandelt wird!",
    "Drawing it again... 🎨": "Ich zeichne es nochmal... 🎨",
    "Pick a side and it'll invent what was just out of the picture.":
      "Such eine Seite aus und was gerade außerhalb des Bildes war, wird " +
      "erfunden.",
    "The picture you're growing": "Das Bild, das du größer machst",
    "Which way?": "Wohin?",
    "Which way to grow": "In welche Richtung größer",
    "All round": "Rundherum",
    "⬅️ Left": "⬅️ Links",
    "➡️ Right": "➡️ Rechts",
    "⬆️ Up": "⬆️ Oben",
    "⬇️ Down": "⬇️ Unten",
    "How much?": "Wie viel?",
    "How much bigger": "Wie viel größer",
    "A bit": "Ein bisschen",
    "A lot": "Ganz viel",
    "What's out there? (you don't have to say)":
      "Was ist da draußen? (musst du nicht sagen)",
    "you don't have to say - or try: a beach, more trees":
      "musst du nicht sagen - oder probier: ein Strand, mehr Bäume",
    "Looking outside the frame... 🔭": "Ich schaue neben das Bild... 🔭",
    "Say what should be there instead, then tap Go.":
      "Sag, was stattdessen da sein soll, und tipp auf Los.",
    "Paint over the bit you want changed first!":
      "Mal erst über die Stelle, die anders werden soll!",
    "Fixing that bit... 🩹": "Ich bessere die Stelle aus... 🩹",
    "Slowing it right down... it comes out quiet 🐌":
      "Ich mache es ganz langsam... es kommt ohne Ton raus 🐌",
    "Smoothing it out... ✨": "Ich mache es flüssig... ✨",
    "Making it huge... 🔍": "Ich mache es riesig... 🔍",
    "Cutting it out...": "Ich schneide es aus...",

    // --- compare ------------------------------------------------------------
    "🔍 Which one?": "🔍 Welches?",
    "Slide across to see one and then the other.":
      "Schieb hin und her, um erst das eine und dann das andere zu sehen.",
    "The first one": "Das erste",
    "The second one": "Das zweite",
    "Slide between the two pictures":
      "Zwischen den beiden Bildern hin- und herschieben",

    // --- the drawing pad ----------------------------------------------------
    "Draw something": "Mal was",
    "Use my drawing": "Zeichnung nehmen",
    "Colour": "Farbe",
    "Colour {n}": "Farbe {n}",
    "Stamps": "Stempel",
    "Stamp {emoji}": "Stempel {emoji}",
    "Thin brush": "Dünner Pinsel",
    "Medium brush": "Mittlerer Pinsel",
    "Thick brush": "Dicker Pinsel",
    "🧽 Rubber": "🧽 Radierer",
    "↶ Undo": "↶ Rückgängig",
    "Start again": "Von vorn",
    "What should be there instead?": "Was soll stattdessen da sein?",
    "what should be there instead? e.g. a red party hat":
      "was soll stattdessen da sein? zum Beispiel ein roter Partyhut",
    "Draw with your finger or a pencil. When you're done, tap <strong>Use my drawing</strong>.":
      "Mal mit dem Finger oder einem Stift. Wenn du fertig bist, tipp auf " +
      "<strong>Zeichnung nehmen</strong>.",
    "Paint over the bit you want changed, say what should be there, then tap <strong>Go</strong>.":
      "Mal über die Stelle, die anders werden soll, sag, was da hin soll, " +
      "und tipp auf <strong>Los</strong>.",

    // --- the chat tab -------------------------------------------------------
    "Chat with": "Chatte mit",
    "Ask for an idea, or tell me what you’re making. Your grown-ups can read everything said here.":
      "Frag nach einer Idee oder erzähl, was du gerade machst. Deine " +
      "Erwachsenen können alles lesen, was hier steht.",
    "Your chat": "Dein Chat",
    "Say something": "Sag was",
    "Say something…": "Sag was…",
    "Send it": "Abschicken",
    "Start a new chat": "Neuen Chat anfangen",
    "Started a new chat. Your grown-ups can still see the old one.":
      "Neuer Chat. Deine Erwachsenen sehen den alten trotzdem noch.",
    "The chat helper isn't set up on this machine yet. Everything else still works!":
      "Die Chat-Hilfe ist auf diesem Computer noch nicht eingerichtet. " +
      "Alles andere geht trotzdem!",
    "Give me an idea for a picture": "Gib mir eine Idee für ein Bild",
    "What can I make here?": "Was kann ich hier machen?",
    // The third starter exists to show them they can write in the other
    // language, so on a French page it is the English one.
    "Donne-moi une idée de dessin": "Give me a drawing idea",
    "🎨 Make a picture of this": "🎨 Bild davon machen",
    "🎬 Make a video of this": "🎬 Video davon machen",
    "📋 Copy": "📋 Kopieren",
    "✓ Copied": "✓ Kopiert",
    "✕ Couldn't copy": "✕ Geht nicht",
    "That's what {name} said. Change anything you like, or tap “Help me write it” to turn it into a proper description.":
      "Das hat {name} gesagt. Ändere, was du willst, oder tipp auf „Hilf " +
      "mir beim Schreiben“, damit eine richtige Beschreibung daraus wird.",
    "the helper": "die Hilfe",

    // --- Settings -----------------------------------------------------------
    "You": "Du",
    "You're {name}!": "Du bist {name}!",
    "🪄 Make a picture of me": "🪄 Bild von mir machen",
    "😃 Pick a face instead": "😃 Lieber ein Gesicht",
    "↩️ Back to the face": "↩️ Zurück zum Gesicht",
    "Pick a face": "Such ein Gesicht aus",
    "Colours": "Farben",
    "Language": "Sprache",
    "Which language": "Welche Sprache",
    "The top of your page": "Der Kopf deiner Seite",
    "What is across the top of your page now":
      "Was gerade oben auf deiner Seite steht",
    "↩️ Put the first one back": "↩️ Das erste zurückholen",
    "Put back the one it came with.": "Das erste ist wieder da.",
    "Couldn't change it back.": "Konnte es nicht zurückholen.",
    "Making new ones is switched off right now, but you can still use any picture from <strong>Gallery</strong> — open one and tap <strong>Put it at the top</strong>.":
      "Neue machen ist gerade ausgeschaltet, aber du kannst jedes Bild aus " +
      "der <strong>Galerie</strong> nehmen — mach eins auf und tipp auf " +
      "<strong>Nach oben auf die Seite</strong>.",
    "It's a long thin strip, so wide things work best — a row of something, a view, a pattern. Your name goes on top of it, so leave the middle fairly quiet.":
      "Es ist ein langer schmaler Streifen, also passt Breites am besten — " +
      "eine Reihe von etwas, eine Landschaft, ein Muster. Dein Name kommt " +
      "darüber, lass die Mitte also ziemlich ruhig.",
    "🖼️ Putting it up...": "🖼️ Ich hänge es auf...",
    "That's the top of your page now! 🖼️":
      "Das ist jetzt der Kopf deiner Seite! 🖼️",
    "That one wouldn't go up there.": "Das wollte da nicht hoch.",
    "Kept it on this device, but it wouldn't save.":
      "Auf diesem Gerät behalten, aber speichern ging nicht.",
    "Tap your face. A grown-up adds and changes these on the parent page.":
      "Tipp auf dein Gesicht. Ein Erwachsener fügt sie auf der " +
      "Eltern-Seite hinzu und ändert sie.",
    "👤 Making it you...": "👤 Ich mache das zu dir...",
    "That's you now! 👤": "Das bist jetzt du! 👤",
    "I'm a grown-up — the parent page": "Ich bin erwachsen — die Eltern-Seite",

    // --- who is making things today -----------------------------------------
    "Who's making things today?": "Wer macht heute etwas?",

    // --- the picture-of-me wizard -------------------------------------------
    "Make a picture of me": "Ein Bild von mir",
    "1. What are you?": "1. Was bist du?",
    "What are you?": "Was bist du?",
    "Or type your own": "Oder schreib deins",
    "…or type your own": "…oder schreib deins",
    "2. What colour?": "2. Welche Farbe?",
    "What colour?": "Welche Farbe?",
    "3. Anything else?": "3. Noch was?",
    "Anything else?": "Noch was?",
    "Anything else": "Noch was",
    "…a wizard hat, freckles, a scarf": "…Zauberhut, Sommersprossen, Schal",
    "Let's make it! ✨": "Los geht's! ✨",
    "It makes four at once so you can pick your favourite. Then tap <strong>👤 That one's me</strong> under the one you like.":
      "Es macht vier auf einmal, damit du dein Lieblingsbild aussuchen " +
      "kannst. Tipp dann unter dem, das du magst, auf <strong>👤 Das bin " +
      "ich</strong>.",
    "Pick what you are to get started!":
      "Such aus, was du bist, dann geht's los!",
    "Pick what you are first!": "Such erst aus, was du bist!",
    "Making pictures is switched off right now.":
      "Bilder machen ist gerade ausgeschaltet.",
    "Tap Go and pick your favourite! ✨":
      "Tipp auf Los und such dein Lieblingsbild aus! ✨",
    // The wizard's choices. The sentence they compose is a prompt, so the
    // article travels with the word in French, where gender does too.
    "a fox": "ein Fuchs", "a cat": "eine Katze", "a dog": "ein Hund",
    "a dragon": "ein Drache", "a robot": "ein Roboter", "an owl": "eine Eule",
    "a unicorn": "ein Einhorn", "a penguin": "ein Pinguin",
    "an astronaut": "ein Astronaut", "a wizard": "ein Zauberer",
    "a superhero": "ein Superheld", "a pirate": "ein Pirat",
    "a mermaid": "eine Meerjungfrau", "a knight": "ein Ritter",
    "a panda": "ein Panda", "an octopus": "ein Oktopus",
    // "en violet" rather than "violet": the colour then agrees with nothing,
    // so one word does for a fox and for a mermaid alike.
    "purple": "Lila", "blue": "Blau", "green": "Grün",
    "orange": "Orange", "pink": "Pink", "red": "Rot",
    "yellow": "Gelb", "rainbow": "Regenbogen", "silver": "Silber",
    "golden": "Gold",
    "a wizard hat": "Zauberhut",
    "big round glasses": "Riesenbrille",
    "a stripy scarf": "Ringelschal",
    "a cape": "Umhang", "headphones": "Kopfhörer",
    "a flower crown": "Blumenkranz", "a bow tie": "Fliege",
    "freckles": "Sommersprossen",

    // --- when it is shut -----------------------------------------------------
    "just now": "gerade eben",
    "{n} minute ago": "vor {n} Minute",
    "{n} minutes ago": "vor {n} Minuten",
    "{n} hour ago": "vor {n} Stunde",
    "{n} hours ago": "vor {n} Stunden",
    "{n} KB": "{n} KB",
    "{n} MB": "{n} MB",

    // The close button on every sheet. Static markup, so it is a
    // data-i18n and not a t() - and it was English in every language
    // until the coverage walk went looking for exactly this.
    "✕ Close": "✕ Schließen",
  };

  // Spanish. The same keys in the same order under the same headings
  // as FR above, so a line missing from one of them is a line out of step.
  var ES = {
    // --- the shell ------------------------------------------------------
    "My AI Factory": "Mi fábrica de IA",
    "AI Factory": "Fábrica de IA",
    "What would you like to do?": "¿Qué quieres hacer?",
    "That's me - tap to swap": "¡Soy yo! Toca para cambiar",
    "Show me": "Muéstramelo",
    "Working...": "Trabajando...",
    "wiz-sentence":
      "{thing} amable{colour}{wearing}, un retrato de dibujos animados " +
      "alegre, de cabeza y hombros, con ojos grandes y simpáticos",
    "wiz-wearing": " con {list}",
    "wiz-and": " y ",
    "wiz-colour": " de color {colour}",

    // Tabs. Short on purpose: seven of them share one row at 390px.
    "Picture": "Imagen",
    "Video": "Vídeo",
    "Comic": "Cómic",
    "Music": "Música",
    "Chat": "Chat",
    "Gallery": "Galería",
    "Settings": "Ajustes",

    // --- "your picture is ready" ----------------------------------------
    "Your picture is ready! ✨": "¡Tu imagen está lista! ✨",
    "Your video is ready! ✨": "¡Tu vídeo está listo! ✨",
    "Your comic is ready! ✨": "¡Tu cómic está listo! ✨",
    "Your film is ready! ✨": "¡Tu película está lista! ✨",
    "Your song is ready! ✨": "¡Tu canción está lista! ✨",
    "Your smooth video is ready! ✨": "¡Tu vídeo fluido está listo! ✨",
    "Your slow-motion video is ready! ✨": "¡Tu cámara lenta está lista! ✨",
    "Your big picture is ready! ✨": "¡Tu imagen grande está lista! ✨",
    "Your bigger picture is ready! ✨": "¡Tu imagen más grande está lista! ✨",
    "Your changed picture is ready! ✨": "¡Tu imagen cambiada está lista! ✨",

    // --- the Gallery ------------------------------------------------------
    "Everything you've made is saved here.":
      "Todo lo que haces se guarda aquí.",
    "Nothing here yet! Make a picture, a video or a comic and it'll turn up here.":
      "¡Aquí no hay nada todavía! Haz una imagen, un vídeo o un cómic y " +
      "aparecerá aquí.",
    "Nothing of yours yet - but there's something on the family shelf!":
      "Tuyo aún no hay nada, ¡pero hay algo en la estantería de la familia!",
    "You've made 1 thing so far.": "Has hecho 1 cosa hasta ahora.",
    "You've made {n} things so far.": "Has hecho {n} cosas hasta ahora.",
    "🧑‍🎤 My characters": "🧑‍🎤 Mis personajes",
    "Show": "Ver",
    "How to show your gallery": "Cómo ver tu galería",
    "Everything": "Todo",
    "In groups": "Por grupos",
    "Order": "Orden",
    "What order to show them in": "En qué orden verlo todo",
    "Newest": "Nuevos",
    "Oldest": "Antiguos",
    "⭐ Favourites": "⭐ Favoritos",
    "By kind": "Por tipo",
    "🔎 Find something you made": "🔎 Busca algo que hayas hecho",
    "Search your gallery": "Buscar en tu galería",
    "Clear the search": "Borrar la búsqueda",
    "Choose": "Elegir",
    "Cancel": "Cancelar",
    "👨‍👩‍👧 Family": "👨‍👩‍👧 Familia",
    "🎨 Pictures": "🎨 Imágenes",
    "📖 Comics": "📖 Cómics",
    "🧩 Comic pictures": "🧩 Viñetas",
    "✂️ Stickers": "✂️ Pegatinas",
    "📷 Photos & drawings": "📷 Fotos y dibujos",
    "🎬 Videos": "🎬 Vídeos",
    "🎵 Songs": "🎵 Canciones",
    "Nothing matches that. Try another word!":
      "No hay nada con eso. ¡Prueba con otra palabra!",
    "Nothing here yet! Go and make something.":
      "¡Aquí no hay nada todavía! Ve a hacer algo.",
    "🗑️ Recently deleted": "🗑️ Borrado hace poco",
    "Things stay here for {days} days, then they're gone for good. Tap one to put it back.":
      "Las cosas se quedan aquí {days} días y luego desaparecen para " +
      "siempre. Toca una para devolverla.",
    "Nothing chosen yet": "Nada elegido todavía",
    "Tap the ones you want": "Toca las que quieras",
    "1 chosen": "1 elegido",
    "{n} chosen": "{n} elegidos",
    "Choose all": "Elegir todo",
    "Choose none": "No elegir nada",
    "🎬 Join into a film": "🎬 Unir en una película",
    "🔍 Compare them": "🔍 Compararlos",
    "🏷️ Add a tag": "🏷️ Poner una etiqueta",
    "⬇︎ Save": "⬇︎ Guardar",
    "🗑️ Delete": "🗑️ Borrar",
    "Deleted": "Borrado",
    "{n} things deleted": "{n} cosas borradas",
    "Undo": "Deshacer",
    "Put back!": "¡De vuelta!",
    "All put back!": "¡Todo de vuelta!",
    "Really delete?": "¿Borrar de verdad?",
    "Really delete it?": "¿Lo borramos?",
    "Really delete all {n}?": "¿Borramos los {n}?",
    "Really delete forever?": "¿Borrar para siempre?",
    "Really clear it?": "¿Borrarlo todo?",
    "Really say goodbye?": "¿Nos despedimos?",

    // --- the maker cards -------------------------------------------------
    "Make a picture": "Hacer una imagen",
    "Make a video": "Hacer un vídeo",
    "Make a comic": "Hacer un cómic",
    "Make a song": "Hacer una canción",
    "↺ Start again": "↺ De nuevo",
    "Clear everything on this card and start again":
      "Borrar todo lo de esta tarjeta y empezar de nuevo",
    "What should the picture be?": "¿Qué quieres que salga en la imagen?",
    "What should the video be?": "¿Qué quieres que pase en el vídeo?",
    "What's your story?": "¿Cuál es tu historia?",
    "What should the song be about?": "¿De qué quieres que trate la canción?",
    "What should the top of your page look like?":
      "¿Cómo quieres que sea la imagen de arriba?",
    "A fluffy dragon eating pancakes on the moon":
      "Un dragón peludo comiendo tortitas en la luna",
    "A puppy surfing a giant wave at sunset":
      "Un perrito surfeando una ola gigante al atardecer",
    "It flaps its wings and flies up into the clouds":
      "Bate las alas y sube volando hasta las nubes",
    "The cat walks across the room and curls up in the sunny spot":
      "El gato cruza la habitación y se acurruca en el rincón soleado",
    "A little robot looking for its lost cat in a big city":
      "Un robot pequeño que busca a su gato perdido en una ciudad grande",
    "A hedgehog who wants to learn to swim":
      "Un erizo que quiere aprender a nadar",
    "A dragon who is scared of pancakes":
      "Un dragón al que le dan miedo las tortitas",
    "A row of hot air balloons over a green valley":
      "Una fila de globos aerostáticos sobre un valle verde",
    "Clear what you typed": "Borrar lo que has escrito",
    "✨ Help me write it": "✨ Ayúdame a escribirlo",
    "👀 Look at my picture and help me write it":
      "👀 Mira mi imagen y ayúdame a escribirlo",
    "✨ Write me a song": "✨ Escríbeme una canción",
    "🎉 Surprise me": "🎉 Sorpréndeme",
    "🎲 Mix it up": "🎲 Mézclalo",
    "📜 Things I've asked for before": "📜 Cosas que ya he pedido",
    "📷 Start from a photo": "📷 Empezar con una foto",
    "🖼️ Pick one from my gallery": "🖼️ Elegir una de mi galería",
    "Who's in it?": "¿Quién sale?",
    "Nobody": "Nadie",
    "📄 Everything with {name} in it": "📄 Todo donde sale {name}",
    "Make": "Hacer",
    "What kind of picture": "Qué tipo de imagen",
    "A picture": "Una imagen",
    "A character": "Un personaje",
    "Drawn on its own with nothing behind it, so you can cut it out as a sticker or keep them as a character.":
      "Se dibuja solo, sin nada detrás, para que puedas recortarlo como " +
      "pegatina o guardarlo como personaje.",
    "Shape": "Forma",
    "Picture shape": "Forma de la imagen",
    "Video shape": "Forma del vídeo",
    "Landscape": "Horizontal",
    "Portrait": "Vertical",
    "Square": "Cuadrado",
    "landscape": "horizontal",
    "portrait": "vertical",
    "square": "cuadrado",
    "How many": "Cuántas",
    "How many pictures": "Cuántas imágenes",
    "How many panels": "Cuántas viñetas",
    "Just one": "Solo una",
    "Four to pick from": "Cuatro a elegir",
    "3 pictures": "3 imágenes",
    "4 pictures": "4 imágenes",
    "6 pictures": "6 imágenes",
    "Look": "Aspecto",
    "Look and sound": "Aspecto y sonido",
    "Sound": "Sonido",
    "Clear these": "Borrar esto",
    "Any": "Cualquiera",
    "Make my picture": "Haz mi imagen",
    "Make {n} pictures": "Haz {n} imágenes",
    "Make my video": "Haz mi vídeo",
    "Make my film": "Haz mi película",
    "Animate it": "Anímala",
    "Make my comic": "Haz mi cómic",
    "Make my song": "Haz mi canción",
    "Make my music": "Haz mi música",
    "Make one": "Haz una",
    "Stop": "Parar",
    "Tell a story and it gets drawn as a comic strip you can print.":
      "Cuenta una historia y se dibujará como una tira de cómic que puedes " +
      "imprimir.",

    // video card
    "Start from": "Empezar con",
    "What to start the video from": "Con qué empezar el vídeo",
    "✏️ Words": "✏️ Palabras",
    "🖼️ A picture": "🖼️ Una imagen",
    "🎞️ Two pictures": "🎞️ Dos imágenes",
    "📽️ A little film": "📽️ Una peli corta",
    "Make a picture up above and tap <strong>Animate this</strong>, or use a photo from your iPad.":
      "Haz una imagen ahí arriba y toca <strong>Anímala</strong>, o usa " +
      "una foto de tu iPad.",
    "The picture you picked": "La imagen que has elegido",
    "This picture is ready to animate!":
      "¡Esta imagen está lista para animarse!",
    "Use a different one": "Usar otra",
    "📷 Take or choose a photo": "📷 Haz o elige una foto",
    "✏️ Draw one": "✏️ Dibuja una",
    "Pick where the video starts and where it ends. The middle gets made up.":
      "Elige dónde empieza el vídeo y dónde acaba. Lo del medio se lo " +
      "inventa.",
    "Starts on": "Empieza con",
    "Ends on": "Acaba con",
    "🖼️ Pick from the gallery": "🖼️ Elegir de la galería",
    "🖼️ Pick a different one": "🖼️ Elegir otra",
    "🗣️ What should they say?": "🗣️ ¿Qué quieres que diga?",
    "(you can leave this empty)": "(puedes dejarlo vacío)",
    "Look at the Earth from up here!": "¡Mira la Tierra desde aquí arriba!",
    "Clear what they say": "Borrar lo que dice",
    "🔊 Videos have sound — they'll say this out loud, so keep it short.":
      "🔊 Los vídeos tienen sonido — esto se dirá en voz alta, así que " +
      "mejor cortito.",
    "Quality": "Calidad",
    "Video quality": "Calidad del vídeo",
    "⚡ Quick": "⚡ Rápida",
    "👍 Normal": "👍 Normal",
    "✨ Sharper": "✨ Más nítida",
    "Sharper means more detail, but it takes a good deal longer to make, and the longest a sharper video can be is":
      "Más nítida quiere decir más detalle, pero tarda bastante más en " +
      "hacerse, y lo más largo que puede durar un vídeo así es",
    "seconds.": "segundos.",
    "How long": "Duración",
    "Video length in seconds": "Duración del vídeo en segundos",
    "How long the song is, in seconds": "Duración de la canción en segundos",
    "{n} seconds": "{n} segundos",
    "Longer videos take longer to make.":
      "Los vídeos más largos tardan más en hacerse.",
    "Longer songs take longer to make.":
      "Las canciones más largas tardan más en hacerse.",
    "How many parts": "Cuántas partes",
    "2 parts": "2 partes",
    "3 parts": "3 partes",
    "4 parts": "4 partes",
    "Each part carries on from the last one, then they're joined into one film. It takes a while, and it uses up one video for each part.":
      "Cada parte sigue donde acaba la anterior y luego se unen en una " +
      "sola película. Tarda un rato y gasta un vídeo por cada parte.",
    "🔊 Add a sound": "🔊 Añadir un sonido",
    "None": "Ninguno",
    "When?": "¿Cuándo?",
    "At the start": "Al principio",
    "In the middle": "En el medio",
    "At the end": "Al final",

    // music card
    "Singing": "Voz",
    "Singing or not": "Con voz o sin voz",
    "With singing": "Con voz",
    "Just music": "Solo música",
    "Words": "Letra",
    "Clear the words": "Borrar la letra",
    "[Verse]\nI met a dragon on the stairs\nHe said he doesn't like éclairs\n\n[Chorus]\nPancakes, pancakes, run away!":
      "[Estrofa]\nMe encontré un dragón en la escalera\nY me dijo que odia " +
      "las peras\n\n[Estribillo]\n¡Tortitas, tortitas, a correr!",
    "Put <strong>[Verse]</strong> or <strong>[Chorus]</strong> on a line of their own to mark the parts. Leave it empty and you'll get music with nobody singing.":
      "Pon <strong>[Estrofa]</strong> o <strong>[Estribillo]</strong> en " +
      "una línea aparte para marcar las partes. Déjalo vacío y tendrás " +
      "música sin que cante nadie.",

    // --- the helpers -----------------------------------------------------
    "Type a few words about your idea first!":
      "¡Escribe antes unas palabras sobre tu idea!",
    "Thinking of ideas...": "Pensando ideas...",
    "Looking at your picture...": "Mirando tu imagen...",
    "This takes a moment the first time.": "La primera vez tarda un poquito.",
    "Here you go! Change anything you like.":
      "¡Aquí tienes! Cambia lo que quieras.",
    "Here's an idea for it - change anything you like.":
      "Aquí tienes una idea - cambia lo que quieras.",
    "Writing your song...": "Escribiendo tu canción...",
    "Here are some words! Change any line you like - they don't have to rhyme.":
      "¡Aquí tienes una letra! Cambia la línea que quieras - no tienen que " +
      "rimar.",
    "🎲 Thinking of something...": "🎲 Pensando algo...",
    "🎲 Writing a song...": "🎲 Escribiendo una canción...",
    "Dreaming up an idea...": "Imaginando una idea...",
    "Here's a whole song! Change any line you like.":
      "¡Aquí tienes una canción entera! Cambia la línea que quieras.",
    "Here's an idea! Change anything you like.":
      "¡Aquí tienes una idea! Cambia lo que quieras.",
    "One of your old ideas with a brand new look. Change anything you like!":
      "Una de tus ideas de antes con un aspecto nuevo. ¡Cambia lo que " +
      "quieras!",
    "A brand new idea. Change anything you like!":
      "Una idea totalmente nueva. ¡Cambia lo que quieras!",
    "🎲 Shuffling...": "🎲 Barajando...",
    "Same as before - change anything you like, then go!":
      "Igual que antes - cambia lo que quieras ¡y a por ello!",
    "Change a word or two and you'll get this same one, but different. “Make another like this” starts from scratch instead.":
      "Cambia una palabra o dos y tendrás esta misma, pero distinta. “Haz " +
      "otro como este” empieza de cero.",
    "Your drawing is ready! Tap the helper to get a script for it, or say what should happen.":
      "¡Tu dibujo está listo! Toca el ayudante para que te escriba algo, o " +
      "di qué tiene que pasar.",
    "This starts where that video stopped. What happens next?":
      "Esto empieza donde acabó ese vídeo. ¿Qué pasa ahora?",

    // --- while it renders -------------------------------------------------
    "Sending it off...": "Enviándolo...",
    "Getting started...": "Empezando...",
    "Starting": "Empezando",
    "Making another one...": "Haciendo otra...",
    "Getting it ready...": "Preparándolo...",
    "Working out your story...": "Pensando tu historia...",
    "Reading your story...": "Leyendo tu historia...",
    "Putting your comic together...": "Montando tu cómic...",
    "Stopping...": "Parando...",
    "Stopped! Nothing was made. Try a different idea.":
      "¡Parado! No se hizo nada. Prueba con otra idea.",
    "Couldn't stop it — it may finish anyway.":
      "No se ha podido parar — puede que acabe igualmente.",
    "Something went wrong. Let's try that again!":
      "Algo ha salido mal. ¡Vamos a probar otra vez!",
    "Pick a picture first — make one above, or use a photo!":
      "Elige antes una imagen — haz una arriba, ¡o usa una foto!",
    "Pick a picture to start on and one to end on!":
      "¡Elige una imagen para empezar y otra para acabar!",
    "Type something you'd like to make first!":
      "¡Escribe antes algo que quieras hacer!",
    "Sending your photo...": "Enviando tu foto...",
    "It's in your gallery! Now pick what to do with it ✨":
      "¡Ya está en tu galería! Ahora elige qué hacer con ella ✨",
    "✅ Ready!": "✅ ¡Listo!",
    "Took {time}.": "Ha tardado {time}.",
    "{n} seconds long": "{n} segundos",
    "{n} second": "{n} segundo",
    "{n} secs": "{n} seg",
    "about {n} seconds": "unos {n} segundos",
    "about a minute": "un minuto más o menos",
    "about {n} minutes": "unos {n} minutos",
    "{time} so far": "llevamos {time}",
    "about {time} to go": "faltan {time}",
    "⏱️ I haven't made one of these yet — I'll time this one.":
      "⏱️ Todavía no he hecho ninguno de estos — voy a cronometrar este.",
    "⏱️ Takes {time} on this computer.": "⏱️ Aquí tarda {time}.",
    "⏱️ Probably takes {time}.": "⏱️ Seguramente tarde {time}.",

    // --- the allowance and the clock --------------------------------------
    "🌙 That's all the pictures for today. See you tomorrow!":
      "🌙 Ya no quedan imágenes por hoy. ¡Hasta mañana!",
    "🌙 That's all the videos for today. See you tomorrow!":
      "🌙 Ya no quedan vídeos por hoy. ¡Hasta mañana!",
    "🌙 That's all the songs for today. See you tomorrow!":
      "🌙 Ya no quedan canciones por hoy. ¡Hasta mañana!",
    "✨ {n} pictures left today, so that's how many you'll get.":
      "✨ Hoy te quedan {n} imágenes, así que harás esas.",
    "✨ {n} videos left today, so that's how many you'll get.":
      "✨ Hoy te quedan {n} vídeos, así que harás esos.",
    "✨ {n} songs left today, so that's how many you'll get.":
      "✨ Hoy te quedan {n} canciones, así que harás esas.",
    "✨ 1 picture left today, so that's how many you'll get.":
      "✨ Hoy te queda 1 imagen, así que harás esa.",
    "✨ 1 video left today, so that's how many you'll get.":
      "✨ Hoy te queda 1 vídeo, así que harás ese.",
    "✨ 1 song left today, so that's how many you'll get.":
      "✨ Hoy te queda 1 canción, así que harás esa.",
    "✨ One more picture today - make it a good one!":
      "✨ Te queda una imagen hoy - ¡que sea buena!",
    "✨ One more video today - make it a good one!":
      "✨ Te queda un vídeo hoy - ¡que sea bueno!",
    "✨ One more song today - make it a good one!":
      "✨ Te queda una canción hoy - ¡que sea buena!",
    "✨ {n} more pictures today": "✨ {n} imágenes más hoy",
    "✨ {n} more videos today": "✨ {n} vídeos más hoy",
    "✨ {n} more songs today": "✨ {n} canciones más hoy",
    "The factory closes at {at} - any minute now!":
      "La fábrica cierra a las {at} - ¡de un momento a otro!",
    "closes-in": "La fábrica cierra a las {at} - quedan unos {mins} minutos.",
    "The factory is closed right now": "La fábrica está cerrada ahora mismo",
    "Back soon!": "¡Vuelvo pronto!",

    // --- the warm-up sums --------------------------------------------------
    "Warm up your brain!": "¡Calienta el cerebro!",
    "Get these right and the factory opens for today.":
      "Acierta estas y la fábrica abre por hoy.",
    "Get it right and the factory opens for today.":
      "Acierta esta y la fábrica abre por hoy.",
    "Get all {n} right and the factory opens for today.":
      "Acierta las {n} y la fábrica abre por hoy.",
    "Check my answers": "Comprueba mis respuestas",
    "Fill them all in first!": "¡Rellénalas todas primero!",
    "All right! Off you go.": "¡Todas bien! Adelante.",
    "So close - one of those wasn't right. Here are some new ones!":
      "Casi - una no estaba bien. ¡Aquí tienes otras nuevas!",
    "Not quite! Here are some new ones.": "¡Casi! Aquí tienes otras nuevas.",
    "Something went wrong. Try again!":
      "Algo ha salido mal. ¡Prueba otra vez!",
    "I'm a grown-up": "Soy un adulto",
    "Grown-up PIN": "PIN de adultos",
    "Let me in": "Déjame entrar",

    // --- the viewer --------------------------------------------------------
    "Pick a picture": "Elige una imagen",
    "Pick where it starts": "Elige dónde empieza",
    "Pick where it ends": "Elige dónde acaba",
    "Done": "Hecho",
    "← Back": "← Atrás",
    "What is it called?": "¿Cómo se llama?",
    "✏️ Give it a name": "✏️ Ponle un nombre",
    "What you asked for": "Lo que pediste",
    "What {name} asked for": "Lo que pidió {name}",
    "{name} made this": "Esto lo hizo {name}",
    "The words": "La letra",
    "Something you made": "Algo que hiciste",
    "Something deleted": "Algo borrado",
    "(music only - nobody sings on this one.)":
      "(solo música - en esta no canta nadie.)",
    "(read back out of the file - this is the whole prompt, including the bits the dropdowns added.)":
      "(leído del archivo - esto es todo lo que se pidió, incluido lo que " +
      "añadieron las listas.)",
    "A drawing you made. Tap Animate this to bring it to life!":
      "Un dibujo que hiciste. ¡Toca Anímala para darle vida!",
    "A card you made. Print it, or share it!":
      "Una tarjeta que hiciste. ¡Imprímela o compártela!",
    "A photo you added. Tap Animate this to bring it to life!":
      "Una foto que añadiste. ¡Toca Anímala para darle vida!",
    "This one's notes are lost - it was made before the app kept them, or straight from ComfyUI.":
      "Las notas de este se han perdido - se hizo antes de que la app las " +
      "guardara, o directamente desde ComfyUI.",
    "☆ Favourite": "☆ Favorito",
    "⭐ Favourite": "⭐ Favorito",
    "⭐ Starred": "⭐ En favoritos",
    "⭐ Starred!": "⭐ ¡En favoritos!",
    "☆ This one’s best": "☆ Esta es la mejor",
    "👨‍👩‍👧 Show the family": "👨‍👩‍👧 Mostrar a la familia",
    "👨‍👩‍👧 Hide from the family": "👨‍👩‍👧 Ocultar a la familia",
    "Everyone can see this one now! 👨‍👩‍👧":
      "¡Ahora lo puede ver todo el mundo! 👨‍👩‍👧",
    "Back to just you.": "Otra vez solo para ti.",
    "🔁 Make another like this": "🔁 Haz otro como este",
    "🎯 Make it again, but…": "🎯 Hazlo otra vez, pero…",
    "✨ Animate this": "✨ Anímala",
    "🧑‍🎤 Save as a character": "🧑‍🎤 Guardar como personaje",
    "🎤 Say something over it": "🎤 Di algo encima",
    "✂️ Turn it into a sticker": "✂️ Conviértela en pegatina",
    "✂️ Cutting it out...": "✂️ Recortándola...",
    "🔍 Make it huge": "🔍 Hazla enorme",
    "🎨 Turn it into…": "🎨 Conviértela en…",
    "🪄 Change this picture": "🪄 Cambia esta imagen",
    "🔭 What's outside the frame?": "🔭 ¿Qué hay alrededor?",
    "🩹 Fix just this bit": "🩹 Arregla solo este trozo",
    "🖼️ Put it at the top": "🖼️ Ponla arriba",
    "👤 That one's me": "👤 Esta soy yo",
    "🔊 Add a sound effect": "🔊 Ponle un sonido",
    "📸 Grab a picture from it": "📸 Sacar una imagen de aquí",
    "✨ Make it smooth": "✨ Hazlo más fluido",
    "🐌 Slow it down": "🐌 A cámara lenta",
    "🌀 Make a moving sticker": "🌀 Haz una pegatina animada",
    "✏️ Draw on it": "✏️ Dibuja encima",
    "🖨️ Print it": "🖨️ Imprímela",
    "💌 Make a card": "💌 Haz una tarjeta",
    "▶️ What happens next?": "▶️ ¿Y ahora qué?",
    "📤 Share": "📤 Compartir",
    "⬇︎ Save it": "⬇︎ Guardar",
    "↩️ Put it back": "↩️ Devolver",
    "🗑️ Delete for good": "🗑️ Borrar para siempre",
    "In the trash": "En la papelera",
    "Gone - it's in the trash.": "Se ha ido - está en la papelera.",
    "＋ Add a tag": "＋ Poner una etiqueta",
    "What tag?": "¿Qué etiqueta?",
    "What tag should these get?": "¿Qué etiqueta les ponemos?",
    "\n\nAlready used: ": "\n\nYa usadas: ",
    "{n} thing tagged “#{tag}”": "{n} cosa con la etiqueta “#{tag}”",
    "{n} things tagged “#{tag}”": "{n} cosas con la etiqueta “#{tag}”",
    "Couldn't open your gallery right now. Try again!":
      "Ahora mismo no se ha podido abrir tu galería. ¡Prueba otra vez!",
    "That one's turned off just now.": "Eso está apagado ahora mismo.",

    // --- what kind of thing a tile is --------------------------------------
    "📖 Comic": "📖 Cómic",
    "🧩 Panel": "🧩 Viñeta",
    "📷 Photo": "📷 Foto",
    "🎬 Film": "🎬 Película",
    "🎤 My voice": "🎤 Mi voz",
    "🔊 Sound": "🔊 Sonido",
    "✂️ Sticker": "✂️ Pegatina",
    "📸 From a video": "📸 De un vídeo",
    "🎵 Song": "🎵 Canción",

    // --- what kind of sound: a song, a little tune, a background
    //     hum. One card and one model; see app/music.py KINDS.
    "What kind": "Qué tipo",
    "What kind of sound to make": "Qué tipo de sonido hacer",
    "Make my tune": "Haz mi melodía",
    "Make my sound": "Haz mi sonido",
    "🎲 Thinking of a sound...": "🎲 Pensando en un sonido...",
    "Your tune is ready! ✨": "¡Tu melodía está lista! ✨",
    "Your sound is ready! ✨": "¡Tu sonido está listo! ✨",
    "Making a little tune": "Estoy haciendo una melodía",
    "Making a background hum": "Estoy haciendo un sonido de fondo",
    "🎺 Little tune": "🎺 Melodía",
    "🌊 Background hum": "🌊 Sonido de fondo",
    "✨ Smooth": "✨ Fluido",
    "🐌 Slow motion": "🐌 Cámara lenta",
    "🌀 Moving sticker": "🌀 Pegatina animada",
    "🔍 Huge": "🔍 Enorme",
    "🪄 Changed": "🪄 Cambiada",
    "🔭 More of it": "🔭 Más grande",
    "🩹 Fixed a bit": "🩹 Arreglada",
    "🎨 A new style": "🎨 Estilo nuevo",
    "✏️ Drawing": "✏️ Dibujo",
    "💌 Card": "💌 Tarjeta",
    "▶ Video": "▶ Vídeo",

    // --- the result row ----------------------------------------------------
    "The picture you made": "La imagen que has hecho",
    "One of the pictures you made": "Una de las imágenes que has hecho",
    "Your comic": "Tu cómic",
    "🎲 Try again": "🎲 Otra vez",
    "⬇︎ Save picture": "⬇︎ Guardar imagen",
    "⬇︎ Save video": "⬇︎ Guardar vídeo",
    "⬇︎ Save song": "⬇︎ Guardar canción",
    "⬇︎ Save my film": "⬇︎ Guardar mi película",
    "⬇︎ Save my comic": "⬇︎ Guardar mi cómic",
    "⬇︎ Save them all": "⬇︎ Guardarlo todo",
    "Keep this one": "Quedarme con esta",
    "✓ Kept": "✓ Guardada",
    "Delete this one": "Borrar esta",
    "It's a sticker! ✂️": "¡Es una pegatina! ✂️",
    "It's ready! ✨": "¡Está lista! ✨",
    "It's ready! 🔍": "¡Está lista! 🔍",
    "Your very first picture! 🎉": "¡Tu primera imagen! 🎉",
    "Your very first video! 🎉": "¡Tu primer vídeo! 🎉",
    "Your very first comic! 🎉": "¡Tu primer cómic! 🎉",
    "Your very first film! 🎉": "¡Tu primera película! 🎉",
    "That's {n} pictures! 🎉": "¡Ya son {n} imágenes! 🎉",
    "That's {n} videos! 🎉": "¡Ya son {n} vídeos! 🎉",
    "That's {n} comics! 🎉": "¡Ya son {n} cómics! 🎉",
    "That's {n} films! 🎉": "¡Ya son {n} películas! 🎉",

    // --- characters ---------------------------------------------------------
    "Character": "Personaje",
    "What's this character called?": "¿Cómo se llama este personaje?",
    "Having a good look at {name}...": "Mirando bien a {name}...",
    "{name} can be in your next one! 🧑‍🎤":
      "¡{name} puede salir en la próxima! 🧑‍🎤",
    "That's {n} characters already! Say goodbye to one first, in the Gallery.":
      "¡Ya tienes {n} personajes! Despídete de uno primero, en la Galería.",
    "Forget “{idea}”": "Olvidar “{idea}”",
    "✏️ Rename": "✏️ Otro nombre",
    "🎨 How they look": "🎨 Cómo es",
    "👋 Say goodbye to them": "👋 Despedirse",
    "Nothing with them in it yet! Choose them under “Who’s in it?” and make something.":
      "¡Todavía no hay nada donde salga! Elígelo en “¿Quién sale?” y haz " +
      "algo.",
    "What should they be called?": "¿Cómo se va a llamar?",
    "One sentence saying what they look like. This gets used in every picture they're in, so be specific about colours and clothes.":
      "Una frase que diga cómo es. Se usa en todas las imágenes donde " +
      "sale, así que di bien los colores y la ropa.",
    "Said goodbye to {name}. Their pictures are still in the Gallery.":
      "Te has despedido de {name}. Sus imágenes siguen en la Galería.",
    "Couldn't load them just now.": "Ahora mismo no se han podido cargar.",

    // --- the film and card makers -------------------------------------------
    "Make a film": "Hacer una película",
    "{n} videos, in the order you chose them. It'll open with a title card - give it a name!":
      "{n} vídeos, en el orden en que los elegiste. Empezará con un cartel " +
      "de título - ¡ponle un nombre!",
    "🎬 What's your film called?": "🎬 ¿Cómo se llama tu película?",
    "The Great Pancake Adventure": "La gran aventura de las tortitas",
    "My Film": "Mi película",
    "{title} presents": "{title} presenta",
    "Joining your film... this takes a little while.":
      "Uniendo tu película... esto tarda un ratito.",
    "Done! It's at the top of your videos.":
      "¡Hecho! Está arriba del todo en tus vídeos.",
    "Make a card": "Hacer una tarjeta",
    "Save my card": "Guardar mi tarjeta",
    "💌 What should it say?": "💌 ¿Qué quieres que ponga?",
    "Happy birthday Grandma!": "¡Feliz cumpleaños, abuela!",
    "Card colour": "Color de la tarjeta",
    "Card colour {n}": "Color de la tarjeta {n}",
    "Made for you!": "¡Hecha para ti!",
    "made at {title}": "hecha en {title}",
    "Saving your card...": "Guardando tu tarjeta...",
    "Saved! It's in Photos & drawings - open it to print or share.":
      "¡Guardada! Está en Fotos y dibujos - ábrela para imprimirla o " +
      "compartirla.",
    "My comic": "Mi cómic",

    // --- their voice, sounds, frames, loops -----------------------------------
    "🎤 Say something": "🎤 Di algo",
    "✕ Close": "✕ Cerrar",
    "Tap the big button and talk. Your voice goes on top of your video.":
      "Toca el botón grande y habla. Tu voz se pone encima de tu vídeo.",
    "Start talking": "Empieza a hablar",
    "Keep the video's own sound too (it goes quieter while you talk)":
      "Dejar también el sonido del vídeo (baja mientras hablas)",
    "✨ Put it on my video": "✨ Ponla en mi vídeo",
    "🔁 Record it again": "🔁 Grabar otra vez",
    "🗑️ Throw the recording away": "🗑️ Tirar la grabación",
    "Or use a sound you already have": "O usa un sonido que ya tengas",
    "This browser can't record here - that needs https. Pick a sound from your files below instead.":
      "Este navegador no puede grabar aquí - hace falta https. Elige abajo " +
      "un sonido de tus archivos.",
    "You haven't put it on your video yet!":
      "¡Todavía no la has puesto en tu vídeo!",
    "Your iPad needs to say yes to the microphone first. Tap the big button again and choose Allow.":
      "Tu iPad tiene que decir que sí al micrófono primero. Toca otra vez " +
      "el botón grande y elige Permitir.",
    "I can't find a microphone on this device. You can pick a sound from your files below instead.":
      "No encuentro ningún micrófono en este aparato. Puedes elegir abajo " +
      "un sonido de tus archivos.",
    "The microphone didn't start ({why}). You can pick a sound from your files below instead.":
      "El micrófono no ha arrancado ({why}). Puedes elegir abajo un sonido " +
      "de tus archivos.",
    "Putting your voice on it...": "Poniendo tu voz...",
    "Your voice is on it! 🎤": "¡Tu voz ya está puesta! 🎤",
    "Pick a sound, slide to where you want it, then put it on.":
      "Elige un sonido, deslízalo hasta donde lo quieras y ponlo.",
    "When the sound happens": "Cuándo suena el sonido",
    "Couldn't load the sounds.": "No se han podido cargar los sonidos.",
    "Putting it on...": "Poniéndolo...",
    "Sound added! 🔊": "¡Sonido añadido! 🔊",
    "📸 Grab a picture": "📸 Sacar una imagen",
    "Slide to the bit you like. The picture underneath is exactly what you'll keep.":
      "Desliza hasta el trozo que te guste. La imagen de abajo es justo lo " +
      "que te vas a quedar.",
    "Which bit?": "¿Qué trozo?",
    "Which moment to keep": "Qué momento quedarse",
    "The picture you are about to keep": "La imagen que te vas a quedar",
    "✨ Keep this picture": "✨ Quédate esta imagen",
    "Keeping it...": "Guardándola...",
    "Kept it as a picture! 📸": "¡Guardada como imagen! 📸",
    "Pick the bit you want and it'll loop for ever - a sticker that moves.":
      "Elige el trozo que quieras y se repetirá sin parar - una pegatina " +
      "que se mueve.",
    "Start here": "Empieza aquí",
    "Where the loop starts": "Dónde empieza el bucle",
    "How long?": "¿Cuánto dura?",
    "How long the loop is": "Cuánto dura el bucle",
    "1 second": "1 segundo",
    "2 seconds": "2 segundos",
    "Where your moving sticker starts": "Dónde empieza tu pegatina animada",
    "✨ Make my sticker": "✨ Haz mi pegatina",
    "Making it...": "Haciéndola...",
    "It moves! 🌀": "¡Se mueve! 🌀",

    // --- the three edits ----------------------------------------------------
    "Say what you'd like different and it'll make the same picture again with that changed.":
      "Di qué quieres que cambie y hará la misma imagen otra vez con ese " +
      "cambio.",
    "The picture you're changing": "La imagen que estás cambiando",
    "What should be different?": "¿Qué quieres que cambie?",
    "make it night-time\ngive the fox a scarf":
      "que sea de noche\nponle una bufanda al zorro",
    "make it night-time": "que sea de noche",
    "make it snowy": "que esté nevando",
    "add a rainbow": "añade un arcoíris",
    "make it look like a painting": "que parezca un cuadro",
    "put a hat on it": "ponle un sombrero",
    "make everything tiny": "que todo sea diminuto",
    "...and put me in it 👤": "...y ponme a mí 👤",
    "✨ Go": "✨ ¡Vamos!",
    "Tell me what should be different!": "¡Dime qué quieres que cambie!",
    "Changing your picture... 🪄": "Cambiando tu imagen... 🪄",
    "Pick a kind of picture and it'll draw this one again that way, with everything still where it is.":
      "Elige un tipo de imagen y dibujará esta otra vez así, con todo en " +
      "el mismo sitio.",
    "The picture you're turning into something else":
      "La imagen que estás convirtiendo en otra cosa",
    "What to turn it into": "En qué convertirla",
    "Anything else? (you don't have to say)":
      "¿Algo más? (no hace falta decir nada)",
    "you don't have to say - or add your own twist: make it night-time":
      "no hace falta decir nada - o añade tu toque: que sea de noche",
    "Pick what to turn it into!": "¡Elige en qué convertirla!",
    "Drawing it again... 🎨": "Dibujándola otra vez... 🎨",
    "Pick a side and it'll invent what was just out of the picture.":
      "Elige un lado y se inventará lo que había justo fuera de la imagen.",
    "The picture you're growing": "La imagen que estás agrandando",
    "Which way?": "¿Hacia dónde?",
    "Which way to grow": "Hacia dónde crecer",
    "All round": "Por todos lados",
    "⬅️ Left": "⬅️ Izquierda",
    "➡️ Right": "➡️ Derecha",
    "⬆️ Up": "⬆️ Arriba",
    "⬇️ Down": "⬇️ Abajo",
    "How much?": "¿Cuánto?",
    "How much bigger": "Cuánto más grande",
    "A bit": "Un poco",
    "A lot": "Mucho",
    "What's out there? (you don't have to say)":
      "¿Qué hay ahí fuera? (no hace falta decir nada)",
    "you don't have to say - or try: a beach, more trees":
      "no hace falta decir nada - o prueba: una playa, más árboles",
    "Looking outside the frame... 🔭": "Mirando fuera de la imagen... 🔭",
    "Say what should be there instead, then tap Go.":
      "Di qué quieres que haya ahí y toca Vamos.",
    "Paint over the bit you want changed first!":
      "¡Pinta primero encima del trozo que quieres cambiar!",
    "Fixing that bit... 🩹": "Arreglando ese trozo... 🩹",
    "Slowing it right down... it comes out quiet 🐌":
      "Poniéndolo muy lento... sale sin sonido 🐌",
    "Smoothing it out... ✨": "Haciéndolo más fluido... ✨",
    "Making it huge... 🔍": "Haciéndola enorme... 🔍",
    "Cutting it out...": "Recortándola...",

    // --- compare ------------------------------------------------------------
    "🔍 Which one?": "🔍 ¿Cuál prefieres?",
    "Slide across to see one and then the other.":
      "Desliza para ver una y luego la otra.",
    "The first one": "La primera",
    "The second one": "La segunda",
    "Slide between the two pictures": "Desliza entre las dos imágenes",

    // --- the drawing pad ----------------------------------------------------
    "Draw something": "Dibuja algo",
    "Use my drawing": "Usa mi dibujo",
    "Colour": "Color",
    "Colour {n}": "Color {n}",
    "Stamps": "Sellos",
    "Stamp {emoji}": "Sello {emoji}",
    "Thin brush": "Pincel fino",
    "Medium brush": "Pincel mediano",
    "Thick brush": "Pincel gordo",
    "🧽 Rubber": "🧽 Goma",
    "↶ Undo": "↶ Deshacer",
    "Start again": "Empezar de nuevo",
    "What should be there instead?": "¿Qué quieres que haya ahí?",
    "what should be there instead? e.g. a red party hat":
      "¿qué quieres que haya ahí? por ejemplo, un gorro de fiesta rojo",
    "Draw with your finger or a pencil. When you're done, tap <strong>Use my drawing</strong>.":
      "Dibuja con el dedo o con un lápiz. Cuando acabes, toca <strong>Usa " +
      "mi dibujo</strong>.",
    "Paint over the bit you want changed, say what should be there, then tap <strong>Go</strong>.":
      "Pinta encima del trozo que quieres cambiar, di qué quieres que haya " +
      "ahí y toca <strong>¡Vamos!</strong>.",

    // --- the chat tab -------------------------------------------------------
    "Chat with": "Chatear con",
    "Ask for an idea, or tell me what you’re making. Your grown-ups can read everything said here.":
      "Pídeme una idea o cuéntame qué estás haciendo. Tus adultos pueden " +
      "leer todo lo que se dice aquí.",
    "Your chat": "Tu chat",
    "Say something": "Di algo",
    "Say something…": "Di algo…",
    "Send it": "Enviar",
    "Start a new chat": "Empezar un chat nuevo",
    "Started a new chat. Your grown-ups can still see the old one.":
      "Chat nuevo empezado. Tus adultos siguen viendo el de antes.",
    "The chat helper isn't set up on this machine yet. Everything else still works!":
      "El ayudante del chat todavía no está puesto en esta máquina. ¡Todo " +
      "lo demás funciona!",
    "Give me an idea for a picture": "Dame una idea para una imagen",
    "What can I make here?": "¿Qué puedo hacer aquí?",
    // The third starter exists to show them they can write in the other
    // language, so on a French page it is the English one.
    "Donne-moi une idée de dessin": "Dame una idea para un dibujo",
    "🎨 Make a picture of this": "🎨 Haz una imagen de esto",
    "🎬 Make a video of this": "🎬 Haz un vídeo de esto",
    "📋 Copy": "📋 Copiar",
    "✓ Copied": "✓ Copiado",
    "✕ Couldn't copy": "✕ No se pudo copiar",
    "That's what {name} said. Change anything you like, or tap “Help me write it” to turn it into a proper description.":
      "Eso es lo que ha dicho {name}. Cambia lo que quieras, o toca " +
      "“Ayúdame a escribirlo” para convertirlo en una descripción de " +
      "verdad.",
    "the helper": "el ayudante",

    // --- Settings -----------------------------------------------------------
    "You": "Tú",
    "You're {name}!": "¡Tú eres {name}!",
    "🪄 Make a picture of me": "🪄 Haz una imagen de mí",
    "😃 Pick a face instead": "😃 Mejor elijo una cara",
    "↩️ Back to the face": "↩️ Volver a la cara",
    "Pick a face": "Elige una cara",
    "Colours": "Colores",
    "Language": "Idioma",
    "Which language": "Qué idioma",
    "The top of your page": "La imagen de arriba",
    "What is across the top of your page now":
      "Lo que hay ahora arriba del todo",
    "↩️ Put the first one back": "↩️ Poner la de antes",
    "Put back the one it came with.": "Vuelve a poner la del principio.",
    "Couldn't change it back.": "No se ha podido volver a poner.",
    "Making new ones is switched off right now, but you can still use any picture from <strong>Gallery</strong> — open one and tap <strong>Put it at the top</strong>.":
      "Ahora mismo no se pueden hacer nuevas, pero puedes usar cualquier " +
      "imagen de la <strong>Galería</strong> — abre una y toca " +
      "<strong>Ponla arriba</strong>.",
    "It's a long thin strip, so wide things work best — a row of something, a view, a pattern. Your name goes on top of it, so leave the middle fairly quiet.":
      "Es una tira larga y estrecha, así que van mejor las cosas anchas — " +
      "una fila de algo, un paisaje, un dibujo repetido. Tu nombre va " +
      "encima, así que deja el centro bastante tranquilo.",
    "🖼️ Putting it up...": "🖼️ Poniéndola...",
    "That's the top of your page now! 🖼️": "¡Ya está arriba del todo! 🖼️",
    "That one wouldn't go up there.": "Esa no se ha podido poner ahí.",
    "Kept it on this device, but it wouldn't save.":
      "Se ha quedado en este aparato, pero no se ha podido guardar.",
    "Tap your face. A grown-up adds and changes these on the parent page.":
      "Toca tu cara. Un adulto las añade y las cambia en la página de los " +
      "padres.",
    "👤 Making it you...": "👤 Poniéndote a ti...",
    "That's you now! 👤": "¡Ahora eres tú! 👤",
    "I'm a grown-up — the parent page":
      "Soy un adulto — la página de los padres",

    // --- who is making things today -----------------------------------------
    "Who's making things today?": "¿Quién hace cosas hoy?",

    // --- the picture-of-me wizard -------------------------------------------
    "Make a picture of me": "Haz una imagen de mí",
    "1. What are you?": "1. ¿Qué eres?",
    "What are you?": "¿Qué eres?",
    "Or type your own": "O escribe lo tuyo",
    "…or type your own": "…o escribe lo tuyo",
    "2. What colour?": "2. ¿De qué color?",
    "What colour?": "¿De qué color?",
    "3. Anything else?": "3. ¿Algo más?",
    "Anything else?": "¿Algo más?",
    "Anything else": "Algo más",
    "…a wizard hat, freckles, a scarf":
      "…un sombrero de mago, pecas, una bufanda",
    "Let's make it! ✨": "¡Vamos a hacerla! ✨",
    "It makes four at once so you can pick your favourite. Then tap <strong>👤 That one's me</strong> under the one you like.":
      "Hace cuatro a la vez para que elijas tu favorita. Luego toca " +
      "<strong>👤 Esta soy yo</strong> debajo de la que más te guste.",
    "Pick what you are to get started!": "¡Elige qué eres para empezar!",
    "Pick what you are first!": "¡Elige primero qué eres!",
    "Making pictures is switched off right now.":
      "Ahora mismo no se pueden hacer imágenes.",
    "Tap Go and pick your favourite! ✨":
      "¡Toca el botón y elige tu favorita! ✨",
    // The wizard's choices. The sentence they compose is a prompt, so the
    // article travels with the word in French, where gender does too.
    "a fox": "un zorro", "a cat": "un gato", "a dog": "un perro",
    "a dragon": "un dragón", "a robot": "un robot", "an owl": "un búho",
    "a unicorn": "un unicornio", "a penguin": "un pingüino",
    "an astronaut": "un astronauta", "a wizard": "un mago",
    "a superhero": "un superhéroe", "a pirate": "un pirata",
    "a mermaid": "una sirena", "a knight": "un caballero",
    "a panda": "un panda", "an octopus": "un pulpo",
    // "en violet" rather than "violet": the colour then agrees with nothing,
    // so one word does for a fox and for a mermaid alike.
    "purple": "morado", "blue": "azul", "green": "verde",
    "orange": "naranja", "pink": "rosa", "red": "rojo",
    "yellow": "amarillo", "rainbow": "arcoíris", "silver": "plateado",
    "golden": "dorado",
    "a wizard hat": "un sombrero de mago",
    "big round glasses": "gafas redondas grandes",
    "a stripy scarf": "una bufanda de rayas",
    "a cape": "una capa", "headphones": "auriculares",
    "a flower crown": "una corona de flores", "a bow tie": "una pajarita",
    "freckles": "pecas",

    // --- when it is shut -----------------------------------------------------
    "just now": "ahora mismo",
    "{n} minute ago": "hace {n} minuto",
    "{n} minutes ago": "hace {n} minutos",
    "{n} hour ago": "hace {n} hora",
    "{n} hours ago": "hace {n} horas",
    "{n} KB": "{n} KB",
    "{n} MB": "{n} MB",

    // The close button on every sheet. Static markup, so it is a
    // data-i18n and not a t() - and it was English in every language
    // until the coverage walk went looking for exactly this.
    "✕ Close": "✕ Cerrar",
  };

  // Italian. The same keys in the same order under the same headings
  // as FR above, so a line missing from one of them is a line out of step.
  var IT = {
    // --- the shell ------------------------------------------------------
    "My AI Factory": "La mia fabbrica IA",
    "AI Factory": "Fabbrica IA",
    "What would you like to do?": "Cosa vuoi fare?",
    "That's me - tap to swap": "Sono io - tocca per cambiare",
    "Show me": "Fammi vedere",
    "Working...": "Sto lavorando...",
    "wiz-sentence":
      "{thing} {colour}molto gentile{wearing}, un allegro ritratto in " +
      "stile cartone animato, testa e spalle, grandi occhi simpatici",
    "wiz-wearing": " che indossa {list}",
    "wiz-and": " e ",
    "wiz-colour": "di colore {colour} ",

    // Tabs. Short on purpose: seven of them share one row at 390px.
    "Picture": "Immagine",
    "Video": "Video",
    "Comic": "Fumetto",
    "Music": "Musica",
    "Chat": "Chat",
    "Gallery": "Galleria",
    "Settings": "Opzioni",

    // --- "your picture is ready" ----------------------------------------
    "Your picture is ready! ✨": "La tua immagine è pronta! ✨",
    "Your video is ready! ✨": "Il tuo video è pronto! ✨",
    "Your comic is ready! ✨": "Il tuo fumetto è pronto! ✨",
    "Your film is ready! ✨": "Il tuo film è pronto! ✨",
    "Your song is ready! ✨": "La tua canzone è pronta! ✨",
    "Your smooth video is ready! ✨": "Il tuo video fluido è pronto! ✨",
    "Your slow-motion video is ready! ✨":
      "Il tuo video al rallentatore è pronto! ✨",
    "Your big picture is ready! ✨": "La tua immagine grande è pronta! ✨",
    "Your bigger picture is ready! ✨":
      "La tua immagine più grande è pronta! ✨",
    "Your changed picture is ready! ✨": "La tua immagine cambiata è pronta! ✨",

    // --- the Gallery ------------------------------------------------------
    "Everything you've made is saved here.":
      "Qui c'è tutto quello che hai fatto.",
    "Nothing here yet! Make a picture, a video or a comic and it'll turn up here.":
      "Qui non c'è ancora niente! Fai un'immagine, un video o un fumetto e " +
      "comparirà qui.",
    "Nothing of yours yet - but there's something on the family shelf!":
      "Ancora niente di tuo - ma c'è qualcosa sullo scaffale di famiglia!",
    "You've made 1 thing so far.": "Finora hai fatto 1 cosa.",
    "You've made {n} things so far.": "Finora hai fatto {n} cose.",
    "🧑‍🎤 My characters": "🧑‍🎤 I miei personaggi",
    "Show": "Mostra",
    "How to show your gallery": "Come mostrare la tua galleria",
    "Everything": "Tutto",
    "In groups": "A gruppi",
    "Order": "Ordine",
    "What order to show them in": "In che ordine mostrarle",
    "Newest": "Più recenti",
    "Oldest": "Più vecchie",
    "⭐ Favourites": "⭐ Preferite",
    "By kind": "Per tipo",
    "🔎 Find something you made": "🔎 Cerca qualcosa che hai fatto",
    "Search your gallery": "Cerca nella tua galleria",
    "Clear the search": "Cancella la ricerca",
    "Choose": "Scegli",
    "Cancel": "Annulla",
    "👨‍👩‍👧 Family": "👨‍👩‍👧 Famiglia",
    "🎨 Pictures": "🎨 Immagini",
    "📖 Comics": "📖 Fumetti",
    "🧩 Comic pictures": "🧩 Vignette",
    "✂️ Stickers": "✂️ Adesivi",
    "📷 Photos & drawings": "📷 Foto e disegni",
    "🎬 Videos": "🎬 Video",
    "🎵 Songs": "🎵 Canzoni",
    "Nothing matches that. Try another word!":
      "Non trovo niente. Prova un'altra parola!",
    "Nothing here yet! Go and make something.":
      "Qui non c'è ancora niente! Vai a fare qualcosa.",
    "🗑️ Recently deleted": "🗑️ Cancellate da poco",
    "Things stay here for {days} days, then they're gone for good. Tap one to put it back.":
      "Le cose restano qui {days} giorni, poi spariscono per sempre. " +
      "Toccane una per rimetterla a posto.",
    "Nothing chosen yet": "Non hai scelto niente",
    "Tap the ones you want": "Tocca quelle che vuoi",
    "1 chosen": "1 scelta",
    "{n} chosen": "{n} scelte",
    "Choose all": "Scegli tutto",
    "Choose none": "Scegli niente",
    "🎬 Join into a film": "🎬 Unisci in un film",
    "🔍 Compare them": "🔍 Mettile a confronto",
    "🏷️ Add a tag": "🏷️ Aggiungi un'etichetta",
    "⬇︎ Save": "⬇︎ Salva",
    "🗑️ Delete": "🗑️ Cancella",
    "Deleted": "Cancellata",
    "{n} things deleted": "{n} cose cancellate",
    "Undo": "Annulla",
    "Put back!": "Rimessa a posto!",
    "All put back!": "Rimesse tutte a posto!",
    "Really delete?": "Cancello davvero?",
    "Really delete it?": "La cancello davvero?",
    "Really delete all {n}?": "Le cancello davvero tutte e {n}?",
    "Really delete forever?": "Cancello per sempre?",
    "Really clear it?": "Cancello tutto davvero?",
    "Really say goodbye?": "Gli dico davvero addio?",

    // --- the maker cards -------------------------------------------------
    "Make a picture": "Fai un'immagine",
    "Make a video": "Fai un video",
    "Make a comic": "Fai un fumetto",
    "Make a song": "Fai una canzone",
    "↺ Start again": "↺ Ricomincia",
    "Clear everything on this card and start again":
      "Cancella tutto su questa scheda e ricomincia",
    "What should the picture be?": "Che immagine vuoi?",
    "What should the video be?": "Che video vuoi?",
    "What's your story?": "Qual è la tua storia?",
    "What should the song be about?": "Di cosa parla la canzone?",
    "What should the top of your page look like?":
      "Come deve essere la cima della tua pagina?",
    "A fluffy dragon eating pancakes on the moon":
      "Un drago peloso che mangia frittelle sulla Luna",
    "A puppy surfing a giant wave at sunset":
      "Un cucciolo che fa surf su un'onda gigante al tramonto",
    "It flaps its wings and flies up into the clouds":
      "Sbatte le ali e vola su tra le nuvole",
    "The cat walks across the room and curls up in the sunny spot":
      "Il gatto attraversa la stanza e si accoccola nel punto assolato",
    "A little robot looking for its lost cat in a big city":
      "Un piccolo robot che cerca il suo gatto perduto in una grande città",
    "A hedgehog who wants to learn to swim":
      "Un riccio che vuole imparare a nuotare",
    "A dragon who is scared of pancakes":
      "Un drago che ha paura delle frittelle",
    "A row of hot air balloons over a green valley":
      "Una fila di mongolfiere sopra una valle verde",
    "Clear what you typed": "Cancella quello che hai scritto",
    "✨ Help me write it": "✨ Aiutami a scrivere",
    "👀 Look at my picture and help me write it":
      "👀 Guarda la mia immagine e aiutami a scrivere",
    "✨ Write me a song": "✨ Scrivimi una canzone",
    "🎉 Surprise me": "🎉 Sorprendimi",
    "🎲 Mix it up": "🎲 Mescola tutto",
    "📜 Things I've asked for before": "📜 Cose che ho già chiesto",
    "📷 Start from a photo": "📷 Parti da una foto",
    "🖼️ Pick one from my gallery": "🖼️ Scegline una dalla galleria",
    "Who's in it?": "Chi c'è dentro?",
    "Nobody": "Nessuno",
    "📄 Everything with {name} in it": "📄 Tutto quello con dentro {name}",
    "Make": "Fai",
    "What kind of picture": "Che tipo di immagine",
    "A picture": "Un'immagine",
    "A character": "Un personaggio",
    "Drawn on its own with nothing behind it, so you can cut it out as a sticker or keep them as a character.":
      "Disegnato da solo, senza niente dietro, così puoi ritagliarlo come " +
      "adesivo o tenerlo come personaggio.",
    "Shape": "Forma",
    "Picture shape": "Forma dell'immagine",
    "Video shape": "Forma del video",
    "Landscape": "Orizzontale",
    "Portrait": "Verticale",
    "Square": "Quadrata",
    "landscape": "orizzontale",
    "portrait": "verticale",
    "square": "quadrata",
    "How many": "Quante",
    "How many pictures": "Quante immagini",
    "How many panels": "Quante vignette",
    "Just one": "Una sola",
    "Four to pick from": "Quattro tra cui scegliere",
    "3 pictures": "3 immagini",
    "4 pictures": "4 immagini",
    "6 pictures": "6 immagini",
    "Look": "Aspetto",
    "Look and sound": "Aspetto e suono",
    "Sound": "Suono",
    "Clear these": "Cancella questi",
    "Any": "A scelta",
    "Make my picture": "Fai la mia immagine",
    "Make {n} pictures": "Fai {n} immagini",
    "Make my video": "Fai il mio video",
    "Make my film": "Fai il mio film",
    "Animate it": "Animala",
    "Make my comic": "Fai il mio fumetto",
    "Make my song": "Fai la mia canzone",
    "Make my music": "Fai la mia musica",
    "Make one": "Fanne una",
    "Stop": "Stop",
    "Tell a story and it gets drawn as a comic strip you can print.":
      "Racconta una storia e diventa un fumetto che puoi stampare.",

    // video card
    "Start from": "Parti da",
    "What to start the video from": "Da cosa far partire il video",
    "✏️ Words": "✏️ Parole",
    "🖼️ A picture": "🖼️ Un'immagine",
    "🎞️ Two pictures": "🎞️ Due immagini",
    "📽️ A little film": "📽️ Un filmino",
    "Make a picture up above and tap <strong>Animate this</strong>, or use a photo from your iPad.":
      "Fai un'immagine qui sopra e tocca <strong>Animala</strong>, oppure " +
      "usa una foto del tuo iPad.",
    "The picture you picked": "L'immagine che hai scelto",
    "This picture is ready to animate!":
      "Questa immagine è pronta per essere animata!",
    "Use a different one": "Usane un'altra",
    "📷 Take or choose a photo": "📷 Scatta o scegli una foto",
    "✏️ Draw one": "✏️ Disegnane una",
    "Pick where the video starts and where it ends. The middle gets made up.":
      "Scegli dove comincia e dove finisce il video. Il mezzo se lo inventa.",
    "Starts on": "Comincia con",
    "Ends on": "Finisce con",
    "🖼️ Pick from the gallery": "🖼️ Scegli dalla galleria",
    "🖼️ Pick a different one": "🖼️ Scegline un'altra",
    "🗣️ What should they say?": "🗣️ Cosa devono dire?",
    "(you can leave this empty)": "(puoi lasciarlo vuoto)",
    "Look at the Earth from up here!": "Guarda la Terra da quassù!",
    "Clear what they say": "Cancella quello che dicono",
    "🔊 Videos have sound — they'll say this out loud, so keep it short.":
      "🔊 I video hanno il suono — lo diranno ad alta voce, quindi tienilo " +
      "corto.",
    "Quality": "Qualità",
    "Video quality": "Qualità del video",
    "⚡ Quick": "⚡ Veloce",
    "👍 Normal": "👍 Normale",
    "✨ Sharper": "✨ Più nitido",
    "Sharper means more detail, but it takes a good deal longer to make, and the longest a sharper video can be is":
      "Più nitido vuol dire più dettagli, ma ci vuole molto più tempo, e " +
      "un video più nitido può durare al massimo",
    "seconds.": "secondi.",
    "How long": "Quanto dura",
    "Video length in seconds": "Durata del video in secondi",
    "How long the song is, in seconds": "Durata della canzone in secondi",
    "{n} seconds": "{n} secondi",
    "Longer videos take longer to make.":
      "I video più lunghi ci mettono più tempo.",
    "Longer songs take longer to make.":
      "Le canzoni più lunghe ci mettono più tempo.",
    "How many parts": "Quante parti",
    "2 parts": "2 parti",
    "3 parts": "3 parti",
    "4 parts": "4 parti",
    "Each part carries on from the last one, then they're joined into one film. It takes a while, and it uses up one video for each part.":
      "Ogni parte continua da quella prima, poi vengono unite in un film " +
      "solo. Ci vuole un po', e consuma un video per ogni parte.",
    "🔊 Add a sound": "🔊 Aggiungi un suono",
    "None": "Niente",
    "When?": "Quando?",
    "At the start": "All'inizio",
    "In the middle": "Nel mezzo",
    "At the end": "Alla fine",

    // music card
    "Singing": "Canto",
    "Singing or not": "Con o senza canto",
    "With singing": "Con il canto",
    "Just music": "Solo musica",
    "Words": "Parole",
    "Clear the words": "Cancella le parole",
    "[Verse]\nI met a dragon on the stairs\nHe said he doesn't like éclairs\n\n[Chorus]\nPancakes, pancakes, run away!":
      "[Strofa]\nHo visto un drago sulle scale\nHa detto che gli fa " +
      "male\n\n[Ritornello]\nFrittelle, frittelle, scappa via!",
    "Put <strong>[Verse]</strong> or <strong>[Chorus]</strong> on a line of their own to mark the parts. Leave it empty and you'll get music with nobody singing.":
      "Metti <strong>[Strofa]</strong> o <strong>[Ritornello]</strong> su " +
      "una riga da soli per segnare le parti. Lascia vuoto e avrai musica " +
      "senza nessuno che canta.",

    // --- the helpers -----------------------------------------------------
    "Type a few words about your idea first!":
      "Prima scrivi due parole sulla tua idea!",
    "Thinking of ideas...": "Penso a qualche idea...",
    "Looking at your picture...": "Guardo la tua immagine...",
    "This takes a moment the first time.":
      "La prima volta ci vuole un momento.",
    "Here you go! Change anything you like.":
      "Ecco qua! Cambia quello che vuoi.",
    "Here's an idea for it - change anything you like.":
      "Ecco un'idea - cambia quello che vuoi.",
    "Writing your song...": "Scrivo la tua canzone...",
    "Here are some words! Change any line you like - they don't have to rhyme.":
      "Ecco delle parole! Cambia le righe che vuoi - non devono per forza " +
      "fare rima.",
    "🎲 Thinking of something...": "🎲 Penso a qualcosa...",
    "🎲 Writing a song...": "🎲 Scrivo una canzone...",
    "Dreaming up an idea...": "Invento un'idea...",
    "Here's a whole song! Change any line you like.":
      "Ecco una canzone intera! Cambia le righe che vuoi.",
    "Here's an idea! Change anything you like.":
      "Ecco un'idea! Cambia quello che vuoi.",
    "One of your old ideas with a brand new look. Change anything you like!":
      "Una delle tue vecchie idee con un aspetto nuovo di zecca. Cambia " +
      "quello che vuoi!",
    "A brand new idea. Change anything you like!":
      "Un'idea nuova di zecca. Cambia quello che vuoi!",
    "🎲 Shuffling...": "🎲 Mescolo...",
    "Same as before - change anything you like, then go!":
      "Come prima - cambia quello che vuoi, poi vai!",
    "Change a word or two and you'll get this same one, but different. “Make another like this” starts from scratch instead.":
      "Cambia una parola o due e avrai questa stessa immagine, ma diversa. " +
      "“Fanne un'altra così” invece ricomincia da capo.",
    "Your drawing is ready! Tap the helper to get a script for it, or say what should happen.":
      "Il tuo disegno è pronto! Tocca l'aiutante per avere un copione, " +
      "oppure di' cosa deve succedere.",
    "This starts where that video stopped. What happens next?":
      "Questo parte da dove finiva quel video. Cosa succede adesso?",

    // --- while it renders -------------------------------------------------
    "Sending it off...": "Lo mando...",
    "Getting started...": "Comincio...",
    "Starting": "Sto cominciando",
    "Making another one...": "Ne faccio un'altra...",
    "Getting it ready...": "La preparo...",
    "Working out your story...": "Penso alla tua storia...",
    "Reading your story...": "Leggo la tua storia...",
    "Putting your comic together...": "Metto insieme il tuo fumetto...",
    "Stopping...": "Mi fermo...",
    "Stopped! Nothing was made. Try a different idea.":
      "Fermato! Non è venuto fuori niente. Prova un'altra idea.",
    "Couldn't stop it — it may finish anyway.":
      "Non sono riuscito a fermarlo — potrebbe finire lo stesso.",
    "Something went wrong. Let's try that again!":
      "Qualcosa è andato storto. Riproviamo!",
    "Pick a picture first — make one above, or use a photo!":
      "Prima scegli un'immagine — fanne una qui sopra, o usa una foto!",
    "Pick a picture to start on and one to end on!":
      "Scegli un'immagine per l'inizio e una per la fine!",
    "Type something you'd like to make first!":
      "Prima scrivi qualcosa che vuoi fare!",
    "Sending your photo...": "Mando la tua foto...",
    "It's in your gallery! Now pick what to do with it ✨":
      "È nella tua galleria! Adesso scegli cosa farci ✨",
    "✅ Ready!": "✅ Pronto!",
    "Took {time}.": "Ci ha messo {time}.",
    "{n} seconds long": "dura {n} secondi",
    "{n} second": "{n} secondo",
    "{n} secs": "{n} sec",
    "about {n} seconds": "circa {n} secondi",
    "about a minute": "circa un minuto",
    "about {n} minutes": "circa {n} minuti",
    "{time} so far": "{time} finora",
    "about {time} to go": "ancora circa {time}",
    "⏱️ I haven't made one of these yet — I'll time this one.":
      "⏱️ Non ne ho ancora fatta una così — cronometro questa.",
    "⏱️ Takes {time} on this computer.":
      "⏱️ Su questo computer ci vuole {time}.",
    "⏱️ Probably takes {time}.": "⏱️ Probabilmente ci vuole {time}.",

    // --- the allowance and the clock --------------------------------------
    "🌙 That's all the pictures for today. See you tomorrow!":
      "🌙 Basta immagini per oggi. A domani!",
    "🌙 That's all the videos for today. See you tomorrow!":
      "🌙 Basta video per oggi. A domani!",
    "🌙 That's all the songs for today. See you tomorrow!":
      "🌙 Basta canzoni per oggi. A domani!",
    "✨ {n} pictures left today, so that's how many you'll get.":
      "✨ Oggi ti restano {n} immagini, quindi te ne faccio altrettante.",
    "✨ {n} videos left today, so that's how many you'll get.":
      "✨ Oggi ti restano {n} video, quindi te ne faccio altrettanti.",
    "✨ {n} songs left today, so that's how many you'll get.":
      "✨ Oggi ti restano {n} canzoni, quindi te ne faccio altrettante.",
    "✨ 1 picture left today, so that's how many you'll get.":
      "✨ Oggi ti resta 1 immagine, quindi ne farai una.",
    "✨ 1 video left today, so that's how many you'll get.":
      "✨ Oggi ti resta 1 video, quindi ne farai uno.",
    "✨ 1 song left today, so that's how many you'll get.":
      "✨ Oggi ti resta 1 canzone, quindi ne farai una.",
    "✨ One more picture today - make it a good one!":
      "✨ Ancora un'immagine per oggi - falla bella!",
    "✨ One more video today - make it a good one!":
      "✨ Ancora un video per oggi - fallo bello!",
    "✨ One more song today - make it a good one!":
      "✨ Ancora una canzone per oggi - falla bella!",
    "✨ {n} more pictures today": "✨ Ancora {n} immagini per oggi",
    "✨ {n} more videos today": "✨ Ancora {n} video per oggi",
    "✨ {n} more songs today": "✨ Ancora {n} canzoni per oggi",
    "The factory closes at {at} - any minute now!":
      "La fabbrica chiude alle {at} - da un momento all'altro!",
    "closes-in": "La fabbrica chiude alle {at} - mancano circa {mins} minuti.",
    "The factory is closed right now": "La fabbrica adesso è chiusa",
    "Back soon!": "Torniamo presto!",

    // --- the warm-up sums --------------------------------------------------
    "Warm up your brain!": "Riscalda il cervello!",
    "Get these right and the factory opens for today.":
      "Indovinali tutti e la fabbrica apre per oggi.",
    "Get it right and the factory opens for today.":
      "Indovinalo e la fabbrica apre per oggi.",
    "Get all {n} right and the factory opens for today.":
      "Indovinali tutti e {n} e la fabbrica apre per oggi.",
    "Check my answers": "Controlla le mie risposte",
    "Fill them all in first!": "Prima riempili tutti!",
    "All right! Off you go.": "Tutto giusto! Vai pure.",
    "So close - one of those wasn't right. Here are some new ones!":
      "Ci sei quasi - uno non era giusto. Eccone dei nuovi!",
    "Not quite! Here are some new ones.": "Non proprio! Eccone dei nuovi.",
    "Something went wrong. Try again!": "Qualcosa è andato storto. Riprova!",
    "I'm a grown-up": "Sono un grande",
    "Grown-up PIN": "PIN dei grandi",
    "Let me in": "Fammi entrare",

    // --- the viewer --------------------------------------------------------
    "Pick a picture": "Scegli un'immagine",
    "Pick where it starts": "Scegli dove comincia",
    "Pick where it ends": "Scegli dove finisce",
    "Done": "Fatto",
    "← Back": "← Indietro",
    "What is it called?": "Come si chiama?",
    "✏️ Give it a name": "✏️ Dagli un nome",
    "What you asked for": "Cosa hai chiesto",
    "What {name} asked for": "Cosa ha chiesto {name}",
    "{name} made this": "L'ha fatta {name}",
    "The words": "Le parole",
    "Something you made": "Qualcosa che hai fatto",
    "Something deleted": "Qualcosa di cancellato",
    "(music only - nobody sings on this one.)":
      "(solo musica - qui non canta nessuno.)",
    "(read back out of the file - this is the whole prompt, including the bits the dropdowns added.)":
      "(letto dal file - questa è tutta la richiesta, comprese le parti " +
      "aggiunte dai menù.)",
    "A drawing you made. Tap Animate this to bring it to life!":
      "Un disegno che hai fatto. Tocca Animala per farlo muovere!",
    "A card you made. Print it, or share it!":
      "Un biglietto che hai fatto. Stampalo o mandalo a qualcuno!",
    "A photo you added. Tap Animate this to bring it to life!":
      "Una foto che hai aggiunto. Tocca Animala per farla muovere!",
    "This one's notes are lost - it was made before the app kept them, or straight from ComfyUI.":
      "Gli appunti di questa sono persi - è stata fatta prima che l'app li " +
      "tenesse, oppure direttamente da ComfyUI.",
    "☆ Favourite": "☆ Preferita",
    "⭐ Favourite": "⭐ Preferita",
    "⭐ Starred": "⭐ Con la stella",
    "⭐ Starred!": "⭐ Con la stella!",
    "☆ This one’s best": "☆ Questa è la migliore",
    "👨‍👩‍👧 Show the family": "👨‍👩‍👧 Mostra alla famiglia",
    "👨‍👩‍👧 Hide from the family": "👨‍👩‍👧 Nascondi alla famiglia",
    "Everyone can see this one now! 👨‍👩‍👧": "Adesso la vedono tutti! 👨‍👩‍👧",
    "Back to just you.": "Di nuovo solo tua.",
    "🔁 Make another like this": "🔁 Fanne un'altra così",
    "🎯 Make it again, but…": "🎯 Rifalla, ma…",
    "✨ Animate this": "✨ Animala",
    "🧑‍🎤 Save as a character": "🧑‍🎤 Salva come personaggio",
    "🎤 Say something over it": "🎤 Parlaci sopra",
    "✂️ Turn it into a sticker": "✂️ Trasformala in adesivo",
    "✂️ Cutting it out...": "✂️ La ritaglio...",
    "🔍 Make it huge": "🔍 Falla enorme",
    "🎨 Turn it into…": "🎨 Trasformala in…",
    "🪄 Change this picture": "🪄 Cambia questa immagine",
    "🔭 What's outside the frame?": "🔭 Cosa c'è fuori dal bordo?",
    "🩹 Fix just this bit": "🩹 Aggiusta solo questo pezzo",
    "🖼️ Put it at the top": "🖼️ Mettila in cima",
    "👤 That one's me": "👤 Questa sono io",
    "🔊 Add a sound effect": "🔊 Aggiungi un effetto sonoro",
    "📸 Grab a picture from it": "📸 Prendine un'immagine",
    "✨ Make it smooth": "✨ Rendilo fluido",
    "🐌 Slow it down": "🐌 Rallentalo",
    "🌀 Make a moving sticker": "🌀 Fai un adesivo che si muove",
    "✏️ Draw on it": "✏️ Disegnaci sopra",
    "🖨️ Print it": "🖨️ Stampala",
    "💌 Make a card": "💌 Fai un biglietto",
    "▶️ What happens next?": "▶️ Cosa succede dopo?",
    "📤 Share": "📤 Condividi",
    "⬇︎ Save it": "⬇︎ Salvala",
    "↩️ Put it back": "↩️ Rimettila a posto",
    "🗑️ Delete for good": "🗑️ Cancella per sempre",
    "In the trash": "Nel cestino",
    "Gone - it's in the trash.": "Sparita - è nel cestino.",
    "＋ Add a tag": "＋ Aggiungi un'etichetta",
    "What tag?": "Quale etichetta?",
    "What tag should these get?": "Che etichetta metto a queste?",
    "\n\nAlready used: ": "\n\nGià usate: ",
    "{n} thing tagged “#{tag}”": "{n} cosa con l'etichetta “#{tag}”",
    "{n} things tagged “#{tag}”": "{n} cose con l'etichetta “#{tag}”",
    "Couldn't open your gallery right now. Try again!":
      "Non sono riuscito ad aprire la tua galleria. Riprova!",
    "That one's turned off just now.": "Quella cosa adesso è spenta.",

    // --- what kind of thing a tile is --------------------------------------
    "📖 Comic": "📖 Fumetto",
    "🧩 Panel": "🧩 Vignetta",
    "📷 Photo": "📷 Foto",
    "🎬 Film": "🎬 Film",
    "🎤 My voice": "🎤 La mia voce",
    "🔊 Sound": "🔊 Suono",
    "✂️ Sticker": "✂️ Adesivo",
    "📸 From a video": "📸 Da un video",
    "🎵 Song": "🎵 Canzone",

    // --- what kind of sound: a song, a little tune, a background
    //     hum. One card and one model; see app/music.py KINDS.
    "What kind": "Che tipo",
    "What kind of sound to make": "Che tipo di suono fare",
    "Make my tune": "Fai la mia melodia",
    "Make my sound": "Fai il mio suono",
    "🎲 Thinking of a sound...": "🎲 Sto pensando a un suono...",
    "Your tune is ready! ✨": "La tua melodia è pronta! ✨",
    "Your sound is ready! ✨": "Il tuo suono è pronto! ✨",
    "Making a little tune": "Sto facendo una melodia",
    "Making a background hum": "Sto facendo un suono di sottofondo",
    "🎺 Little tune": "🎺 Melodia",
    "🌊 Background hum": "🌊 Suono di sottofondo",
    "✨ Smooth": "✨ Fluido",
    "🐌 Slow motion": "🐌 Rallentatore",
    "🌀 Moving sticker": "🌀 Adesivo animato",
    "🔍 Huge": "🔍 Enorme",
    "🪄 Changed": "🪄 Cambiata",
    "🔭 More of it": "🔭 Più larga",
    "🩹 Fixed a bit": "🩹 Pezzo aggiustato",
    "🎨 A new style": "🎨 Uno stile nuovo",
    "✏️ Drawing": "✏️ Disegno",
    "💌 Card": "💌 Biglietto",
    "▶ Video": "▶ Video",

    // --- the result row ----------------------------------------------------
    "The picture you made": "L'immagine che hai fatto",
    "One of the pictures you made": "Una delle immagini che hai fatto",
    "Your comic": "Il tuo fumetto",
    "🎲 Try again": "🎲 Riprova",
    "⬇︎ Save picture": "⬇︎ Salva immagine",
    "⬇︎ Save video": "⬇︎ Salva video",
    "⬇︎ Save song": "⬇︎ Salva canzone",
    "⬇︎ Save my film": "⬇︎ Salva il mio film",
    "⬇︎ Save my comic": "⬇︎ Salva il mio fumetto",
    "⬇︎ Save them all": "⬇︎ Salvale tutte",
    "Keep this one": "Tieni questa",
    "✓ Kept": "✓ Tenuta",
    "Delete this one": "Cancella questa",
    "It's a sticker! ✂️": "È un adesivo! ✂️",
    "It's ready! ✨": "È pronta! ✨",
    "It's ready! 🔍": "È pronta! 🔍",
    "Your very first picture! 🎉": "La tua primissima immagine! 🎉",
    "Your very first video! 🎉": "Il tuo primissimo video! 🎉",
    "Your very first comic! 🎉": "Il tuo primissimo fumetto! 🎉",
    "Your very first film! 🎉": "Il tuo primissimo film! 🎉",
    "That's {n} pictures! 🎉": "Sono {n} immagini! 🎉",
    "That's {n} videos! 🎉": "Sono {n} video! 🎉",
    "That's {n} comics! 🎉": "Sono {n} fumetti! 🎉",
    "That's {n} films! 🎉": "Sono {n} film! 🎉",

    // --- characters ---------------------------------------------------------
    "Character": "Personaggio",
    "What's this character called?": "Come si chiama questo personaggio?",
    "Having a good look at {name}...": "Guardo bene {name}...",
    "{name} can be in your next one! 🧑‍🎤":
      "{name} può stare nella prossima! 🧑‍🎤",
    "That's {n} characters already! Say goodbye to one first, in the Gallery.":
      "Hai già {n} personaggi! Prima di' addio a uno, nella Galleria.",
    "Forget “{idea}”": "Dimentica “{idea}”",
    "✏️ Rename": "✏️ Cambia nome",
    "🎨 How they look": "🎨 Com'è fatto",
    "👋 Say goodbye to them": "👋 Digli addio",
    "Nothing with them in it yet! Choose them under “Who’s in it?” and make something.":
      "Non c'è ancora niente con lui dentro! Scegli il suo nome sotto “Chi " +
      "c'è dentro?” e fai qualcosa.",
    "What should they be called?": "Come si deve chiamare?",
    "One sentence saying what they look like. This gets used in every picture they're in, so be specific about colours and clothes.":
      "Una frase che dice com'è fatto. Viene usata in ogni immagine dove " +
      "compare, quindi descrivi bene colori e vestiti.",
    "Said goodbye to {name}. Their pictures are still in the Gallery.":
      "Hai detto addio a {name}. Le sue immagini sono ancora nella Galleria.",
    "Couldn't load them just now.": "Non sono riuscito a caricarli adesso.",

    // --- the film and card makers -------------------------------------------
    "Make a film": "Fai un film",
    "{n} videos, in the order you chose them. It'll open with a title card - give it a name!":
      "{n} video, nell'ordine in cui li hai scelti. Comincia con un titolo " +
      "- dagli un nome!",
    "🎬 What's your film called?": "🎬 Come si chiama il tuo film?",
    "The Great Pancake Adventure": "La grande avventura delle frittelle",
    "My Film": "Il mio film",
    "{title} presents": "{title} presenta",
    "Joining your film... this takes a little while.":
      "Unisco il tuo film... ci vuole un po'.",
    "Done! It's at the top of your videos.": "Fatto! È in cima ai tuoi video.",
    "Make a card": "Fai un biglietto",
    "Save my card": "Salva il mio biglietto",
    "💌 What should it say?": "💌 Cosa deve dire?",
    "Happy birthday Grandma!": "Buon compleanno nonna!",
    "Card colour": "Colore del biglietto",
    "Card colour {n}": "Colore del biglietto {n}",
    "Made for you!": "Fatto per te!",
    "made at {title}": "fatto a {title}",
    "Saving your card...": "Salvo il tuo biglietto...",
    "Saved! It's in Photos & drawings - open it to print or share.":
      "Salvato! È in Foto e disegni - aprilo per stamparlo o mandarlo.",
    "My comic": "Il mio fumetto",

    // --- their voice, sounds, frames, loops -----------------------------------
    "🎤 Say something": "🎤 Di' qualcosa",
    "✕ Close": "✕ Chiudi",
    "Tap the big button and talk. Your voice goes on top of your video.":
      "Tocca il bottone grande e parla. La tua voce va sopra il tuo video.",
    "Start talking": "Comincia a parlare",
    "Keep the video's own sound too (it goes quieter while you talk)":
      "Tieni anche il suono del video (si abbassa mentre parli)",
    "✨ Put it on my video": "✨ Mettila sul mio video",
    "🔁 Record it again": "🔁 Registra di nuovo",
    "🗑️ Throw the recording away": "🗑️ Butta via la registrazione",
    "Or use a sound you already have": "Oppure usa un suono che hai già",
    "This browser can't record here - that needs https. Pick a sound from your files below instead.":
      "Questo browser non può registrare qui - serve https. Scegli invece " +
      "un suono dai tuoi file qui sotto.",
    "You haven't put it on your video yet!":
      "Non l'hai ancora messa sul tuo video!",
    "Your iPad needs to say yes to the microphone first. Tap the big button again and choose Allow.":
      "Prima il tuo iPad deve dire sì al microfono. Tocca di nuovo il " +
      "bottone grande e scegli Consenti.",
    "I can't find a microphone on this device. You can pick a sound from your files below instead.":
      "Non trovo nessun microfono su questo apparecchio. Puoi scegliere un " +
      "suono dai tuoi file qui sotto.",
    "The microphone didn't start ({why}). You can pick a sound from your files below instead.":
      "Il microfono non è partito ({why}). Puoi scegliere un suono dai " +
      "tuoi file qui sotto.",
    "Putting your voice on it...": "Ci metto sopra la tua voce...",
    "Your voice is on it! 🎤": "La tua voce è sopra! 🎤",
    "Pick a sound, slide to where you want it, then put it on.":
      "Scegli un suono, scorri fino al punto che vuoi, poi mettilo.",
    "When the sound happens": "Quando parte il suono",
    "Couldn't load the sounds.": "Non sono riuscito a caricare i suoni.",
    "Putting it on...": "Lo metto...",
    "Sound added! 🔊": "Suono aggiunto! 🔊",
    "📸 Grab a picture": "📸 Prendi un'immagine",
    "Slide to the bit you like. The picture underneath is exactly what you'll keep.":
      "Scorri fino al pezzo che ti piace. L'immagine qui sotto è " +
      "esattamente quella che terrai.",
    "Which bit?": "Quale pezzo?",
    "Which moment to keep": "Quale momento tenere",
    "The picture you are about to keep": "L'immagine che stai per tenere",
    "✨ Keep this picture": "✨ Tieni questa immagine",
    "Keeping it...": "La tengo...",
    "Kept it as a picture! 📸": "Tenuta come immagine! 📸",
    "Pick the bit you want and it'll loop for ever - a sticker that moves.":
      "Scegli il pezzo che vuoi e girerà all'infinito - un adesivo che si " +
      "muove.",
    "Start here": "Comincia qui",
    "Where the loop starts": "Dove comincia il giro",
    "How long?": "Quanto dura?",
    "How long the loop is": "Quanto dura il giro",
    "1 second": "1 secondo",
    "2 seconds": "2 secondi",
    "Where your moving sticker starts": "Dove comincia il tuo adesivo animato",
    "✨ Make my sticker": "✨ Fai il mio adesivo",
    "Making it...": "Lo faccio...",
    "It moves! 🌀": "Si muove! 🌀",

    // --- the three edits ----------------------------------------------------
    "Say what you'd like different and it'll make the same picture again with that changed.":
      "Di' cosa vuoi di diverso e rifarà la stessa immagine con quella " +
      "cosa cambiata.",
    "The picture you're changing": "L'immagine che stai cambiando",
    "What should be different?": "Cosa deve essere diverso?",
    "make it night-time\ngive the fox a scarf":
      "falla di notte\nmetti una sciarpa alla volpe",
    "make it night-time": "falla di notte",
    "make it snowy": "fai che nevichi",
    "add a rainbow": "aggiungi un arcobaleno",
    "make it look like a painting": "falla sembrare un dipinto",
    "put a hat on it": "mettici un cappello",
    "make everything tiny": "fai tutto piccolissimo",
    "...and put me in it 👤": "...e mettici me 👤",
    "✨ Go": "✨ Vai",
    "Tell me what should be different!": "Dimmi cosa deve essere diverso!",
    "Changing your picture... 🪄": "Cambio la tua immagine... 🪄",
    "Pick a kind of picture and it'll draw this one again that way, with everything still where it is.":
      "Scegli un tipo di immagine e la ridisegnerà così, lasciando tutto " +
      "dov'è.",
    "The picture you're turning into something else":
      "L'immagine che stai trasformando",
    "What to turn it into": "In cosa trasformarla",
    "Anything else? (you don't have to say)":
      "Altro? (non devi per forza dirlo)",
    "you don't have to say - or add your own twist: make it night-time":
      "non devi per forza dirlo - o aggiungi la tua idea: falla di notte",
    "Pick what to turn it into!": "Scegli in cosa trasformarla!",
    "Drawing it again... 🎨": "La ridisegno... 🎨",
    "Pick a side and it'll invent what was just out of the picture.":
      "Scegli un lato e inventerà quello che stava appena fuori " +
      "dall'immagine.",
    "The picture you're growing": "L'immagine che stai allargando",
    "Which way?": "Da che parte?",
    "Which way to grow": "Da che parte allargarla",
    "All round": "Tutt'intorno",
    "⬅️ Left": "⬅️ Sinistra",
    "➡️ Right": "➡️ Destra",
    "⬆️ Up": "⬆️ Su",
    "⬇️ Down": "⬇️ Giù",
    "How much?": "Quanto?",
    "How much bigger": "Quanto più grande",
    "A bit": "Un po'",
    "A lot": "Tanto",
    "What's out there? (you don't have to say)":
      "Cosa c'è là fuori? (non devi per forza dirlo)",
    "you don't have to say - or try: a beach, more trees":
      "non devi per forza dirlo - o prova: una spiaggia, altri alberi",
    "Looking outside the frame... 🔭": "Guardo fuori dal bordo... 🔭",
    "Say what should be there instead, then tap Go.":
      "Di' cosa ci deve essere invece, poi tocca Vai.",
    "Paint over the bit you want changed first!":
      "Prima colora il pezzo che vuoi cambiare!",
    "Fixing that bit... 🩹": "Aggiusto quel pezzo... 🩹",
    "Slowing it right down... it comes out quiet 🐌":
      "Lo rallento tantissimo... viene fuori senza audio 🐌",
    "Smoothing it out... ✨": "Lo rendo fluido... ✨",
    "Making it huge... 🔍": "La faccio enorme... 🔍",
    "Cutting it out...": "La ritaglio...",

    // --- compare ------------------------------------------------------------
    "🔍 Which one?": "🔍 Quale?",
    "Slide across to see one and then the other.":
      "Scorri per vedere prima una e poi l'altra.",
    "The first one": "La prima",
    "The second one": "La seconda",
    "Slide between the two pictures": "Scorri tra le due immagini",

    // --- the drawing pad ----------------------------------------------------
    "Draw something": "Disegna qualcosa",
    "Use my drawing": "Usa il mio disegno",
    "Colour": "Colore",
    "Colour {n}": "Colore {n}",
    "Stamps": "Timbri",
    "Stamp {emoji}": "Timbro {emoji}",
    "Thin brush": "Pennello sottile",
    "Medium brush": "Pennello medio",
    "Thick brush": "Pennello grosso",
    "🧽 Rubber": "🧽 Gomma",
    "↶ Undo": "↶ Annulla",
    "Start again": "Ricomincia",
    "What should be there instead?": "Cosa ci deve essere invece?",
    "what should be there instead? e.g. a red party hat":
      "cosa ci deve essere invece? per esempio un cappellino rosso da festa",
    "Draw with your finger or a pencil. When you're done, tap <strong>Use my drawing</strong>.":
      "Disegna col dito o con una matita. Quando hai finito, tocca " +
      "<strong>Usa il mio disegno</strong>.",
    "Paint over the bit you want changed, say what should be there, then tap <strong>Go</strong>.":
      "Colora il pezzo che vuoi cambiare, di' cosa ci deve essere, poi " +
      "tocca <strong>Vai</strong>.",

    // --- the chat tab -------------------------------------------------------
    "Chat with": "Chatta con",
    "Ask for an idea, or tell me what you’re making. Your grown-ups can read everything said here.":
      "Chiedimi un'idea, oppure dimmi cosa stai facendo. I tuoi grandi " +
      "possono leggere tutto quello che si dice qui.",
    "Your chat": "La tua chat",
    "Say something": "Di' qualcosa",
    "Say something…": "Di' qualcosa…",
    "Send it": "Manda",
    "Start a new chat": "Comincia una nuova chat",
    "Started a new chat. Your grown-ups can still see the old one.":
      "Hai cominciato una nuova chat. I tuoi grandi possono ancora vedere " +
      "quella vecchia.",
    "The chat helper isn't set up on this machine yet. Everything else still works!":
      "L'aiutante della chat non è ancora pronto su questo computer. Tutto " +
      "il resto funziona!",
    "Give me an idea for a picture": "Dammi un'idea per un'immagine",
    "What can I make here?": "Cosa posso fare qui?",
    // The third starter exists to show them they can write in the other
    // language, so on a French page it is the English one.
    "Donne-moi une idée de dessin": "Give me a drawing idea",
    "🎨 Make a picture of this": "🎨 Fanne un'immagine",
    "🎬 Make a video of this": "🎬 Fanne un video",
    "📋 Copy": "📋 Copia",
    "✓ Copied": "✓ Copiato",
    "✕ Couldn't copy": "✕ Non sono riuscito a copiare",
    "That's what {name} said. Change anything you like, or tap “Help me write it” to turn it into a proper description.":
      "Questo è quello che ha detto {name}. Cambia quello che vuoi, oppure " +
      "tocca “Aiutami a scrivere” per farne una vera descrizione.",
    "the helper": "l'aiutante",

    // --- Settings -----------------------------------------------------------
    "You": "Tu",
    "You're {name}!": "Sei {name}!",
    "🪄 Make a picture of me": "🪄 Fai un'immagine di me",
    "😃 Pick a face instead": "😃 Scegli invece una faccia",
    "↩️ Back to the face": "↩️ Torna alla faccia",
    "Pick a face": "Scegli una faccia",
    "Colours": "Colori",
    "Language": "Lingua",
    "Which language": "Quale lingua",
    "The top of your page": "La cima della tua pagina",
    "What is across the top of your page now":
      "Cosa c'è adesso in cima alla tua pagina",
    "↩️ Put the first one back": "↩️ Rimetti quella di prima",
    "Put back the one it came with.": "Rimetti quella di partenza.",
    "Couldn't change it back.": "Non sono riuscito a rimetterla com'era.",
    "Making new ones is switched off right now, but you can still use any picture from <strong>Gallery</strong> — open one and tap <strong>Put it at the top</strong>.":
      "Adesso non se ne possono fare di nuove, ma puoi usare qualsiasi " +
      "immagine della <strong>Galleria</strong> — aprine una e tocca " +
      "<strong>Mettila in cima</strong>.",
    "It's a long thin strip, so wide things work best — a row of something, a view, a pattern. Your name goes on top of it, so leave the middle fairly quiet.":
      "È una striscia lunga e stretta, quindi funzionano meglio le cose " +
      "larghe — una fila di qualcosa, un panorama, un motivo. Il tuo nome " +
      "va sopra, quindi lascia il centro abbastanza tranquillo.",
    "🖼️ Putting it up...": "🖼️ La metto su...",
    "That's the top of your page now! 🖼️":
      "Adesso è la cima della tua pagina! 🖼️",
    "That one wouldn't go up there.": "Quella non ci stava.",
    "Kept it on this device, but it wouldn't save.":
      "L'ho tenuta su questo apparecchio, ma non si è salvata.",
    "Tap your face. A grown-up adds and changes these on the parent page.":
      "Tocca la tua faccia. Un grande le aggiunge e le cambia nella pagina " +
      "dei genitori.",
    "👤 Making it you...": "👤 La faccio diventare te...",
    "That's you now! 👤": "Adesso sei tu! 👤",
    "I'm a grown-up — the parent page":
      "Sono un grande — la pagina dei genitori",

    // --- who is making things today -----------------------------------------
    "Who's making things today?": "Chi fa le cose oggi?",

    // --- the picture-of-me wizard -------------------------------------------
    "Make a picture of me": "Fai un'immagine di me",
    "1. What are you?": "1. Cosa sei?",
    "What are you?": "Cosa sei?",
    "Or type your own": "Oppure scrivi il tuo",
    "…or type your own": "…oppure scrivi il tuo",
    "2. What colour?": "2. Di che colore?",
    "What colour?": "Di che colore?",
    "3. Anything else?": "3. Altro?",
    "Anything else?": "Altro?",
    "Anything else": "Altro",
    "…a wizard hat, freckles, a scarf":
      "…un cappello da mago, le lentiggini, una sciarpa",
    "Let's make it! ✨": "Facciamola! ✨",
    "It makes four at once so you can pick your favourite. Then tap <strong>👤 That one's me</strong> under the one you like.":
      "Ne fa quattro in una volta così puoi scegliere la tua preferita. " +
      "Poi tocca <strong>👤 Questa sono io</strong> sotto quella che ti " +
      "piace.",
    "Pick what you are to get started!": "Scegli cosa sei per cominciare!",
    "Pick what you are first!": "Prima scegli cosa sei!",
    "Making pictures is switched off right now.":
      "Adesso non si possono fare immagini.",
    "Tap Go and pick your favourite! ✨":
      "Tocca Vai e scegli la tua preferita! ✨",
    // The wizard's choices. The sentence they compose is a prompt, so the
    // article travels with the word in French, where gender does too.
    "a fox": "una volpe", "a cat": "un gatto", "a dog": "un cane",
    "a dragon": "un drago", "a robot": "un robot", "an owl": "un gufo",
    "a unicorn": "un unicorno", "a penguin": "un pinguino",
    "an astronaut": "un astronauta", "a wizard": "un mago",
    "a superhero": "un supereroe", "a pirate": "un pirata",
    "a mermaid": "una sirena", "a knight": "un cavaliere",
    "a panda": "un panda", "an octopus": "un polpo",
    // "en violet" rather than "violet": the colour then agrees with nothing,
    // so one word does for a fox and for a mermaid alike.
    "purple": "viola", "blue": "blu", "green": "verde",
    "orange": "arancione", "pink": "rosa", "red": "rosso",
    "yellow": "giallo", "rainbow": "arcobaleno", "silver": "argentato",
    "golden": "dorato",
    "a wizard hat": "un cappello da mago",
    "big round glasses": "occhiali grandi e rotondi",
    "a stripy scarf": "una sciarpa a righe",
    "a cape": "un mantello", "headphones": "le cuffie",
    "a flower crown": "una corona di fiori", "a bow tie": "un papillon",
    "freckles": "le lentiggini",

    // --- when it is shut -----------------------------------------------------
    "just now": "proprio adesso",
    "{n} minute ago": "{n} minuto fa",
    "{n} minutes ago": "{n} minuti fa",
    "{n} hour ago": "{n} ora fa",
    "{n} hours ago": "{n} ore fa",
    "{n} KB": "{n} KB",
    "{n} MB": "{n} MB",

    // The close button on every sheet. Static markup, so it is a
    // data-i18n and not a t() - and it was English in every language
    // until the coverage walk went looking for exactly this.
    "✕ Close": "✕ Chiudi",
  };

  // Dutch. The same keys in the same order under the same headings
  // as FR above, so a line missing from one of them is a line out of step.
  var NL = {
    // --- the shell ------------------------------------------------------
    "My AI Factory": "Mijn AI-fabriek",
    "AI Factory": "AI-fabriek",
    "What would you like to do?": "Wat wil je doen?",
    "That's me - tap to swap": "Dat ben ik - tik om te wisselen",
    "Show me": "Laat zien",
    "Working...": "Bezig...",
    "wiz-sentence":
      "{thing}{colour}, heel vriendelijk{wearing}, een vrolijk " +
      "cartoonportret, hoofd en schouders, grote vriendelijke ogen",
    "wiz-wearing": " met {list}",
    "wiz-and": " en ",
    "wiz-colour": " in de kleur {colour}",

    // Tabs. Short on purpose: seven of them share one row at 390px.
    "Picture": "Plaatje",
    "Video": "Video",
    "Comic": "Strip",
    "Music": "Muziek",
    "Chat": "Chat",
    "Gallery": "Galerij",
    "Settings": "Opties",

    // --- "your picture is ready" ----------------------------------------
    "Your picture is ready! ✨": "Je plaatje is klaar! ✨",
    "Your video is ready! ✨": "Je video is klaar! ✨",
    "Your comic is ready! ✨": "Je strip is klaar! ✨",
    "Your film is ready! ✨": "Je film is klaar! ✨",
    "Your song is ready! ✨": "Je liedje is klaar! ✨",
    "Your smooth video is ready! ✨": "Je vloeiende video is klaar! ✨",
    "Your slow-motion video is ready! ✨": "Je vertraagde video is klaar! ✨",
    "Your big picture is ready! ✨": "Je grote plaatje is klaar! ✨",
    "Your bigger picture is ready! ✨": "Je vergrote plaatje is klaar! ✨",
    "Your changed picture is ready! ✨": "Je veranderde plaatje is klaar! ✨",

    // --- the Gallery ------------------------------------------------------
    "Everything you've made is saved here.":
      "Alles wat je maakt wordt hier bewaard.",
    "Nothing here yet! Make a picture, a video or a comic and it'll turn up here.":
      "Nog niets! Maak een plaatje, een video of een strip en het komt " +
      "hier te staan.",
    "Nothing of yours yet - but there's something on the family shelf!":
      "Nog niets van jou - maar er staat wel iets op de familieplank!",
    "You've made 1 thing so far.": "Je hebt tot nu toe 1 ding gemaakt.",
    "You've made {n} things so far.": "Je hebt tot nu toe {n} dingen gemaakt.",
    "🧑‍🎤 My characters": "🧑‍🎤 Mijn personages",
    "Show": "Toon",
    "How to show your gallery": "Hoe je je galerij ziet",
    "Everything": "Alles",
    "In groups": "In groepen",
    "Order": "Volgorde",
    "What order to show them in": "In welke volgorde je ze ziet",
    "Newest": "Nieuwste",
    "Oldest": "Oudste",
    "⭐ Favourites": "⭐ Favorieten",
    "By kind": "Per soort",
    "🔎 Find something you made": "🔎 Zoek iets dat je maakte",
    "Search your gallery": "Zoek in je galerij",
    "Clear the search": "Zoekwoord wissen",
    "Choose": "Kiezen",
    "Cancel": "Annuleren",
    "👨‍👩‍👧 Family": "👨‍👩‍👧 Familie",
    "🎨 Pictures": "🎨 Plaatjes",
    "📖 Comics": "📖 Strips",
    "🧩 Comic pictures": "🧩 Stripplaatjes",
    "✂️ Stickers": "✂️ Stickers",
    "📷 Photos & drawings": "📷 Foto's en tekeningen",
    "🎬 Videos": "🎬 Video's",
    "🎵 Songs": "🎵 Liedjes",
    "Nothing matches that. Try another word!":
      "Niets gevonden. Probeer een ander woord!",
    "Nothing here yet! Go and make something.":
      "Nog niets! Ga maar iets maken.",
    "🗑️ Recently deleted": "🗑️ Net weggegooid",
    "Things stay here for {days} days, then they're gone for good. Tap one to put it back.":
      "Dingen blijven hier {days} dagen staan, daarna zijn ze voorgoed " +
      "weg. Tik erop om er een terug te zetten.",
    "Nothing chosen yet": "Nog niets gekozen",
    "Tap the ones you want": "Tik op wat je wilt",
    "1 chosen": "1 gekozen",
    "{n} chosen": "{n} gekozen",
    "Choose all": "Alles kiezen",
    "Choose none": "Niets kiezen",
    "🎬 Join into a film": "🎬 Tot film plakken",
    "🔍 Compare them": "🔍 Vergelijken",
    "🏷️ Add a tag": "🏷️ Label erbij",
    "⬇︎ Save": "⬇︎ Opslaan",
    "🗑️ Delete": "🗑️ Weggooien",
    "Deleted": "Weggegooid",
    "{n} things deleted": "{n} dingen weggegooid",
    "Undo": "Toch niet",
    "Put back!": "Teruggezet!",
    "All put back!": "Alles teruggezet!",
    "Really delete?": "Echt weggooien?",
    "Really delete it?": "Deze echt weggooien?",
    "Really delete all {n}?": "Alle {n} echt weggooien?",
    "Really delete forever?": "Echt voorgoed weggooien?",
    "Really clear it?": "Echt alles wissen?",
    "Really say goodbye?": "Echt afscheid nemen?",

    // --- the maker cards -------------------------------------------------
    "Make a picture": "Plaatje maken",
    "Make a video": "Video maken",
    "Make a comic": "Strip maken",
    "Make a song": "Liedje maken",
    "↺ Start again": "↺ Opnieuw",
    "Clear everything on this card and start again":
      "Alles op deze kaart wissen en opnieuw beginnen",
    "What should the picture be?": "Wat moet er op het plaatje?",
    "What should the video be?": "Wat moet er in de video gebeuren?",
    "What's your story?": "Wat is jouw verhaal?",
    "What should the song be about?": "Waar gaat het liedje over?",
    "What should the top of your page look like?":
      "Hoe moet de bovenkant van je pagina eruitzien?",
    "A fluffy dragon eating pancakes on the moon":
      "Een pluizige draak die pannenkoeken eet op de maan",
    "A puppy surfing a giant wave at sunset":
      "Een puppy die surft op een reuzengolf bij zonsondergang",
    "It flaps its wings and flies up into the clouds":
      "Hij klapt met zijn vleugels en vliegt de wolken in",
    "The cat walks across the room and curls up in the sunny spot":
      "De kat loopt door de kamer en rolt zich op in het zonnetje",
    "A little robot looking for its lost cat in a big city":
      "Een klein robotje dat zijn kat zoekt in een grote stad",
    "A hedgehog who wants to learn to swim": "Een egel die wil leren zwemmen",
    "A dragon who is scared of pancakes":
      "Een draak die bang is voor pannenkoeken",
    "A row of hot air balloons over a green valley":
      "Een rij luchtballonnen boven een groen dal",
    "Clear what you typed": "Wissen wat je typte",
    "✨ Help me write it": "✨ Help me schrijven",
    "👀 Look at my picture and help me write it":
      "👀 Kijk naar mijn plaatje en help me schrijven",
    "✨ Write me a song": "✨ Schrijf een liedje",
    "🎉 Surprise me": "🎉 Verras me",
    "🎲 Mix it up": "🎲 Husselen",
    "📜 Things I've asked for before": "📜 Wat ik eerder vroeg",
    "📷 Start from a photo": "📷 Met een foto beginnen",
    "🖼️ Pick one from my gallery": "🖼️ Kies uit mijn galerij",
    "Who's in it?": "Wie zit erin?",
    "Nobody": "Niemand",
    "📄 Everything with {name} in it": "📄 Alles met {name} erin",
    "Make": "Maak",
    "What kind of picture": "Wat voor plaatje",
    "A picture": "Een plaatje",
    "A character": "Een personage",
    "Drawn on its own with nothing behind it, so you can cut it out as a sticker or keep them as a character.":
      "Los getekend, met niks erachter, zodat je het kunt uitknippen als " +
      "sticker of kunt bewaren als personage.",
    "Shape": "Vorm",
    "Picture shape": "Vorm van het plaatje",
    "Video shape": "Vorm van de video",
    "Landscape": "Liggend",
    "Portrait": "Staand",
    "Square": "Vierkant",
    "landscape": "liggend",
    "portrait": "staand",
    "square": "vierkant",
    "How many": "Hoeveel",
    "How many pictures": "Hoeveel plaatjes",
    "How many panels": "Hoeveel vakjes",
    "Just one": "Eentje",
    "Four to pick from": "Vier om uit te kiezen",
    "3 pictures": "3 plaatjes",
    "4 pictures": "4 plaatjes",
    "6 pictures": "6 plaatjes",
    "Look": "Beeld",
    "Look and sound": "Beeld en geluid",
    "Sound": "Geluid",
    "Clear these": "Deze wissen",
    "Any": "Alles mag",
    "Make my picture": "Maak mijn plaatje",
    "Make {n} pictures": "Maak {n} plaatjes",
    "Make my video": "Maak mijn video",
    "Make my film": "Maak mijn film",
    "Animate it": "Laat het bewegen",
    "Make my comic": "Maak mijn strip",
    "Make my song": "Maak mijn liedje",
    "Make my music": "Maak mijn muziek",
    "Make one": "Maak er een",
    "Stop": "Stop",
    "Tell a story and it gets drawn as a comic strip you can print.":
      "Vertel een verhaal en het wordt getekend als een strip die je kunt " +
      "printen.",

    // video card
    "Start from": "Beginnen met",
    "What to start the video from": "Waarmee de video begint",
    "✏️ Words": "✏️ Woorden",
    "🖼️ A picture": "🖼️ Een plaatje",
    "🎞️ Two pictures": "🎞️ Twee plaatjes",
    "📽️ A little film": "📽️ Een filmpje",
    "Make a picture up above and tap <strong>Animate this</strong>, or use a photo from your iPad.":
      "Maak hierboven een plaatje en tik op <strong>Laat dit " +
      "bewegen</strong>, of gebruik een foto van je iPad.",
    "The picture you picked": "Het plaatje dat je koos",
    "This picture is ready to animate!": "Dit plaatje kan gaan bewegen!",
    "Use a different one": "Neem een ander",
    "📷 Take or choose a photo": "📷 Foto maken of kiezen",
    "✏️ Draw one": "✏️ Zelf tekenen",
    "Pick where the video starts and where it ends. The middle gets made up.":
      "Kies waar de video begint en waar hij eindigt. Het stuk ertussen " +
      "wordt verzonnen.",
    "Starts on": "Begint met",
    "Ends on": "Eindigt met",
    "🖼️ Pick from the gallery": "🖼️ Kies uit de galerij",
    "🖼️ Pick a different one": "🖼️ Kies een andere",
    "🗣️ What should they say?": "🗣️ Wat moeten ze zeggen?",
    "(you can leave this empty)": "(dit mag je leeg laten)",
    "Look at the Earth from up here!": "Kijk, de aarde van hierboven!",
    "Clear what they say": "Wissen wat ze zeggen",
    "🔊 Videos have sound — they'll say this out loud, so keep it short.":
      "🔊 Video's hebben geluid — dit wordt hardop gezegd, dus hou het kort.",
    "Quality": "Kwaliteit",
    "Video quality": "Videokwaliteit",
    "⚡ Quick": "⚡ Snel",
    "👍 Normal": "👍 Gewoon",
    "✨ Sharper": "✨ Scherper",
    "Sharper means more detail, but it takes a good deal longer to make, and the longest a sharper video can be is":
      "Scherper betekent meer details, maar het duurt een stuk langer, en " +
      "een scherpere video kan hoogstens",
    "seconds.": "seconden duren.",
    "How long": "Hoe lang",
    "Video length in seconds": "Videolengte in seconden",
    "How long the song is, in seconds": "Hoe lang het liedje is, in seconden",
    "{n} seconds": "{n} seconden",
    "Longer videos take longer to make.":
      "Langere video's duren langer om te maken.",
    "Longer songs take longer to make.":
      "Langere liedjes duren langer om te maken.",
    "How many parts": "Hoeveel delen",
    "2 parts": "2 delen",
    "3 parts": "3 delen",
    "4 parts": "4 delen",
    "Each part carries on from the last one, then they're joined into one film. It takes a while, and it uses up one video for each part.":
      "Elk deel gaat verder waar het vorige stopte, daarna worden ze één " +
      "film. Dat duurt even, en het kost één video per deel.",
    "🔊 Add a sound": "🔊 Geluid erbij",
    "None": "Geen",
    "When?": "Wanneer?",
    "At the start": "Aan het begin",
    "In the middle": "In het midden",
    "At the end": "Aan het eind",

    // music card
    "Singing": "Zingen",
    "Singing or not": "Met zingen of niet",
    "With singing": "Met zang",
    "Just music": "Alleen muziek",
    "Words": "Tekst",
    "Clear the words": "Tekst wissen",
    "[Verse]\nI met a dragon on the stairs\nHe said he doesn't like éclairs\n\n[Chorus]\nPancakes, pancakes, run away!":
      "[Couplet]\nIk zag een draak boven op de trap\nHij lustte geen " +
      "pannenkoek, wat een grap\n\n[Refrein]\nPannenkoeken, pannenkoeken, " +
      "rennen maar!",
    "Put <strong>[Verse]</strong> or <strong>[Chorus]</strong> on a line of their own to mark the parts. Leave it empty and you'll get music with nobody singing.":
      "Zet <strong>[Couplet]</strong> of <strong>[Refrein]</strong> op een " +
      "eigen regel om de stukken te markeren. Laat je het leeg, dan krijg " +
      "je muziek waar niemand op zingt.",

    // --- the helpers -----------------------------------------------------
    "Type a few words about your idea first!":
      "Typ eerst een paar woorden over je idee!",
    "Thinking of ideas...": "Ideeën aan het bedenken...",
    "Looking at your picture...": "Naar je plaatje aan het kijken...",
    "This takes a moment the first time.": "De eerste keer duurt dit even.",
    "Here you go! Change anything you like.":
      "Alsjeblieft! Verander gerust wat je wilt.",
    "Here's an idea for it - change anything you like.":
      "Hier is een idee - verander gerust wat je wilt.",
    "Writing your song...": "Je liedje aan het schrijven...",
    "Here are some words! Change any line you like - they don't have to rhyme.":
      "Hier is wat tekst! Verander gerust een regel - het hoeft niet te " +
      "rijmen.",
    "🎲 Thinking of something...": "🎲 Iets aan het bedenken...",
    "🎲 Writing a song...": "🎲 Een liedje aan het schrijven...",
    "Dreaming up an idea...": "Een idee aan het verzinnen...",
    "Here's a whole song! Change any line you like.":
      "Hier is een heel liedje! Verander gerust een regel.",
    "Here's an idea! Change anything you like.":
      "Hier is een idee! Verander gerust wat je wilt.",
    "One of your old ideas with a brand new look. Change anything you like!":
      "Een oud idee van jou in een gloednieuw jasje. Verander gerust wat " +
      "je wilt!",
    "A brand new idea. Change anything you like!":
      "Een gloednieuw idee. Verander gerust wat je wilt!",
    "🎲 Shuffling...": "🎲 Aan het husselen...",
    "Same as before - change anything you like, then go!":
      "Net als daarnet - verander wat je wilt en ga!",
    "Change a word or two and you'll get this same one, but different. “Make another like this” starts from scratch instead.":
      "Verander een woord of twee en je krijgt dezelfde, maar dan anders. " +
      "“Nog zo eentje” begint juist helemaal opnieuw.",
    "Your drawing is ready! Tap the helper to get a script for it, or say what should happen.":
      "Je tekening is klaar! Tik op de helper voor een verhaaltje, of zeg " +
      "zelf wat er moet gebeuren.",
    "This starts where that video stopped. What happens next?":
      "Dit begint waar die video stopte. Wat gebeurt er nu?",

    // --- while it renders -------------------------------------------------
    "Sending it off...": "Aan het versturen...",
    "Getting started...": "Aan het opstarten...",
    "Starting": "Starten",
    "Making another one...": "Nog eentje aan het maken...",
    "Getting it ready...": "Aan het klaarzetten...",
    "Working out your story...": "Je verhaal aan het uitwerken...",
    "Reading your story...": "Je verhaal aan het lezen...",
    "Putting your comic together...": "Je strip aan het maken...",
    "Stopping...": "Aan het stoppen...",
    "Stopped! Nothing was made. Try a different idea.":
      "Gestopt! Er is niets gemaakt. Probeer een ander idee.",
    "Couldn't stop it — it may finish anyway.":
      "Stoppen lukte niet — misschien wordt het toch af.",
    "Something went wrong. Let's try that again!":
      "Er ging iets mis. Probeer het nog eens!",
    "Pick a picture first — make one above, or use a photo!":
      "Kies eerst een plaatje — maak er hierboven een, of neem een foto!",
    "Pick a picture to start on and one to end on!":
      "Kies een plaatje om mee te beginnen en een om mee te eindigen!",
    "Type something you'd like to make first!": "Typ eerst wat je wilt maken!",
    "Sending your photo...": "Je foto aan het versturen...",
    "It's in your gallery! Now pick what to do with it ✨":
      "Hij staat in je galerij! Kies nu wat je ermee doet ✨",
    "✅ Ready!": "✅ Klaar!",
    "Took {time}.": "Duurde {time}.",
    "{n} seconds long": "{n} seconden lang",
    "{n} second": "{n} seconde",
    "{n} secs": "{n} sec",
    "about {n} seconds": "ongeveer {n} seconden",
    "about a minute": "ongeveer een minuut",
    "about {n} minutes": "ongeveer {n} minuten",
    "{time} so far": "{time} tot nu toe",
    "about {time} to go": "nog ongeveer {time}",
    "⏱️ I haven't made one of these yet — I'll time this one.":
      "⏱️ Zoiets heb ik nog nooit gemaakt — ik klok deze.",
    "⏱️ Takes {time} on this computer.": "⏱️ Duurt {time} op deze computer.",
    "⏱️ Probably takes {time}.": "⏱️ Duurt waarschijnlijk {time}.",

    // --- the allowance and the clock --------------------------------------
    "🌙 That's all the pictures for today. See you tomorrow!":
      "🌙 Dat waren alle plaatjes voor vandaag. Tot morgen!",
    "🌙 That's all the videos for today. See you tomorrow!":
      "🌙 Dat waren alle video's voor vandaag. Tot morgen!",
    "🌙 That's all the songs for today. See you tomorrow!":
      "🌙 Dat waren alle liedjes voor vandaag. Tot morgen!",
    "✨ {n} pictures left today, so that's how many you'll get.":
      "✨ Nog {n} plaatjes vandaag, dus zoveel krijg je er.",
    "✨ {n} videos left today, so that's how many you'll get.":
      "✨ Nog {n} video's vandaag, dus zoveel krijg je er.",
    "✨ {n} songs left today, so that's how many you'll get.":
      "✨ Nog {n} liedjes vandaag, dus zoveel krijg je er.",
    "✨ 1 picture left today, so that's how many you'll get.":
      "✨ Nog 1 plaatje vandaag, dus je krijgt er één.",
    "✨ 1 video left today, so that's how many you'll get.":
      "✨ Nog 1 video vandaag, dus je krijgt er één.",
    "✨ 1 song left today, so that's how many you'll get.":
      "✨ Nog 1 liedje vandaag, dus je krijgt er één.",
    "✨ One more picture today - make it a good one!":
      "✨ Nog één plaatje vandaag - maak er iets moois van!",
    "✨ One more video today - make it a good one!":
      "✨ Nog één video vandaag - maak er iets moois van!",
    "✨ One more song today - make it a good one!":
      "✨ Nog één liedje vandaag - maak er iets moois van!",
    "✨ {n} more pictures today": "✨ Nog {n} plaatjes vandaag",
    "✨ {n} more videos today": "✨ Nog {n} video's vandaag",
    "✨ {n} more songs today": "✨ Nog {n} liedjes vandaag",
    "The factory closes at {at} - any minute now!":
      "De fabriek gaat om {at} dicht - zo meteen dus!",
    "closes-in":
      "De fabriek gaat om {at} dicht - nog ongeveer {mins} minuten.",
    "The factory is closed right now": "De fabriek is nu dicht",
    "Back soon!": "Tot straks!",

    // --- the warm-up sums --------------------------------------------------
    "Warm up your brain!": "Warm je hersens op!",
    "Get these right and the factory opens for today.":
      "Heb je ze goed, dan gaat de fabriek open voor vandaag.",
    "Get it right and the factory opens for today.":
      "Heb je hem goed, dan gaat de fabriek open voor vandaag.",
    "Get all {n} right and the factory opens for today.":
      "Heb je alle {n} goed, dan gaat de fabriek open voor vandaag.",
    "Check my answers": "Kijk mijn antwoorden na",
    "Fill them all in first!": "Vul ze eerst allemaal in!",
    "All right! Off you go.": "Allemaal goed! Ga je gang.",
    "So close - one of those wasn't right. Here are some new ones!":
      "Bijna! Eentje was niet goed. Hier zijn nieuwe.",
    "Not quite! Here are some new ones.": "Net niet! Hier zijn nieuwe.",
    "Something went wrong. Try again!":
      "Er ging iets mis. Probeer het nog eens!",
    "I'm a grown-up": "Ik ben een volwassene",
    "Grown-up PIN": "Pincode voor volwassenen",
    "Let me in": "Laat me erin",

    // --- the viewer --------------------------------------------------------
    "Pick a picture": "Kies een plaatje",
    "Pick where it starts": "Kies waar het begint",
    "Pick where it ends": "Kies waar het eindigt",
    "Done": "Klaar",
    "← Back": "← Terug",
    "What is it called?": "Hoe heet het?",
    "✏️ Give it a name": "✏️ Geef het een naam",
    "What you asked for": "Wat je vroeg",
    "What {name} asked for": "Wat {name} vroeg",
    "{name} made this": "{name} maakte dit",
    "The words": "De tekst",
    "Something you made": "Iets dat je maakte",
    "Something deleted": "Iets uit de prullenbak",
    "(music only - nobody sings on this one.)":
      "(alleen muziek - hier zingt niemand op.)",
    "(read back out of the file - this is the whole prompt, including the bits the dropdowns added.)":
      "(uit het bestand teruggelezen - dit is de hele opdracht, ook wat de " +
      "keuzelijstjes erbij deden.)",
    "A drawing you made. Tap Animate this to bring it to life!":
      "Een tekening van jou. Tik op Laat dit bewegen om hem tot leven te " +
      "wekken!",
    "A card you made. Print it, or share it!":
      "Een kaart van jou. Print hem, of deel hem!",
    "A photo you added. Tap Animate this to bring it to life!":
      "Een foto van jou. Tik op Laat dit bewegen om hem tot leven te wekken!",
    "This one's notes are lost - it was made before the app kept them, or straight from ComfyUI.":
      "De notities hiervan zijn weg - dit is gemaakt voordat de app ze " +
      "bewaarde, of rechtstreeks in ComfyUI.",
    "☆ Favourite": "☆ Favoriet",
    "⭐ Favourite": "⭐ Favoriet",
    "⭐ Starred": "⭐ Favoriet",
    "⭐ Starred!": "⭐ Favoriet!",
    "☆ This one’s best": "☆ Deze is de beste",
    "👨‍👩‍👧 Show the family": "👨‍👩‍👧 Aan familie laten zien",
    "👨‍👩‍👧 Hide from the family": "👨‍👩‍👧 Voor familie verbergen",
    "Everyone can see this one now! 👨‍👩‍👧": "Iedereen kan deze nu zien! 👨‍👩‍👧",
    "Back to just you.": "Weer alleen voor jou.",
    "🔁 Make another like this": "🔁 Nog zo eentje",
    "🎯 Make it again, but…": "🎯 Nog eens, maar…",
    "✨ Animate this": "✨ Laat dit bewegen",
    "🧑‍🎤 Save as a character": "🧑‍🎤 Bewaar als personage",
    "🎤 Say something over it": "🎤 Zeg er iets overheen",
    "✂️ Turn it into a sticker": "✂️ Maak er een sticker van",
    "✂️ Cutting it out...": "✂️ Aan het uitknippen...",
    "🔍 Make it huge": "🔍 Maak het reuzegroot",
    "🎨 Turn it into…": "🎨 Omtoveren tot…",
    "🪄 Change this picture": "🪄 Dit plaatje veranderen",
    "🔭 What's outside the frame?": "🔭 Wat zie je erbuiten?",
    "🩹 Fix just this bit": "🩹 Dit stukje aanpassen",
    "🖼️ Put it at the top": "🖼️ Zet het bovenaan",
    "👤 That one's me": "👤 Die ben ik",
    "🔊 Add a sound effect": "🔊 Geluidje erbij",
    "📸 Grab a picture from it": "📸 Pak er een plaatje uit",
    "✨ Make it smooth": "✨ Maak het vloeiend",
    "🐌 Slow it down": "🐌 Vertraag het",
    "🌀 Make a moving sticker": "🌀 Maak een bewegende sticker",
    "✏️ Draw on it": "✏️ Teken erop",
    "🖨️ Print it": "🖨️ Print het",
    "💌 Make a card": "💌 Maak een kaart",
    "▶️ What happens next?": "▶️ Wat gebeurt er nu?",
    "📤 Share": "📤 Delen",
    "⬇︎ Save it": "⬇︎ Opslaan",
    "↩️ Put it back": "↩️ Terugzetten",
    "🗑️ Delete for good": "🗑️ Voorgoed weggooien",
    "In the trash": "In de prullenbak",
    "Gone - it's in the trash.": "Weg - hij zit in de prullenbak.",
    "＋ Add a tag": "＋ Label erbij",
    "What tag?": "Welk label?",
    "What tag should these get?": "Welk label krijgen deze?",
    "\n\nAlready used: ": "\n\nAl gebruikt: ",
    "{n} thing tagged “#{tag}”": "{n} ding met label “#{tag}”",
    "{n} things tagged “#{tag}”": "{n} dingen met label “#{tag}”",
    "Couldn't open your gallery right now. Try again!":
      "Je galerij ging even niet open. Probeer het nog eens!",
    "That one's turned off just now.": "Die staat nu even uit.",

    // --- what kind of thing a tile is --------------------------------------
    "📖 Comic": "📖 Strip",
    "🧩 Panel": "🧩 Vakje",
    "📷 Photo": "📷 Foto",
    "🎬 Film": "🎬 Film",
    "🎤 My voice": "🎤 Mijn stem",
    "🔊 Sound": "🔊 Geluid",
    "✂️ Sticker": "✂️ Sticker",
    "📸 From a video": "📸 Uit een video",
    "🎵 Song": "🎵 Liedje",

    // --- what kind of sound: a song, a little tune, a background
    //     hum. One card and one model; see app/music.py KINDS.
    "What kind": "Wat voor",
    "What kind of sound to make": "Wat voor geluid je maakt",
    "Make my tune": "Maak mijn deuntje",
    "Make my sound": "Maak mijn geluid",
    "🎲 Thinking of a sound...": "🎲 Ik bedenk een geluid...",
    "Your tune is ready! ✨": "Je deuntje is klaar! ✨",
    "Your sound is ready! ✨": "Je geluid is klaar! ✨",
    "Making a little tune": "Ik maak een deuntje",
    "Making a background hum": "Ik maak een achtergrondgeluid",
    "🎺 Little tune": "🎺 Deuntje",
    "🌊 Background hum": "🌊 Achtergrondgeluid",
    "✨ Smooth": "✨ Vloeiend",
    "🐌 Slow motion": "🐌 Vertraagd",
    "🌀 Moving sticker": "🌀 Bewegende sticker",
    "🔍 Huge": "🔍 Reuzegroot",
    "🪄 Changed": "🪄 Veranderd",
    "🔭 More of it": "🔭 Meer eromheen",
    "🩹 Fixed a bit": "🩹 Stukje aangepast",
    "🎨 A new style": "🎨 Nieuwe stijl",
    "✏️ Drawing": "✏️ Tekening",
    "💌 Card": "💌 Kaart",
    "▶ Video": "▶ Video",

    // --- the result row ----------------------------------------------------
    "The picture you made": "Het plaatje dat je maakte",
    "One of the pictures you made": "Een van de plaatjes die je maakte",
    "Your comic": "Jouw strip",
    "🎲 Try again": "🎲 Nog eens proberen",
    "⬇︎ Save picture": "⬇︎ Plaatje opslaan",
    "⬇︎ Save video": "⬇︎ Video opslaan",
    "⬇︎ Save song": "⬇︎ Liedje opslaan",
    "⬇︎ Save my film": "⬇︎ Mijn film opslaan",
    "⬇︎ Save my comic": "⬇︎ Mijn strip opslaan",
    "⬇︎ Save them all": "⬇︎ Alles opslaan",
    "Keep this one": "Deze bewaren",
    "✓ Kept": "✓ Bewaard",
    "Delete this one": "Deze weggooien",
    "It's a sticker! ✂️": "Het is een sticker! ✂️",
    "It's ready! ✨": "Hij is klaar! ✨",
    "It's ready! 🔍": "Hij is klaar! 🔍",
    "Your very first picture! 🎉": "Je allereerste plaatje! 🎉",
    "Your very first video! 🎉": "Je allereerste video! 🎉",
    "Your very first comic! 🎉": "Je allereerste strip! 🎉",
    "Your very first film! 🎉": "Je allereerste film! 🎉",
    "That's {n} pictures! 🎉": "Dat zijn al {n} plaatjes! 🎉",
    "That's {n} videos! 🎉": "Dat zijn al {n} video's! 🎉",
    "That's {n} comics! 🎉": "Dat zijn al {n} strips! 🎉",
    "That's {n} films! 🎉": "Dat zijn al {n} films! 🎉",

    // --- characters ---------------------------------------------------------
    "Character": "Personage",
    "What's this character called?": "Hoe heet dit personage?",
    "Having a good look at {name}...": "Goed naar {name} aan het kijken...",
    "{name} can be in your next one! 🧑‍🎤":
      "{name} kan in je volgende meedoen! 🧑‍🎤",
    "That's {n} characters already! Say goodbye to one first, in the Gallery.":
      "Je hebt al {n} personages! Neem eerst afscheid van eentje, in de " +
      "Galerij.",
    "Forget “{idea}”": "“{idea}” vergeten",
    "✏️ Rename": "✏️ Andere naam",
    "🎨 How they look": "🎨 Hoe ze eruitzien",
    "👋 Say goodbye to them": "👋 Afscheid nemen",
    "Nothing with them in it yet! Choose them under “Who’s in it?” and make something.":
      "Nog niets met ze erin! Kies ze bij “Wie zit erin?” en maak iets.",
    "What should they be called?": "Hoe moeten ze heten?",
    "One sentence saying what they look like. This gets used in every picture they're in, so be specific about colours and clothes.":
      "Eén zin over hoe ze eruitzien. Die wordt gebruikt in elk plaatje " +
      "met hen erin, dus wees duidelijk over kleuren en kleren.",
    "Said goodbye to {name}. Their pictures are still in the Gallery.":
      "Afscheid genomen van {name}. Hun plaatjes staan nog in de Galerij.",
    "Couldn't load them just now.": "Ze konden even niet geladen worden.",

    // --- the film and card makers -------------------------------------------
    "Make a film": "Film maken",
    "{n} videos, in the order you chose them. It'll open with a title card - give it a name!":
      "{n} video's, in de volgorde die je koos. Er komt een titelkaartje " +
      "voor - geef het een naam!",
    "🎬 What's your film called?": "🎬 Hoe heet je film?",
    "The Great Pancake Adventure": "Het Grote Pannenkoekenavontuur",
    "My Film": "Mijn film",
    "{title} presents": "{title} presenteert",
    "Joining your film... this takes a little while.":
      "Je film aan het plakken... dat duurt even.",
    "Done! It's at the top of your videos.":
      "Klaar! Hij staat bovenaan bij je video's.",
    "Make a card": "Kaart maken",
    "Save my card": "Mijn kaart opslaan",
    "💌 What should it say?": "💌 Wat moet erop staan?",
    "Happy birthday Grandma!": "Fijne verjaardag, oma!",
    "Card colour": "Kleur van de kaart",
    "Card colour {n}": "Kaartkleur {n}",
    "Made for you!": "Voor jou gemaakt!",
    "made at {title}": "gemaakt bij {title}",
    "Saving your card...": "Je kaart aan het opslaan...",
    "Saved! It's in Photos & drawings - open it to print or share.":
      "Opgeslagen! Hij staat bij Foto's en tekeningen - open hem om te " +
      "printen of te delen.",
    "My comic": "Mijn strip",

    // --- their voice, sounds, frames, loops -----------------------------------
    "🎤 Say something": "🎤 Zeg iets",
    "✕ Close": "✕ Sluiten",
    "Tap the big button and talk. Your voice goes on top of your video.":
      "Tik op de grote knop en praat. Jouw stem komt over je video heen.",
    "Start talking": "Begin met praten",
    "Keep the video's own sound too (it goes quieter while you talk)":
      "Hou het geluid van de video er ook bij (het wordt zachter als jij " +
      "praat)",
    "✨ Put it on my video": "✨ Zet het op mijn video",
    "🔁 Record it again": "🔁 Nog eens opnemen",
    "🗑️ Throw the recording away": "🗑️ Opname weggooien",
    "Or use a sound you already have": "Of gebruik een geluid dat je al hebt",
    "This browser can't record here - that needs https. Pick a sound from your files below instead.":
      "Deze browser kan hier niet opnemen - daar is https voor nodig. Kies " +
      "hieronder een geluid uit je bestanden.",
    "You haven't put it on your video yet!":
      "Je hebt het nog niet op je video gezet!",
    "Your iPad needs to say yes to the microphone first. Tap the big button again and choose Allow.":
      "Je iPad moet eerst ja zeggen tegen de microfoon. Tik nog eens op de " +
      "grote knop en kies Sta toe.",
    "I can't find a microphone on this device. You can pick a sound from your files below instead.":
      "Ik vind geen microfoon op dit apparaat. Je kunt hieronder een " +
      "geluid uit je bestanden kiezen.",
    "The microphone didn't start ({why}). You can pick a sound from your files below instead.":
      "De microfoon startte niet ({why}). Je kunt hieronder een geluid uit " +
      "je bestanden kiezen.",
    "Putting your voice on it...": "Je stem erop aan het zetten...",
    "Your voice is on it! 🎤": "Je stem staat erop! 🎤",
    "Pick a sound, slide to where you want it, then put it on.":
      "Kies een geluid, schuif naar de plek die je wilt en zet het erop.",
    "When the sound happens": "Wanneer het geluid komt",
    "Couldn't load the sounds.": "De geluiden laadden niet.",
    "Putting it on...": "Bezig met erop zetten...",
    "Sound added! 🔊": "Geluid erbij! 🔊",
    "📸 Grab a picture": "📸 Pak een plaatje",
    "Slide to the bit you like. The picture underneath is exactly what you'll keep.":
      "Schuif naar het stukje dat je mooi vindt. Het plaatje eronder is " +
      "precies wat je bewaart.",
    "Which bit?": "Welk stukje?",
    "Which moment to keep": "Welk moment je bewaart",
    "The picture you are about to keep": "Het plaatje dat je gaat bewaren",
    "✨ Keep this picture": "✨ Dit plaatje bewaren",
    "Keeping it...": "Aan het bewaren...",
    "Kept it as a picture! 📸": "Bewaard als plaatje! 📸",
    "Pick the bit you want and it'll loop for ever - a sticker that moves.":
      "Kies het stukje dat je wilt en het blijft eeuwig rondgaan - een " +
      "sticker die beweegt.",
    "Start here": "Begin hier",
    "Where the loop starts": "Waar het rondje begint",
    "How long?": "Hoe lang?",
    "How long the loop is": "Hoe lang het rondje duurt",
    "1 second": "1 seconde",
    "2 seconds": "2 seconden",
    "Where your moving sticker starts": "Waar je bewegende sticker begint",
    "✨ Make my sticker": "✨ Maak mijn sticker",
    "Making it...": "Aan het maken...",
    "It moves! 🌀": "Hij beweegt! 🌀",

    // --- the three edits ----------------------------------------------------
    "Say what you'd like different and it'll make the same picture again with that changed.":
      "Zeg wat er anders moet en hetzelfde plaatje wordt opnieuw gemaakt, " +
      "met dat veranderd.",
    "The picture you're changing": "Het plaatje dat je verandert",
    "What should be different?": "Wat moet er anders?",
    "make it night-time\ngive the fox a scarf":
      "maak er nacht van\ngeef de vos een sjaal",
    "make it night-time": "maak er nacht van",
    "make it snowy": "laat het sneeuwen",
    "add a rainbow": "doe er een regenboog bij",
    "make it look like a painting": "laat het op een schilderij lijken",
    "put a hat on it": "zet er een hoed op",
    "make everything tiny": "maak alles piepklein",
    "...and put me in it 👤": "...en zet mij erin 👤",
    "✨ Go": "✨ Start",
    "Tell me what should be different!": "Zeg wat er anders moet!",
    "Changing your picture... 🪄": "Je plaatje aan het veranderen... 🪄",
    "Pick a kind of picture and it'll draw this one again that way, with everything still where it is.":
      "Kies een soort plaatje en dit wordt zo opnieuw getekend, met alles " +
      "nog op dezelfde plek.",
    "The picture you're turning into something else":
      "Het plaatje dat je omtovert",
    "What to turn it into": "Waarin je het omtovert",
    "Anything else? (you don't have to say)": "Nog iets anders? (hoeft niet)",
    "you don't have to say - or add your own twist: make it night-time":
      "hoeft niet - of verzin er iets bij: maak er nacht van",
    "Pick what to turn it into!": "Kies waarin je het omtovert!",
    "Drawing it again... 🎨": "Opnieuw aan het tekenen... 🎨",
    "Pick a side and it'll invent what was just out of the picture.":
      "Kies een kant en er wordt verzonnen wat er net buiten het plaatje was.",
    "The picture you're growing": "Het plaatje dat je groter maakt",
    "Which way?": "Welke kant?",
    "Which way to grow": "Naar welke kant het groeit",
    "All round": "Rondom",
    "⬅️ Left": "⬅️ Links",
    "➡️ Right": "➡️ Rechts",
    "⬆️ Up": "⬆️ Omhoog",
    "⬇️ Down": "⬇️ Omlaag",
    "How much?": "Hoeveel?",
    "How much bigger": "Hoeveel groter",
    "A bit": "Een beetje",
    "A lot": "Veel",
    "What's out there? (you don't have to say)": "Wat is daar? (hoeft niet)",
    "you don't have to say - or try: a beach, more trees":
      "hoeft niet - of probeer: een strand, meer bomen",
    "Looking outside the frame... 🔭": "Buiten het plaatje aan het kijken... 🔭",
    "Say what should be there instead, then tap Go.":
      "Zeg wat er dan moet komen en tik op Start.",
    "Paint over the bit you want changed first!":
      "Verf eerst over het stukje dat anders moet!",
    "Fixing that bit... 🩹": "Dat stukje aan het aanpassen... 🩹",
    "Slowing it right down... it comes out quiet 🐌":
      "Flink aan het vertragen... hij wordt stil 🐌",
    "Smoothing it out... ✨": "Aan het vloeiend maken... ✨",
    "Making it huge... 🔍": "Reuzegroot aan het maken... 🔍",
    "Cutting it out...": "Aan het uitknippen...",

    // --- compare ------------------------------------------------------------
    "🔍 Which one?": "🔍 Welke?",
    "Slide across to see one and then the other.":
      "Schuif heen en weer om de een en de ander te zien.",
    "The first one": "De eerste",
    "The second one": "De tweede",
    "Slide between the two pictures": "Schuif tussen de twee plaatjes",

    // --- the drawing pad ----------------------------------------------------
    "Draw something": "Teken iets",
    "Use my drawing": "Gebruik mijn tekening",
    "Colour": "Kleur",
    "Colour {n}": "Kleur {n}",
    "Stamps": "Stempels",
    "Stamp {emoji}": "Stempel {emoji}",
    "Thin brush": "Dunne kwast",
    "Medium brush": "Gewone kwast",
    "Thick brush": "Dikke kwast",
    "🧽 Rubber": "🧽 Gum",
    "↶ Undo": "↶ Terug",
    "Start again": "Opnieuw",
    "What should be there instead?": "Wat moet er dan komen?",
    "what should be there instead? e.g. a red party hat":
      "wat moet er dan komen? bijv. een rood feestmutsje",
    "Draw with your finger or a pencil. When you're done, tap <strong>Use my drawing</strong>.":
      "Teken met je vinger of een pen. Ben je klaar, tik dan op " +
      "<strong>Gebruik mijn tekening</strong>.",
    "Paint over the bit you want changed, say what should be there, then tap <strong>Go</strong>.":
      "Verf over het stukje dat anders moet, zeg wat er moet komen en tik " +
      "op <strong>Start</strong>.",

    // --- the chat tab -------------------------------------------------------
    "Chat with": "Chatten met",
    "Ask for an idea, or tell me what you’re making. Your grown-ups can read everything said here.":
      "Vraag om een idee, of vertel wat je aan het maken bent. Je ouders " +
      "kunnen alles lezen wat hier gezegd wordt.",
    "Your chat": "Jouw chat",
    "Say something": "Zeg iets",
    "Say something…": "Zeg iets…",
    "Send it": "Versturen",
    "Start a new chat": "Nieuwe chat beginnen",
    "Started a new chat. Your grown-ups can still see the old one.":
      "Nieuwe chat begonnen. Je ouders kunnen de oude nog zien.",
    "The chat helper isn't set up on this machine yet. Everything else still works!":
      "De chathelper staat op deze computer nog niet klaar. De rest werkt " +
      "gewoon!",
    "Give me an idea for a picture": "Geef me een idee voor een plaatje",
    "What can I make here?": "Wat kan ik hier maken?",
    // The third starter exists to show them they can write in the other
    // language, so on a French page it is the English one.
    "Donne-moi une idée de dessin": "Give me a drawing idea",
    "🎨 Make a picture of this": "🎨 Maak hier een plaatje van",
    "🎬 Make a video of this": "🎬 Maak hier een video van",
    "📋 Copy": "📋 Kopiëren",
    "✓ Copied": "✓ Gekopieerd",
    "✕ Couldn't copy": "✕ Kopiëren lukte niet",
    "That's what {name} said. Change anything you like, or tap “Help me write it” to turn it into a proper description.":
      "Dat zei {name}. Verander gerust wat je wilt, of tik op “Help me " +
      "schrijven” om er een echte beschrijving van te maken.",
    "the helper": "de helper",

    // --- Settings -----------------------------------------------------------
    "You": "Jij",
    "You're {name}!": "Jij bent {name}!",
    "🪄 Make a picture of me": "🪄 Maak een plaatje van mij",
    "😃 Pick a face instead": "😃 Kies liever een gezicht",
    "↩️ Back to the face": "↩️ Terug naar het gezicht",
    "Pick a face": "Kies een gezicht",
    "Colours": "Kleuren",
    "Language": "Taal",
    "Which language": "Welke taal",
    "The top of your page": "De bovenkant van je pagina",
    "What is across the top of your page now":
      "Wat er nu bovenaan je pagina staat",
    "↩️ Put the first one back": "↩️ Zet de eerste terug",
    "Put back the one it came with.": "Zet terug wat er eerst stond.",
    "Couldn't change it back.": "Terugzetten lukte niet.",
    "Making new ones is switched off right now, but you can still use any picture from <strong>Gallery</strong> — open one and tap <strong>Put it at the top</strong>.":
      "Nieuwe maken staat nu uit, maar je kunt elk plaatje uit de " +
      "<strong>Galerij</strong> gebruiken — open er een en tik op " +
      "<strong>Zet het bovenaan</strong>.",
    "It's a long thin strip, so wide things work best — a row of something, a view, a pattern. Your name goes on top of it, so leave the middle fairly quiet.":
      "Het is een lange smalle strook, dus brede dingen werken het best — " +
      "een rij van iets, een uitzicht, een patroon. Je naam komt " +
      "eroverheen, dus hou het midden rustig.",
    "🖼️ Putting it up...": "🖼️ Aan het ophangen...",
    "That's the top of your page now! 🖼️":
      "Dat staat nu bovenaan je pagina! 🖼️",
    "That one wouldn't go up there.": "Die wilde daar niet staan.",
    "Kept it on this device, but it wouldn't save.":
      "Op dit apparaat bewaard, maar opslaan lukte niet.",
    "Tap your face. A grown-up adds and changes these on the parent page.":
      "Tik op je gezicht. Een volwassene zet ze erbij en verandert ze op " +
      "de ouderpagina.",
    "👤 Making it you...": "👤 Jou aan het maken...",
    "That's you now! 👤": "Dat ben jij nu! 👤",
    "I'm a grown-up — the parent page":
      "Ik ben een volwassene — de ouderpagina",

    // --- who is making things today -----------------------------------------
    "Who's making things today?": "Wie gaat er vandaag iets maken?",

    // --- the picture-of-me wizard -------------------------------------------
    "Make a picture of me": "Maak een plaatje van mij",
    "1. What are you?": "1. Wat ben jij?",
    "What are you?": "Wat ben jij?",
    "Or type your own": "Of typ er zelf een",
    "…or type your own": "…of typ er zelf een",
    "2. What colour?": "2. Welke kleur?",
    "What colour?": "Welke kleur?",
    "3. Anything else?": "3. Nog iets anders?",
    "Anything else?": "Nog iets anders?",
    "Anything else": "Nog iets anders",
    "…a wizard hat, freckles, a scarf":
      "…een tovenaarshoed, sproeten, een sjaal",
    "Let's make it! ✨": "Maken maar! ✨",
    "It makes four at once so you can pick your favourite. Then tap <strong>👤 That one's me</strong> under the one you like.":
      "Er komen er vier tegelijk, zodat je je favoriet kunt kiezen. Tik " +
      "dan op <strong>👤 Die ben ik</strong> onder degene die je het mooist " +
      "vindt.",
    "Pick what you are to get started!": "Kies wat je bent om te beginnen!",
    "Pick what you are first!": "Kies eerst wat je bent!",
    "Making pictures is switched off right now.":
      "Plaatjes maken staat nu uit.",
    "Tap Go and pick your favourite! ✨": "Tik op Start en kies je favoriet! ✨",
    // The wizard's choices. The sentence they compose is a prompt, so the
    // article travels with the word in French, where gender does too.
    "a fox": "een vos", "a cat": "een kat", "a dog": "een hond",
    "a dragon": "een draak", "a robot": "een robot", "an owl": "een uil",
    "a unicorn": "een eenhoorn", "a penguin": "een pinguïn",
    "an astronaut": "een astronaut", "a wizard": "een tovenaar",
    "a superhero": "een superheld", "a pirate": "een piraat",
    "a mermaid": "een zeemeermin", "a knight": "een ridder",
    "a panda": "een panda", "an octopus": "een octopus",
    // "en violet" rather than "violet": the colour then agrees with nothing,
    // so one word does for a fox and for a mermaid alike.
    "purple": "paars", "blue": "blauw", "green": "groen",
    "orange": "oranje", "pink": "roze", "red": "rood",
    "yellow": "geel", "rainbow": "regenboog", "silver": "zilver",
    "golden": "goud",
    "a wizard hat": "een tovenaarshoed",
    "big round glasses": "een grote ronde bril",
    "a stripy scarf": "een gestreepte sjaal",
    "a cape": "een cape", "headphones": "een koptelefoon",
    "a flower crown": "een bloemenkrans", "a bow tie": "een vlinderdas",
    "freckles": "sproeten",

    // --- when it is shut -----------------------------------------------------
    "just now": "net",
    "{n} minute ago": "{n} minuut geleden",
    "{n} minutes ago": "{n} minuten geleden",
    "{n} hour ago": "{n} uur geleden",
    "{n} hours ago": "{n} uur geleden",
    "{n} KB": "{n} KB",
    "{n} MB": "{n} MB",

    // The close button on every sheet. Static markup, so it is a
    // data-i18n and not a t() - and it was English in every language
    // until the coverage walk went looking for exactly this.
    "✕ Close": "✕ Sluiten",
  };

  // Portuguese. The same keys in the same order under the same headings
  // as FR above, so a line missing from one of them is a line out of step.
  var PT = {
    // --- the shell ------------------------------------------------------
    "My AI Factory": "A Minha Fábrica IA",
    "AI Factory": "Fábrica IA",
    "What would you like to do?": "O que é que queres fazer?",
    "That's me - tap to swap": "Sou eu - toca para trocar",
    "Show me": "Mostra-me",
    "Working...": "A trabalhar...",
    "wiz-sentence":
      "{thing} amigável{colour}{wearing}, um retrato de desenho animado " +
      "alegre, cabeça e ombros, olhos grandes e simpáticos",
    "wiz-wearing": " que veste {list}",
    "wiz-and": " e ",
    "wiz-colour": " em {colour}",

    // Tabs. Short on purpose: seven of them share one row at 390px.
    "Picture": "Imagem",
    "Video": "Vídeo",
    "Comic": "BD",
    "Music": "Música",
    "Chat": "Chat",
    "Gallery": "Galeria",
    "Settings": "Ajustes",

    // --- "your picture is ready" ----------------------------------------
    "Your picture is ready! ✨": "A tua imagem está pronta! ✨",
    "Your video is ready! ✨": "O teu vídeo está pronto! ✨",
    "Your comic is ready! ✨": "A tua BD está pronta! ✨",
    "Your film is ready! ✨": "O teu filme está pronto! ✨",
    "Your song is ready! ✨": "A tua canção está pronta! ✨",
    "Your smooth video is ready! ✨": "O teu vídeo fluido está pronto! ✨",
    "Your slow-motion video is ready! ✨":
      "O teu vídeo em câmara lenta está pronto! ✨",
    "Your big picture is ready! ✨": "A tua imagem grande está pronta! ✨",
    "Your bigger picture is ready! ✨": "A tua imagem ampliada está pronta! ✨",
    "Your changed picture is ready! ✨": "A tua imagem mudada está pronta! ✨",

    // --- the Gallery ------------------------------------------------------
    "Everything you've made is saved here.":
      "Tudo o que fazes fica guardado aqui.",
    "Nothing here yet! Make a picture, a video or a comic and it'll turn up here.":
      "Ainda não há nada! Faz uma imagem, um vídeo ou uma BD e aparece aqui.",
    "Nothing of yours yet - but there's something on the family shelf!":
      "Ainda nada teu - mas há qualquer coisa na prateleira da família!",
    "You've made 1 thing so far.": "Já fizeste 1 coisa.",
    "You've made {n} things so far.": "Já fizeste {n} coisas.",
    "🧑‍🎤 My characters": "🧑‍🎤 As minhas personagens",
    "Show": "Ver",
    "How to show your gallery": "Como mostrar a tua galeria",
    "Everything": "Tudo",
    "In groups": "Por grupos",
    "Order": "Ordem",
    "What order to show them in": "Por que ordem mostrar",
    "Newest": "Recentes",
    "Oldest": "Antigas",
    "⭐ Favourites": "⭐ Favoritas",
    "By kind": "Por tipo",
    "🔎 Find something you made": "🔎 Encontra algo que fizeste",
    "Search your gallery": "Procurar na tua galeria",
    "Clear the search": "Limpar a procura",
    "Choose": "Escolher",
    "Cancel": "Cancelar",
    "👨‍👩‍👧 Family": "👨‍👩‍👧 Família",
    "🎨 Pictures": "🎨 Imagens",
    "📖 Comics": "📖 BD",
    "🧩 Comic pictures": "🧩 Imagens de BD",
    "✂️ Stickers": "✂️ Autocolantes",
    "📷 Photos & drawings": "📷 Fotos e desenhos",
    "🎬 Videos": "🎬 Vídeos",
    "🎵 Songs": "🎵 Canções",
    "Nothing matches that. Try another word!":
      "Não há nada assim. Experimenta outra palavra!",
    "Nothing here yet! Go and make something.":
      "Ainda não há nada! Vai fazer alguma coisa.",
    "🗑️ Recently deleted": "🗑️ Apagado há pouco",
    "Things stay here for {days} days, then they're gone for good. Tap one to put it back.":
      "As coisas ficam aqui {days} dias e depois vão-se de vez. Toca numa " +
      "para a pores de volta.",
    "Nothing chosen yet": "Ainda não escolheste nada",
    "Tap the ones you want": "Toca nas que queres",
    "1 chosen": "1 escolhida",
    "{n} chosen": "{n} escolhidas",
    "Choose all": "Escolher tudo",
    "Choose none": "Não escolher nada",
    "🎬 Join into a film": "🎬 Juntar num filme",
    "🔍 Compare them": "🔍 Compará-las",
    "🏷️ Add a tag": "🏷️ Pôr uma etiqueta",
    "⬇︎ Save": "⬇︎ Guardar",
    "🗑️ Delete": "🗑️ Apagar",
    "Deleted": "Apagada",
    "{n} things deleted": "{n} coisas apagadas",
    "Undo": "Anular",
    "Put back!": "De volta!",
    "All put back!": "Todas de volta!",
    "Really delete?": "Apagar mesmo?",
    "Really delete it?": "Apagar mesmo esta?",
    "Really delete all {n}?": "Apagar mesmo as {n}?",
    "Really delete forever?": "Apagar para sempre?",
    "Really clear it?": "Limpar mesmo tudo?",
    "Really say goodbye?": "Dizer mesmo adeus?",

    // --- the maker cards -------------------------------------------------
    "Make a picture": "Fazer uma imagem",
    "Make a video": "Fazer um vídeo",
    "Make a comic": "Fazer uma BD",
    "Make a song": "Fazer uma canção",
    "↺ Start again": "↺ Recomeçar",
    "Clear everything on this card and start again":
      "Limpar tudo neste cartão e recomeçar",
    "What should the picture be?": "O que é que a imagem vai mostrar?",
    "What should the video be?": "O que é que o vídeo vai mostrar?",
    "What's your story?": "Qual é a tua história?",
    "What should the song be about?": "A canção fala sobre o quê?",
    "What should the top of your page look like?":
      "Como é que vai ser o topo da tua página?",
    "A fluffy dragon eating pancakes on the moon":
      "Um dragão fofinho a comer panquecas na Lua",
    "A puppy surfing a giant wave at sunset":
      "Um cachorrinho a surfar uma onda gigante ao pôr do sol",
    "It flaps its wings and flies up into the clouds":
      "Bate as asas e voa até às nuvens",
    "The cat walks across the room and curls up in the sunny spot":
      "O gato atravessa a sala e enrosca-se no sítio com sol",
    "A little robot looking for its lost cat in a big city":
      "Um robô pequenino à procura do seu gato perdido numa cidade grande",
    "A hedgehog who wants to learn to swim":
      "Um ouriço que quer aprender a nadar",
    "A dragon who is scared of pancakes":
      "Um dragão que tem medo de panquecas",
    "A row of hot air balloons over a green valley":
      "Uma fila de balões de ar quente sobre um vale verde",
    "Clear what you typed": "Limpar o que escreveste",
    "✨ Help me write it": "✨ Ajuda-me a escrever",
    "👀 Look at my picture and help me write it":
      "👀 Olha para a minha imagem e ajuda-me a escrever",
    "✨ Write me a song": "✨ Escreve-me uma canção",
    "🎉 Surprise me": "🎉 Surpreende-me",
    "🎲 Mix it up": "🎲 Baralha tudo",
    "📜 Things I've asked for before": "📜 O que já pedi antes",
    "📷 Start from a photo": "📷 Partir de uma foto",
    "🖼️ Pick one from my gallery": "🖼️ Escolher da minha galeria",
    "Who's in it?": "Quem entra?",
    "Nobody": "Ninguém",
    "📄 Everything with {name} in it": "📄 Tudo onde entra {name}",
    "Make": "Fazer",
    "What kind of picture": "Que tipo de imagem",
    "A picture": "Uma imagem",
    "A character": "Uma personagem",
    "Drawn on its own with nothing behind it, so you can cut it out as a sticker or keep them as a character.":
      "Desenhada sozinha, sem nada por trás, para poderes recortá-la como " +
      "autocolante ou guardá-la como personagem.",
    "Shape": "Forma",
    "Picture shape": "Forma da imagem",
    "Video shape": "Forma do vídeo",
    "Landscape": "Horizontal",
    "Portrait": "Vertical",
    "Square": "Quadrada",
    "landscape": "horizontal",
    "portrait": "vertical",
    "square": "quadrada",
    "How many": "Quantas",
    "How many pictures": "Quantas imagens",
    "How many panels": "Quantos quadradinhos",
    "Just one": "Só uma",
    "Four to pick from": "Quatro à escolha",
    "3 pictures": "3 imagens",
    "4 pictures": "4 imagens",
    "6 pictures": "6 imagens",
    "Look": "Aspeto",
    "Look and sound": "Aspeto e som",
    "Sound": "Som",
    "Clear these": "Limpar isto",
    "Any": "À escolha",
    "Make my picture": "Faz a minha imagem",
    "Make {n} pictures": "Faz {n} imagens",
    "Make my video": "Faz o meu vídeo",
    "Make my film": "Faz o meu filme",
    "Animate it": "Dá-lhe vida",
    "Make my comic": "Faz a minha BD",
    "Make my song": "Faz a minha canção",
    "Make my music": "Faz a minha música",
    "Make one": "Faz uma",
    "Stop": "Parar",
    "Tell a story and it gets drawn as a comic strip you can print.":
      "Conta uma história e ela é desenhada como uma BD que podes imprimir.",

    // video card
    "Start from": "Partir de",
    "What to start the video from": "De onde parte o vídeo",
    "✏️ Words": "✏️ Palavras",
    "🖼️ A picture": "🖼️ Uma imagem",
    "🎞️ Two pictures": "🎞️ Duas imagens",
    "📽️ A little film": "📽️ Um filme pequenino",
    "Make a picture up above and tap <strong>Animate this</strong>, or use a photo from your iPad.":
      "Faz uma imagem aí em cima e toca em <strong>Dá-lhe vida</strong>, " +
      "ou usa uma foto do teu iPad.",
    "The picture you picked": "A imagem que escolheste",
    "This picture is ready to animate!":
      "Esta imagem está pronta a ganhar vida!",
    "Use a different one": "Usar outra",
    "📷 Take or choose a photo": "📷 Tira ou escolhe uma foto",
    "✏️ Draw one": "✏️ Desenha uma",
    "Pick where the video starts and where it ends. The middle gets made up.":
      "Escolhe onde o vídeo começa e onde acaba. O meio é inventado.",
    "Starts on": "Começa em",
    "Ends on": "Acaba em",
    "🖼️ Pick from the gallery": "🖼️ Escolher da galeria",
    "🖼️ Pick a different one": "🖼️ Escolher outra",
    "🗣️ What should they say?": "🗣️ O que é que eles dizem?",
    "(you can leave this empty)": "(podes deixar vazio)",
    "Look at the Earth from up here!": "Olha a Terra cá de cima!",
    "Clear what they say": "Limpar o que eles dizem",
    "🔊 Videos have sound — they'll say this out loud, so keep it short.":
      "🔊 Os vídeos têm som — eles vão dizer isto em voz alta, por isso não " +
      "escrevas muito.",
    "Quality": "Qualidade",
    "Video quality": "Qualidade do vídeo",
    "⚡ Quick": "⚡ Rápido",
    "👍 Normal": "👍 Normal",
    "✨ Sharper": "✨ Mais nítido",
    "Sharper means more detail, but it takes a good deal longer to make, and the longest a sharper video can be is":
      "Mais nítido quer dizer mais pormenores, mas demora bastante mais a " +
      "fazer, e um vídeo mais nítido não pode passar dos",
    "seconds.": "segundos.",
    "How long": "Duração",
    "Video length in seconds": "Duração do vídeo em segundos",
    "How long the song is, in seconds": "Duração da canção, em segundos",
    "{n} seconds": "{n} segundos",
    "Longer videos take longer to make.":
      "Vídeos mais longos demoram mais a fazer.",
    "Longer songs take longer to make.":
      "Canções mais longas demoram mais a fazer.",
    "How many parts": "Quantas partes",
    "2 parts": "2 partes",
    "3 parts": "3 partes",
    "4 parts": "4 partes",
    "Each part carries on from the last one, then they're joined into one film. It takes a while, and it uses up one video for each part.":
      "Cada parte continua a anterior e depois é tudo juntado num só " +
      "filme. Demora um bocado e gasta um vídeo por cada parte.",
    "🔊 Add a sound": "🔊 Juntar um som",
    "None": "Nenhum",
    "When?": "Quando?",
    "At the start": "No início",
    "In the middle": "A meio",
    "At the end": "No fim",

    // music card
    "Singing": "Canto",
    "Singing or not": "Com canto ou sem",
    "With singing": "Com canto",
    "Just music": "Só música",
    "Words": "Letra",
    "Clear the words": "Limpar a letra",
    "[Verse]\nI met a dragon on the stairs\nHe said he doesn't like éclairs\n\n[Chorus]\nPancakes, pancakes, run away!":
      "[Estrofe]\nVi um dragão lá nas escadas\nDisse que odeia " +
      "marmeladas\n\n[Refrão]\nPanquecas, panquecas, fujam já!",
    "Put <strong>[Verse]</strong> or <strong>[Chorus]</strong> on a line of their own to mark the parts. Leave it empty and you'll get music with nobody singing.":
      "Põe <strong>[Estrofe]</strong> ou <strong>[Refrão]</strong> numa " +
      "linha só para eles, para marcar as partes. Deixa vazio e tens " +
      "música sem ninguém a cantar.",

    // --- the helpers -----------------------------------------------------
    "Type a few words about your idea first!":
      "Escreve primeiro umas palavras sobre a tua ideia!",
    "Thinking of ideas...": "A pensar em ideias...",
    "Looking at your picture...": "A olhar para a tua imagem...",
    "This takes a moment the first time.":
      "Da primeira vez demora um bocadinho.",
    "Here you go! Change anything you like.":
      "Aqui tens! Muda o que quiseres.",
    "Here's an idea for it - change anything you like.":
      "Aqui tens uma ideia - muda o que quiseres.",
    "Writing your song...": "A escrever a tua canção...",
    "Here are some words! Change any line you like - they don't have to rhyme.":
      "Aqui tens a letra! Muda as linhas que quiseres - não têm de rimar.",
    "🎲 Thinking of something...": "🎲 A pensar nalguma coisa...",
    "🎲 Writing a song...": "🎲 A escrever uma canção...",
    "Dreaming up an idea...": "A inventar uma ideia...",
    "Here's a whole song! Change any line you like.":
      "Aqui tens uma canção inteira! Muda as linhas que quiseres.",
    "Here's an idea! Change anything you like.":
      "Aqui tens uma ideia! Muda o que quiseres.",
    "One of your old ideas with a brand new look. Change anything you like!":
      "Uma das tuas ideias antigas com um visual novinho. Muda o que " +
      "quiseres!",
    "A brand new idea. Change anything you like!":
      "Uma ideia novinha em folha. Muda o que quiseres!",
    "🎲 Shuffling...": "🎲 A baralhar...",
    "Same as before - change anything you like, then go!":
      "Igual a antes - muda o que quiseres e vai!",
    "Change a word or two and you'll get this same one, but different. “Make another like this” starts from scratch instead.":
      "Muda uma palavra ou duas e tens esta mesma, mas diferente. “Faz " +
      "outra assim” começa do zero.",
    "Your drawing is ready! Tap the helper to get a script for it, or say what should happen.":
      "O teu desenho está pronto! Toca no ajudante para teres um texto, ou " +
      "diz o que deve acontecer.",
    "This starts where that video stopped. What happens next?":
      "Isto começa onde esse vídeo parou. O que acontece a seguir?",

    // --- while it renders -------------------------------------------------
    "Sending it off...": "A enviar...",
    "Getting started...": "A começar...",
    "Starting": "Início",
    "Making another one...": "A fazer outra...",
    "Getting it ready...": "A preparar...",
    "Working out your story...": "A imaginar a tua história...",
    "Reading your story...": "A ler a tua história...",
    "Putting your comic together...": "A montar a tua BD...",
    "Stopping...": "A parar...",
    "Stopped! Nothing was made. Try a different idea.":
      "Parado! Não se fez nada. Experimenta outra ideia.",
    "Couldn't stop it — it may finish anyway.":
      "Não deu para parar — se calhar acaba na mesma.",
    "Something went wrong. Let's try that again!":
      "Alguma coisa correu mal. Vamos tentar outra vez!",
    "Pick a picture first — make one above, or use a photo!":
      "Escolhe primeiro uma imagem — faz uma aí em cima, ou usa uma foto!",
    "Pick a picture to start on and one to end on!":
      "Escolhe uma imagem para começar e outra para acabar!",
    "Type something you'd like to make first!":
      "Escreve primeiro o que gostavas de fazer!",
    "Sending your photo...": "A enviar a tua foto...",
    "It's in your gallery! Now pick what to do with it ✨":
      "Está na tua galeria! Agora escolhe o que fazer com ela ✨",
    "✅ Ready!": "✅ Pronto!",
    "Took {time}.": "Demorou {time}.",
    "{n} seconds long": "{n} segundos",
    "{n} second": "{n} segundo",
    "{n} secs": "{n} s",
    "about {n} seconds": "cerca de {n} segundos",
    "about a minute": "cerca de um minuto",
    "about {n} minutes": "cerca de {n} minutos",
    "{time} so far": "{time} até agora",
    "about {time} to go": "faltam cerca de {time}",
    "⏱️ I haven't made one of these yet — I'll time this one.":
      "⏱️ Ainda não fiz nenhuma destas — vou cronometrar esta.",
    "⏱️ Takes {time} on this computer.": "⏱️ Demora {time} neste computador.",
    "⏱️ Probably takes {time}.": "⏱️ Deve demorar {time}.",

    // --- the allowance and the clock --------------------------------------
    "🌙 That's all the pictures for today. See you tomorrow!":
      "🌙 Acabaram as imagens por hoje. Até amanhã!",
    "🌙 That's all the videos for today. See you tomorrow!":
      "🌙 Acabaram os vídeos por hoje. Até amanhã!",
    "🌙 That's all the songs for today. See you tomorrow!":
      "🌙 Acabaram as canções por hoje. Até amanhã!",
    "✨ {n} pictures left today, so that's how many you'll get.":
      "✨ Só te restam {n} imagens hoje, é isso que vais ter.",
    "✨ {n} videos left today, so that's how many you'll get.":
      "✨ Só te restam {n} vídeos hoje, é isso que vais ter.",
    "✨ {n} songs left today, so that's how many you'll get.":
      "✨ Só te restam {n} canções hoje, é isso que vais ter.",
    "✨ 1 picture left today, so that's how many you'll get.":
      "✨ Só te resta 1 imagem hoje, é isso que vais ter.",
    "✨ 1 video left today, so that's how many you'll get.":
      "✨ Só te resta 1 vídeo hoje, é isso que vais ter.",
    "✨ 1 song left today, so that's how many you'll get.":
      "✨ Só te resta 1 canção hoje, é isso que vais ter.",
    "✨ One more picture today - make it a good one!":
      "✨ Mais uma imagem hoje - faz uma bonita!",
    "✨ One more video today - make it a good one!":
      "✨ Mais um vídeo hoje - faz um bonito!",
    "✨ One more song today - make it a good one!":
      "✨ Mais uma canção hoje - faz uma bonita!",
    "✨ {n} more pictures today": "✨ Mais {n} imagens hoje",
    "✨ {n} more videos today": "✨ Mais {n} vídeos hoje",
    "✨ {n} more songs today": "✨ Mais {n} canções hoje",
    "The factory closes at {at} - any minute now!":
      "A fábrica fecha às {at} - é de um momento para o outro!",
    "closes-in": "A fábrica fecha às {at} - faltam cerca de {mins} minutos.",
    "The factory is closed right now": "A fábrica está fechada neste momento",
    "Back soon!": "Já volta!",

    // --- the warm-up sums --------------------------------------------------
    "Warm up your brain!": "Aquece o cérebro!",
    "Get these right and the factory opens for today.":
      "Acerta nestas e a fábrica abre por hoje.",
    "Get it right and the factory opens for today.":
      "Acerta nesta e a fábrica abre por hoje.",
    "Get all {n} right and the factory opens for today.":
      "Acerta nas {n} e a fábrica abre por hoje.",
    "Check my answers": "Vê as minhas respostas",
    "Fill them all in first!": "Preenche-as todas primeiro!",
    "All right! Off you go.": "Tudo certo! Podes ir.",
    "So close - one of those wasn't right. Here are some new ones!":
      "Tão perto - uma delas não estava certa. Aqui tens outras novas!",
    "Not quite! Here are some new ones.":
      "Não foi bem! Aqui tens outras novas.",
    "Something went wrong. Try again!":
      "Alguma coisa correu mal. Tenta outra vez!",
    "I'm a grown-up": "Sou adulto",
    "Grown-up PIN": "PIN dos adultos",
    "Let me in": "Deixa-me entrar",

    // --- the viewer --------------------------------------------------------
    "Pick a picture": "Escolhe uma imagem",
    "Pick where it starts": "Escolhe onde começa",
    "Pick where it ends": "Escolhe onde acaba",
    "Done": "Pronto",
    "← Back": "← Voltar",
    "What is it called?": "Como é que se chama?",
    "✏️ Give it a name": "✏️ Dá-lhe um nome",
    "What you asked for": "O que pediste",
    "What {name} asked for": "O que {name} pediu",
    "{name} made this": "{name} fez isto",
    "The words": "A letra",
    "Something you made": "Uma coisa que fizeste",
    "Something deleted": "Uma coisa apagada",
    "(music only - nobody sings on this one.)":
      "(só música - ninguém canta nesta.)",
    "(read back out of the file - this is the whole prompt, including the bits the dropdowns added.)":
      "(lido do ficheiro - esta é a descrição inteira, com o que os menus " +
      "juntaram.)",
    "A drawing you made. Tap Animate this to bring it to life!":
      "Um desenho que fizeste. Toca em Dá-lhe vida para o pôr a mexer!",
    "A card you made. Print it, or share it!":
      "Um cartão que fizeste. Imprime-o, ou partilha-o!",
    "A photo you added. Tap Animate this to bring it to life!":
      "Uma foto que juntaste. Toca em Dá-lhe vida para a pôr a mexer!",
    "This one's notes are lost - it was made before the app kept them, or straight from ComfyUI.":
      "As notas desta perderam-se - foi feita antes de a aplicação as " +
      "guardar, ou direto no ComfyUI.",
    "☆ Favourite": "☆ Favorita",
    "⭐ Favourite": "⭐ Favorita",
    "⭐ Starred": "⭐ Marcada",
    "⭐ Starred!": "⭐ Marcada!",
    "☆ This one’s best": "☆ Esta é a melhor",
    "👨‍👩‍👧 Show the family": "👨‍👩‍👧 Mostrar à família",
    "👨‍👩‍👧 Hide from the family": "👨‍👩‍👧 Esconder da família",
    "Everyone can see this one now! 👨‍👩‍👧":
      "Agora toda a gente pode ver esta! 👨‍👩‍👧",
    "Back to just you.": "Outra vez só tua.",
    "🔁 Make another like this": "🔁 Faz outra assim",
    "🎯 Make it again, but…": "🎯 Faz outra vez, mas…",
    "✨ Animate this": "✨ Dá-lhe vida",
    "🧑‍🎤 Save as a character": "🧑‍🎤 Guardar como personagem",
    "🎤 Say something over it": "🎤 Fala por cima",
    "✂️ Turn it into a sticker": "✂️ Transforma em autocolante",
    "✂️ Cutting it out...": "✂️ A recortar...",
    "🔍 Make it huge": "🔍 Torna-a gigante",
    "🎨 Turn it into…": "🎨 Transforma em…",
    "🪄 Change this picture": "🪄 Muda esta imagem",
    "🔭 What's outside the frame?": "🔭 O que há à volta?",
    "🩹 Fix just this bit": "🩹 Arranja só este bocado",
    "🖼️ Put it at the top": "🖼️ Põe-na no topo",
    "👤 That one's me": "👤 Esta sou eu",
    "🔊 Add a sound effect": "🔊 Junta um som",
    "📸 Grab a picture from it": "📸 Tira uma imagem dali",
    "✨ Make it smooth": "✨ Torna-a fluida",
    "🐌 Slow it down": "🐌 Abranda-a",
    "🌀 Make a moving sticker": "🌀 Faz um autocolante animado",
    "✏️ Draw on it": "✏️ Desenha por cima",
    "🖨️ Print it": "🖨️ Imprime",
    "💌 Make a card": "💌 Faz um cartão",
    "▶️ What happens next?": "▶️ E a seguir?",
    "📤 Share": "📤 Partilhar",
    "⬇︎ Save it": "⬇︎ Guarda",
    "↩️ Put it back": "↩️ Põe de volta",
    "🗑️ Delete for good": "🗑️ Apagar de vez",
    "In the trash": "No lixo",
    "Gone - it's in the trash.": "Foi-se - está no lixo.",
    "＋ Add a tag": "＋ Pôr uma etiqueta",
    "What tag?": "Que etiqueta?",
    "What tag should these get?": "Que etiqueta para estas?",
    "\n\nAlready used: ": "\n\nJá usadas: ",
    "{n} thing tagged “#{tag}”": "{n} coisa com a etiqueta “#{tag}”",
    "{n} things tagged “#{tag}”": "{n} coisas com a etiqueta “#{tag}”",
    "Couldn't open your gallery right now. Try again!":
      "Não deu para abrir a tua galeria agora. Tenta outra vez!",
    "That one's turned off just now.": "Isso está desligado neste momento.",

    // --- what kind of thing a tile is --------------------------------------
    "📖 Comic": "📖 BD",
    "🧩 Panel": "🧩 Quadradinho",
    "📷 Photo": "📷 Foto",
    "🎬 Film": "🎬 Filme",
    "🎤 My voice": "🎤 A minha voz",
    "🔊 Sound": "🔊 Som",
    "✂️ Sticker": "✂️ Autocolante",
    "📸 From a video": "📸 De um vídeo",
    "🎵 Song": "🎵 Canção",

    // --- what kind of sound: a song, a little tune, a background
    //     hum. One card and one model; see app/music.py KINDS.
    "What kind": "Que tipo",
    "What kind of sound to make": "Que tipo de som fazer",
    "Make my tune": "Faz a minha melodia",
    "Make my sound": "Faz o meu som",
    "🎲 Thinking of a sound...": "🎲 A pensar num som...",
    "Your tune is ready! ✨": "A tua melodia está pronta! ✨",
    "Your sound is ready! ✨": "O teu som está pronto! ✨",
    "Making a little tune": "Estou a fazer uma melodia",
    "Making a background hum": "Estou a fazer um som de fundo",
    "🎺 Little tune": "🎺 Melodia",
    "🌊 Background hum": "🌊 Som de fundo",
    "✨ Smooth": "✨ Fluida",
    "🐌 Slow motion": "🐌 Câmara lenta",
    "🌀 Moving sticker": "🌀 Autocolante animado",
    "🔍 Huge": "🔍 Gigante",
    "🪄 Changed": "🪄 Mudada",
    "🔭 More of it": "🔭 Mais à volta",
    "🩹 Fixed a bit": "🩹 Arranjada",
    "🎨 A new style": "🎨 Estilo novo",
    "✏️ Drawing": "✏️ Desenho",
    "💌 Card": "💌 Cartão",
    "▶ Video": "▶ Vídeo",

    // --- the result row ----------------------------------------------------
    "The picture you made": "A imagem que fizeste",
    "One of the pictures you made": "Uma das imagens que fizeste",
    "Your comic": "A tua BD",
    "🎲 Try again": "🎲 Tenta outra vez",
    "⬇︎ Save picture": "⬇︎ Guarda a imagem",
    "⬇︎ Save video": "⬇︎ Guarda o vídeo",
    "⬇︎ Save song": "⬇︎ Guarda a canção",
    "⬇︎ Save my film": "⬇︎ Guarda o meu filme",
    "⬇︎ Save my comic": "⬇︎ Guarda a minha BD",
    "⬇︎ Save them all": "⬇︎ Guarda-as todas",
    "Keep this one": "Fico com esta",
    "✓ Kept": "✓ Guardada",
    "Delete this one": "Apagar esta",
    "It's a sticker! ✂️": "É um autocolante! ✂️",
    "It's ready! ✨": "Está pronta! ✨",
    "It's ready! 🔍": "Está pronta! 🔍",
    "Your very first picture! 🎉": "A tua primeiríssima imagem! 🎉",
    "Your very first video! 🎉": "O teu primeiríssimo vídeo! 🎉",
    "Your very first comic! 🎉": "A tua primeiríssima BD! 🎉",
    "Your very first film! 🎉": "O teu primeiríssimo filme! 🎉",
    "That's {n} pictures! 🎉": "Já são {n} imagens! 🎉",
    "That's {n} videos! 🎉": "Já são {n} vídeos! 🎉",
    "That's {n} comics! 🎉": "Já são {n} BD! 🎉",
    "That's {n} films! 🎉": "Já são {n} filmes! 🎉",

    // --- characters ---------------------------------------------------------
    "Character": "Personagem",
    "What's this character called?": "Como se chama esta personagem?",
    "Having a good look at {name}...": "A olhar bem para {name}...",
    "{name} can be in your next one! 🧑‍🎤":
      "{name} pode entrar na próxima! 🧑‍🎤",
    "That's {n} characters already! Say goodbye to one first, in the Gallery.":
      "Já são {n} personagens! Diz adeus a uma primeiro, na Galeria.",
    "Forget “{idea}”": "Esquecer “{idea}”",
    "✏️ Rename": "✏️ Mudar o nome",
    "🎨 How they look": "🎨 Como é",
    "👋 Say goodbye to them": "👋 Dizer-lhe adeus",
    "Nothing with them in it yet! Choose them under “Who’s in it?” and make something.":
      "Ainda não há nada com ela! Escolhe-a em “Quem entra?” e faz alguma " +
      "coisa.",
    "What should they be called?": "Como se vai chamar?",
    "One sentence saying what they look like. This gets used in every picture they're in, so be specific about colours and clothes.":
      "Uma frase a dizer como ela é. Serve em todas as imagens onde ela " +
      "entra, por isso diz bem as cores e a roupa.",
    "Said goodbye to {name}. Their pictures are still in the Gallery.":
      "Adeus, {name}. As imagens dela continuam na Galeria.",
    "Couldn't load them just now.": "Não deu para as carregar agora.",

    // --- the film and card makers -------------------------------------------
    "Make a film": "Fazer um filme",
    "{n} videos, in the order you chose them. It'll open with a title card - give it a name!":
      "{n} vídeos, pela ordem que escolheste. Começa com um cartão de " +
      "título - dá-lhe um nome!",
    "🎬 What's your film called?": "🎬 Como se chama o teu filme?",
    "The Great Pancake Adventure": "A Grande Aventura das Panquecas",
    "My Film": "O Meu Filme",
    "{title} presents": "{title} apresenta",
    "Joining your film... this takes a little while.":
      "A juntar o teu filme... demora um bocadinho.",
    "Done! It's at the top of your videos.":
      "Pronto! Está no topo dos teus vídeos.",
    "Make a card": "Fazer um cartão",
    "Save my card": "Guarda o meu cartão",
    "💌 What should it say?": "💌 O que é que vai dizer?",
    "Happy birthday Grandma!": "Parabéns, Avó!",
    "Card colour": "Cor do cartão",
    "Card colour {n}": "Cor do cartão {n}",
    "Made for you!": "Feito para ti!",
    "made at {title}": "feito em {title}",
    "Saving your card...": "A guardar o teu cartão...",
    "Saved! It's in Photos & drawings - open it to print or share.":
      "Guardado! Está em Fotos e desenhos - abre para imprimir ou partilhar.",
    "My comic": "A Minha BD",

    // --- their voice, sounds, frames, loops -----------------------------------
    "🎤 Say something": "🎤 Diz qualquer coisa",
    "✕ Close": "✕ Fechar",
    "Tap the big button and talk. Your voice goes on top of your video.":
      "Toca no botão grande e fala. A tua voz fica por cima do teu vídeo.",
    "Start talking": "Começa a falar",
    "Keep the video's own sound too (it goes quieter while you talk)":
      "Manter também o som do vídeo (fica mais baixo enquanto falas)",
    "✨ Put it on my video": "✨ Põe no meu vídeo",
    "🔁 Record it again": "🔁 Gravar outra vez",
    "🗑️ Throw the recording away": "🗑️ Deitar a gravação fora",
    "Or use a sound you already have": "Ou usa um som que já tens",
    "This browser can't record here - that needs https. Pick a sound from your files below instead.":
      "Este navegador não pode gravar aqui - é preciso https. Escolhe " +
      "antes um som dos teus ficheiros, aqui em baixo.",
    "You haven't put it on your video yet!":
      "Ainda não a puseste no teu vídeo!",
    "Your iPad needs to say yes to the microphone first. Tap the big button again and choose Allow.":
      "O teu iPad tem de dizer sim ao microfone primeiro. Toca outra vez " +
      "no botão grande e escolhe Permitir.",
    "I can't find a microphone on this device. You can pick a sound from your files below instead.":
      "Não encontro nenhum microfone neste aparelho. Podes escolher um som " +
      "dos teus ficheiros, aqui em baixo.",
    "The microphone didn't start ({why}). You can pick a sound from your files below instead.":
      "O microfone não arrancou ({why}). Podes escolher um som dos teus " +
      "ficheiros, aqui em baixo.",
    "Putting your voice on it...": "A pôr a tua voz por cima...",
    "Your voice is on it! 🎤": "A tua voz está lá! 🎤",
    "Pick a sound, slide to where you want it, then put it on.":
      "Escolhe um som, arrasta até onde o queres e depois põe-no.",
    "When the sound happens": "Quando o som acontece",
    "Couldn't load the sounds.": "Não deu para carregar os sons.",
    "Putting it on...": "A pôr...",
    "Sound added! 🔊": "Som juntado! 🔊",
    "📸 Grab a picture": "📸 Tirar uma imagem",
    "Slide to the bit you like. The picture underneath is exactly what you'll keep.":
      "Arrasta até ao bocado que gostas. A imagem aqui em baixo é mesmo a " +
      "que vais ficar.",
    "Which bit?": "Que momento?",
    "Which moment to keep": "Que momento guardar",
    "The picture you are about to keep": "A imagem que vais guardar",
    "✨ Keep this picture": "✨ Guarda esta imagem",
    "Keeping it...": "A guardar...",
    "Kept it as a picture! 📸": "Guardada como imagem! 📸",
    "Pick the bit you want and it'll loop for ever - a sticker that moves.":
      "Escolhe o bocado que queres e vai rodar em círculo para sempre - um " +
      "autocolante que mexe.",
    "Start here": "Começa aqui",
    "Where the loop starts": "Onde a volta começa",
    "How long?": "Que duração?",
    "How long the loop is": "Quanto dura a volta",
    "1 second": "1 segundo",
    "2 seconds": "2 segundos",
    "Where your moving sticker starts":
      "Onde começa o teu autocolante animado",
    "✨ Make my sticker": "✨ Faz o meu autocolante",
    "Making it...": "A fazer...",
    "It moves! 🌀": "Mexe! 🌀",

    // --- the three edits ----------------------------------------------------
    "Say what you'd like different and it'll make the same picture again with that changed.":
      "Diz o que queres diferente e a mesma imagem é feita outra vez com " +
      "essa mudança.",
    "The picture you're changing": "A imagem que estás a mudar",
    "What should be different?": "O que é que vai ser diferente?",
    "make it night-time\ngive the fox a scarf":
      "põe de noite\npõe um cachecol na raposa",
    "make it night-time": "põe de noite",
    "make it snowy": "põe neve",
    "add a rainbow": "junta um arco-íris",
    "make it look like a painting": "faz com que pareça uma pintura",
    "put a hat on it": "põe-lhe um chapéu",
    "make everything tiny": "torna tudo pequenino",
    "...and put me in it 👤": "...e põe-me lá dentro 👤",
    "✨ Go": "✨ Vai",
    "Tell me what should be different!": "Diz-me o que vai ser diferente!",
    "Changing your picture... 🪄": "A mudar a tua imagem... 🪄",
    "Pick a kind of picture and it'll draw this one again that way, with everything still where it is.":
      "Escolhe um tipo de imagem e esta é desenhada outra vez assim, com " +
      "tudo no mesmo sítio.",
    "The picture you're turning into something else":
      "A imagem que estás a transformar",
    "What to turn it into": "Em que a transformar",
    "Anything else? (you don't have to say)":
      "Mais alguma coisa? (não tens de dizer)",
    "you don't have to say - or add your own twist: make it night-time":
      "não tens de dizer - ou junta a tua ideia: põe de noite",
    "Pick what to turn it into!": "Escolhe em que a transformar!",
    "Drawing it again... 🎨": "A desenhá-la outra vez... 🎨",
    "Pick a side and it'll invent what was just out of the picture.":
      "Escolhe um lado e vai ser inventado o que estava mesmo fora da imagem.",
    "The picture you're growing": "A imagem que estás a aumentar",
    "Which way?": "Para que lado?",
    "Which way to grow": "Para que lado aumentar",
    "All round": "À volta toda",
    "⬅️ Left": "⬅️ Esquerda",
    "➡️ Right": "➡️ Direita",
    "⬆️ Up": "⬆️ Cima",
    "⬇️ Down": "⬇️ Baixo",
    "How much?": "Quanto?",
    "How much bigger": "Quanto maior",
    "A bit": "Um bocado",
    "A lot": "Muito",
    "What's out there? (you don't have to say)":
      "O que há lá fora? (não tens de dizer)",
    "you don't have to say - or try: a beach, more trees":
      "não tens de dizer - ou tenta: uma praia, mais árvores",
    "Looking outside the frame... 🔭": "A olhar para fora da imagem... 🔭",
    "Say what should be there instead, then tap Go.":
      "Diz o que deve ficar ali e depois toca em Vai.",
    "Paint over the bit you want changed first!":
      "Pinta primeiro por cima do bocado que queres mudar!",
    "Fixing that bit... 🩹": "A arranjar esse bocado... 🩹",
    "Slowing it right down... it comes out quiet 🐌":
      "A abrandá-la até ao fundo... vai sair sem som 🐌",
    "Smoothing it out... ✨": "A torná-la fluida... ✨",
    "Making it huge... 🔍": "A torná-la gigante... 🔍",
    "Cutting it out...": "A recortar...",

    // --- compare ------------------------------------------------------------
    "🔍 Which one?": "🔍 Qual delas?",
    "Slide across to see one and then the other.":
      "Arrasta para ver uma e depois a outra.",
    "The first one": "A primeira",
    "The second one": "A segunda",
    "Slide between the two pictures": "Arrasta entre as duas imagens",

    // --- the drawing pad ----------------------------------------------------
    "Draw something": "Desenha alguma coisa",
    "Use my drawing": "Usa o meu desenho",
    "Colour": "Cor",
    "Colour {n}": "Cor {n}",
    "Stamps": "Carimbos",
    "Stamp {emoji}": "Carimbo {emoji}",
    "Thin brush": "Pincel fino",
    "Medium brush": "Pincel médio",
    "Thick brush": "Pincel grosso",
    "🧽 Rubber": "🧽 Borracha",
    "↶ Undo": "↶ Anular",
    "Start again": "Recomeçar",
    "What should be there instead?": "O que é que deve ficar ali?",
    "what should be there instead? e.g. a red party hat":
      "o que deve ficar ali? por exemplo um chapéu de festa vermelho",
    "Draw with your finger or a pencil. When you're done, tap <strong>Use my drawing</strong>.":
      "Desenha com o dedo ou com um lápis. Quando acabares, toca em " +
      "<strong>Usa o meu desenho</strong>.",
    "Paint over the bit you want changed, say what should be there, then tap <strong>Go</strong>.":
      "Pinta por cima do bocado a mudar, diz o que deve ficar ali e depois " +
      "toca em <strong>Vai</strong>.",

    // --- the chat tab -------------------------------------------------------
    "Chat with": "Conversa com",
    "Ask for an idea, or tell me what you’re making. Your grown-ups can read everything said here.":
      "Pede uma ideia, ou conta-me o que estás a fazer. Os teus adultos " +
      "podem ler tudo o que se diz aqui.",
    "Your chat": "A tua conversa",
    "Say something": "Diz qualquer coisa",
    "Say something…": "Diz qualquer coisa…",
    "Send it": "Enviar",
    "Start a new chat": "Começar uma conversa nova",
    "Started a new chat. Your grown-ups can still see the old one.":
      "Conversa nova. Os teus adultos ainda podem ver a antiga.",
    "The chat helper isn't set up on this machine yet. Everything else still works!":
      "O ajudante de chat ainda não está instalado neste computador. Tudo " +
      "o resto funciona!",
    "Give me an idea for a picture": "Dá-me uma ideia para uma imagem",
    "What can I make here?": "O que posso fazer aqui?",
    // The third starter exists to show them they can write in the other
    // language, so on a French page it is the English one.
    "Donne-moi une idée de dessin": "Give me a drawing idea",
    "🎨 Make a picture of this": "🎨 Faz uma imagem disto",
    "🎬 Make a video of this": "🎬 Faz um vídeo disto",
    "📋 Copy": "📋 Copiar",
    "✓ Copied": "✓ Copiado",
    "✕ Couldn't copy": "✕ Não deu para copiar",
    "That's what {name} said. Change anything you like, or tap “Help me write it” to turn it into a proper description.":
      "Foi isso que {name} disse. Muda o que quiseres, ou toca em " +
      "“Ajuda-me a escrever” para fazer disso uma descrição a sério.",
    "the helper": "o ajudante",

    // --- Settings -----------------------------------------------------------
    "You": "Tu",
    "You're {name}!": "Tu és {name}!",
    "🪄 Make a picture of me": "🪄 Faz uma imagem de mim",
    "😃 Pick a face instead": "😃 Escolhe antes uma cara",
    "↩️ Back to the face": "↩️ Voltar à cara",
    "Pick a face": "Escolhe uma cara",
    "Colours": "Cores",
    "Language": "Língua",
    "Which language": "Que língua",
    "The top of your page": "O topo da tua página",
    "What is across the top of your page now":
      "O que está no topo da tua página agora",
    "↩️ Put the first one back": "↩️ Põe a primeira de volta",
    "Put back the one it came with.": "Voltou a primeira de todas.",
    "Couldn't change it back.": "Não deu para a pôr de volta.",
    "Making new ones is switched off right now, but you can still use any picture from <strong>Gallery</strong> — open one and tap <strong>Put it at the top</strong>.":
      "Fazer novas está desligado neste momento, mas podes usar qualquer " +
      "imagem da <strong>Galeria</strong> — abre uma e toca em " +
      "<strong>Põe-na no topo</strong>.",
    "It's a long thin strip, so wide things work best — a row of something, a view, a pattern. Your name goes on top of it, so leave the middle fairly quiet.":
      "É uma tira comprida e estreita, por isso as coisas largas funcionam " +
      "melhor — uma fila de alguma coisa, uma paisagem, um padrão. O teu " +
      "nome fica por cima, por isso deixa o meio bastante calmo.",
    "🖼️ Putting it up...": "🖼️ A pôr no topo...",
    "That's the top of your page now! 🖼️": "Já é o topo da tua página! 🖼️",
    "That one wouldn't go up there.": "Essa não deu para pôr lá em cima.",
    "Kept it on this device, but it wouldn't save.":
      "Ficou neste aparelho, mas não deu para guardar.",
    "Tap your face. A grown-up adds and changes these on the parent page.":
      "Toca na tua cara. Um adulto acrescenta e muda isto na página dos " +
      "adultos.",
    "👤 Making it you...": "👤 A fazer com que sejas tu...",
    "That's you now! 👤": "Agora és tu! 👤",
    "I'm a grown-up — the parent page": "Sou adulto — a página dos adultos",

    // --- who is making things today -----------------------------------------
    "Who's making things today?": "Quem vai fabricar hoje?",

    // --- the picture-of-me wizard -------------------------------------------
    "Make a picture of me": "Uma imagem de mim",
    "1. What are you?": "1. O que és tu?",
    "What are you?": "O que és tu?",
    "Or type your own": "Ou escreve o teu",
    "…or type your own": "…ou escreve o teu",
    "2. What colour?": "2. De que cor?",
    "What colour?": "De que cor?",
    "3. Anything else?": "3. Mais alguma coisa?",
    "Anything else?": "Mais alguma coisa?",
    "Anything else": "Mais alguma coisa",
    "…a wizard hat, freckles, a scarf":
      "…um chapéu de feiticeiro, sardas, um cachecol",
    "Let's make it! ✨": "Vamos a isso! ✨",
    "It makes four at once so you can pick your favourite. Then tap <strong>👤 That one's me</strong> under the one you like.":
      "Faz quatro de uma vez para escolheres a tua preferida. Depois toca " +
      "em <strong>👤 Esta sou eu</strong> por baixo daquela que gostares.",
    "Pick what you are to get started!": "Escolhe o que és para começar!",
    "Pick what you are first!": "Escolhe primeiro o que és!",
    "Making pictures is switched off right now.":
      "Fazer imagens está desligado neste momento.",
    "Tap Go and pick your favourite! ✨":
      "Toca em Vai e escolhe a tua preferida! ✨",
    // The wizard's choices. The sentence they compose is a prompt, so the
    // article travels with the word in French, where gender does too.
    "a fox": "uma raposa", "a cat": "um gato", "a dog": "um cão",
    "a dragon": "um dragão", "a robot": "um robô", "an owl": "uma coruja",
    "a unicorn": "um unicórnio", "a penguin": "um pinguim",
    "an astronaut": "um astronauta", "a wizard": "um feiticeiro",
    "a superhero": "um super-herói", "a pirate": "um pirata",
    "a mermaid": "uma sereia", "a knight": "um cavaleiro",
    "a panda": "um panda", "an octopus": "um polvo",
    // "en violet" rather than "violet": the colour then agrees with nothing,
    // so one word does for a fox and for a mermaid alike.
    "purple": "roxo", "blue": "azul", "green": "verde",
    "orange": "laranja", "pink": "cor-de-rosa", "red": "vermelho",
    "yellow": "amarelo", "rainbow": "arco-íris", "silver": "prateado",
    "golden": "dourado",
    "a wizard hat": "um chapéu de feiticeiro",
    "big round glasses": "uns óculos grandes e redondos",
    "a stripy scarf": "um cachecol às riscas",
    "a cape": "uma capa", "headphones": "uns auscultadores",
    "a flower crown": "uma coroa de flores", "a bow tie": "um laço ao pescoço",
    "freckles": "sardas",

    // --- when it is shut -----------------------------------------------------
    "just now": "agora mesmo",
    "{n} minute ago": "há {n} minuto",
    "{n} minutes ago": "há {n} minutos",
    "{n} hour ago": "há {n} hora",
    "{n} hours ago": "há {n} horas",
    "{n} KB": "{n} KB",
    "{n} MB": "{n} MB",

    // The close button on every sheet. Static markup, so it is a
    // data-i18n and not a t() - and it was English in every language
    // until the coverage walk went looking for exactly this.
    "✕ Close": "✕ Fechar",
  };

  var DICTS = { en: EN, fr: FR, de: DE, es: ES, it: IT,
                 nl: NL, pt: PT };

  function cookieLang() {
    try {
      var m = / *lang=(en|fr|de|es|it|nl|pt)\b/.exec("; " + document.cookie);
      return m ? m[1] : "";
    } catch (e) { return ""; }
  }

  function storedLang() {
    try {
      var v = localStorage.getItem("makery:lang") || "";
      return DICTS[v] ? v : "";
    } catch (e) { return ""; }
  }

  // The cookie is what the server reads, so it wins. localStorage is only the
  // pre-paint guess for a browser where the two could differ - the same trick
  // the colour scheme uses, and /api/app corrects both.
  var lang = cookieLang() || storedLang() || "en";

  function t(key, vars) {
    var out = DICTS[lang] && DICTS[lang][key];
    if (out === undefined) out = EN[key];
    if (out === undefined) out = key;
    if (vars) {
      out = out.replace(/\{(\w+)\}/g, function (whole, name) {
        return vars[name] === undefined || vars[name] === null ? "" : String(vars[name]);
      });
    }
    return lang === "fr" ? spaces(out) : out;
  }

  // French puts a space in front of ! ? : and ;, and it has to be one that
  // does not break: "Échauffe ton cerveau !" wrapped with the ! alone on the
  // next line. Done here rather than in every entry so the dictionary above
  // stays readable with ordinary spaces.
  //
  // French and nothing else. Spanish opens its questions instead (¿…?), which
  // is a character and is written into the entries; German, Dutch, Italian
  // and Portuguese set their marks tight against the word the way English
  // does. One rule for all seven would put a gap in front of every
  // exclamation mark on six pages that do not want one.
  function spaces(text) {
    return text.replace(/ ([!?;:»])/g, " $1").replace(/« /g, "« ");
  }

  // The static markup, in place. `data-i18n` is the element's text and its
  // English *is* the key, so the HTML still reads as the page it renders;
  // `data-i18n-attr` is "attr:key;attr:key" for the placeholders, the
  // aria-labels and the titles.
  function apply(root) {
    var where = root || document;
    Array.prototype.forEach.call(where.querySelectorAll("[data-i18n]"), function (el) {
      var key = el.getAttribute("data-i18n") || el.textContent.trim();
      var out = t(key);
      if (out === key) return;
      // A few carry markup (a <strong> inside a sentence), and those keys say
      // so by containing a tag. Everything else is text, which is safer.
      if (/<[a-z]/i.test(out)) el.innerHTML = out; else el.textContent = out;
    });
    Array.prototype.forEach.call(where.querySelectorAll("[data-i18n-attr]"),
      function (el) {
        (el.getAttribute("data-i18n-attr") || "").split(";").forEach(function (pair) {
          var at = pair.indexOf(":");
          if (at < 1) return;
          var attr = pair.slice(0, at).trim();
          var key = pair.slice(at + 1).trim();
          var out = t(key);
          if (out !== key || attr === "placeholder") el.setAttribute(attr, out);
        });
      });
  }

  function set(next) {
    if (!DICTS[next]) return;
    lang = next;
    try { localStorage.setItem("makery:lang", next); } catch (e) {}
    // A year, and lax so it survives the page being opened from a bookmark or
    // a home-screen icon. Whoever is at the screen chose it; it is not a
    // per-profile setting, so there is nothing on the server to save.
    document.cookie = "lang=" + next + "; max-age=31536000; path=/; samesite=lax";
  }

  return {
    t: t,
    apply: apply,
    set: set,
    get lang() { return lang; },
    // The dictionaries themselves, for anything that has to look one up by
    // name - the coverage walk does, and so does anybody in a console.
    DICTS: DICTS,
    FR: FR,
    EN: EN,
  };
})();

window.t = window.I18N.t;

// Straight away, not on DOMContentLoaded: this file is loaded at the end of
// the body, so every element it has to touch already exists, and waiting for
// an event would put a flash of English on the screen first - the same reason
// the colour scheme is set in a snippet in <head>.
window.I18N.apply();
