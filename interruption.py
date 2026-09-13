import re
import speech_recognition as sr
import threading
from collections import Counter

from voice.speaker import stop_speaking

# ---------------------------------------------------------------- defaults

# The monitor must never be *more* sensitive than this, so a quiet room
# cannot push the bar down until her own voice trips the trigger.
BASE_THRESHOLD = 600


class InterruptionController:

    THRESHOLD = BASE_THRESHOLD

    # Words that are unmistakable orders on their own.
    STOP_WORDS = {
        "stop",
        "stop it",
        "quiet",
        "enough",
        "cancel",

        # Telugu
        "aagu",
        "aagipo",
        "aapandi",

        # Hindi
        "ruko",
        "rukiye",
        "roko",
    }

    # Words she often says herself. They only silence her when the Boss
    # also uses her name, or she would talk herself off the air.
    NAME_NEEDED_STOP = {
        "bas",
        "band",
        "wait",
        "chup",
        "chaalu",
        "vaddu",
    }

    def __init__(self):
        self.recognizer = sr.Recognizer()

        self.running = False
        self.interrupted = False
        self.thread = None

        self.recognizer.dynamic_energy_threshold = False
        self.recognizer.energy_threshold = BASE_THRESHOLD
        self.recognizer.pause_threshold = 0.5

    def start(self):
        if self.running:
            return

        self.running = True
        self.interrupted = False

        self.thread = threading.Thread(
            target=self._monitor,
            daemon=True
        )

        self.thread.start()

    def stop(self):
        self.running = False

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.5)

        self.thread = None

    def reset(self):
        self.interrupted = False

    def tune(self, energy_threshold):
        # A quiet room measured below the floor must not lower it.
        if energy_threshold is None:
            return

        if energy_threshold < BASE_THRESHOLD:
            return

        self.recognizer.energy_threshold = float(energy_threshold)

    def was_interrupted(self):
        return self.interrupted

    # ------------------------------------------------------- decision logic

    @staticmethod
    def _normalize(text):
        text = str(text).lower().strip()

        # Dots inside "F.R.I.D.A.Y." merge into the word; every other
        # punctuation becomes a space. Letters/digits stay put.
        text = text.replace(".", "")

        text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)

        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _is_trigger(cls, text):
        """
        True when the Boss actually interrupted.

        Her name alone inside an everyday sentence ("today is FRIDAY and
        the weather...") is NOT an interruption. Repeating her name, or
        pairing it with a stop word, is.
        """
        text = cls._normalize(text)

        if not text:
            return False

        # A bare stop word is always an order.
        if text in cls.STOP_WORDS:
            return True

        words = text.split()

        if "friday" not in words:
            return False

        # Repeating her name is how the Boss snaps her out of it.
        if sum(1 for word in words if word == "friday") >= 2:
            return True

        # A stop word plus her name, wherever they land in the phrase.
        if any(word in cls.STOP_WORDS for word in words):
            return True

        # Weak stop words only count when her name is attached.
        if any(word in cls.NAME_NEEDED_STOP for word in words):
            return True

        # Short name-only utterances ("hey friday") are interrupts, but a
        # long sentence that merely mentions the weekday is not.
        if all(word in {"friday", "hey"} for word in words):
            return True

        return False

    @classmethod
    def _is_echo(cls, text):
        """
        True when the heard words are F.R.I.D.A.Y.'s own current speech,
        so her voice cannot interrupt herself.

        The Boss's interruption always gets through: an echo must be a
        subset of what she is currently saying, and nothing else.
        """
        from voice.speaker import current_speech

        current = current_speech()

        if not current:
            return False

        spoken = cls._normalize(current).split()

        if not spoken:
            return False

        heard = cls._normalize(text).split()

        if not heard:
            return False

        spoken_count = Counter(spoken)
        heard_count = Counter(heard)

        return all(
            spoken_count[word] >= count
            for word, count in heard_count.items()
        )

    # ------------------------------------------------------------ monitoring

    def _monitor(self):

        from voice.audio import mic_hub

        try:
            with mic_hub.session(
                recognizer=self.recognizer,
                calibrate=0.5
            ) as source:

                while self.running:

                    try:
                        audio = self.recognizer.listen(
                            source,
                            timeout=0.5,
                            phrase_time_limit=2
                        )

                    except sr.WaitTimeoutError:
                        continue

                    try:
                        text = self.recognizer.recognize_google(
                            audio
                        ).lower().strip()

                    except (
                        sr.UnknownValueError,
                        sr.RequestError
                    ):
                        continue

                    if not text:
                        continue

                    if self._is_trigger(text) and not self._is_echo(text):
                        print(
                            f"F.R.I.D.A.Y.: "
                            f"Interruption detected: {text}"
                        )

                        self.interrupted = True
                        self.running = False

                        stop_speaking()

                        break

        except Exception as error:

            print(
                "F.R.I.D.A.Y.: "
                "Interruption monitor stopped: "
                f"{type(error).__name__}"
            )