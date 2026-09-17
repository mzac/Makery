"""Prompt safety.

Two layers:

1. `check_prompt` - the one that actually works. Rejects the prompt before it
   ever reaches ComfyUI. This is the real filter.
2. `NEGATIVE_*` - hidden negative prompts injected into every job. Note that
   all three workflows currently run at CFG 1.0 (Flux schnell, and the LTX
   DualCFGGuider), where negative conditioning is mathematically ignored.
   They are here so they take effect if CFG is ever raised.
"""

import re
import unicodedata

from . import i18n

# --- Layer 1: input-side blocklist -----------------------------------------

# An adjective in front of a noun takes an ending in most of these, and the
# list has to carry every one of them: "nackt" does not match "eine nackte
# Frau", which is a miss with nothing subtle about it - found by testing, not
# by reading. So the adjectives are written once and expanded here.
#
# The endings are bounded on both sides, which is the point: "nackt" as a
# *prefix* would match "Nacktschnecke", which is a slug.
_DE = ("", "e", "em", "en", "er", "es")     # German, before the noun
_NL = ("", "e")                             # Dutch adds one and no more
_PLURAL = ("", "s")                         # Spanish and Portuguese
_IT = ("o", "a", "i", "e")                  # Italian, off the stem


def _inflect(words, endings):
    return [word + end for word in words for end in endings]


# "see through" and "see-through" were on the sexual list as bare adjectives,
# and a bare adjective for transparent is not a sexual word: it is a ghost, a
# soap bubble, a pane of glass, a jellyfish, a window, stained glass - which
# is one of the restyle chips - and the app's own wording for what a sticker
# is made of, which the filter refused when it was run over its own UI text.
# A refusal is not a shrug here: it quotes what the child typed to a parent
# and can shut the factory for the rest of the day, so a ghost costing them the
# afternoon is a far worse outcome than the thing this entry was guarding
# against - which a determined prompt would write round in any case, since two
# words in a fixed order is the easiest kind of entry to avoid.
#
# So it is qualified with the nouns that make it mean the thing it was for,
# and it covers more than it did on the way past: "sheer" and "transparent"
# come along, and the old list had "transparent clothing" and nothing else.
_SHEER = [
    f"{adj} {noun}"
    for adj in ("see through", "see-through", "transparent", "sheer")
    for noun in ("clothing", "clothes", "dress", "top", "shirt", "blouse",
                 "skirt", "gown", "outfit", "lingerie", "underwear")
]


