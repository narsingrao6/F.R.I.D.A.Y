"""
Local (offline) language + style detection for F.R.I.D.A.Y.

Recognises: English, Telugu, Hindi, Tenglish, Hinglish,
Romanized Telugu and Romanized Hindi.

Design rules that this module enforces:

  * Whisper's own language label is NEVER the final truth. It is only
    accepted as a tie-breaker (`analyze(text, hint=...)`).
  * Spelling is not trusted either: every word is also matched through a
    phonetic normalizer, so "kaavaali", "kavali" and "kawali" are one
    word, and so are "chaahiye" and "chahiye".
  * Devanagari is transliterated back to Latin and re-scored, because
    Whisper often writes Telugu speech in Devanagari. That is how
    "नाकु ओका हेल्प कावाली" is still recognised as Telugu.
  * Words that also exist in English are ignored, so a single common
    word cannot flip an English sentence into Telugu or Hindi.
  * Words shared by Telugu and Hindi carry no discriminating signal and
    are dropped from both lexicons automatically.
  * `choose()` arbitrates between several Whisper transcripts of the
    same audio - that is what fixes wrong-script and translated
    transcripts without a single extra network call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------- constants

TELUGU_RANGE = re.compile(r"[ఀ-౿]")
DEVANAGARI_RANGE = re.compile(r"[ऀ-ॿ]")

_LATIN_TOKEN = re.compile(r"[a-z]+")
_DEVA_TOKEN = re.compile(r"[ऀ-ॿ]+")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)

STRONG = 3.0
MEDIUM = 2.0
# Morphology (word endings) can support a decision but never make one.
WEAK = 1.0

# A winner needs at least one strong cue (or two medium ones)...
MIN_WEIGHT = 3.0
# ...must beat the other language by this much...
MIN_MARGIN = 2.0
# ...and the cues must not be drowned in a long English sentence.
MIN_DENSITY = 0.12
# Unless the evidence is simply overwhelming.
STRONG_WEIGHT = 6.0

# Enough native characters to trust the script outright.
MIN_SCRIPT_CHARS = 3
MIN_SCRIPT_RATIO = 0.18

# Phonetic (spelling-tolerant) matching is only allowed for words this
# long, so short English words cannot collide with an Indic entry.
MIN_NORM_LEN = 4

# ---------------------------------------------------------------- English

# Words that must never be counted as Telugu/Hindi evidence, because an
# English speaker uses them constantly ("the" used to make every English
# sentence look like Hindi).
ENGLISH_GUARD = {
    "the", "and", "are", "you", "your", "yours", "our", "his", "her",
    "him", "she", "they", "them", "their", "was", "were", "has", "have",
    "had", "will", "would", "shall", "should", "can", "could", "may",
    "might", "must", "this", "that", "these", "those", "there", "here",
    "what", "when", "where", "who", "whom", "whose", "how", "why",
    "which", "for", "with", "from", "into", "onto", "about", "after",
    "before", "than", "then", "also", "just", "only", "very", "not",
    "now", "out", "off", "over", "under", "again", "any", "all", "some",
    "more", "most", "less", "many", "much", "few", "one", "two", "three",
    "own", "same", "such", "both", "each", "other", "another",
    "main", "mere", "ate", "art", "ant", "end", "eye", "ear",
    "man", "men", "way", "say", "see", "saw", "get", "got", "let", "put",
    "run", "ran", "sit", "set", "top", "tap", "car", "cat", "dog", "day",
    "new", "old", "big", "bad", "yes", "yeah", "yep", "nope", "okay",
    "please", "thanks", "thank", "sorry", "hello", "hey", "friday",
    "time", "date", "help", "tell", "make", "made", "take", "give",
    "know", "need", "want", "like", "look", "come", "came", "went",
    "good", "great", "fine", "nice", "well", "sure", "right", "wrong",
    "today", "tomorrow", "yesterday", "morning", "night", "week",
    "month", "year", "hour", "minute", "second", "people", "thing",
    "kind", "sort", "part", "lot", "bit", "still", "even", "ever",
    "never", "always", "because", "while", "until", "since", "though",
    # Long English words whose phonetic skeleton could otherwise land on
    # an Indic entry once spelling is normalised away.
    "challenge", "challenges", "challenging", "revenge", "avenge",
    "arrange", "orange", "manage", "message", "package", "language",
    "bass", "base", "case", "cause", "chase", "phase", "raise",
    "praise", "waste", "waist", "wait", "weight", "eight", "sale",
    "sail", "mail", "email", "male", "tale", "tail", "detail", "daily",
    "value", "venue", "avenue", "movie", "money", "moody", "media",
    "maybe",
}

# Used only to decide "is this code-mixed?" (Tenglish / Hinglish).
ENGLISH_MARKERS = ENGLISH_GUARD | {
    "weather", "college", "school", "office", "meeting", "class",
    "exam", "phone", "music", "song", "play", "email", "message",
    "call", "work", "computer", "laptop", "internet", "whatsapp",
    "youtube", "google", "boss", "battery", "volume", "reminder",
    "alarm", "news", "temperature", "traffic", "movie", "video",
    "photo", "file", "code", "project", "assignment", "bus", "train",
    "doctor", "hospital", "market", "shop", "money", "birthday",
    "breakfast", "lunch", "dinner", "coffee", "tea", "restaurant",
    "ticket", "flight", "bank", "account", "password", "download",
    "upload", "install", "update", "battery", "charger", "wifi",
    "screen", "camera", "notes", "note", "list", "calendar", "event",
    "holiday", "leave", "salary", "interview", "resume", "friend",
    "family", "cricket", "match", "score", "game", "level", "server",
    "python", "java", "error", "bug", "test", "report", "presentation",
}

# The wake word is not evidence of code-mixing - she is always called
# "Friday", whatever language follows.
_WAKE_WORDS = {"friday", "fryday", "freeday", "fridays"}

MIX_MARKERS = ENGLISH_MARKERS - _WAKE_WORDS

# ----------------------------------------------------------------- Telugu

# Distinctive Romanized Telugu. One of these is enough to decide.
TELUGU_STRONG = {
    "naku", "naaku", "naaaku", "nenu", "nuvvu", "neevu", "nuvu",
    "meeru", "manam", "vaadu", "vallu", "vaallu", "atanu", "aame",
    "nannu", "naadi", "maaku", "meeku", "memu", "manaki", "thanu",
    "kavali", "kaavali", "kaavaali", "kavalani", "kaavalani", "kavala",
    "cheppu", "cheppandi", "chepthanu", "cheptha", "cheppara",
    "cheppava", "cheppali", "cheppagalara", "chebutunna",
    "enti", "emiti", "emiiti", "endhuku", "enduku", "eppudu",
    "ekkada", "ikkada", "akkada", "evaru", "entha", "ento", "enno",
    "ivala", "ivvala", "ivaala", "repu", "ninna", "nedu", "monna",
    "vellali", "vellala", "vellalsina", "veldam", "vellandi", "vellanu",
    "veltunna", "veltunnanu", "vellipoya", "vellava",
    "chestunna", "chestunnav", "chestunnaru", "chesanu", "chesav",
    "chesavu", "chestha", "chesthanu", "cheyyali", "cheyali", "cheyyandi",
    "cheyyi", "cheyyu", "chey", "cheyi", "cheddam", "chesukunna",
    "avunu", "avunandi", "kaadu", "kadhu", "ledu", "ledhu", "levu",
    "undi", "undhi", "undha", "unnanu", "unnav", "unnavu", "unnaru",
    "unnadu", "vundi", "vunnanu",
    "bagunnara", "baagunnara", "bagunnava", "bagundi", "baagundi",
    "bagoledu", "baaledu",
    "idhi", "adhi", "edhi", "ippudu", "appudu", "tarvatha", "taruvata",
    "konchem", "koncham", "koddiga", "gurthu", "gurthundi", "gnapakam",
    "kalisi", "kotha", "chinna", "pedda", "thondaraga", "mellaga",
    "vaddu", "choodu", "chudu", "chuddam", "chudandi", "vinu", "vinnanu",
    "randi", "podam", "telusu", "telisa", "telusa", "teliyadu",
    "teliyada", "telidu", "artham", "ardham", "kosam", "gurinchi",
    "inka", "inkaa", "kani", "gani", "ante", "antey", "anta", "anthaa",
    "aithe", "aite", "ayite", "ayina", "ayyo", "ammo", "abbo", "avunaa",
    "ekkuva", "thakkuva", "ekkuvaga", "sepu", "peru", "sunna",
    "okka", "oka", "okati", "rendu", "moodu", "naalugu", "aidu",
    "emaindi", "emandi", "emo", "kudaa", "kooda", "emaina", "edaina",
    "evaraina", "eppatiki", "sahayam", "sahaayam", "vatavaranam",
    "vaatavaranam", "samayam", "samayaniki", "gantalaku", "nimishalu",
    "pettu", "pettandi", "pettuko", "teesuko", "teeyi", "aapu", "aagu",
    "ivvu", "ivvandi", "pampu", "pampandi", "adagu", "adigandi",
    "vachindi", "vachhindi", "vastunna", "vasthunna", "vastha",
    "nijamga", "nijam", "asalu", "sarigga", "motham", "avasaram",
    "marchipoya", "matladu", "matladutunna", "matladtunna",
    "ayya", "amma", "anna", "chusko", "paduko", "rara", "povali", "podham",
    # App/action command verbs — Telugu-exclusive
    "thiyu", "tiyyandi", "therivu", "aapeyyi", "aapeyi",
    "chesuko", "cheseyyi", "pampinchu", "choostu",
    "raayyi", "chaduvvu", "vinnu", "vinandi", "cheppara",
}

# Suggestive but not decisive on its own.
TELUGU_MEDIUM = {
    "mee", "mari", "baga", "bagane", "mundu", "venaka", "pakka",
    "chala", "chaala", "sare", "sarle", "mana", "ela", "elaa",
    "ammayi", "abbayi", "akka", "nanna", "thammudu",
    "pilla", "pani", "vellipo", "daggara", "dooram", "lopala",
    "bayata", "pakkana", "meeda", "kinda", "roju", "rojulu",
    "varam", "nela", "gantalu", "bhale", "matram", "valla", "vaadi",
}

# Word endings that only Telugu produces. They add supporting weight for
# words the lexicon has never seen, e.g. "vinipinchamantunnanu".
TELUGU_SUFFIX = (
    "tunnanu", "tunnaru", "tunnadu", "tunnavu", "tunnaam", "unnanu",
    "aalani", "alanukunna", "chesanu", "chestunna", "cheyyali",
    "ppudu", "nduku", "ledhu", "kavali", "gaaru", "andi",
)

# ------------------------------------------------------------------ Hindi

HINDI_STRONG = {
    "mujhe", "mujhko", "mujhse", "mujhpe", "hum", "hume", "humein",
    "hamein", "hamko", "humko", "hamara", "humara", "hamari",
    "tum", "tumhe", "tumhein", "tumko", "tumhara", "tumhari",
    "aap", "aapko", "aapka", "aapki", "aapse", "aapne",
    "kya", "kyun", "kyon", "kyu", "kyunki", "kyonki",
    "kaise", "kaisa", "kaisi", "kaha", "kahan", "kaun", "kaunsa",
    "kitna", "kitni", "kitne", "kabhi",
    "chahiye", "chaahiye", "chahiya", "chahta", "chahti", "chahte",
    "batao", "bataao", "bataiye", "bataye", "batana", "bata", "batado",
    "karna", "karni", "karne", "karenge", "karunga", "karungi",
    "karta", "karti", "karte", "karo", "kariye", "kijiye", "kiya",
    "hoga", "hogi", "honge", "hona", "hota", "hoti", "hote", "hokar",
    "raha", "rahi", "rahe", "rahega", "rahegi", "rahunga",
    "gaya", "gayi", "gaye", "jaana", "jana", "jaunga", "jaoge",
    "aaunga", "aaoge", "aaya", "aayi", "aaye", "aana",
    "nahi", "nahin", "nahee", "haan", "accha", "acha", "achha",
    "achcha", "badhiya", "bekar", "theek", "thik", "bilkul",
    "zaroor", "jaroor", "matlab", "shayad", "zaroorat", "zarurat",
    "samajh", "samjha", "samajhta", "bahut", "bohot", "bahot",
    "thoda", "thodi", "jaldi", "abhi", "parso", "kripya", "zara",
    "yahan", "wahan", "vahan", "idhar", "udhar", "kahin",
    "kuch", "kuchh", "sabhi", "phir", "fir", "lekin", "magar",
    "aur", "agar", "isliye", "warna", "toh", "bhi", "dobara",
    "dena", "lena", "dedo", "lelo", "dijiye", "diya", "dikhao",
    "dikhaao", "sunao", "bajao", "bajaao", "chalao", "kholo", "khol", "kholna", "chalu",
    "bhejo", "bhej", "padho", "likho", "karke", "uthna", "utho",
    "chalo", "chaliye", "kaam", "baat", "baatein", "madad",
    "shukriya", "dhanyavaad", "namaste", "yaar", "bhai", "arre",
    "waqt", "samay", "khana", "peena", "suno", "suniye", "dekho",
    "dekhiye", "bola", "boli", "bolo", "milega", "milegi", "chahe",
    "hain", "hoon", "hun", "hai", "yeh", "woh", "jaisa", "jaise",
    "mausam", "tapman", "garmi", "sardi", "barish", "dhoop",
    "khabar", "samachar", "paise", "rupaye", "ghante", "baje",
    "hafta", "mahina", "saal", "tarikh", "pichle", "agla", "agle",
    "wapas", "phirse", "turant", "mushkil", "aasan", "asaan",
    # App/action command verbs — Hindi-exclusive
    "khol", "kholna", "kholke", "khulwa", "chalu", "chalana",
    "hatao", "hataiye", "dikhana", "dikha", "sunna", "sunaiye",
    "band", "bandh", "rokna", "roko", "rukna", "ruko",
}

HINDI_MEDIUM = {
    "tha", "thi", "thay", "mein", "meri", "apna", "apne",
    "apni", "uska", "iska", "unka", "sab", "kal", "par", "bas",
    "wala", "wali", "wale", "saath", "paas", "liye", "bina", "zyada",
    "kar", "din", "raat", "subah", "subha", "shaam", "ghar", "sahi",
    "galat", "aaj", "kitab", "gaana", "gana", "pyaar", "dil",
    # deliberately listed in both lexicons so they cancel out:
    "chala", "sare", "mana", "pani",
}

HINDI_SUFFIX = (
    "aunga", "aungi", "oonga", "unga", "ungi", "iyega", "chuka",
    "kariye", "kijiye", "rahaa", "wale", "walon", "taahai", "hunga",
)

# ------------------------------------------------- Devanagari safety net
#
# Whisper often hears Telugu and writes it in Devanagari (because it
# labelled the audio as Hindi). Devanagari is therefore transliterated
# back to Latin and re-scored; these explicit cues are only the first,
# cheapest check.

DEVANAGARI_TELUGU_CUES = {
    "नाकु", "नाकू", "नाको", "नेनु", "नुव्वु", "मीरु", "ओका", "ओक्का",
    "कावालि", "कावाली", "कावली", "एंटि", "एंटी", "एमिटि", "एमिटी",
    "चेप्पु", "चेप्पू", "चेप्पंडि", "इवाला", "इव्वाला", "इवाल", "रेपु",
    "वेल्लालि", "वेल्लाली", "वैलाला", "विल्लाला", "अवुनु", "लेदु",
    "लेदू", "उंदि", "उंधि", "उंदी", "इंदि", "एंदुकु", "एक्कड",
    "इक्कड", "अक्कड", "चेय्याली", "बागुन्नारा", "कोंचेम", "तेलुसु",
    "एप्पुडु", "इप्पुडु", "इपुडु", "सहायम", "समयम्", "एंता", "एंताा",
    "पिट्टू", "पेट्टु", "एला", "वातावरणं", "उकस", "उकर",
}

DEVANAGARI_HINDI_CUES = {
    "मुझे", "मुझको", "चाहिए", "क्या", "कैसे", "कैसा", "कैसी", "है",
    "हैं", "हूँ", "हूं", "हो", "था", "थी", "थे", "आज", "कल", "अभी",
    "नहीं", "हाँ", "हां", "मदद", "बताओ", "बताइये", "करना", "मैं",
    "आप", "आपको", "आपकी", "आपका", "तुम", "हम", "रहा", "रही", "रहे",
    "क्यों", "कहाँ", "कहां", "कब", "कौन", "कितना", "बहुत", "थोड़ा",
    "अच्छा", "ठीक", "और", "लेकिन", "अगर", "नमस्ते", "धन्यवाद",
    "शुक्रिया", "जाना", "काम", "बात", "समय", "एक", "मौसम", "हुआ",
    "मेरा", "मेरी", "जल्दी", "उठना", "सुबह", "बजे", "दिखाओ",
    "सुनाओ", "बजाओ", "याद", "टाइम", "बताओं",
}

# ------------------------------------------------------ phonetic matching
#
# Whisper spells Romanized Indic words differently every time
# ("kaavaali" / "kavali" / "kawali"). Both the lexicons and the incoming
# words are reduced to the same rough phonetic skeleton so that spelling
# stops mattering. The rules are applied in order.

_NORM_RULES = (
    ("chh", "ch"), ("shh", "sh"),
    ("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"),
    ("ai", "e"), ("ay", "e"), ("ei", "e"), ("au", "o"), ("ou", "o"),
    ("ow", "o"),
    ("dh", "d"), ("th", "t"), ("bh", "b"), ("gh", "g"), ("jh", "j"),
    ("kh", "k"), ("ph", "f"), ("sh", "s"),
    ("w", "v"), ("z", "j"), ("q", "k"), ("x", "ks"), ("y", "i"),
)

_DOUBLE = re.compile(r"(.)\1+")


def normalize_word(word: str) -> str:
    """Spelling-independent skeleton of a Romanized word."""
    text = (word or "").lower()

    for source, target in _NORM_RULES:
        text = text.replace(source, target)

    # "vellala" and "velala" are the same word.
    text = _DOUBLE.sub(r"\1", text)

    # Trailing breath consonants carry no information ("subah" = "suba").
    if len(text) > 3 and text.endswith("h"):
        text = text[:-1]

    return text


# English words that must not be reachable through the phonetic path.
_ENGLISH_NORM = {
    normalize_word(word)
    for word in (ENGLISH_MARKERS | {
        "china", "marry", "married", "marriage", "merry", "mood",
        "ammo", "aid", "aide", "sauna", "canny", "quota", "vinyl",
        "level", "salt", "boat", "bait", "cease", "anti", "aunt",
    })
}

def _build_lexicon(strong, medium, other):
    """Weighted lexicon, minus English collisions and cross-language noise."""
    lexicon = {}

    for word in medium:
        lexicon[word] = MEDIUM

    for word in strong:
        lexicon[word] = STRONG

    return {
        word: weight
        for word, weight in lexicon.items()
        if len(word) > 2
        and word not in ENGLISH_GUARD
        and word not in other
    }


def _build_normalized(lexicon):
    """Phonetic view of a lexicon, keeping the strongest weight per key."""
    normalized = {}

    for word, weight in lexicon.items():
        if len(word) < MIN_NORM_LEN:
            continue

        key = normalize_word(word)

        if len(key) < 3 or key in _ENGLISH_NORM:
            continue

        normalized[key] = max(normalized.get(key, 0.0), weight)

    return normalized


_TELUGU_ALL = TELUGU_STRONG | TELUGU_MEDIUM
_HINDI_ALL = HINDI_STRONG | HINDI_MEDIUM

TELUGU_LEXICON = _build_lexicon(TELUGU_STRONG, TELUGU_MEDIUM, _HINDI_ALL)
HINDI_LEXICON = _build_lexicon(HINDI_STRONG, HINDI_MEDIUM, _TELUGU_ALL)

_TELUGU_NORM = _build_normalized(TELUGU_LEXICON)
_HINDI_NORM = _build_normalized(HINDI_LEXICON)

# A skeleton both languages share tells us nothing about which one it is.
_SHARED_NORM = set(_TELUGU_NORM) & set(_HINDI_NORM)

TELUGU_NORMALIZED = {k: v for k, v in _TELUGU_NORM.items() if k not in _SHARED_NORM}
HINDI_NORMALIZED = {k: v for k, v in _HINDI_NORM.items() if k not in _SHARED_NORM}

# -------------------------------------------------- Devanagari -> Latin
#
# Rough but deterministic transliteration. Its only job is to turn
# Devanagari back into something the Romanized lexicons can score, so
# Telugu that Whisper wrote in Devanagari is still recognised as Telugu.

_DEVA_VOWEL = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ii", "उ": "u", "ऊ": "uu",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o",
    "ऍ": "e", "ऎ": "e", "ऒ": "o",
}

_DEVA_MATRA = {
    "ा": "aa", "ि": "i", "ी": "ii", "ु": "u", "ू": "uu", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e",
    "ॆ": "e", "ॊ": "o",
}

_DEVA_CONSONANT = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "ळ": "l",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "r",
    "ढ़": "rh", "फ़": "f", "य़": "y",
}

_NUKTA = "़"
_VIRAMA = "्"
_NASAL = ("ं", "ँ", "ः")

_DEVA_DIGIT = {
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}

def deva_to_latin(text: str) -> str:
    """Transliterate one Devanagari word into Latin letters."""
    out = []
    index = 0
    length = len(text)
    inherent = False

    while index < length:
        char = text[index]

        if char in _DEVA_CONSONANT:
            out.append(_DEVA_CONSONANT[char])
            index += 1
            inherent = False

            if index < length and text[index] == _NUKTA:
                index += 1

            if index < length and text[index] == _VIRAMA:
                index += 1

            elif index < length and text[index] in _DEVA_MATRA:
                out.append(_DEVA_MATRA[text[index]])
                index += 1

            else:
                # Every bare consonant carries a silent "a".
                out.append("a")
                inherent = True

            while index < length and text[index] in _NASAL:
                out.append("n" if text[index] != "ः" else "h")
                index += 1
                inherent = False

            continue

        if char in _DEVA_VOWEL:
            out.append(_DEVA_VOWEL[char])
            index += 1
            inherent = False

            while index < length and text[index] in _NASAL:
                out.append("n" if text[index] != "ः" else "h")
                index += 1

            continue

        if char in _DEVA_DIGIT:
            out.append(_DEVA_DIGIT[char])
            index += 1
            inherent = False
            continue

        index += 1

    word = "".join(out)

    # Hindi and Telugu both drop the final inherent vowel: "madada" is
    # written and heard as "madad".
    if inherent and len(word) > 3 and word.endswith("a"):
        word = word[:-1]

    return word

# ----------------------------------------------------------------- result

# What the brain is asked to reply in.
#
# Two measured facts shape these, not taste:
#
#   * Nobody speaks textbook Telugu or Hindi out loud. Every Indic reply
#     therefore keeps the everyday words in English, the way the Boss
#     himself says them - "meeting", "college", "time", "sorry".
#   * The Indic voices read their OWN script correctly and read embedded
#     Latin English words naturally, but they mangle Romanized Indic
#     words: te-IN-ShrutiNeural read "aragantha" as "argandha" and
#     "9:15 AM" as "nine point one five", while the same sentence in
#     Telugu script came out as "ఉదయం 9 గంటల 15 నిమిషాలు". So the Telugu
#     and Hindi words are always asked for in their own script, whatever
#     script the transcript happened to arrive in.
STYLE_LABELS = {
    "english": "English",
    "telugu": (
        "everyday spoken Telugu - Telugu words in Telugu script, and the "
        "words Telugu speakers normally say in English left in English "
        "letters"
    ),
    "hindi": (
        "everyday spoken Hindi - Hindi words in Devanagari, and the words "
        "Hindi speakers normally say in English left in English letters"
    ),
    "tenglish": (
        "everyday spoken Telugu with a little more English than usual, "
        "because that is how the Boss just spoke - the Telugu words still "
        "in Telugu script, the English words in English letters"
    ),
    "hinglish": (
        "everyday spoken Hindi with a little more English than usual, "
        "because that is how the Boss just spoke - the Hindi words still "
        "in Devanagari, the English words in English letters"
    ),
}


@dataclass
class LanguageResult:
    """Outcome of a detection pass."""

    code: str = "en"            # en | te | hi  (used for TTS voice choice)
    style: str = "english"      # english | telugu | hindi | tenglish | hinglish
    confidence: float = 0.0
    telugu: float = 0.0
    hindi: float = 0.0
    english: float = 0.0        # how many clear English words were spoken
    romanized: bool = True      # was the transcript itself Latin-only?
    script: str = "latin"       # latin | telugu | devanagari | other
    matched: tuple = ()
    source: str = "default"     # script | words | phonetic | hint | vote

    @property
    def is_indic(self) -> bool:
        return self.code in ("te", "hi")

    @property
    def is_mixed(self) -> bool:
        return self.style in ("tenglish", "hinglish")

    def label(self) -> str:
        """Human readable style, used for the brain's style hint."""
        return STYLE_LABELS.get(self.style, "English")

    def __str__(self) -> str:
        return self.code

