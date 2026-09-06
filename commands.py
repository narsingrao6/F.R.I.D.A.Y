"""
Instant local answers (no AI call needed).

Triggers and replies exist in English, Telugu and Hindi, including the
Romanized forms, so the fast path is not English-only. Native-script
keywords are also matched with their vowel marks folded away, because
Whisper spells them loosely ("సమేయం" for "సమయం") and a missed local
answer means the brain would happily invent the time instead.
"""

import re
import string
from datetime import datetime

from app_launcher import handle_app_command
from pc_control import handle_pc_control_command

# ------------------------------------------------------------- triggers

TIME_PHRASES = (
    # English
    "what time is it", "what's the time", "whats the time",
    "current time", "tell me the time", "time now", "the time",
    # Romanized Telugu / Tenglish
    "time enti", "time entha", "samayam enti", "samayam entha",
    "ippudu time", "time cheppu", "samayam cheppu", "entha time",
    # Romanized Hindi / Hinglish
    "time kya", "samay kya", "kitna baja", "kitne baje",
    "time batao", "samay batao", "time bataiye",
    # Native scripts
    "సమయం", "టైమ్", "समय", "टाइम", "बजे",
)

DATE_PHRASES = (
    # English
    "what is today's date", "what's today's date", "whats todays date",
    "today's date", "todays date", "what date is it",
    "what is the date", "what's the date", "the date today",
    # Romanized Telugu / Tenglish
    "date enti", "ivala date", "ivvala date", "date cheppu",
    "ee roju date", "eroju date", "thedi enti", "thedi entha",
    # Romanized Hindi / Hinglish
    "date kya", "aaj ki date", "aaj kaunsi tarikh", "tarikh kya",
    "date batao", "tarikh batao", "aaj kaun din",
    # Native scripts
    "తేదీ", "తారీఖు", "तारीख", "तारीक", "दिनांक",
)

# Native-script words matched as whole words with the vowel marks
# removed, so a wobbly transcription still lands on the fast path.
TIME_WORDS = ("సమయం", "సమయము", "समय", "बजे", "వేళ")

DATE_WORDS = ("తేదీ", "తారీఖు", "तारीख", "दिनांक", "తేది")

# Telugu and Devanagari vowel signs, virama, nukta and length marks.
_VOWEL_SIGN = re.compile(
    "[ా-్ౕౖౢౣ"
    "़ा-्ॕ-ॗॢॣ]"
)

# Indic vowel marks are combining characters, so `\w` would split words
# apart at them - whitespace and punctuation are the real boundaries.
_PUNCT = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~।॥"

# --------------------------------------------------------- localisation

WEEKDAYS = {
    "te": ["సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం",
           "శుక్రవారం", "శనివారం", "ఆదివారం"],
    "hi": ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार",
           "शुक्रवार", "शनिवार", "रविवार"],
}

MONTHS = {
    "te": ["జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్",
           "జూలై", "ఆగస్టు", "సెప్టెంబర్", "అక్టోబర్",
           "నవంబర్", "డిసెంబర్"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून",
           "जुलाई", "अगस्त", "सितंबर", "अक्टूबर",
           "नवंबर", "दिसंबर"],
}


def _matches(text, phrases) -> bool:
    return any(phrase in text for phrase in phrases)


def _fold(word: str) -> str:
    """Drop the vowel marks Whisper gets wrong, keep the consonants."""
    return _VOWEL_SIGN.sub("", word)


def _matches_word(text, words) -> bool:
    """Whole-word match on folded native script, never a substring."""
    folded = {
        _fold(token.strip(_PUNCT))
        for token in text.split()
    }

    folded.discard("")

    return any(_fold(word) in folded for word in words)


def _time_answer(language: str) -> str:
    now = datetime.now()
    clock = now.strftime("%I:%M %p").lstrip("0")

    if language == "te":
        return f"ఇప్పుడు సమయం {clock}."

    if language == "hi":
        return f"अभी समय {clock} है।"

    return f"The current time is {clock}."


def _date_answer(language: str) -> str:
    now = datetime.now()

    if language in ("te", "hi"):
        weekday = WEEKDAYS[language][now.weekday()]
        month = MONTHS[language][now.month - 1]

        if language == "te":
            return f"ఈరోజు {weekday}, {now.day} {month} {now.year}."

        return f"आज {weekday}, {now.day} {month} {now.year} है।"

    return f"Today is {now.strftime('%A, %d %B %Y')}."



# ------------------------------------------------------------- system commands

SYSTEM_COMMANDS = {
    "shutdown": (
        "shutdown the computer", "shut down my pc", "shutdown my pc",
        "turn off the computer", "turn off my pc", "system shutdown",
        "pc band karo", "computer band karo", "system close cheyyi",
        "computer close cheyyi", "system band karo", "shutdown the pc",
        "shut down the computer", "shut down the pc", "shutdown",
        "shut down", "close the pc", "close the computer", "close pc"
    ),
    "restart": (
        "restart the computer", "restart my pc", "pc restart karo",
        "computer restart cheyyi", "restart the pc", "system restart",
        "restart", "reboot the pc", "reboot the computer"
    ),
    "sleep": (
        "put computer to sleep", "sleep mode", "system sleep",
        "sleep the pc", "pc sleep lo pettu"
    ),
    "logout": (
        "log off", "sign out", "logout", "log out", "system logout",
        "sign me out"
    )
}

