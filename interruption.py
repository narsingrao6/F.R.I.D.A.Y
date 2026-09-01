"""
Barge-in support: lets the Boss stop F.R.I.D.A.Y. mid-sentence.

Three things had to be right before this worked reliably, and each one
was a real defect rather than a preference:

  * The microphone is borrowed from the shared `mic_hub`, so the monitor
    and the main listener never open the device at the same time.
  * The monitor must never calibrate itself. It only ever opens the
    microphone while she is already talking, so measuring the "ambient"
    noise floor measured *her voice* and raised the threshold until the
    Boss could not be heard at all. It borrows the main listener's floor
    instead, which was measured while the room was quiet.
  * Her own voice is in the microphone the whole time she speaks, so the
    phrase the recogniser returns is usually her words with the Boss's
    command buried inside. A wake or stop word therefore counts wherever
    it lands, and a phrase built only of wake and stop words is never
    dismissed as an echo - that is what used to swallow the most natural
    interruption of all, saying "Friday, Friday" until she stops.
"""

import re
import threading
import time

import speech_recognition as sr

from voice.audio import mic_hub, is_shutting_down, MicrophoneBusy
from voice.speaker import stop_speaking, is_speaking, current_speech

# Recogniser spellings of "Friday" that show up in practice.
WAKE_WORDS = {
    "friday",
    "fryday",
    "freeday",
    "fridays",
}

# Optional second word, in any of the supported languages. The spellings
# with no dictionary entry are what the recogniser actually returns for
# those sounds, so they have to be listed too.
STOP_WORDS = {
    "stop", "quiet", "enough", "cancel", "wait", "shh",
    "aagu", "aagandi", "apu", "aapu", "chaalu", "chalu", "vadhu",
    "ruko", "ruk", "rukiye", "band", "bas", "chup",
    "agu", "augu", "aagipo", "agipo", "aapandi", "vaddu",
    "roko", "rooko", "rukho", "bandh", "chupp",
}

# Said on their own - with no "Friday" in front - these can only be aimed
# at her. The rest of STOP_WORDS needs the name, because words like
# "bas", "band", "wait" and "chaalu" turn up inside her own replies
# ("alarm set कर दिया", "wait a moment, Boss") and she must never talk
# herself into silence.
SOLO_STOP_WORDS = {
    "stop", "quiet", "enough", "cancel", "shh",
    "aagu", "aagandi", "aapu", "apu", "aagipo", "agipo", "aapandi",
    "ruko", "rukiye", "rooko", "rukho", "roko",
}

_WORD = re.compile(r"[a-z]+")

MAX_COMMAND_WORDS = 4
MAX_SOLO_STOP_WORDS = 2
ECHO_OVERLAP = 0.6
MIN_ECHO_WORDS = 3

# Floor for the borrowed threshold, in case the room was silent when the
# listener calibrated and the number came back unusably low.
BASE_THRESHOLD = 400

# Short phrases: she has to react while she is still talking, and the
# microphone has to be handed back quickly once she stops.
LISTEN_TIMEOUT = 0.4
PHRASE_LIMIT = 2.0