# ------------------------------------------------------------- primitives

_HINT_MAP = {
    "en": "en", "eng": "en", "english": "en",
    "te": "te", "tel": "te", "telugu": "te",
    "hi": "hi", "hin": "hi", "hindi": "hi",
}


def normalize_hint(value) -> str | None:
    """Map anything Whisper (or a caller) gives us onto en/te/hi."""
    if not value:
        return None

    return _HINT_MAP.get(str(value).strip().lower())


def _script_profile(text: str):
    telugu = len(TELUGU_RANGE.findall(text))
    devanagari = len(DEVANAGARI_RANGE.findall(text))
    letters = len(_LETTER.findall(text))

    return telugu, devanagari, letters


def dominant_script(text: str) -> str:
    """'latin' | 'telugu' | 'devanagari' | 'other' - for logs and routing."""
    telugu, devanagari, letters = _script_profile(text or "")

    if not letters:
        return "latin"

    if telugu >= devanagari and telugu / letters >= MIN_SCRIPT_RATIO:
        return "telugu"

    if devanagari > telugu and devanagari / letters >= MIN_SCRIPT_RATIO:
        return "devanagari"

    if unsupported_script_ratio(text) >= 0.15:
        return "other"

    return "latin"


def _latin_tokens(text: str):
    return _LATIN_TOKEN.findall(text.lower())