CONFIRMATION_YES = (
    "yes", "yeah", "yep", "do it", "avunu", "haan", "han", "yes boss",
    "cheyyi", "karo", "confirm", "proceed", "go ahead"
)

# Global state for confirmation
_pending_system_action = None


def _is_confirmation_yes(text: str) -> bool:
    if text in CONFIRMATION_YES:
        return True

    first_word = text.split(maxsplit=1)[0] if text else ""
    if first_word in {"yes", "yeah", "yep", "avunu", "haan", "han", "confirm", "proceed"}:
        return True

    return any(
        " " in phrase and re.search(rf"\b{re.escape(phrase)}\b", text)
        for phrase in CONFIRMATION_YES
    )


def _matches_system_command(text) -> str:
    """Returns the action name if matched, else None."""
    # Check exact match first
    for action, phrases in SYSTEM_COMMANDS.items():
        if text in phrases:
            return action
    # Then check substring (stricter for shutdown to avoid accidents)
    for action, phrases in SYSTEM_COMMANDS.items():
        if _matches(text, phrases):
            return action
    return None

def _get_confirmation_prompt(action: str, language: str) -> str:
    if action == "shutdown":
        if language == "te": return "బాస్, నేను పీసీ షట్ డౌన్ చేయాలా?"
        if language == "hi": return "बॉस, क्या मुझे पीसी शट डाउन करना चाहिए?"
        return "Boss, do you want me to shut down the PC?"
    if action == "restart":
        if language == "te": return "పీసీ రీస్టార్ట్ చేయమంటారా?"
        if language == "hi": return "क्या पीसी रीस्टार्ट करूँ?"
        return "Should I restart the PC?"
    if action == "sleep":
        if language == "te": return "పీసీని స్లీప్ మోడ్ లో పెట్టాలా?"
        if language == "hi": return "क्या पीसी को स्लीप मोड में डालूँ?"
        return "Should I put the PC to sleep?"
    if action == "logout":
        if language == "te": return "మీ అకౌంట్ నుండి లాగౌట్ చేయాలా?"
        if language == "hi": return "क्या मैं लॉग आउट कर दूँ?"
        return "Should I log you out?"
    return "Are you sure?"

def _execute_system_action(action: str, language: str) -> str:
    import subprocess
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if action == "shutdown":
        subprocess.Popen(["shutdown", "/s", "/t", "0"], creationflags=flags)
        return "Shutting down." if language == "en" else ("షట్ డౌన్ చేస్తున్నాను." if language == "te" else "शट डाउन कर रही हूँ।")
    if action == "restart":
        subprocess.Popen(["shutdown", "/r", "/t", "0"], creationflags=flags)
        return "Restarting." if language == "en" else ("రీస్టార్ట్ చేస్తున్నాను." if language == "te" else "रीस्टार्ट कर रही हूँ।")
    if action == "sleep":
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=flags)
        return "Sleeping." if language == "en" else ("స్లీప్ మోడ్." if language == "te" else "स्लीप मोड।")
    if action == "logout":
        subprocess.Popen(["shutdown", "/l"], creationflags=flags)
        return "Logging out." if language == "en" else ("లాగౌట్ చేస్తున్నాను." if language == "te" else "लॉग आउट कर रही हूँ।")
    return "Done."


# ------------------------------------------------------------- public API


def handle_local_command(command, language: str = "en"):
    """
    Answer trivial questions without touching the AI brain.

    `language` is the detected language of the request ('en'|'te'|'hi'),
    so the reply comes back in the same language and the right voice is
    selected downstream. Returns None when there is no local answer.
    """
    global _pending_system_action
    
    if not command:
        return None

    text = command.lower().strip()
    text = text.translate(str.maketrans("", "", string.punctuation))

    if language not in ("en", "te", "hi"):
        language = "en"
        
    # 1. Check for pending confirmations FIRST
    if _pending_system_action:
        action = _pending_system_action
        _pending_system_action = None # Clear immediately
        
        # Did the user say yes?
        if _is_confirmation_yes(text):
            return _execute_system_action(action, language)
            
        # If they said anything else, cancel
        if language == "te": return "క్యాన్సిల్ చేశాను."
        if language == "hi": return "कैंसिल कर दिया।"
        return "Cancelled."

    if _matches(text, TIME_PHRASES) or _matches_word(text, TIME_WORDS):
        return _time_answer(language)

    if _matches(text, DATE_PHRASES) or _matches_word(text, DATE_WORDS):
        return _date_answer(language)

    pc_answer = handle_pc_control_command(command, language)
    if pc_answer is not None:
        return pc_answer
        
    # 2. Check for new system commands
    sys_action = _matches_system_command(text)
    if sys_action:
        _pending_system_action = sys_action
        return _get_confirmation_prompt(sys_action, language)

    # App open / close — handled locally for instant response.
    # We pass the command text as-is to preserve casing for app names
    app_answer = handle_app_command(command, language)
    if app_answer is not None:
        return app_answer

    return None