class InterruptionController:

    def __init__(self):
        self.recognizer = sr.Recognizer()

        self.recognizer.energy_threshold = BASE_THRESHOLD

        # Never adaptive here: her own playback would push the threshold
        # up and up until nothing the Boss said could clear it.
        self.recognizer.dynamic_energy_threshold = False

        self.recognizer.pause_threshold = 0.4
        self.recognizer.non_speaking_duration = 0.2

        self.running = False
        self.interrupted = False
        self.thread = None

    # ------------------------------------------------------- lifecycle

    def tune(self, threshold):
        """Borrow a noise floor measured while the room was quiet."""
        if threshold:
            self.recognizer.energy_threshold = max(
                BASE_THRESHOLD,
                float(threshold),
            )

    def start(self):
        if self.running:
            return

        self.running = True
        self.interrupted = False

        self.thread = threading.Thread(
            target=self._monitor,
            daemon=True,
        )

        self.thread.start()

    def stop(self):
        self.running = False

        thread = self.thread
        self.thread = None

        if thread and thread.is_alive():
            # The shared microphone lock guarantees safety even if the
            # thread needs another moment to finish its current phrase,
            # so there is no need to block the conversation here.
            thread.join(timeout=1.0)

    def reset(self):
        self.interrupted = False

    def was_interrupted(self) -> bool:
        return self.interrupted

    # -------------------------------------------------------- decisions

    @staticmethod
    def _is_echo(text: str) -> bool:
        """True if this is most likely F.R.I.D.A.Y.'s own voice."""
        spoken = current_speech().lower()

        if not spoken:
            return False

        heard = _WORD.findall(text)

        if not heard:
            return True

        named = any(word in WAKE_WORDS for word in heard)

        # Without her name, a phrase she is literally saying right now is
        # her own voice - even a bare "stop", which she can say herself
        # ("ఆ alarm stop చేసాను") and must not be silenced by.
        if not named and text in spoken:
            return True

        # A phrase built only out of her name and stop words is not
        # something she ever says, so it must never be written off as an
        # echo. Without this, "friday friday friday" was discarded the
        # moment her own reply happened to contain the word "Friday".
        if all(
            word in WAKE_WORDS or word in STOP_WORDS
            for word in heard
        ):
            return False

        if text in spoken:
            return True

        spoken_words = set(_WORD.findall(spoken))

        # Her name is not evidence of an echo - the Boss says it too - so
        # only the surrounding words are compared.
        content = {word for word in heard if word not in WAKE_WORDS}

        if len(content) >= MIN_ECHO_WORDS and spoken_words:
            overlap = len(content & spoken_words) / len(content)

            if overlap >= ECHO_OVERLAP:
                return True

        return False

    @staticmethod
    def _is_trigger(text: str) -> bool:
        """
        Does this phrase look like the Boss telling her to stop?

        Her voice is in the microphone while she talks, so the recogniser
        usually returns her words with his command somewhere inside. A
        clean four-word command is the easy case; the rules below are the
        ones that survive her voice being mixed into the same phrase.
        """
        words = _WORD.findall(text)

        if not words:
            return False

        wake = [word for word in words if word in WAKE_WORDS]

        if wake:
            # "friday stop", "friday aagu", "hey friday ruko" - and the
            # same command with her own sentence wrapped around it.
            if any(word in STOP_WORDS for word in words):
                return True

            # Saying her name again is how people actually interrupt.
            if len(wake) >= 2:
                return True

            # A plain "friday" or "hey friday" on its own.
            return len(words) <= MAX_COMMAND_WORDS

        # No name, but an unmistakable stop word said on its own. She is
        # speaking, so there is nothing else it could be aimed at.
        return len(words) <= MAX_SOLO_STOP_WORDS and any(
            word in SOLO_STOP_WORDS for word in words
        )

    # ---------------------------------------------------------- monitor

    def _monitor(self):
        failures = 0

        try:
            with mic_hub.session(
                recognizer=self.recognizer,
                # Deliberately no calibration: she is already speaking,
                # so the only thing there is to measure is her own voice.
                calibrate=0.0,
                timeout=5.0,
            ) as source:

                while self.running and not is_shutting_down():

                    try:
                        audio = self.recognizer.listen(
                            source,
                            timeout=LISTEN_TIMEOUT,
                            phrase_time_limit=PHRASE_LIMIT,
                        )

                    except sr.WaitTimeoutError:
                        continue

                    if not self.running or is_shutting_down():
                        break

                    import voice.vad as vad
                    import voice.speaker_verification as sv
                    
                    samples = vad.dsp.from_audiodata(audio)
                    report = vad.inspect(samples)
                    
                    if not report.ok:
                        continue
                        
                    is_auth, score = sv.verify_samples(samples, report)
                    if not is_auth:
                        print("F.R.I.D.A.Y.: Unauthorized interruption attempt.")
                        continue

                    try:
                        # en-IN, not en-US: the Indian English model is
                        # far better at Indian accents and at Romanized
                        # Telugu/Hindi stop words like "aagu" or "ruko".
                        text = self.recognizer.recognize_google(
                            audio,
                            language="en-IN",
                        ).lower().strip()

                        failures = 0

                    except sr.UnknownValueError:
                        continue

                    except sr.RequestError:
                        failures += 1

                        # Network trouble: back off instead of hammering.
                        time.sleep(min(failures * 0.2, 1.0))
                        continue

                    if not text:
                        continue

                    # Only meaningful while she is actually speaking.
                    if not is_speaking():
                        continue

                    if self._is_echo(text):
                        continue

                    if not self._is_trigger(text):
                        continue

                    print(
                        f"F.R.I.D.A.Y.: Interruption detected: {text}"
                    )

                    self.interrupted = True
                    stop_speaking()

                    self.running = False
                    break

        except MicrophoneBusy as error:
            print(f"F.R.I.D.A.Y.: Interruption monitor idle: {error}")

        except Exception as error:
            print(
                "F.R.I.D.A.Y.: Interruption monitor stopped: "
                f"{type(error).__name__}"
            )

        finally:
            self.running = False