def _english_hits(tokens) -> int:
    return sum(1 for token in tokens if token in MIX_MARKERS)

def _score_latin(tokens):
    """Weighted Telugu/Hindi evidence from Romanized words."""
    telugu = 0.0
    hindi = 0.0
    matched = []

    for token in tokens:
        if len(token) <= 2 or token in ENGLISH_GUARD:
            continue

        weight = TELUGU_LEXICON.get(token)

        if weight:
            telugu += weight
            matched.append(token)
            continue

        weight = HINDI_LEXICON.get(token)

        if weight:
            hindi += weight
            matched.append(token)
            continue

        # Same word, different spelling.
        if len(token) >= MIN_NORM_LEN and token not in ENGLISH_MARKERS:
            key = normalize_word(token)

            if key not in _ENGLISH_NORM:
                weight = TELUGU_NORMALIZED.get(key)

                if weight:
                    telugu += weight
                    matched.append(token)
                    continue

                weight = HINDI_NORMALIZED.get(key)

                if weight:
                    hindi += weight
                    matched.append(token)
                    continue

        # Never-seen word, but the ending gives it away.
        if len(token) >= 7 and token not in ENGLISH_MARKERS:
            if token.endswith(TELUGU_SUFFIX):
                telugu += WEAK
                matched.append(token)

            elif token.endswith(HINDI_SUFFIX):
                hindi += WEAK
                matched.append(token)

    return telugu, hindi, matched

