"""
Memory detector — decides whether a user utterance contains information
worth remembering, across English, Telugu, Hindi, Tenglish, and Hinglish.

Design principles:
    1.  Conservative: only clear, definitive statements are saved.
    2.  Multilingual: patterns cover native scripts and romanised forms.
    3.  Normalised: detected facts are stored as "The Boss ..." so
        retrieval works regardless of the original language.
    4.  Safe: passwords, API keys, and credentials are never auto-saved.
"""

import re
from dataclasses import dataclass, field


# ------------------------------------------------------------------ data


@dataclass
class MemoryCandidate:
    content: str            # original utterance (kept for logging)
    normalized: str         # standardised "The Boss ..." form for storage
    category: str
    confidence: float


# -------------------------------------------------------- ignore filters

# Commands, greetings, ephemeral questions, and actions that should
# never be treated as memorisable facts.
IGNORE_PATTERNS = (
    # time / date / weather
    r"\bwhat time\b", r"\bwhat date\b", r"\bwhat day\b",
    r"\bwhat.?s the time\b", r"\bwhat.?s the date\b",
    r"\bwhat.?s the weather\b", r"\bhow.?s the weather\b",
    r"\bweather\b.*\btoday\b", r"\btoday.?s weather\b",
    r"\btime enti\b", r"\bsamayam\b", r"\btime kya\b",
    r"\bsamay kya\b", r"\bkitne baje\b",

    # system / app commands
    r"\bopen\b", r"\bclose\b", r"\bsearch\b", r"\bgoogle\b",
    r"\bshutdown\b", r"\brestart\b", r"\bplay\b", r"\bstop\b",
    r"\bpause\b", r"\bresume\b", r"\bvolume\b", r"\bbrightness\b",
    r"\bscreenshot\b", r"\block\b", r"\bunlock\b",
    r"\bbandh? (?:karo|cheyyi)\b", r"\bband (?:karo|cheyyi)\b",

    # greetings
    r"^(?:hi|hello|hey|hey friday|good morning|good evening|good night"
    r"|howdy|what.?s up|sup)[\s!.?]*$",

    # exit / bye
    r"^(?:bye|goodbye|exit|quit|alvida|sari bye)[\s!.?]*$",

    # simple yes/no/ok
    r"^(?:yes|no|yeah|nah|ok|okay|fine|sure|alright|hmm|haan|nahi"
    r"|avunu|kaadu|sari|theek hai)[\s!.?]*$",

    # memory meta-commands (handled by commands.py, not detector)
    r"\bwhat do you (?:remember|know)\b",
    r"\bshow (?:my )?memories\b",
    r"\blist (?:my )?memories\b",
    r"\bforget\b",
)

# Sensitive data that must never be stored automatically.
SENSITIVE_PATTERNS = (
    r"\bpassword\b", r"\bpasscode\b", r"\bpin (?:number|code)\b",
    r"\bapi[_ -]?key\b", r"\bsecret[_ -]?key\b",
    r"\btoken\b", r"\bcredential\b", r"\bauth\b",
    r"\botp\b", r"\bcredit card\b", r"\bdebit card\b",
    r"\bbank account\b", r"\bsocial security\b",
    r"\bprivate key\b", r"\baccess key\b",
)


# ----------------------------------------------------- explicit triggers