# Matched case-insensitively on word boundaries against the child's prompt.
# Entries may be multi-word. Keep these lowercase.
BLOCKLIST = {
    "sexual": [
        "nude", "nudes", "naked", "nsfw", "porn", "porno", "pornographic",
        "hentai", "erotic", "erotica", "sex", "sexy", "sexual", "orgasm",
        "masturbat", "genital", "genitals", "penis", "vagina", "breasts",
        "boobs", "tits", "nipple", "nipples", "areola", "butt", "buttocks",
        "ass", "crotch", "groin", "lingerie", "underwear", "panties", "thong",
        "bikini", "topless", "bottomless", "undressed", "undressing",
        "stripping", "strip club", "stripper", "fetish", "bdsm", "bondage",
        "seductive", "sensual", "provocative", "suggestive", "lewd", "smut",
        "cleavage", "upskirt", "voyeur", "onlyfans", "escort", "prostitute",
        "hooker", "brothel", "milf", "twerk", "twerking", "grinding",
        "skimpy", "revealing outfit", *_SHEER,
        "wet t-shirt", "micro bikini",
    ],
    "minors_sexual": [
        "loli", "lolicon", "shota", "shotacon", "jailbait", "cp",
        "child porn", "underage", "preteen", "pre-teen",
    ],
    "violence": [
        "gore", "gory", "blood", "bloody", "bleeding", "mutilat", "mutilated",
        "dismember", "dismembered", "decapitat", "decapitated", "beheaded",
        "beheading", "corpse", "corpses", "dead body", "dead bodies",
        "carnage", "massacre", "slaughter", "torture", "tortured", "torturing",
        "gruesome", "brutal", "brutality", "murder", "murdered", "killing",
        "stabbing", "stabbed", "shooting", "shot dead", "execution",
        "executed", "lynching", "hanging", "impaled", "disembowel",
        "guts", "entrails", "severed head", "severed limb", "wound", "wounds",
        "wounded", "injury", "injured", "self harm", "self-harm", "suicide",
        "cutting myself", "kill myself", "anorexia", "anorexic",
    ],
    "weapons": [
        "gun", "guns", "rifle", "pistol", "handgun", "shotgun", "firearm",
        "firearms", "ak-47", "ak47", "ar-15", "ar15", "machine gun",
        "assault weapon", "bomb", "bombs", "grenade", "explosive",
        "explosives", "ied", "molotov", "landmine", "warhead", "sniper",
    ],
    "drugs": [
        "cocaine", "heroin", "meth", "methamphetamine", "crack pipe",
        "fentanyl", "lsd", "ecstasy", "mdma", "ketamine", "opioid",
        "syringe", "needle drugs", "injecting drugs", "bong", "weed",
        "marijuana", "cannabis", "stoned", "drunk", "alcoholic",
        "beer", "vodka", "whiskey", "tequila", "cigarette", "cigarettes",
        "smoking", "vape", "vaping", "juul",
    ],
    "hate": [
        "nazi", "nazis", "swastika", "hitler", "kkk", "ku klux klan",
        "white power", "white supremacy", "ethnic cleansing", "genocide",
        "holocaust", "isis", "terrorist", "terrorism", "jihad",
        "racist", "racial slur", "lynch",
        # Add any slurs you want blocked here; they are matched on word
        # boundaries like everything else.
    ],
    "real_people": [
        "deepfake", "deep fake", "face swap", "faceswap",
        "revenge porn", "without consent", "non-consensual", "nonconsensual",
    ],
    # --- and the same categories in the other six ---------------------------
    #
    # They read seven languages, so the blocklist has to. Each list is that
    # language's spelling of the English categories above, kept accented:
    # `normalize` folds accents on the *input*, so an accented term still
    # matches there, while the raw pass catches anything whose folded form
    # would collide with an ordinary English word.
    #
    # **Every list has words deliberately left out of it**, and they are named
    # in the comment above each one. The rule is the one French set: a word
    # that is vulgar in one sense and completely ordinary in another belongs
    # off the list, because refusing a child's picture of a fox's tail is a
    # visible failure where letting a rude word through to Flux is not.
    # The commonest shape of it is an anatomical slang word that is also an
    # animal or a part of one - "queue", "Schwanz", "rabo", "uccello", "poes".
    #
    # None of the seven blocks the word for *wine*, because the English list
    # does not either. The rule was to say the English categories in another
    # language, not to improve on them on the way past.
    #
    # **Every list is matched against every prompt**, whatever page they are on,
    # so a word only has to be innocent in *one* of the seven to be a false
    # positive in all of them. That is a class of mistake French could not
    # make on its own and it caught seven words here: "bom" is a bomb in
    # Dutch and "good" in Portuguese, "pila" is vulgar in Portuguese and a
    # battery in Spanish, "porro" is a joint in Spanish and a leek in
    # Italian, "charro" is a joint in Portuguese and a Mexican horseman in
    # Spanish, "colocado" is stoned and also simply "placed", "scopare" is
    # vulgar and also sweeping the floor, and "joint" is an ordinary English
    # word for the bend in a robot's arm. All seven are out; the compounds
    # that can only mean the bad thing ("bomaanslag", "injectiespuit") stay.
    #
    # A *short* word cannot be kept honest by hand that way - there are only
    # so many two-letter words and all seven languages have spent them, which
    # is how French "nu" came to refuse the Dutch for "now". So the shortest
    # entries are matched only when the page is in their own language:
    # `SHORT_TERM_CHARS`, below the lists, is where that happens and why.
    # French. Two words deliberately absent: "bite" is vulgar in French and an
    # everyday English word ("takes a bite"), and "sang" is blood in French and
    # the past tense of sing. "queue" is absent for the same reason it is in
    # every other language here - it is a tail. "héroïne" is listed accented
    # only and excluded from folding, because "heroine" is a word every brave
    # heroine needs.
    "sexual_fr": [
        "nu", "nue", "nus", "nues", "tout nu", "toute nue", "déshabillé",
        "déshabillée", "se déshabiller", "sexe", "sexy", "sexuel", "sexuelle",
        "pornographie", "pornographique", "érotique", "seins", "nichons",
        "téton", "tétons", "fesses", "cul", "culotte", "soutien-gorge",
        "sous-vêtements", "petite tenue", "strip-tease", "prostituée",
        "salope", "pute", "putain", "baise", "baiser une", "enculé",
        "aguicheuse", "aguicheur", "suggestif", "suggestive", "lingerie fine",
    ],
    "violence_fr": [
        "sanglant", "sanglante", "sanguinolent", "ensanglanté", "ensanglantée",
        "hémorragie", "égorger", "égorgé", "décapiter", "décapité", "décapitée",
        "décapitation", "mutiler", "mutilé", "mutilée", "démembrer", "démembré",
        "cadavre", "cadavres", "meurtre", "meurtrier", "assassiner", "assassiné",
        "tuer", "tuerie", "massacre", "carnage", "torturer", "torturé",
        "éventrer", "éventré", "pendaison", "pendu", "poignarder", "poignardé",
        "fusillade", "boyaux", "tripes", "automutilation", "se suicider",
        "suicider", "me tuer", "atroce", "horrible mort",
    ],
    "weapons_fr": [
        "pistolet", "fusil", "arme à feu", "armes à feu", "mitraillette",
        "mitrailleuse", "kalachnikov", "bombe", "bombes", "explosif",
        "explosifs", "cocktail molotov", "poignard",
    ],
    "drugs_fr": [
        "drogue", "drogues", "drogué", "droguée", "cocaïne", "héroïne",
        "seringue", "cannabis", "haschisch", "shit", "défoncé", "défoncée",
        "ivre", "saoul", "soûl", "bourré", "bourrée", "alcoolique", "bière",
        "vodka", "whisky", "cigarette", "cigarettes", "fumer une",
    ],
    "hate_fr": [
        "nazi", "nazie", "nazis", "croix gammée", "suprémaciste",
        "nettoyage ethnique", "génocide", "terroriste", "terrorisme",
        "raciste", "insulte raciste",
    ],
    "scary_fr": [
        "démoniaque", "satanique", "démon", "possédé", "possédée",
        "exorcisme", "cauchemardesque", "terrifiant", "terrifiante",
        "horrifiant", "horrifiante", "dérangeant", "dérangeante",
        "image maudite", "gore",
    ],
    # Spanish. Left out on purpose: "zorra" is a vulgar word for a woman and
    # also a female fox, which this app draws more than almost anything else;
    # "concha" is vulgar in the River Plate and a seashell everywhere else;
    # "coger" is vulgar in Mexico and the everyday word for "take" in Spain;
    # "heroína" is heroin *and* heroine in the same spelling, accents and all,
    # so unlike French there is no accented form to keep; "granada" is a
    # grenade, a pomegranate and a city; "cañón" is a cannon and a canyon;
    # "vino" is wine and "he came"; "coca" is cocaine, a flatbread and a
    # fizzy drink. "pecho" and "herido" are out for the reason English keeps
    # "wound" and French keeps no word for it - a chest and a hurt knee are
    # ordinary things in a story.
    "sexual_es": [
        "desnudo", "desnuda", "desnudos", "desnudas", "desnudez",
        "desvestido", "desvestida", "desvestirse", "semidesnudo",
        "semidesnuda", "sexo", "sexual", "sexy", "porno", "pornografía",
        "pornográfico", "erótico", "erótica", "tetas", "senos", "pezón",
        "pezones", "culo", "nalgas", "trasero", "bragas", "ropa interior",
        "sujetador", "lencería", "tanga", "estriptis", "striptease",
        "prostituta", "puta", "follar", "polla", "cachondo", "cachonda",
        "provocativo", "provocativa", "insinuante", "sin ropa", "en topless",
        *_inflect(("desnudo", "desnuda", "desvestido", "desvestida",
                   "semidesnudo", "semidesnuda", "erótico", "erótica",
                   "cachondo", "cachonda", "provocativo", "provocativa"),
                  _PLURAL),
    ],
    "violence_es": [
        "sangre", "sangriento", "sangrienta", "ensangrentado",
        "ensangrentada", "desangrar", "degollar", "degollado", "decapitar",
        "decapitado", "decapitada", "decapitación", "mutilar", "mutilado",
        "mutilada", "descuartizar", "descuartizado", "cadáver", "cadáveres",
        "asesinar", "asesinato", "asesino", "matar a", "masacre", "matanza",
        "carnicería", "torturar", "tortura", "torturado", "destripar",
        "destripado", "ahorcar", "ahorcado", "ahorcamiento", "apuñalar",
        "apuñalado", "tiroteo", "disparar a", "tripas", "vísceras",
        "suicidio", "suicidarse", "autolesión", "autolesionarse", "anorexia",
        "anoréxica", "muerte horrible",
        *_inflect(("sangriento", "sangrienta", "ensangrentado",
                   "ensangrentada", "degollado", "decapitado",
                   "decapitada", "mutilado", "mutilada",
                   "descuartizado", "torturado", "ahorcado",
                   "apuñalado", "destripado", "asesinado"), _PLURAL),
    ],
    "weapons_es": [
        "pistola", "revólver", "escopeta", "fusil", "ametralladora",
        "subfusil", "arma de fuego", "armas de fuego", "kalashnikov",
        "bomba", "bombas", "explosivo", "explosivos", "cóctel molotov",
        "mina antipersona", "francotirador", "puñal",
    ],
    "drugs_es": [
        "droga", "drogas", "drogado", "drogada", "drogarse", "cocaína",
        "metanfetamina", "jeringuilla", "jeringa", "marihuana",
        "cannabis", "hachís", "borracho", "borracha",
        "emborracharse", "ebrio", "alcohólico", "alcohólica", "cerveza",
        "vodka", "whisky", "tequila", "cigarrillo", "cigarrillos", "cigarro",
        "fumar", "fumando", "vapear",
        *_inflect(("drogado", "drogada", "borracho", "borracha",
                   "alcohólico", "alcohólica"), _PLURAL),
    ],
    "hate_es": [
        "esvástica", "cruz gamada", "supremacista", "supremacía blanca",
        "limpieza étnica", "genocidio", "holocausto", "terrorista",
        "terrorismo", "yihad", "racista", "insulto racista",
    ],
    "scary_es": [
        "demoníaco", "demoníaca", "satánico", "satánica", "demonio",
        "poseído", "poseída", "exorcismo", "de pesadilla", "aterrador",
        "aterradora", "horripilante", "perturbador", "perturbadora",
        "macabro", "macabra", "imagen maldita",
        *_inflect(("demoníaco", "demoníaca", "satánico", "satánica",
                   "poseído", "poseída", "macabro", "macabra",
                   "aterrador", "aterradora"), _PLURAL),
    ],

    # Italian. Left out on purpose: "uccello" is a bird and vulgar slang;
    # "sedere" is a bottom and the verb "to sit"; "troia" is a sow, the city
    # of Troy and an insult - and a Trojan horse is a picture a child asks
    # for; "canna" is a reed, a fishing rod and a joint; "fatto" is "done" and
    # "stoned"; "eroina" is heroin *and* heroine, like the Spanish; "seno" is
    # a breast, a bosom and a sine, so only the plural is listed; "ferito" is
    # out with the other languages' words for wounded.
    "sexual_it": [
        "nudo", "nuda", "nudi", "nudità", "spogliato", "spogliata",
        "spogliarsi", "spogliarello", "seminudo", "seminuda", "sesso",
        "sessuale", "porno", "pornografia", "pornografico", "erotico",
        "erotica", "tette", "seni", "capezzolo", "capezzoli", "culo",
        "mutande", "mutandine", "reggiseno", "biancheria intima", "perizoma",
        "prostituta", "puttana", "cazzo", "figa", "provocante",
        "ammiccante", "senza vestiti",
        *_inflect(("nud", "spogliat", "seminud", "erotic"), _IT),
    ],
    "violence_it": [
        "sangue", "sanguinante", "insanguinato", "insanguinata",
        "sanguinolento", "dissanguare", "sgozzare", "sgozzato", "decapitare",
        "decapitato", "decapitata", "decapitazione", "mutilare", "mutilato",
        "mutilata", "smembrare", "smembrato", "cadavere", "cadaveri",
        "omicidio", "assassinare", "assassinato", "uccidere", "strage",
        "massacro", "carneficina", "torturare", "tortura", "torturato",
        "sventrare", "sventrato", "impiccare", "impiccato", "impiccagione",
        "accoltellare", "accoltellato", "sparatoria", "sparare a", "budella",
        "viscere", "suicidio", "suicidarsi", "autolesionismo", "anoressia",
        "anoressica", "morte atroce", "raccapricciante",
        *_inflect(("insanguinat", "sgozzat", "decapitat", "mutilat",
                   "smembrat", "torturat", "sventrat", "impiccat",
                   "accoltellat"), _IT),
    ],
    "weapons_it": [
        "pistola", "fucile", "fucile d'assalto", "mitra", "mitragliatrice",
        "arma da fuoco", "armi da fuoco", "kalashnikov", "bomba", "bombe",
        "bomba a mano", "esplosivo", "esplosivi", "molotov",
        "mina antiuomo",
        "cecchino", "pugnale",
    ],
    "drugs_it": [
        "droga", "droghe", "drogato", "drogata", "drogarsi", "cocaina",
        "metanfetamina", "siringa", "spinello", "marijuana", "cannabis",
        "hashish", "ubriaco", "ubriaca", "ubriacarsi", "alcolizzato",
        "alcolizzata", "birra", "vodka", "whisky", "sigaretta", "sigarette",
        "fumare", "svapare",
        *_inflect(("drogat", "ubriac"), _IT), "ubriachi",
    ],
    "hate_it": [
        "nazista", "nazisti", "svastica", "croce uncinata", "suprematista",
        "supremazia bianca", "pulizia etnica", "genocidio", "olocausto",
        "terrorista", "terrorismo", "razzista", "insulto razzista",
    ],
    "scary_it": [
        "demoniaco", "demoniaca", "satanico", "satanica", "demone",
        "posseduto", "posseduta", "esorcismo", "da incubo", "terrificante",
        "orripilante", "inquietante", "macabro", "macabra",
        "immagine maledetta",
        *_inflect(("demoniac", "satanic", "possedut", "macabr"), _IT),
    ],

    # German. Left out on purpose: "Schwanz" is a tail and vulgar slang - the
    # single most likely word in this app to refuse an innocent fox;
    # "Muschi" is a cat's name as often as it is anything else; "schießen" is
    # what you do to a football, so only the compounds that mean shooting a
    # person are listed; "dampfen" is vaping and a steam engine; "Waffe" and
    # "Kanone" are a knight's sword and a star player; "gruselig" is the word
    # the Spooky mood is made of; "Po" and "Popo" are a small child's word for
    # a bottom; "Wunde" is out with the other languages' wounds.
    #
    # German is the one language here that *can* block "Heroin": its word for
    # a brave heroine is "Heldin", so there is no collision to work around.
    # ß is not an accent and NFKD leaves it alone, so anything holding one is
    # written twice, ß and ss - that is a tablet keyboard, not an evasion.
    "sexual_de": [
        "nackt", "nackte", "nackter", "nacktes", "nacktheit", "halbnackt",
        "ausgezogen", "sich ausziehen", "sex", "sexuell", "sexy", "porno",
        "pornografie", "pornographie", "pornografisch", "erotisch", "erotik",
        "brüste", "busen", "nippel", "brustwarze", "brustwarzen", "hintern",
        "arsch", "unterwäsche", "höschen", "tanga", "dessous", "striptease",
        "prostituierte", "nutte", "hure", "ficken", "aufreizend",
        "freizügig", "anzüglich", "oben ohne",
        *_inflect(("nackt", "halbnackt", "erotisch", "aufreizend",
                   "freizügig", "anzüglich"), _DE),
    ],
    "violence_de": [
        "blut", "blutig", "blutige", "blutend", "blutüberströmt",
        "verbluten", "enthaupten", "enthauptet", "enthauptung",
        "verstümmeln", "verstümmelt", "zerstückeln", "zerstückelt", "leiche",
        "leichen", "mord", "ermorden", "ermordet", "mörder", "massaker",
        "gemetzel", "blutbad", "folter", "foltern", "gefoltert", "ausweiden",
        "erhängen", "erhängt", "erstechen", "erstochen", "erschießen",
        "erschiessen", "erschossen", "schießerei", "schiesserei", "töten",
        "gedärme", "eingeweide", "selbstmord", "suizid", "selbstverletzung",
        "magersucht", "magersüchtig", "grausamer tod",
        *_inflect(("blutig", "blutend", "blutüberströmt", "enthauptet",
                   "verstümmelt", "zerstückelt", "ermordet",
                   "gefoltert", "erhängt", "erstochen", "erschossen",
                   "grausam"), _DE),
    ],
    "weapons_de": [
        "pistole", "gewehr", "jagdgewehr", "sturmgewehr", "maschinengewehr",
        "maschinenpistole", "schusswaffe", "schusswaffen", "kalaschnikow",
        "bombe", "bomben", "handgranate", "sprengstoff", "sprengsatz",
        "molotowcocktail", "landmine", "scharfschütze", "dolch",
    ],
    "drugs_de": [
        "droge", "drogen", "drogensüchtig", "kokain", "heroin",
        "crystal meth", "methamphetamin", "spritze", "marihuana",
        "cannabis", "haschisch", "kiffen", "bekifft", "betrunken",
        "besoffen", "alkoholiker", "alkoholikerin", "bier", "wodka",
        "whisky", "zigarette", "zigaretten", "rauchen",
        *_inflect(("betrunken", "besoffen", "bekifft",
                   "drogensüchtig"), _DE),
    ],
    "hate_de": [
        "hakenkreuz", "hitlergruß", "hitlergruss", "rassist", "rassistisch",
        "rassistische beleidigung", "völkermord", "ethnische säuberung",
        "weiße vorherrschaft", "weisse vorherrschaft", "terrorismus",
        "dschihad",
        *_inflect(("rassistisch",), _DE),
    ],
    "scary_de": [
        "dämonisch", "satanisch", "dämon", "besessen", "exorzismus",
        "albtraumhaft", "alptraumhaft", "entsetzlich", "grauenhaft",
        "verstörend", "makaber", "verfluchtes bild",
        *_inflect(("dämonisch", "satanisch", "besessen", "albtraumhaft",
                   "alptraumhaft", "entsetzlich", "grauenhaft",
                   "verstörend", "makaber"), _DE),
    ],

    # Portuguese. Left out on purpose: "rabo" is a tail; "pinto" is a chick,
    # a paintbrush stroke ("eu pinto") and vulgar slang in Brazil; "heroína"
    # is heroin *and* heroine, as in Spanish; "peito" is a chest; "matar" is
    # too broad on its own, so only "assassinar" and its family are listed;
    # "ferido" is out with the other languages' wounded; "arma" alone is a
    # knight's sword, so only "arma de fogo" counts.
    "sexual_pt": [
        "nu", "nua", "nus", "nuas", "nudez", "despido", "despida",
        "despir-se", "seminu", "seminua", "sexo", "sexual", "porno",
        "pornografia", "pornográfico", "erótico", "erótica", "mamas",
        "seios", "mamilo", "mamilos", "bunda", "nádegas", "cuecas", "sutiã",
        "soutien", "roupa interior", "lingerie", "striptease", "prostituta",
        "puta", "foder", "caralho", "cona", "provocante",
        "insinuante", "sem roupa", "em topless",
        *_inflect(("despido", "despida", "seminu", "seminua",
                   "erótico", "erótica"), _PLURAL),
    ],
    "violence_pt": [
        "sangue", "sangrento", "sangrenta", "ensanguentado",
        "ensanguentada", "sangrar", "degolar", "degolado", "decapitar",
        "decapitado", "decapitada", "decapitação", "mutilar", "mutilado",
        "mutilada", "esquartejar", "esquartejado", "cadáver", "cadáveres",
        "assassinar", "assassinato", "assassino", "homicídio", "matança",
        "massacre", "chacina", "torturar", "tortura", "torturado",
        "estripar", "enforcar", "enforcado", "enforcamento", "esfaquear",
        "esfaqueado", "tiroteio", "tripas", "vísceras", "suicídio",
        "suicidar-se", "automutilação", "anorexia", "anoréxica",
        "morte horrível",
        *_inflect(("sangrento", "sangrenta", "ensanguentado",
                   "ensanguentada", "degolado", "decapitado",
                   "decapitada", "mutilado", "mutilada",
                   "esquartejado", "torturado", "enforcado",
                   "esfaqueado"), _PLURAL),
    ],
    "weapons_pt": [
        "pistola", "espingarda", "caçadeira", "revólver", "metralhadora",
        "arma de fogo", "armas de fogo", "kalashnikov", "bomba", "bombas",
        "granada de mao", "granada de mão", "explosivo", "explosivos",
        "cocktail molotov", "coquetel molotov", "mina antipessoal",
        "franco-atirador", "punhal",
    ],
    "drugs_pt": [
        "droga", "drogas", "drogado", "drogada", "drogar-se", "cocaína",
        "metanfetamina", "seringa", "ganza", "marijuana",
        "maconha", "cannabis", "haxixe", "pedrado", "bêbado", "bêbada",
        "embriagado", "alcoólico", "alcoólica", "cerveja", "vodka",
        "uísque", "whisky", "cigarro", "cigarros", "fumar",
        *_inflect(("drogado", "drogada", "bêbado", "bêbada",
                   "embriagado", "alcoólico", "alcoólica",
                   "pedrado"), _PLURAL),
    ],
    "hate_pt": [
        "nazista", "suástica", "supremacista", "supremacia branca",
        "limpeza étnica", "genocídio", "holocausto", "terrorista",
        "terrorismo", "racista", "insulto racista",
    ],
    "scary_pt": [
        "demoníaco", "demoníaca", "satânico", "satânica", "demónio",
        "demônio", "possuído", "possuída", "exorcismo", "de pesadelo",
        "aterrorizante", "horripilante", "perturbador", "perturbadora",
        "macabro", "macabra", "imagem amaldiçoada",
        *_inflect(("demoníaco", "demoníaca", "satânico", "satânica",
                   "possuído", "possuída", "macabro", "macabra"),
                  _PLURAL),
    ],

    # Dutch. Left out on purpose: "poes" is a cat; "string" is a thong in
    # Dutch and a piece of string in English, which is a puppet, a kite and a
    # row of lights; "pik" is a pickaxe and "I pick"; "lijken" is corpses and
    # "to seem", which is far commoner, so only the singular is listed;
    # "ophangen" is hanging up a picture; "schieten" is what you do to a
    # football; "dampen" is vaping and steaming; "wapen" is a coat of arms;
    # "eng" and "griezelig" are the words the Spooky mood is made of;
    # "heroïne" is heroin *and* heroine, as in Spanish and Italian.
    "sexual_nl": [
        "naakt", "naakte", "naaktheid", "bloot", "blote", "halfnaakt",
        "uitgekleed", "zich uitkleden", "seks", "seksueel", "sexy", "porno",
        "pornografie", "pornografisch", "erotisch", "erotiek", "borsten",
        "tepel", "tepels", "kont", "billen", "achterwerk", "onderbroek",
        "ondergoed", "beha", "lingerie", "striptease", "prostituee", "hoer",
        "neuken", "kut", "verleidelijk", "schaars gekleed", "topless",
        *_inflect(("naakt", "bloot", "halfnaakt", "erotisch"), _NL),
    ],
    "violence_nl": [
        "bloed", "bloederig", "bloederige", "bebloed", "bloedend",
        "doodbloeden", "onthoofden", "onthoofd", "onthoofding", "verminken",
        "verminkt", "lijk", "kadaver", "moord", "vermoorden", "vermoord",
        "moordenaar", "bloedbad", "slachting", "massamoord", "martelen",
        "gemarteld", "marteling", "neersteken", "neergestoken",
        "neerschieten", "neergeschoten", "schietpartij", "ingewanden",
        "darmen", "zelfmoord", "zelfdoding", "zelfbeschadiging", "anorexia",
        "gruwelijke dood",
        *_inflect(("bloederig", "bebloed", "bloedend", "verminkt",
                   "onthoofd", "vermoord", "gemarteld",
                   "gruwelijk"), _NL),
    ],
    "weapons_nl": [
        "pistool", "geweer", "jachtgeweer", "machinegeweer",
        "aanvalsgeweer", "vuurwapen", "vuurwapens", "kalasjnikov",
        "bommen", "bomaanslag", "handgranaat", "explosief", "explosieven",
        "molotovcocktail",
        "landmijn", "sluipschutter", "dolk",
    ],
    "drugs_nl": [
        "drugs", "gedrogeerd", "cocaïne", "crystal meth", "methamfetamine",
        "injectiespuit", "wiet", "marihuana", "cannabis", "hasj",
        "stoned", "blowen", "dronken", "bezopen", "alcoholist", "bier",
        "wodka", "whisky", "sigaret", "sigaretten", "roken",
        *_inflect(("dronken", "bezopen", "gedrogeerd"), _NL),
    ],
    "hate_nl": [
        "hakenkruis", "racist", "racistisch", "racistische scheldwoorden",
        "volkerenmoord", "etnische zuivering", "blanke suprematie",
        "terrorisme",
        *_inflect(("racistisch",), _NL),
    ],
    "scary_nl": [
        "demonisch", "satanisch", "demon", "bezeten", "exorcisme",
        "nachtmerrieachtig", "angstaanjagend", "gruwelijk", "verontrustend",
        "macaber", "vervloekte afbeelding",
        *_inflect(("demonisch", "satanisch", "bezeten",
                   "nachtmerrieachtig", "angstaanjagend",
                   "verontrustend", "macaber", "vervloekt"), _NL),
    ],

    "scary": [
        "creepypasta", "jumpscare", "jump scare", "demonic", "satanic",
        "satan", "devil worship", "possessed", "exorcism", "hellscape",
        "nightmare fuel", "disturbing", "horrifying", "terrifying",
        "body horror", "cursed image",
    ],
}