def _deva_words(text: str):
    """Devanagari tokens rewritten in Latin, so the lexicons still work."""
    return [w for w in (deva_to_latin(t) for t in _DEVA_TOKEN.findall(text)) if w]


def _deva_scores(text: str):
    """Whose language is this Devanagari? Cue words plus transliteration."""
    cue_telugu = 0
    cue_hindi = 0

    for token in _DEVA_TOKEN.findall(text):
        if token in DEVANAGARI_TELUGU_CUES:
            cue_telugu += 1

        if token in DEVANAGARI_HINDI_CUES:
            cue_hindi += 1

    telugu, hindi, matched = _score_latin(_deva_words(text))

    return (
        telugu + cue_telugu * STRONG,
        hindi + cue_hindi * STRONG,
        matched,
    )


def _style_for(code: str, tokens):
    """
    Reply style: pure vs code-mixed.

    Only *spoken English words* make it mixed. The script Whisper
    happened to use says nothing about how the user spoke, so a pure
    Telugu/Hindi sentence is answered in native script even when the
    transcript came back Romanized - the Indic voices read their own
    script far better than they read Latin letters.
    """
    english = _english_hits(tokens)

    if code == "en":
        return "english", english

    mixed = english >= 1

    if code == "te":
        style = "tenglish" if mixed else "telugu"

    else:
        style = "hinglish" if mixed else "hindi"

    return style, english