# "Remember that ...", "Don't forget ...", "Keep in mind ..."
# across English, Telugu (script + romanised), and Hindi.
EXPLICIT_TRIGGERS = (
    # English
    (r"^(?:friday[\s,:-]*)?"
     r"(?:please\s+)?"
     r"(?:remember|don'?t forget|keep in mind)"
     r"(?:\s+that)?[\s,:-]+(.+)",
     re.IGNORECASE),

    # Telugu script:  గుర్తుపెట్టుకో / గుర్తుంచుకో
    (r"(.+?)\s*(?:గుర్తు\s*పెట్టుకో|గుర్తుంచుకో|remember\s*చే(?:యి|య్యి))",
     re.IGNORECASE),
    (r"(?:గుర్తు\s*పెట్టుకో|గుర్తుంచుకో|remember\s*చే(?:యి|య్యి))[\s,:-]+(.+)",
     re.IGNORECASE),

    # Telugu romanised
    (r"(.+?)\s*(?:gurthu?\s*pet(?:t?)uko|gurthunchuko|remember\s*cheyyi)",
     re.IGNORECASE),
    (r"(?:gurthu?\s*pet(?:t?)uko|gurthunchuko|remember\s*cheyyi)[\s,:-]+(.+)",
     re.IGNORECASE),

    # Hindi script: याद रखो / याद रख लो
    (r"(.+?)\s*(?:याद\s*(?:रखो|रख\s*लो|रखना)|remember\s*करो)",
     re.IGNORECASE),
    (r"(?:याद\s*(?:रखो|रख\s*लो|रखना)|remember\s*करो)[\s,:-]+(.+)",
     re.IGNORECASE),

    # Hindi romanised
    (r"(.+?)\s*(?:yaad?\s*(?:rakho|rakh\s*lo|rakhna)|remember\s*karo)",
     re.IGNORECASE),
    (r"(?:yaad?\s*(?:rakho|rakh\s*lo|rakhna)|remember\s*karo)[\s,:-]+(.+)",
     re.IGNORECASE),
)


# -------------------------------------------------- category detectors
# Each function returns (normalized_content, confidence) or None.

def _detect_identity(text):
    """Name, age, location, role — who the Boss is."""
    patterns = (
        # English
        (r"\bmy name is\s+(.+?)[\s.!?,]*$", "The Boss's name is {}."),
        (r"\bi am\s+(\w+)\b(?!.*(?:working|building|making|doing|trying|going|using|thinking|looking|learning))",
         "The Boss's name is {}."),
        (r"\bcall me\s+(.+?)[\s.!?,]*$", "The Boss wants to be called {}."),
        (r"\bi'?m\s+(\d{1,3})\s*(?:years?\s*old)?", "The Boss is {} years old."),
        (r"\bi (?:live|stay) in\s+(.+?)[\s.!?,]*$", "The Boss lives in {}."),
        (r"\bi'?m from\s+(.+?)[\s.!?,]*$", "The Boss is from {}."),

        # Telugu script
        (r"నా పేరు\s+(.+?)[\s.!?,]*$", "The Boss's name is {}."),
        (r"నన్ను\s+(.+?)\s*అని\s*(?:పిలు|అను)", "The Boss wants to be called {}."),
        (r"నేను\s+(.+?)\s*(?:లో|నుండి)\s*(?:ఉంటాను|ఉన్నాను)", "The Boss lives in {}."),

        # Telugu romanised (Tenglish)
        (r"\bnaa?\s+peru\s+(.+?)[\s.!?,]*$", "The Boss's name is {}."),
        (r"\bnaa?\s+name\s+(.+?)[\s.!?,]*$", "The Boss's name is {}."),
        (r"\bnannu\s+(.+?)\s*ani\s*(?:pilu|anu)", "The Boss wants to be called {}."),

        # Hindi script
        (r"मेरा नाम\s+(.+?)[\s.!?,।]*$", "The Boss's name is {}."),
        (r"मुझे\s+(.+?)\s*(?:बुलाओ|कहो|बोलो)", "The Boss wants to be called {}."),
        (r"मैं\s+(.+?)\s*(?:में|से)\s*(?:रहता|रहती|हूँ|हूं)", "The Boss lives in {}."),

        # Hindi romanised (Hinglish)
        (r"\bmera\s+naam\s+(.+?)[\s.!?,]*$", "The Boss's name is {}."),
        (r"\bmera\s+name\s+(.+?)[\s.!?,]*$", "The Boss's name is {}."),
        (r"\bmujhe\s+(.+?)\s*(?:bulao|kaho|bolo)", "The Boss wants to be called {}."),
    )

    for pattern, template in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().rstrip(".")
            if value and len(value) < 80:
                return template.format(value), 0.95

    return None


