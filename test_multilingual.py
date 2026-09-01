"""
Offline self-check for F.R.I.D.A.Y.'s multilingual pipeline.

    python test_multilingual.py          # detection + routing (no network)
    python test_multilingual.py --tts    # also speaks one line per voice

Covers TEST 1-7 (language understanding and voice selection) and the
decision logic behind TEST 8 (interruption). TEST 9 (Ctrl+C) has to be
tried by hand on the real assistant.
"""

import sys
import time

from voice.language import (
    analyze,
    choose,
    Candidate,
    deva_to_latin,
    normalize_word,
    reply_problem,
    STYLE_LABELS,
)
from voice.speaker import resolve_voice, sanitize
from commands import handle_local_command
from interruption import InterruptionController
from brain import FridayBrain, FALLBACK_REPLY

PASS = "PASS"
FAIL = "FAIL"

_failures = []


def check(name, got, expected):
    ok = got == expected

    if not ok:
        _failures.append(f"{name}: expected {expected!r}, got {got!r}")

    print(
        f"  [{PASS if ok else FAIL}] {name}: "
        f"{got!r}" + ("" if ok else f" (expected {expected!r})")
    )


# --------------------------------------------- what the user says (1-7)

# (transcript, whisper's - possibly wrong - label, expected code, style)
INPUT_CASES = [
    ("Hey Friday, what time is it?", "en", "en", "english"),
    ("Hey Friday, naku oka help kavali", "hi", "te", "tenglish"),
    ("Hey Friday, mujhe ek help chahiye", "te", "hi", "hinglish"),
    ("ఫ్రైడే నాకు ఒక సహాయం కావాలి", "hi", "te", "telugu"),
    ("फ्राइडे मुझे एक मदद चाहिए", "en", "hi", "hindi"),
    ("Friday ivala weather enti?", "hi", "te", "tenglish"),
    ("Friday aaj weather kaisa hai?", "te", "hi", "hinglish"),
    ("Friday, naaku college ki vellala?", "hi", "te", "tenglish"),
    ("Friday, mujhe time batao", "te", "hi", "hinglish"),
    # English must survive words that used to trip the old detector.
    ("Tell me the time and the weather for today please", "en",
     "en", "english"),
    ("I need help with the main project file", "hi", "en", "english"),
]


def test_inputs():
    print("\nUser speech -> language / style")

    for text, whisper, code, style in INPUT_CASES:
        result = analyze(text, hint=whisper)

        check(f"code  {text[:38]!r}", result.code, code)
        check(f"style {text[:38]!r}", result.style, style)


# ------------------------------------- English must stay English (TEST 1)

# Sentences full of words that phonetically resemble Telugu/Hindi ones.
# Whisper's label is deliberately wrong in every row.
ENGLISH_CASES = [
    ("Tell me the time and the weather for today please", "te"),
    ("I need help with the main project file", "hi"),
    ("Should I use orange or green for the message package", "te"),
    ("The daily value of the movie was maybe eight", "hi"),
    ("Can you arrange a call and manage the language settings", "te"),
    ("Raise the volume, then chase the last change in the code", "hi"),
    ("Email the sale details to the whole team by Friday", "te"),
    ("What is the weight of the base case in this challenge", "hi"),
    ("Play the next song and open my calendar for tomorrow", "te"),
    ("Take a screenshot and send it to my laptop", "hi"),
]


def test_english_false_positives():
    print("\nEnglish stays English even when Whisper says otherwise")

    for text, whisper in ENGLISH_CASES:
        result = analyze(text, hint=whisper)

        check(f"en {text[:38]!r}", result.code, "en")


# ------------------------------------- spelling-tolerant matching (2-5)

# Whisper spells Romanized Indic words differently every time, and it
# writes Telugu in Devanagari more often than not.
SPELLING_CASES = [
    ("naku oka sahayam kaavaali", "te"),
    ("naaku okka sahaayam kavali", "te"),
    ("nenu repu collegeki vellalaa", "te"),
    ("ippudu samayam entha ayindi", "te"),
    ("mujhe abhi thodi madad chaahiye", "hi"),
    ("mujhey ek madat chahiyeh", "hi"),
    ("aaj mousam kaisaa hai", "hi"),
    ("kal subah jaldi uthna hai", "hi"),
    # Telugu speech that Whisper wrote in Devanagari must stay Telugu.
    ("नाकु ओका सहायम कावाली", "te"),
    ("नाको कॉलेज की वैलाला", "te"),
    ("मुझे एक मदद चाहिए", "hi"),
    ("आज मौसम कैसा है", "hi"),
]