# Substring-match terms: caught even when glued to other characters, for the
# ones where evasion by concatenation is likely.
#
# The condition for being on this list is that no ordinary word in the seven
# languages *contains* the letters, because nothing here is bounded at either
# end. Every entry was checked against the seven languages' own UI text and
# against a list of the words a child actually types; the two glued compounds
# are here rather than below because the guard below would swallow them.
SUBSTRING_TERMS = [
    "nsfw", "porn", "hentai", "lolicon", "shotacon", "masturbat",
    "pedophil", "paedophil", "bestiality", "zoophil", "incest", "necrophil",
    "gangrape", "daterape",
]

# "rape" was on the list above and does not meet that condition: four letters
# that sit inside "grape", "trapeze", "scrape", "drape", "serape" and
# "therapeutic". A fox eating grapes and a girl on a trapeze were both
# refused, live - and a refusal is not a shrug here, it quotes their words to a
# parent and can shut the factory for the rest of the day.
#
# Moving it to BLOCKLIST would have been the other mistake: `\b` boundaries
# drop exactly the padding this list exists to catch. So it is still matched
# as a substring, with two guards:
#
#   * in front, the single letters that *begin* one of those innocent hosts -
#     g(rape), t(rapeze), s-c(rape), d(rape), th-e(rapeutic), s-a(rape) - so
#     any word ending in one of them is not a match. That is why "gangrape"
#     and "daterape" are spelled out above.
#   * behind, a real inflection and then a letter boundary, so "rapeseed" and
#     Dutch "rapen" (to gather) pass while "raped" and "rapist" do not.
#
# Padding by anything that is not a letter is untouched by either guard:
# "rape69", "9rape" and "r-a-p-e" (which `normalize` glues back together) are
# all still caught. What is given up is a whole word glued on the front in
# letters, which is the price of not refusing the fruit bowl.
_RAPE_RE = (
    r"(?<!g)(?<!t)(?<!c)(?<!d)(?<!e)(?<!a)"
    r"rap(?:e|es|ed|er|ers|ing|ist|ists)(?![^\W\d_])"
)