def _detect_preference(text):
    """Likes, dislikes, and preferred ways of doing things."""
    patterns = (
        # English
        (r"\bi (?:prefer|like|love)\s+(.+?)[\s.!?,]*$",
         "The Boss prefers {}."),
        (r"\bi usually (?:use|go with|pick|choose)\s+(.+?)[\s.!?,]*$",
         "The Boss usually uses {}."),
        (r"\bi prefer\s+(.+?)\s+(?:over|instead of|rather than)\s+(.+?)[\s.!?,]*$",
         "The Boss prefers {} over {}."),

        # Telugu script
        (r"నాకు\s+(.+?)\s*(?:ఇష్టం|నచ్చుతుంది|నచ్చింది)",
         "The Boss likes {}."),
        (r"నేను\s+(?:mostly|usually|ఎక్కువగా)\s+(.+?)\s*(?:వాడతాను|use\s*చేస్తాను)",
         "The Boss usually uses {}."),

        # Telugu romanised
        (r"\bnaaku\s+(.+?)\s*(?:ishtam|nachuthundi|nachindi)",
         "The Boss likes {}."),
        (r"\bnenu\s+(?:mostly|usually|ekkuvaga)\s+(.+?)\s*(?:vadataanu|use\s*chesthaanu)",
         "The Boss usually uses {}."),

        # Hindi script
        (r"मुझे\s+(.+?)\s*(?:पसंद|अच्छा लगता|अच्छी लगती)",
         "The Boss likes {}."),
        (r"मैं\s+(?:mostly|usually|ज़्यादातर)\s+(.+?)\s*(?:use करता|इस्तेमाल करता)",
         "The Boss usually uses {}."),

        # Hindi romanised
        (r"\bmujhe\s+(.+?)\s*(?:pasand|accha lagta|achhi lagti)",
         "The Boss likes {}."),
        (r"\bmain\s+(?:mostly|usually|zyada(?:tar)?)\s+(.+?)\s*(?:use karta|istemaal karta)",
         "The Boss usually uses {}."),
    )

    for pattern, template in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = [g.strip().rstrip(".") for g in match.groups() if g]
            if groups and len(groups[0]) < 120:
                return template.format(*groups), 0.85

    return None


def _detect_project(text):
    """Current projects and things being built."""
    patterns = (
        # English
        (r"\bi'?m (?:working on|building|making|creating|developing)\s+(.+?)[\s.!?,]*$",
         "The Boss is working on {}."),
        (r"\bmy (?:project|app|application|game|mod|website|tool|bot|assistant) (?:is |called |named )(.+?)[\s.!?,]*$",
         "The Boss's project is called {}."),
        (r"\bi'?m (?:working on|building|making|creating|developing)\s+(?:a |an )?(.+?)[\s.!?,]*$",
         "The Boss is working on {}."),

        # Telugu script
        (r"నేను\s+(.+?)\s*(?:మీద\s*(?:work|పని)\s*చేస్తున్నాను|build\s*చేస్తున్నాను)",
         "The Boss is working on {}."),
        (r"నా project\s+(.+?)[\s.!?,]*$",
         "The Boss's project is called {}."),

        # Telugu romanised
        (r"\bnenu\s+(.+?)\s*(?:meeda\s*(?:work|pani)\s*chestunnanu|build\s*chestunnanu)",
         "The Boss is working on {}."),
        (r"\bnaa?\s+project\s+(.+?)[\s.!?,]*$",
         "The Boss's project is called {}."),

        # Hindi script
        (r"मैं\s+(.+?)\s*(?:पर\s*(?:work|काम)\s*कर रहा|बना रहा)",
         "The Boss is working on {}."),
        (r"मेरा project\s+(.+?)[\s.!?,।]*$",
         "The Boss's project is called {}."),

        # Hindi romanised
        (r"\bmain\s+(.+?)\s*(?:pe\s*(?:work|kaam)\s*kar raha|bana raha)",
         "The Boss is working on {}."),
        (r"\bmera\s+project\s+(.+?)[\s.!?,]*$",
         "The Boss's project is called {}."),
    )

    for pattern, template in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().rstrip(".")
            if value and len(value) < 120:
                return template.format(value), 0.85

    return None