def test_spelling_tolerance():
    print("\nUnseen spellings and wrong scripts still resolve")

    for text, code in SPELLING_CASES:
        # No hint at all: the words alone have to carry the decision.
        check(f"{code} {text[:38]!r}", analyze(text).code, code)

    check("normalize vailala == vellala",
          normalize_word("vailala") == normalize_word("vellala"), True)
    check("normalize kaavaali == kavali",
          normalize_word("kaavaali") == normalize_word("kavali"), True)
    check("normalize chaahiye == chahie",
          normalize_word("chaahiye") == normalize_word("chahie"), True)
    check("deva madad", deva_to_latin("मदद"), "madad")
    check("deva mujhe", deva_to_latin("मुझे"), "mujhe")


# ------------------------------- two-pass arbitration on real ASR output

# Every row is a real `whisper-large-v3` result pair recorded from spoken
# audio: the Latin-locked pass, then the free-detection pass (with the
# language label Whisper reported for it). These are the transcripts
# `choose()` has to arbitrate at runtime - translations, Devanagari
# Telugu, Tamil and all.
#
# (id, latin, latin_logprob, auto, auto_label, auto_logprob,
#  code, style, winner)
ASR_CASES = [
    ("te1", "Naaku waka sahayam kavali", -0.343,
     "नाकु उकस सहायम कावाली", "Hindi", -0.165,
     "te", "telugu", "latin"),
    # The Latin pass translated instead of transcribing.
    ("te2", "How is the environment today?", -0.483,
     "ఇవాల వాతావరణం ఎలా ఉంది", "Telugu", -0.074,
     "te", "telugu", "auto"),
    ("te3", "Ippudu samayam entha indi.", -0.215,
     "ఇపుడు సమేయం ఎంతా ఇంది", "Telugu", -0.112,
     "te", "telugu", "auto"),
    ("te4", "nenu repu college ki vellala", -0.254,
     "నేను రేపు కాలేజికి విల్లాలా", "Telugu", -0.08,
     "te", "tenglish", "latin"),
    ("tn1", "Naaku o ka help kaavali", -0.362,
     "नाकु ओका हेल्प कावाली", "Hindi", -0.148,
     "te", "tenglish", "latin"),
    # Telugu heard as Tamil: unspeakable script, must be discarded.
    ("tn2", "Ivala weather enti", -0.342,
     "இவால வேதை எண்டி", "Tamil", -0.241,
     "te", "tenglish", "latin"),
    # Whisper labelled this Hindi and wrote Devanagari. It is Telugu.
    ("tn3", "naaku college ki vellala", -0.235,
     "नाको कॉलेज की वैलाला", "Hindi", -0.125,
     "te", "tenglish", "latin"),
    ("tn4", "Friday, naaku, okar reminder pittu", -0.232,
     "Friday, नाकु उकर reminder पिट्टू", "Hindi", -0.145,
     "te", "tenglish", "latin"),
    ("hi1", "mujhe ek madad chahiye", -0.172,
     "मुझे एक मदद चाहिए", "Hindi", -0.031,
     "hi", "hindi", "auto"),
    ("hi2", "Aaj mausam kaisa hai?", -0.114,
     "आज मौसम कैसा है?", "Hindi", -0.039,
     "hi", "hindi", "auto"),
    ("hi3", "Abhi kya samay hua hai?", -0.09,
     "अभी क्या समय हुआ है?", "Hindi", -0.042,
     "hi", "hindi", "auto"),
    ("hi4", "mujhe kal subah jaldi uthna hai", -0.11,
     "मुझे कल सुबह जल्दी उठना है", "Hindi", -0.025,
     "hi", "hindi", "auto"),
    ("hn1", "Mujhe ek help chahiye.", -0.156,
     "मुझे एक हेल्प चाहिए", "Hindi", -0.057,
     "hi", "hinglish", "latin"),
    ("hn2", "Aaj weather kaisa hai?", -0.091,
     "आज weather कैसा है?", "Hindi", -0.11,
     "hi", "hinglish", "latin"),
    ("hn3", "mujhe time batao", -0.172,
     "मुझे टाइम बताओ", "Hindi", -0.058,
     "hi", "hinglish", "latin"),
    ("hn4", "Friday mera alarm subah 6 baje laga do", -0.162,
     "Friday मेरा अलाम सुबह छह बजे लगा दो", "Hindi", -0.077,
     "hi", "hinglish", "latin"),
    ("en1", "Hey Friday, what time is it?", -0.139,
     "Hey Friday, what time is it?", "English", -0.139,
     "en", "english", "latin"),
    ("en2", "Friday, tell me about the weather today.", -0.221,
     "Friday, tell me about the weather today.", "English", -0.221,
     "en", "english", "latin"),
]