# Terms matched as prefixes, so inflections are caught: "mutilat" also hits
# "mutilated" / "mutilating". Everything else gets a closing word boundary so
# short words don't swallow innocent ones ("ass" must not match "assassin").
STEMS = {
    "masturbat", "mutilat", "dismember", "decapitat", "disembowel",
    "murder", "torture", "brutal", "stabbing", "behead", "bleeding",
}


def strip_accents(text: str) -> str:
    """é -> e, ç -> c. Typing French without the accents is normal on a tablet
    keyboard, and it must not be a way past the list."""
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )


# Characters that are not there. A zero-width space between two letters is
# the same word on the screen and to the model, and was a different string
# here: "nu<U+200B>de" walked past the whole filter, which is the only filter
# there is. They are taken by Unicode *category* rather than by a hand-listed
# set, because the set is long and grows - Cf alone is U+200B-200D, U+2060,
# U+FEFF, the soft hyphen, the bidi and interlinear controls and the Arabic
# ones - and a list that goes out of date reopens the hole quietly.
#
# Cs (unpaired surrogates) and Co (private use) go with them: nothing legible
# is written in either. So do the control characters, but only the ones that
# are not whitespace - a newline has to stay a space, or two words on two
# lines glue into a third that nobody typed.
_UNSEEN = frozenset({"Cf", "Cs", "Co"})
_MARKS = frozenset({"Mn", "Me"})