def _confidence(weight: float, margin: float, density: float) -> float:
    score = 0.45
    score += min(weight, 12.0) / 30.0
    score += min(margin, 8.0) / 40.0
    score += min(density, 0.6) / 4.0

    return round(min(score, 0.99), 3)

def analyze(text: str, hint: str = None) -> LanguageResult:
    """Decide language + reply style locally. `hint` is Whisper's guess."""
    if not text or not text.strip():
        return LanguageResult(script="latin")

    hint = normalize_hint(hint)
    telugu_chars, deva_chars, letters = _script_profile(text)
    native_chars = telugu_chars + deva_chars
    tokens = _latin_tokens(text)
    script = dominant_script(text)

    # ---- native script: the strongest possible signal -------------
    if (
        native_chars >= MIN_SCRIPT_CHARS
        and letters
        and native_chars / letters >= MIN_SCRIPT_RATIO
    ):
        deva_telugu, deva_hindi, matched = (
            _deva_scores(text) if deva_chars else (0.0, 0.0, [])
        )

        if telugu_chars > deva_chars:
            code = "te"

        elif deva_chars > telugu_chars:
            if deva_telugu > deva_hindi:
                code = "te"

            elif deva_hindi > deva_telugu:
                code = "hi"

            else:
                code = hint if hint in ("te", "hi") else "hi"

        else:
            code = hint if hint in ("te", "hi") else "te"

        style, english = _style_for(code, tokens + _deva_words(text))

        return LanguageResult(
            code=code,
            style=style,
            confidence=round(min(0.99, 0.72 + native_chars / letters / 4), 3),
            telugu=deva_telugu,
            hindi=deva_hindi,
            english=float(english),
            romanized=False,
            script=script,
            matched=tuple(matched[:8]),
            source="script",
        )

    return _analyze_latin(text, tokens, hint, script)