def test_arbitration():
    print("\nTwo Whisper passes -> one local decision")

    for case in ASR_CASES:
        (cid, latin, latin_lp, auto, auto_label, auto_lp,
         code, style, winner) = case

        text, result = choose([
            Candidate(text=latin, hint="en", logprob=latin_lp,
                      locked=True, name="latin"),
            Candidate(text=auto, hint=auto_label, logprob=auto_lp,
                      name="auto"),
        ])

        check(f"{cid} code", result.code, code)
        check(f"{cid} style", result.style, style)
        check(f"{cid} kept", "latin" if text == latin else "auto", winner)

# ----------------------------------------- which voice speaks the reply

# (response text, user's language hint, expected voice)
VOICE_CASES = [
    ("Hello Boss, how can I help you?", "te", "en-US-AriaNeural"),
    ("The current time is 9:15 AM.", "en", "en-US-AriaNeural"),
    ("శుభోదయం! ఏం సహాయంగా చేయాలి?", "en", "te-IN-ShrutiNeural"),
    ("नमस्ते Boss, मैं आपकी मदद कर सकती हूँ।", "en",
     "hi-IN-SwaraNeural"),
    ("Avunu Boss, today college ki vellali.", "en",
     "te-IN-ShrutiNeural"),
    ("Haan Boss, today college jaana hai.", "en", "hi-IN-SwaraNeural"),
    ("Cheppandi Boss, emi kavali?", "en", "te-IN-ShrutiNeural"),
    ("Bataiye Boss, kya chahiye?", "en", "hi-IN-SwaraNeural"),

    # Real replies from the current brain: native script with the everyday
    # words left in English. A reply like this must not be read by the
    # English voice just because it contains English words - and one that
    # starts on an English word must not be either.
    ("చెప్పండి Boss, ఎలాంటి help కావాలి? నేను ready గా ఉన్నాను.", "te",
     "te-IN-ShrutiNeural"),
    ("Sure Boss, ఏ time కి reminder set చేయాలి? అలాగే topic ఏంటో "
     "చెప్తే note చేసుకుంటాను.", "te", "te-IN-ShrutiNeural"),
    ("Boss, మీ current location చెప్తే, నేను weather details check "
     "చేసి చెప్తాను.", "hi", "te-IN-ShrutiNeural"),
    ("आज का weather थोड़ा ठंडा है, बाहर coat पहन लेना ठीक रहेगा।", "hi",
     "hi-IN-SwaraNeural"),
    ("ज़रूर Boss, alarm 6 am पर set कर दिया है. अब आराम से सो जाइए.", "hi",
     "hi-IN-SwaraNeural"),
    ("हां Boss, aaj का weather थोड़ा cloudy है.", "te", "hi-IN-SwaraNeural"),

    # An English answer stays English even when the Boss was speaking Telugu.
    ("It's currently about 3 PM in London.", "te", "en-US-AriaNeural"),
]


def test_voices():
    print("\nResponse text -> Edge TTS voice")

    for text, hint, voice in VOICE_CASES:
        code, chosen, _ = resolve_voice(text, hint)

        check(f"voice {text[:38]!r}", chosen, voice)

    check(
        "markdown/emoji stripped",
        sanitize("**Hi** Boss `x` 🙂"),
        "Hi Boss x",
    )

    check("emoji only is unspeakable", sanitize("🙂🙂"), "")


# ------------------------------------------------ local fast path + TEST 8