def _detect_technology(text):
    """Tools, languages, editors, and tech the Boss uses."""
    patterns = (
        # English
        (r"\bi (?:use|code in|develop in|program in|write in)\s+(.+?)[\s.!?,]*$",
         "The Boss uses {}."),
        (r"\bmy (?:editor|ide|stack|setup|environment) is\s+(.+?)[\s.!?,]*$",
         "The Boss's editor/IDE is {}."),
        (r"\bi (?:switched|moved|migrated) to\s+(.+?)[\s.!?,]*$",
         "The Boss uses {}."),

        # Telugu script
        (r"నేను\s+(.+?)\s*(?:వాడతాను|use\s*చేస్తాను|లో\s*code\s*చేస్తాను)",
         "The Boss uses {}."),

        # Telugu romanised
        (r"\bnenu\s+(.+?)\s*(?:vadataanu|use\s*chesthaanu|lo\s*code\s*chesthaanu)",
         "The Boss uses {}."),

        # Hindi script
        (r"मैं\s+(.+?)\s*(?:use करता|इस्तेमाल करता|में\s*code करता)",
         "The Boss uses {}."),

        # Hindi romanised
        (r"\bmain\s+(.+?)\s*(?:use karta|istemaal karta|mein\s*code karta)",
         "The Boss uses {}."),
    )

    for pattern, template in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().rstrip(".")
            if value and len(value) < 80:
                return template.format(value), 0.82

    return None


def _detect_favorite(text):
    """Favourite games, foods, colours, etc."""
    patterns = (
        # English
        (r"\bmy fav(?:ou?rite)?\s+(\w+)\s+is\s+(.+?)[\s.!?,]*$",
         "{1} is one of the Boss's favorite {0}s."),

        # Telugu script
        (r"నాకు\s+(.+?)\s*అంటే\s*(?:చాలా\s*)?ఇష్టం",
         "The Boss really likes {}."),

        # Telugu romanised
        (r"\bnaaku\s+(.+?)\s*ante\s*(?:chaala?\s*)?ishtam",
         "The Boss really likes {}."),

        # Hindi script
        (r"मेरा fav(?:ou?rite)?\s+(\w+)\s+(.+?)[\s.!?,।]*$",
         "{1} is one of the Boss's favorite {0}s."),
        (r"मुझे\s+(.+?)\s*(?:बहुत\s*)?पसंद",
         "The Boss really likes {}."),

        # Hindi romanised
        (r"\bmera\s+fav(?:ou?rite)?\s+(\w+)\s+(?:hai\s+)?(.+?)[\s.!?,]*$",
         "{1} is one of the Boss's favorite {0}s."),
        (r"\bmujhe\s+(.+?)\s*(?:bahut\s*)?pasand",
         "The Boss really likes {}."),
    )

    for pattern, template in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = [g.strip().rstrip(".") for g in match.groups() if g]
            if groups and len(groups[0]) < 80:
                # Templates may use positional {0}, {1} or plain {}
                try:
                    normalized = template.format(*groups)
                except (IndexError, KeyError):
                    normalized = template.format(groups[0])
                return normalized, 0.80

    return None


def _detect_goal(text):
    """Ambitions, plans, and learning goals."""
    # Only save clear intent, not vague "maybe" statements.
    # "I want to learn Python" = yes (0.78)
    # "I'm thinking about maybe learning Python" = no (too vague)
    vague = re.search(
        r"\b(?:maybe|might|thinking about|not sure|possibly|perhaps)\b",
        text,
        re.IGNORECASE,
    )

    if vague:
        return None

    patterns = (
        # English
        (r"\bi want to\s+(.+?)[\s.!?,]*$",
         "The Boss wants to {}."),
        (r"\bmy goal is (?:to )?(.+?)[\s.!?,]*$",
         "The Boss's goal is to {}."),
        (r"\bi'?m (?:planning|going) to\s+(.+?)[\s.!?,]*$",
         "The Boss is planning to {}."),
        (r"\bi need to (?:learn|study|master)\s+(.+?)[\s.!?,]*$",
         "The Boss wants to learn {}."),

        # Telugu script
        (r"నాకు\s+(.+?)\s*(?:నేర్చుకోవాలి|చేయాలి|కావాలి)",
         "The Boss wants to {}."),

        # Telugu romanised
        (r"\bnaaku\s+(.+?)\s*(?:nerchukovaali|cheyyaali|kaavaali)",
         "The Boss wants to {}."),

        # Hindi script
        (r"मुझे\s+(.+?)\s*(?:सीखना है|करना है|चाहिए)",
         "The Boss wants to {}."),

        # Hindi romanised
        (r"\bmujhe\s+(.+?)\s*(?:seekhna hai|karna hai|chahiye)",
         "The Boss wants to {}."),
    )

    for pattern, template in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().rstrip(".")
            if value and len(value) < 120:
                return template.format(value), 0.78

    return None