def _analyze_latin(text, tokens, hint, script) -> LanguageResult:
    """Romanized speech: Tenglish, Hinglish or plain English."""
    telugu, hindi, matched = _score_latin(tokens)
    english = _english_hits(tokens)

    content = [t for t in tokens if len(t) > 2 and t not in ENGLISH_GUARD]
    density = len(matched) / len(content) if content else 0.0

    weight = max(telugu, hindi)
    
    # Short sentence exception: if <= 6 content words and at least one strong hit,
    # lower the density requirement because small utterances have high variance.
    required_density = MIN_DENSITY
    if len(content) <= 6 and weight >= STRONG_WEIGHT:
        required_density = 0.08

    margin = abs(telugu - hindi)
    leader = "te" if telugu > hindi else "hi" if hindi > telugu else None

    code = "en"
    source = "words"

    if weight >= MIN_WEIGHT and density >= required_density:
        if leader and (margin >= MIN_MARGIN or weight >= STRONG_WEIGHT):
            code = leader

        elif hint in ("te", "hi"):
            # Both languages scored: Whisper breaks the tie, nothing more.
            code = hint
            source = "hint"

        elif leader:
            code = leader

    elif (
        weight >= MEDIUM
        and density >= required_density
        and hint in ("te", "hi")
        and (hint == leader or margin < MIN_MARGIN)
    ):
        # Thin evidence on its own, but it agrees with what was heard.
        code = hint
        source = "hint"

    if code == "en":
        return LanguageResult(
            code="en",
            style="english",
            confidence=0.9 if not weight else 0.6,
            telugu=telugu,
            hindi=hindi,
            english=float(english),
            romanized=True,
            script=script,
            matched=tuple(matched[:8]),
            source=source if weight else "default",
        )

    style, english = _style_for(code, tokens)

    return LanguageResult(
        code=code,
        style=style,
        confidence=_confidence(weight, margin, density),
        telugu=telugu,
        hindi=hindi,
        english=float(english),
        romanized=True,
        script=script,
        matched=tuple(matched[:8]),
        source=source,
    )