def test_local_commands():
    print("\nLocal commands answer in the caller's language")

    english = handle_local_command("what time is it", "en")
    telugu = handle_local_command("friday ippudu time enti", "te")
    hindi = handle_local_command("friday time kya hai", "hi")

    check("english time", bool(english and "current time" in english), True)
    check("telugu time", bool(telugu and "సమయం" in telugu), True)
    check("hindi time", bool(hindi and "समय" in hindi), True)
    check("no false trigger", handle_local_command("play music", "en"), None)


# Native script arrives misspelled ("సమేయం"), and a missed local answer
# means the brain would invent the time. Folded matching must catch it -
# without turning "team" or "budget" into a clock question.
NATIVE_COMMAND_CASES = [
    ("ఇపుడు సమేయం ఎంతా ఇంది", "te", "సమయం"),
    ("ఇప్పుడు సమయం ఎంత అయింది", "te", "సమయం"),
    ("अभी क्या समय हुआ है?", "hi", "समय"),
    ("मुझे टाइम बताओ", "hi", "समय"),
    ("ఈరోజు తేదీ ఎంత", "te", "ఈరోజు"),
    ("आज तारीख क्या है", "hi", "आज"),
]

NATIVE_COMMAND_NEGATIVES = [
    ("నా టీమ్ ఎక్కడ ఉంది", "te"),
    ("मेरा बजट क्या है", "hi"),
    ("మీటింగ్ సమయానికి రా", "te"),
    ("मेरी टीम को बुलाओ", "hi"),
]


def test_native_script_commands():
    print("\nLocal fast path survives native script and loose spelling")

    for text, language, marker in NATIVE_COMMAND_CASES:
        answer = handle_local_command(text, language)

        check(f"{text[:26]!r}", bool(answer and marker in answer), True)

    for text, language in NATIVE_COMMAND_NEGATIVES:
        check(f"no trigger {text[:22]!r}",
              handle_local_command(text, language), None)


def test_interruption_logic():
    print("\nInterruption triggers (TEST 8) and self-echo rejection")

    trigger = InterruptionController._is_trigger

    check("'friday'", trigger("friday"), True)
    check("'hey friday'", trigger("hey friday"), True)
    check("'friday stop'", trigger("friday stop"), True)
    check("'hey friday stop'", trigger("hey friday stop"), True)
    check("'friday aagu'", trigger("friday aagu"), True)
    check("'friday ruko'", trigger("friday ruko"), True)
    check("random speech", trigger("the weather looks nice"), False)

    check(
        "long sentence mentioning friday",
        trigger(
            "today is friday and the weather in the city is quite warm"
        ),
        False,
    )

    # What the Boss actually does: says her name again until she stops.
    check("'friday friday'", trigger("friday friday"), True)
    check("'friday friday friday'", trigger("friday friday friday"), True)
    check("'friday friday stop'", trigger("friday friday stop"), True)
    check("'friday, friday!'", trigger("friday, friday!"), True)

    # The name repeated inside a phrase her own voice contributed to.
    check(
        "repeated name buried in her reply",
        trigger("friday friday aaj ka weather thoda garam hai"),
        True,
    )

    # A stop word plus her name, wherever they land in the phrase.
    check(
        "'friday stop' buried in her reply",
        trigger("yes boss your alarm is set friday stop"),
        True,
    )
    check(
        "'friday band karo' buried in her reply",
        trigger("thoda garam hai boss friday band karo"),
        True,
    )

    # Unmistakable stop words said on their own, in any of the languages.
    for word in ("stop", "stop it", "quiet", "enough", "cancel",
                 "aagu", "aagipo", "aapandi", "ruko", "rukiye", "roko"):
        check(f"solo {word!r}", trigger(word), True)

    # These are in STOP_WORDS but appear inside her own Hindi and Telugu
    # replies, so on their own they must not silence her.
    for word in ("bas", "band", "wait", "chup", "chaalu", "vaddu"):
        check(f"solo {word!r} needs the name", trigger(word), False)
        check(f"{word!r} with the name", trigger(f"friday {word}"), True)

    # A whole sentence of her own reply is never a command.
    check(
        "her reply is not a trigger",
        trigger("yes boss the weather is warm so carry a water bottle"),
        False,
    )
    check(
        "her Hinglish reply is not a trigger",
        trigger("haan boss alarm subah 6 baje set kar diya hai"),
        False,
    )

    # Nothing recognisable at all.
    check("empty phrase", trigger(""), False)
    check("digits only", trigger("6 30"), False)