def strip_invisible(text: str) -> str:
    """Drop what cannot be seen, so a word split by nothing is still a word.

    Combining marks are deliberately left in place: `strip_accents` needs them
    to fold "é" into "e", and `normalize` drops whatever is left over once it
    has. That also lets the raw pass put a decomposed accent back together.
    """
    out = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in _UNSEEN or (cat == "Cc" and not ch.isspace()):
            continue
        out.append(ch)
    return "".join(out)


# Homoglyphs. NFKD already folds the fullwidth and the mathematical alphabets
# - "ｎｕｄｅ" and its bold and script cousins all come out as the letters they
# are drawn as - but nothing in Unicode maps a Cyrillic "о" onto a Latin "o":
# they are different letters that happen to be drawn identically. All seven
# languages here are written in the Latin alphabet, so folding the handful
# that are genuinely indistinguishable costs nothing that they can type and
# closes the substitution. Mapped before lowercasing, so the capitals that
# only look alike as capitals ("Н", "Μ") are folded too.
_CONFUSABLES = str.maketrans({
    # Cyrillic
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "У": "Y", "Х": "X", "І": "I", "Ј": "J",
    "Ѕ": "S", "Ԁ": "D", "Ԛ": "Q", "Ԝ": "W", "Ѵ": "V",
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "һ": "h", "ӏ": "l", "ԛ": "q",
    "ԝ": "w", "ѵ": "v",
    # Greek
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p",
    "τ": "t", "υ": "u", "χ": "x",
    # Latin letters drawn as other Latin letters
    "ı": "i", "ȷ": "j", "ɑ": "a", "ɡ": "g", "ɩ": "i", "ɪ": "i", "ʟ": "l",
    "ʏ": "y", "ʜ": "h", "ᴏ": "o", "ᴜ": "u", "ᴇ": "e", "ᴀ": "a",
})