# ------------------------------------------------------- arbitration

@dataclass
class Candidate:
    """One transcript of the *same* audio, from one decoding pass."""

    text: str = ""
    hint: str = None            # Whisper's language label for this pass
    logprob: float = None       # average log-probability, if reported
    locked: bool = False        # was the language forced for this pass?
    name: str = ""


def _relabel(text: str, code: str, base: LanguageResult) -> LanguageResult:
    """Keep the decided language, recompute style/script for this text."""
    telugu_chars, deva_chars, _ = _script_profile(text)
    native = telugu_chars + deva_chars
    tokens = _latin_tokens(text) + _deva_words(text)
    style, english = _style_for(code, tokens)

    return LanguageResult(
        code=code,
        style=style,
        confidence=base.confidence,
        telugu=base.telugu,
        hindi=base.hindi,
        english=float(english),
        romanized=native == 0,
        script=dominant_script(text),
        matched=base.matched,
        source=base.source if base.code == code else "vote",
    )


def _rank(entry):
    """Prefer the more confident decode when everything else is equal."""
    logprob = entry[0].logprob

    return -(logprob if logprob is not None else -5.0)

def choose(candidates, hint: str = None):
    """
    Pick the best transcript of one utterance and its language.

    Whisper is asked twice for the same audio (once locked to Latin
    letters, once free) and this decides locally which decode to trust.
    No network call, no model, just script + lexicon evidence.
    """
    pool = []

    for cand in candidates or ():
        text = (cand.text or "").strip()

        if text:
            pool.append((cand, text, analyze(text, cand.hint or hint)))

    if not pool:
        return "", LanguageResult(script="latin")

    # A transcript in a script we cannot speak is worthless.
    readable = [p for p in pool if not has_unsupported_script(p[1])]
    pool = readable or pool

    latin = sorted((p for p in pool if p[2].script == "latin"), key=_rank)
    native = sorted(
        (p for p in pool if p[2].script in ("telugu", "devanagari")),
        key=_rank,
    )

    # ---- 1. which language was actually spoken? -------------------
    telugu = max((p[2].telugu for p in pool), default=0.0)
    hindi = max((p[2].hindi for p in pool), default=0.0)

    # Telugu script is proof of Telugu. Devanagari is not proof of
    # Hindi - Whisper writes Telugu in Devanagari too - so it only
    # counts through the transliterated cues already scored above.
    if any(p[2].script == "telugu" for p in native):
        telugu += STRONG_WEIGHT

    votes_te = sum(1 for p in pool if p[2].code == "te")
    votes_hi = sum(1 for p in pool if p[2].code == "hi")

    if telugu >= MIN_WEIGHT or hindi >= MIN_WEIGHT:
        if telugu > hindi + WEAK:
            code = "te"

        elif hindi > telugu + WEAK:
            code = "hi"

        elif votes_te != votes_hi:
            code = "te" if votes_te > votes_hi else "hi"

        else:
            code = normalize_hint(hint) if normalize_hint(hint) in ("te", "hi") \
                else ("te" if telugu >= hindi else "hi")

    elif native and not any(p[2].english for p in latin):
        code = native[0][2].code

    else:
        code = "en"

    # ---- 2. which transcript do we hand over? ---------------------
    if code == "en":
        best = [p for p in latin if p[2].code == "en"] or latin or pool
        _, text, result = best[0]

        return text, _relabel(text, "en", result)

    want = "telugu" if code == "te" else "devanagari"
    right_script = [p for p in native if p[2].script == want]

    # A Latin decode that agrees with the decision is a real
    # transcript; one with no Indic evidence at all is a translation.
    agreeing = [p for p in latin if p[2].code == code] or \
               [p for p in latin if p[2].is_indic]
    latin_pick = agreeing[0] if agreeing else (latin[0] if latin else None)

    # Code-mixed speech stays Romanized: rewriting "fix the code" in
    # Telugu script would only make the voice mispronounce it.
    mixed = bool(agreeing) and latin_pick[2].english >= 1

    if right_script and not mixed:
        _, text, result = right_script[0]

    elif agreeing:
        _, text, result = latin_pick

    elif right_script:
        _, text, result = right_script[0]

    elif latin_pick is not None:
        _, text, result = latin_pick

    else:
        _, text, result = (native or pool)[0]

    base = LanguageResult(
        code=result.code,
        confidence=max(result.confidence, 0.6),
        telugu=telugu,
        hindi=hindi,
        matched=result.matched,
        source=result.source,
    )

    return text, _relabel(text, code, base)