def _detect_habit(text):
    """Daily routines and habitual behaviours."""
    patterns = (
        # English
        (r"\bi (?:always|usually|normally|typically|often)\s+(.+?)[\s.!?,]*$",
         "The Boss usually {}."),
        (r"\bevery (?:day|morning|evening|night|week)\s+i\s+(.+?)[\s.!?,]*$",
         "The Boss regularly {}."),

        # Telugu script
        (r"నేను\s+(?:ఎప్పుడూ|ఎక్కువగా|usually)\s+(.+?)[\s.!?,]*$",
         "The Boss usually {}."),
        (r"ప్రతి\s+(?:రోజు|ఉదయం|సాయంత్రం)\s+(?:నేను\s+)?(.+?)[\s.!?,]*$",
         "The Boss regularly {}."),

        # Telugu romanised
        (r"\bnenu\s+(?:eppudu|ekkuvaga|usually)\s+(.+?)[\s.!?,]*$",
         "The Boss usually {}."),

        # Hindi script
        (r"मैं\s+(?:हमेशा|आमतौर पर|usually|अक्सर)\s+(.+?)[\s.!?,।]*$",
         "The Boss usually {}."),

        # Hindi romanised
        (r"\bmain\s+(?:hamesha|usually|aksar)\s+(.+?)[\s.!?,]*$",
         "The Boss usually {}."),
    )

    for pattern, template in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().rstrip(".")
            if value and len(value) < 120:
                return template.format(value), 0.78

    return None


def _detect_instruction(text):
    """Direct standing instructions for F.R.I.D.A.Y."""
    patterns = (
        # English
        (r"\balways\s+(.+?)[\s.!?,]*$",
         "Standing instruction: always {}."),
        (r"\bnever\s+(.+?)[\s.!?,]*$",
         "Standing instruction: never {}."),
        (r"\bfrom now on[\s,]+(.+?)[\s.!?,]*$",
         "Standing instruction: {}."),

        # Telugu script
        (r"(?:ఎప్పుడూ|ఇక నుండి)\s+(.+?)[\s.!?,]*$",
         "Standing instruction: {}."),

        # Hindi script
        (r"(?:हमेशा|आज से|अब से)\s+(.+?)[\s.!?,।]*$",
         "Standing instruction: {}."),
    )

    for pattern, template in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().rstrip(".")
            if value and len(value) > 5 and len(value) < 150:
                return template.format(value), 0.90

    return None


# ---------------------------------------------------- ordered pipeline

# Checked in priority order; first match wins.
_CATEGORY_DETECTORS = (
    ("identity",    _detect_identity),
    ("preference",  _detect_preference),
    ("project",     _detect_project),
    ("technology",  _detect_technology),
    ("favorite",    _detect_favorite),
    ("goal",        _detect_goal),
    ("habit",       _detect_habit),
    ("instruction", _detect_instruction),
)


# ------------------------------------------------------------- public

def detect(text):
    """
    Analyse a user utterance and return a MemoryCandidate if it
    contains information worth remembering, or None otherwise.
    """
    if not text:
        return None

    text = text.strip()

    # Too short to carry useful information.
    if len(text) < 6:
        return None

    lower = text.lower()

    # ---- ignore filter ----
    if any(
        re.search(p, lower)
        for p in IGNORE_PATTERNS
    ):
        return None

    # ---- sensitive data filter ----
    if any(
        re.search(p, lower)
        for p in SENSITIVE_PATTERNS
    ):
        return None

    # ---- explicit "remember that ..." ----
    for pattern, flags in EXPLICIT_TRIGGERS:
        match = re.search(pattern, text, flags)
        if match:
            content = match.group(1).strip().rstrip(".")
            if content and len(content) > 2:
                return MemoryCandidate(
                    content=text,
                    normalized=content,
                    category="explicit",
                    confidence=1.0,
                )

    # ---- category detectors ----
    for category, detector in _CATEGORY_DETECTORS:
        result = detector(text)
        if result is not None:
            normalized, confidence = result
            return MemoryCandidate(
                content=text,
                normalized=normalized,
                category=category,
                confidence=confidence,
            )

    return None