def _compile(terms):
    # Multi-word terms tolerate any whitespace run between the words.
    parts = []
    for t in sorted(terms, key=len, reverse=True):
        esc = r"\s+".join(re.escape(w) for w in t.split())
        parts.append(rf"\b{esc}" if t in STEMS else rf"\b{esc}\b")
    return re.compile("|".join(parts), re.IGNORECASE)


# Each category is compiled twice: once as written, and once with the accents
# stripped, so "epee" is caught by the same entry as "épée". Terms whose folded
# form is an ordinary English word are matched only in the raw pass - see the
# note on the French lists above.
#
# "soûl" folds to "soul", which is a word about music and about people, and
# "dämon" folds to "damon", which is somebody's name. Both are still caught as
# written; only the folded pass skips them. German loses least by it: a German
# keyboard without umlauts writes "ae", not "a".
_COLLIDES_WHEN_FOLDED = {"héroïne", "soûl", "dämon"}


def _folded(terms):
    return [strip_accents(t) for t in terms if t not in _COLLIDES_WHEN_FOLDED]


# Every list is matched against every prompt, whatever page they are on - and
# that is safe for a word of any length except a very short one, because a
# two-letter word in one language is an everyday word in another. French and
# Portuguese both list "nu"; "nu" is Dutch for "now", so "teken nu een kat" -
# draw a cat now - was refused as sexual content, in one of the seven
# languages the page ships in. "cul" and "kut" are the same shape of risk.
#
# So a *short* entry in a language list is matched only when that language is
# the one on the screen. The short English entries are not scoped: English is
# what the models are prompted in and what they are most likely to reach for,
# so "sex", "ass", "gun" and "cp" stay on for everybody, as they always were.
# Nothing longer than this is scoped - four letters is enough to be a word
# only its own language has, and the collisions at that length ("bom",
# "pila", "porro") were kept off the lists by hand instead.
SHORT_TERM_CHARS = 3