# --------------------------------------------------------- script sanity

# The three scripts this assistant can read out loud.
_SUPPORTED_LETTER = re.compile(r"[A-Za-zऀ-ॿఀ-౿]")


def unsupported_script_ratio(text: str) -> float:
    """Share of letters we could never pronounce (Tamil, Gujarati, ...)."""
    letters = _LETTER.findall(text or "")

    if not letters:
        return 0.0

    bad = sum(1 for char in letters if not _SUPPORTED_LETTER.match(char))

    return bad / len(letters)


def has_unsupported_script(text: str, threshold: float = 0.15) -> bool:
    """True when Whisper wrote the answer in a script we cannot speak."""
    return unsupported_script_ratio(text) >= threshold

# ------------------------------------------------------------ public API


def detect_language(text: str, hint: str = None) -> str:
    """Language code of spoken input: 'en', 'te' or 'hi'."""
    return analyze(text, hint).code


def reply_problem(answer: str, expected: str):
    """
    Why a reply does not match the language the Boss actually used.

    Returns None when the reply is fine, otherwise 'language' (she
    answered in the wrong language) or 'script' (right language, but
    written in Latin letters the Telugu voice mispronounces).

    This is the cheap local gate in front of the one corrective retry:
    every reply is checked for free, and a second API call is only ever
    spent on a reply that is genuinely wrong.
    """
    expected = normalize_hint(expected)
    answer = (answer or "").strip()

    if expected not in ("te", "hi") or not answer:
        return None

    result = analyze(answer)

    if result.code != expected:
        return "language"

    # Hindi is safe either way - hi-IN-SwaraNeural turned Romanized and
    # Devanagari Hindi into byte-identical audio. Telugu is not: Latin
    # Telugu is measurably mispronounced, so it is worth one retry.
    if expected == "te" and not TELUGU_RANGE.search(answer):
        return "script"

    return None


def _needs_rescue(text: str, result: LanguageResult) -> bool:
    """A reply too short to carry evidence, like 'Sare.' or 'OK.'"""
    content = [t for t in _latin_tokens(text) if len(t) > 2]

    return not result.english and len(content) <= 3

def detect_response_language(text: str, fallback: str = None) -> LanguageResult:
    """
    Voice choice for a reply: the reply text itself decides.

    Latin letters do not mean English - Romanized Telugu or Hindi is
    spoken by the Indic voice. `fallback` (the user's language) only
    rescues replies too short to carry any evidence.
    """
    result = analyze(text)

    if result.is_indic:
        return result

    hint = normalize_hint(fallback)

    if hint in ("te", "hi") and _needs_rescue(text, result):
        telugu_chars, deva_chars, _ = _script_profile(text or "")
        style, english = _style_for(hint, _latin_tokens(text or ""))

        return LanguageResult(
            code=hint,
            style=style,
            confidence=0.5,
            english=float(english),
            romanized=(telugu_chars + deva_chars) == 0,
            script=dominant_script(text or ""),
            source="hint",
        )

    return result


def describe(text: str, hint: str = None) -> str:
    """One line for the console: what was decided and why."""
    result = analyze(text, hint)
    words = ", ".join(result.matched) if result.matched else "-"

    return (
        f"{result.code}/{result.style} conf={result.confidence} "
        f"script={result.script} te={result.telugu:.1f} "
        f"hi={result.hindi:.1f} via={result.source} [{words}]"
    )