def test_echo_rejection():
    """While she is speaking, her own words must not interrupt her."""
    from voice import speaker

    speaker._begin("F.R.I.D.A.Y. is online, Boss.")

    try:
        is_echo = InterruptionController._is_echo

        check(
            "her own sentence is echo",
            is_echo("friday is online boss"),
            True,
        )

        check(
            "the Boss saying 'friday stop' is not echo",
            is_echo("friday stop"),
            False,
        )

        # The case that used to be swallowed: her reply contains her name,
        # so every "friday" looked like her own voice coming back.
        check(
            "'friday friday' is not echo",
            is_echo("friday friday"),
            False,
        )

        check(
            "'friday friday friday' is not echo",
            is_echo("friday friday friday"),
            False,
        )

        check(
            "bare 'stop' is not echo here",
            is_echo("stop"),
            False,
        )

    finally:
        speaker._end()

    # A reply that says a stop word herself: the same bare word is now her
    # own voice, and she must not talk herself into silence.
    speaker._begin("సరే Boss, ఆ alarm stop చేసాను.")

    try:
        is_echo = InterruptionController._is_echo

        check("her own 'stop' is echo", is_echo("stop"), True)
        check("'friday stop' still gets through", is_echo("friday stop"), False)

    finally:
        speaker._end()

    # Nothing is playing, so nothing can be an echo of it.
    check(
        "silence means no echo",
        InterruptionController._is_echo("friday stop"),
        False,
    )


def test_interruption_tuning():
    """The monitor must never let her own voice raise the bar on itself."""
    from interruption import BASE_THRESHOLD

    monitor = InterruptionController()

    check(
        "adaptive threshold is off",
        monitor.recognizer.dynamic_energy_threshold,
        False,
    )
    check("starts at the floor", monitor.recognizer.energy_threshold,
          BASE_THRESHOLD)

    # A quiet room measured below the floor must not lower it.
    monitor.tune(50)
    check("a quiet room cannot lower it",
          monitor.recognizer.energy_threshold, BASE_THRESHOLD)

    # A noisy room is borrowed as measured.
    monitor.tune(1300)
    check("a noisy room is borrowed",
          monitor.recognizer.energy_threshold, 1300.0)

    # No measurement yet: keep whatever is already set.
    monitor.tune(None)
    check("no measurement changes nothing",
          monitor.recognizer.energy_threshold, 1300.0)

    monitor.interrupted = True
    monitor.reset()
    check("reset clears the flag", monitor.was_interrupted(), False)


# ------------------------------------ how she is asked to speak (register)


def test_reply_register():
    """
    Every Telugu/Hindi style must ask for two things at once: the native
    script, and the everyday English words kept in English. Asking for
    one without the other is exactly what made her sound robotic.
    """
    print("\nRequested reply register")

    for style in ("telugu", "tenglish"):
        label = STYLE_LABELS[style]

        check(f"{style} asks for Telugu script", "Telugu script" in label, True)
        check(f"{style} keeps English words", "English letters" in label, True)

    for style in ("hindi", "hinglish"):
        label = STYLE_LABELS[style]

        check(f"{style} asks for Devanagari", "Devanagari" in label, True)
        check(f"{style} keeps English words", "English letters" in label, True)

    # The old policy asked mixed input for Romanized Telugu, which the
    # Telugu voice mispronounced. Nothing may ask for that again.
    for style, label in STYLE_LABELS.items():
        check(
            f"{style} never asks for Romanized Indic",
            "Romanized" in label or "roman" in label.lower(),
            False,
        )

    check("English stays plain English", STYLE_LABELS["english"], "English")