# Three letters is the rule; these two are four and went through the same door,
# found by running each language's short entries against ordinary sentences in
# the other six. German "mord" (a murder) is French for "bites", so "le chien
# mord un os" - the dog bites a bone - was refused as violence; Italian "figa"
# is vulgar there and a little wooden good-luck charm in Portuguese. Both are
# still caught in their own language, which is the only language either word
# means what the list thinks it means.
ALSO_SCOPED = {("violence_de", "mord"), ("sexual_it", "figa")}


def _language_of(category: str) -> str:
    """"sexual_de" -> "de". The English categories have no suffix."""
    head, _, tail = category.rpartition("_")
    return tail if head and tail in i18n.LANGS else "en"


def _short(category: str, term: str) -> bool:
    """Is this entry too short to be trusted outside its own language?"""
    return (_language_of(category) != "en"
            and " " not in term
            and (len(term) <= SHORT_TERM_CHARS
                 or (category, term) in ALSO_SCOPED))


def _both_ways(terms):
    """The terms as written, plus their accent-folded forms."""
    return set(terms) | set(_folded(terms))


_CATEGORY_RE = {
    cat: _compile(_both_ways([t for t in terms if not _short(cat, t)]))
    for cat, terms in BLOCKLIST.items()
}

# The short entries, held back from the pass above and matched only against a
# prompt written by somebody reading that language.
_SHORT_RE = {
    cat: _compile(_both_ways(short))
    for cat, terms in BLOCKLIST.items()
    if (short := [t for t in terms if _short(cat, t)])
}
_SUBSTRING_RE = re.compile(
    "|".join([*(re.escape(t) for t in SUBSTRING_TERMS), _RAPE_RE]),
    re.IGNORECASE,
)

# Collapse common letter-substitution evasion (l33t speak) before matching.
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})

MAX_PROMPT_CHARS = 1500

FRIENDLY_MESSAGE = (
    "Let's pick something else! That idea isn't one we can make here. "
    "Try describing a place, an animal, a character, or a cool adventure."
)

FRIENDLY_MESSAGE_FR = (
    "Choisissons autre chose ! Cette idée-là, on ne peut pas la faire ici. "
    "Essaie un endroit, un animal, un personnage, ou une belle aventure."
)

# The same sentence in the rest of them. English stays the source of truth
# here, rather than moving into i18n.py with everything else they read,
# because this string is older than the language switch and is quoted in the
# tests and the notes; the six beside it are the same sentence, not six more
# rules.
FRIENDLY_MESSAGES = {
    "fr": FRIENDLY_MESSAGE_FR,
    "es": (
        "¡Vamos a elegir otra cosa! Esa idea no la podemos hacer aquí. "
        "Prueba con un lugar, un animal, un personaje o una aventura genial."
    ),
    "it": (
        "Scegliamo qualcos'altro! Quell'idea qui non possiamo farla. "
        "Prova con un posto, un animale, un personaggio o una bella avventura."
    ),
    "de": (
        "Such dir etwas anderes aus! Diese Idee können wir hier nicht machen. "
        "Probier einen Ort, ein Tier, eine Figur oder ein tolles Abenteuer."
    ),
    "pt": (
        "Vamos escolher outra coisa! Essa ideia não a podemos fazer aqui. "
        "Experimenta um lugar, um animal, uma personagem ou uma bela aventura."
    ),
    "nl": (
        "Laten we iets anders kiezen! Dat idee kunnen we hier niet maken. "
        "Probeer een plek, een dier, een figuur of een spannend avontuur."
    ),
}