def test_reply_problem():
    """The free local gate that decides whether a retry is worth paying."""
    print("\nIs the reply in the language the Boss used?")

    good_te = "అవును Boss, ఈ weather లో బయటికి వెళ్ళడం కష్టం."
    good_hi = "हाँ Boss, aaj का weather thoda garam है."

    check("good Telugu passes", reply_problem(good_te, "te"), None)
    check("good Hindi passes", reply_problem(good_hi, "hi"), None)

    check(
        "English reply to a Telugu request is wrong",
        reply_problem("Sure Boss, what should the reminder say?", "te"),
        "language",
    )

    check(
        "English reply to a Hindi request is wrong",
        reply_problem("Sure Boss, I will set that alarm.", "hi"),
        "language",
    )

    check(
        "Hindi reply to a Telugu request is wrong",
        reply_problem(good_hi, "te"),
        "language",
    )

    # Latin Telugu is measurably mispronounced, so it is worth one retry.
    check(
        "Romanized Telugu is a script problem",
        reply_problem("Avunu Boss, ivala weather bagundi", "te"),
        "script",
    )

    # Romanized and Devanagari Hindi came out byte-identical, so it is not.
    check(
        "Romanized Hindi is good enough",
        reply_problem("Haan Boss, aaj ka weather thoda garam hai", "hi"),
        None,
    )

    check("English turns are never gated", reply_problem(good_te, "en"), None)
    check("no language means no gate", reply_problem("anything", None), None)
    check("an empty reply is not gated", reply_problem("", "te"), None)


def _offline_brain(replies):
    """A real FridayBrain with the network replaced by a scripted list."""
    brain = object.__new__(FridayBrain)
    brain.system_prompt = "test"

    asked = []

    def chain(message):
        asked.append(message)

        return replies[len(asked) - 1] if len(asked) <= len(replies) else None

    brain._run_chain = chain

    return brain, asked


def test_reply_retry():
    """One corrective retry, only when the reply is genuinely wrong."""
    print("\nOne retry, and only when it is needed")

    # main.py sends the label itself, so the test sends the label too.
    TE_STYLE = STYLE_LABELS["telugu"]
    HI_STYLE = STYLE_LABELS["hindi"]

    good_te = "అవును Boss, ఈ weather బాగుంది."
    good_hi = "हाँ Boss, aaj का weather अच्छा है."
    english = "Sure Boss, what should I set?"
    roman_te = "Avunu Boss, ivala weather bagundi"

    brain, asked = _offline_brain([good_te, good_hi])
    check("a good reply is kept", brain.ask("x", TE_STYLE, "te"), good_te)
    check("a good reply costs one call", len(asked), 1)

    brain, asked = _offline_brain([english, good_te])
    check("English is retried", brain.ask("x", TE_STYLE, "te"), good_te)
    check("the retry is one extra call", len(asked), 2)
    check("the retry says what was wrong", "[note:" in asked[1], True)
    check("the retry restates the style", "Telugu script" in asked[1], True)

    brain, asked = _offline_brain([roman_te, good_te])
    check("Latin Telugu is retried", brain.ask("x", TE_STYLE, "te"), good_te)
    check("the note names the script", "Telugu script" in asked[1], True)

    # A second bad reply must not start a third attempt.
    brain, asked = _offline_brain([english, english])
    check("a hopeless turn still answers", brain.ask("x", TE_STYLE, "te"), english)
    check("never more than two calls", len(asked), 2)

    # Right language, wrong script beats wrong language: keep the better one.
    brain, asked = _offline_brain([english, roman_te])
    check("a partial fix is kept", brain.ask("x", TE_STYLE, "te"), roman_te)

    brain, asked = _offline_brain([roman_te, english])
    check("a worse retry is discarded", brain.ask("x", TE_STYLE, "te"), roman_te)

    brain, asked = _offline_brain([good_hi])
    check("Hindi needs no retry", brain.ask("x", HI_STYLE, "hi"), good_hi)
    check("Hindi costs one call", len(asked), 1)

    # An English turn is never gated, whatever comes back.
    brain, asked = _offline_brain([good_te])
    check("English turns never retry", brain.ask("x", None, "en"), good_te)
    check("English turns cost one call", len(asked), 1)

    brain, asked = _offline_brain([])
    check("total failure is graceful", brain.ask("x", TE_STYLE, "te"), FALLBACK_REPLY)

    check(
        "the style reaches the model",
        FridayBrain._with_style("hi", "English"),
        "hi\n\n[reply style: English]",
    )

    check(
        "hidden reasoning is never spoken",
        FridayBrain._clean_reply(
            "<think>which language?</think>హాయ్ Boss [note: do better]"
        ),
        "హాయ్ Boss",
    )

    check(
        "the style tag is never spoken",
        FridayBrain._clean_reply("Hi Boss [reply style: English]"),
        "Hi Boss",
    )


def test_speech_pipeline():
    """
    Splitting a long reply must not lose or reorder a single word, and
    the next piece must already be downloading while this one plays.
    """
    from voice import speaker

    print("\nSpeech chunking and prefetch")

    long_te = (
        "అవును Boss, ఇవాళ weather sunny గా ఉంది. Temperature 32 degrees "
        "ఉంది, బయటికి వెళ్ళేటప్పుడు water bottle తీసుకెళ్ళండి. "
        "రేపు college కి వెళ్ళి classes attend చేయడం better, ఇవాళే notes "
        "అన్నీ సర్దుకోండి, morning rush లో time waste అవ్వదు."
    )

    samples = [
        "Short reply, Boss.",
        long_te,
        "हाँ Boss. alarm 6 am पर set कर दिया है. अब सो जाइए.",
        "x" * 1500,
        "One sentence that is quite long. " * 40,
    ]

    for sample in samples:
        pieces = speaker._chunks(sample)
        label = sample[:24].replace("\n", " ")

        check(
            f"nothing lost {label!r}",
            "".join(pieces).replace(" ", ""),
            sample.replace(" ", ""),
        )

        check(
            f"every piece fits {label!r}",
            all(len(piece) <= speaker.CHUNK_LIMIT for piece in pieces),
            True,
        )

    # A normal reply must stay a single request - splitting it would only
    # buy an extra round trip, which is what the measurements showed.
    check("a normal reply is one request", len(speaker._chunks(long_te)), 1)
    check("empty text has nothing to say", speaker._chunks(""), [])

    # Prefetch: piece N+1 is downloading while piece N is still playing.
    events = []
    real_synthesize = speaker._synthesize
    real_play = speaker._play

    def fake_synthesize(text, voice, backup_voice):
        events.append(f"get:{text}")

        return None if text == "bad" else f"/tmp/{text}.mp3"

    def fake_play(path):
        # Playback takes real time; that is the window the next download
        # is supposed to hide inside.
        events.append(f"start:{path}")
        time.sleep(0.1)
        events.append(f"end:{path}")

        return True

    speaker._synthesize = fake_synthesize
    speaker._play = fake_play

    try:
        completed = speaker._speak_chunks(
            ["one", "two", "three"], "voice", "backup"
        )

        events_ok = list(events)
        events.clear()

        # One piece the voice service could not produce: the rest of the
        # reply must still be spoken.
        survived = speaker._speak_chunks(
            ["one", "bad", "three"], "voice", "backup"
        )
        events_bad = list(events)

    finally:
        speaker._synthesize = real_synthesize
        speaker._play = real_play

    check("the whole reply was spoken", completed, True)

    check(
        "played in order",
        [event for event in events_ok if event.startswith("start:")],
        ["start:/tmp/one.mp3", "start:/tmp/two.mp3", "start:/tmp/three.mp3"],
    )

    check(
        "the next piece downloads during this one",
        events_ok.index("get:two") < events_ok.index("end:/tmp/one.mp3"),
        True,
    )

    check("a failed piece is reported", survived, False)

    check(
        "a failed piece does not stop the reply",
        [event for event in events_bad if event.startswith("start:")],
        ["start:/tmp/one.mp3", "start:/tmp/three.mp3"],
    )


def test_tts():
    """Optional: actually generate and play one line per language."""
    from voice.speaker import speak

    print("\nSpeaking one line per language (needs internet)")

    lines = [
        "Hello Boss, all systems are online.",
        "శుభోదయం బాస్! ఏం సహాయం చేయాలి?",
        "नमस्ते Boss, मैं आपकी मदद कर सकती हूँ।",
        "Avunu Boss, today college ki vellali.",
    ]

    for line in lines:
        spoken = speak(line)
        check(f"spoke {line[:30]!r}", spoken, True)


def main():
    test_inputs()
    test_english_false_positives()
    test_spelling_tolerance()
    test_arbitration()
    test_voices()
    test_local_commands()
    test_native_script_commands()
    test_interruption_logic()
    test_echo_rejection()
    test_interruption_tuning()
    test_reply_register()
    test_reply_problem()
    test_reply_retry()
    test_speech_pipeline()

    if "--tts" in sys.argv:
        test_tts()

    print()

    if _failures:
        print(f"{len(_failures)} check(s) failed:")

        for failure in _failures:
            print(f"  - {failure}")

        return 1

    print("All checks passed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