def friendly_message() -> str:
    """The refusal, in the language they read."""
    return FRIENDLY_MESSAGES.get(i18n.lang(), FRIENDLY_MESSAGE)


def _screen_language() -> str:
    """Which language is on the screen, for the short terms in `_SHORT_RE`.

    Wrapped, because that answer comes from a setting and the filter must not
    fall over - or fail open - because a setting could not be read. Anything
    unreadable is English, which is the list that is never scoped anyway.
    """
    try:
        return i18n.lang()
    except Exception:
        return "en"


def in_every_language(*bases: str) -> tuple[str, ...]:
    """("sexual",) -> every language's copy of that category.

    The chat tab and the lyric check each run a *narrower* list than a picture
    prompt does, and each named its categories by hand. With one other
    language that was two strings; with six it would be seven, and the way
    that goes wrong is somebody adding a language and leaving the chat
    checking English only. The names are built from the list itself instead.
    """
    return tuple(cat for cat in BLOCKLIST if base_of(cat) in bases)


def base_of(category: str) -> str:
    """"sexual_de" -> "sexual". The English categories have no suffix."""
    head, _, tail = category.rpartition("_")
    return head if head and tail in i18n.LANGS else category


def normalize(text: str) -> str:
    """Fold the tricks people use to slip words past a blocklist."""
    t = strip_invisible(text).translate(_CONFUSABLES)
    t = strip_accents(t.lower())
    # NFKD leaves behind the marks that carry no combining class of their own
    # - variation selectors, enclosing keycaps - and they split a word just as
    # well as a zero-width space does.
    t = "".join(ch for ch in t if unicodedata.category(ch) not in _MARKS)
    t = t.translate(_LEET)
    # Strip characters used to break up words: p-o-r-n, p.o.r.n, p_o_r_n
    t = re.sub(r"[\-_.*+~^|/\\]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def candidates(text: str) -> tuple[str, str]:
    """The two strings every pass is run against: the text as written, and the
    de-obfuscated version.

    The raw one keeps its accents - see `_COLLIDES_WHEN_FOLDED` - so it gets
    its own cleaning rather than none: the invisible characters come out, and
    NFC puts a combining accent typed as its own character back together, so
    an accented entry matches however a tablet keyboard spelled it.
    """
    return unicodedata.normalize("NFC", strip_invisible(text)), normalize(text)


def check_categories(text: str, categories=None) -> tuple[bool, str]:
    """(ok, category) for some of the blocklist, or all of it.

    **This is the loop.** `check_prompt` below is this function plus the
    friendly wording and the length check, and the two callers that want a
    *narrower* list - the chat tab and the lyric check, which leave out the
    categories a conversation can innocently touch - pass their category names
    in rather than writing the loop out again. They did write it out, twice,
    and both copies then sat unchanged through two changes to this file: they
    missed the language-scoped short terms entirely. One loop, three callers,
    and the next thing added here reaches all of them.

    `categories=None` means the whole blocklist. The substring pass runs
    whatever the categories, because nothing on that list is innocent in any
    context and it is the one that catches evasion by gluing.
    """
    wanted = None if categories is None else set(categories)
    screen = _screen_language()
    for candidate in candidates(text):
        if _SUBSTRING_RE.search(candidate):
            return False, "blocked"
        for category, pattern in _CATEGORY_RE.items():
            if wanted is not None and category not in wanted:
                continue
            if pattern.search(candidate):
                return False, category
        for category, pattern in _SHORT_RE.items():
            if wanted is not None and category not in wanted:
                continue
            if _language_of(category) == screen and pattern.search(candidate):
                return False, category
    return True, ""


def check_prompt(text: str):
    """Return (ok, message, category). `ok=False` means do not generate."""
    if not text or not text.strip():
        return False, i18n.t("Type something you'd like to make first!"), "empty"

    if len(text) > MAX_PROMPT_CHARS:
        return False, i18n.t("That's a bit long! Keep it under {max} characters.",
                             max=MAX_PROMPT_CHARS), "length"

    ok, category = check_categories(text)
    if not ok:
        return False, friendly_message(), category

    return True, "", ""


# --- Layer 2: hidden negative prompts --------------------------------------

_SHARED_NEGATIVE = (
    "nsfw, nude, nudity, naked, topless, bottomless, exposed breasts, "
    "exposed genitals, nipples, areola, cleavage, underwear, lingerie, "
    "bikini, swimsuit, skimpy clothing, revealing clothing, see-through "
    "clothing, wet clothing, sexual, sexualized, seductive, sensual, erotic, "
    "suggestive pose, provocative pose, fetish, bondage, porn, hentai, "
    "child in revealing clothing, sexualized minor, "
    "gore, blood, bloody, wounds, injury, mutilation, dismemberment, "
    "decapitation, corpse, dead body, torture, violence, brutality, "
    "weapons, gun, rifle, knife threatening, explosion harming people, "
    "self-harm, suicide, drugs, drug paraphernalia, syringe, cigarette, "
    "smoking, alcohol, "
    "nazi symbols, swastika, hate symbols, slurs, "
    "disturbing imagery, body horror, creepy distorted faces, demonic, "
    "satanic imagery, nightmare imagery, "
    "deformed, disfigured, extra limbs, extra fingers, mutated hands, "
    "malformed anatomy, watermark, signature, text artifacts, jpeg artifacts, "
    "lowres, blurry, low quality, worst quality"
)

NEGATIVE_IMAGE = _SHARED_NEGATIVE

# The video workflows shipped with an aesthetic negative; keep it and append
# the safety terms.
NEGATIVE_VIDEO = (
    "pc game, console game, video game, cartoon, childish, ugly, "
    + _SHARED_NEGATIVE
    + ", flickering, jittery motion, warped faces, melting features"
)
