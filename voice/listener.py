"""
Microphone capture + Groq Whisper transcription for F.R.I.D.A.Y.

Why this file looks the way it does - each point was measured, not
guessed, on recorded Telugu/Hindi/Tenglish/Hinglish utterances:

  1. The microphone is borrowed from the shared `mic_hub`, so this
     listener can never fight the interruption monitor for the device.
  2. The model is `whisper-large-v3`, not the turbo variant. Turbo
     mangled Indic speech ("Na ku college ke wahi lala.", "Abhi kya
     sumay hua hai?") and was not faster here.
  3. The prompt is a plain *word list*, never an instruction. An
     English instruction makes Whisper translate Telugu instead of
     transcribing it, and it sometimes swallows the wake word.
  4. Each utterance is decoded twice, in parallel: once locked to Latin
     letters, once with language detection left free. Whisper writes
     Telugu in Devanagari - or even Tamil - often enough that one pass
     cannot be trusted, and no local trick can repair a transcript that
     came back in the wrong script or already translated.
     `voice.language.choose()` then decides locally which decode to
     keep, with no additional network call. Both passes overlap, so the
     wall clock stays that of a single request; set FRIDAY_SINGLE_PASS=1
     to fall back to one call per utterance.
  5. Whisper's own language label is a tie-breaker at most. The
     transcript decides, which is what stops Romanized Telugu from
     being mistaken for Hindi.
"""

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

import speech_recognition as sr
from groq import Groq

from voice.audio import mic_hub, is_shutting_down, MicrophoneBusy
from voice.language import (
    Candidate,
    choose,
    has_unsupported_script,
    LanguageResult,
)

MODEL = "whisper-large-v3"

# Vocabulary, not instructions: it nudges spelling without ever asking
# Whisper to "write" or "translate" anything.
VOCAB_PROMPT = (
    "naku, naaku, nenu, kavali, kaavali, enti, emiti, ivala, repu, "
    "vellali, vellala, cheppu, undi, ledu, ippudu, samayam, entha, "
    "mujhe, chahiye, batao, kya, kaisa, kaisi, hai, aaj, kal, abhi, "
    "samay, madad, jaldi, subah, weather, college, help, reminder, "
    "alarm, time, friday"
)

# Classic Whisper filler on near-silent audio.
JUNK = (
    "thank you for watching",
    "thanks for watching",
    "please subscribe",
    "subtitles by",
    "amara.org",
    "www.",
)

# Anything shorter than this is a cough, not a sentence.
MIN_SECONDS = 0.35

# A hung request must never hold the assistant - or Ctrl+C - hostage.
CLIENT_LIMITS = {"timeout": 20.0, "max_retries": 1}


class VoiceListener:

    def __init__(self):

        self.recognizer = sr.Recognizer()

        # Speech detection settings. Indic sentences carry longer
        # internal pauses than English ones, so cutting at 0.6s used to
        # chop them in half - and half a sentence is half the evidence.
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.9
        self.recognizer.non_speaking_duration = 0.4

        api_key = os.environ.get("GROQ_API_KEY_1")

        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY_1 is not set, so Whisper cannot be used."
            )

        self.groq = Groq(api_key=api_key, **CLIENT_LIMITS)

        # The second decode goes through the spare key when there is
        # one, so the two parallel passes never queue behind each other.
        backup_key = os.environ.get("GROQ_API_KEY_2")

        self.groq_backup = (
            Groq(api_key=backup_key, **CLIENT_LIMITS)
            if backup_key
            else self.groq
        )

        self.single_pass = os.environ.get("FRIDAY_SINGLE_PASS") == "1"

        self._pool = ThreadPoolExecutor(max_workers=2)

        # Full detection details of the last utterance.
        self.last_result = LanguageResult()

        self._calibrated = False

    # ------------------------------------------------------ microphone

    def _capture(self, text_queue=None):
        """Wait for one utterance. Returns audio data or None."""
        try:
            with mic_hub.session(
                recognizer=self.recognizer,
                # A longer first calibration means the very first
                # sentence is not clipped by a wrong noise floor.
                calibrate=0.2 if self._calibrated else 0.8,
            ) as source:

                self._calibrated = True

                print("F.R.I.D.A.Y.: Listening...")

                while not is_shutting_down():
                    
                    if text_queue is not None and not text_queue.empty():
                        return None

                    try:
                        return self.recognizer.listen(
                            source,
                            timeout=0.5,
                            phrase_time_limit=15,
                        )

                    except sr.WaitTimeoutError:
                        # Nothing said yet - loop so Ctrl+C stays responsive.
                        continue

        except MicrophoneBusy as error:
            print(f"F.R.I.D.A.Y.: {error}")

        except Exception as error:
            print(
                "F.R.I.D.A.Y.: Microphone error: "
                f"{type(error).__name__}: {error}"
            )

        return None

    @staticmethod
    def _duration(audio) -> float:
        try:
            frames = len(audio.frame_data)
            rate = audio.sample_rate * audio.sample_width

            return frames / rate if rate else 0.0

        except Exception:
            return 1.0

    # ----------------------------------------------------- transcription

    def _write_wav(self, audio) -> str:
        """One 16 kHz mono WAV on disk, reused by every decoding pass."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            handle.write(
                audio.get_wav_data(convert_rate=16000, convert_width=2)
            )

            return handle.name

    def _decode(self, path, client, language=None):
        """One Whisper pass. Returns a Candidate (empty text on failure)."""
        options = {
            "model": MODEL,
            "response_format": "verbose_json",
            "prompt": VOCAB_PROMPT,
            "temperature": 0.0,
        }

        if language:
            options["language"] = language

        try:
            with open(path, "rb") as audio_file:

                transcription = client.audio.transcriptions.create(
                    file=audio_file,
                    **options,
                )

        except Exception as error:
            print(
                "F.R.I.D.A.Y.: Transcription error "
                f"({language or 'auto'}): {type(error).__name__}: {error}"
            )

            return Candidate(name=language or "auto")

        return Candidate(
            text=(transcription.text or "").strip(),
            hint=language or getattr(transcription, "language", None),
            logprob=_mean_logprob(transcription),
            locked=bool(language),
            name=language or "auto",
        )

    def _transcribe(self, audio):
        """
        Decode one utterance and decide its language locally.

        Returns `(text, LanguageResult, candidates)`.
        """
        path = None

        try:
            path = self._write_wav(audio)

            print("F.R.I.D.A.Y.: Transcribing...")

            if self.single_pass:
                candidates = [self._decode(path, self.groq)]

            else:
                # Latin-locked and free detection at the same time.
                latin = self._pool.submit(
                    self._decode, path, self.groq, "en"
                )
                auto = self._pool.submit(
                    self._decode, path, self.groq_backup, None
                )

                candidates = [latin.result(), auto.result()]

            text, result = choose(candidates)

            # Rare: every pass came back in a script we cannot speak
            # (Urdu, Tamil...). One Latin-locked retry rescues it.
            if text and has_unsupported_script(text):
                print(
                    "F.R.I.D.A.Y.: Unreadable script from Whisper "
                    f"({text!r}) - retrying in Latin letters..."
                )

                repair = self._decode(path, self.groq, "en")

                if repair.text and not has_unsupported_script(repair.text):
                    candidates.append(repair)
                    text, result = choose(candidates)

            return text, result, candidates

        finally:
            if path and os.path.exists(path):
                try:
                    os.remove(path)

                except OSError:
                    pass

    # ------------------------------------------------------------ public

    @staticmethod
    def _is_junk(text: str) -> bool:
        lowered = text.lower()

        if len(lowered) < 2:
            return True

        return any(marker in lowered for marker in JUNK)

    def listen(self, text_queue=None):
        """
        Capture one utterance.

        Returns `(text, language_code)` for backwards compatibility.
        The full detection detail stays available in `self.last_result`.
        """
        self.last_result = LanguageResult()

        audio = self._capture(text_queue=text_queue)

        if audio is None:
            return "", "en"

        if self._duration(audio) < MIN_SECONDS:
            # Too short to be speech; do not spend a Whisper call on it.
            return "", "en"

        import voice.vad as vad
        import voice.speaker_verification as sv
        
        samples = vad.dsp.from_audiodata(audio)
        report = vad.inspect(samples)
        
        if not report.ok:
            print(f"F.R.I.D.A.Y.: No meaningful speech detected ({report.reason}).")
            return "", "en"
            
        is_auth, score = sv.verify_samples(samples, report)
        if not is_auth:
            print("F.R.I.D.A.Y.: Unauthorized speaker detected.")
            return "UNAUTHORIZED_SPEAKER", "en"

        text, result, candidates = self._transcribe(audio)

        if not text or self._is_junk(text):
            return "", "en"

        self.last_result = result

        print(f"You: {text}")

        heard = ", ".join(
            f"{c.name}={c.hint or '?'}" for c in candidates if c.text
        )

        print(
            f"Detected: {result.code} / {result.style} "
            f"(whisper said: {heard or 'nothing'}, "
            f"local source: {result.source})"
        )

        return text, result.code

    def close(self):
        """Release the decoding threads on shutdown."""
        try:
            self._pool.shutdown(wait=False, cancel_futures=True)

        except TypeError:
            # cancel_futures needs Python 3.9+.
            self._pool.shutdown(wait=False)


def _mean_logprob(transcription):
    """Average segment confidence, when Whisper reports it."""
    segments = getattr(transcription, "segments", None) or []
    values = []

    for segment in segments:
        value = (
            segment.get("avg_logprob")
            if isinstance(segment, dict)
            else getattr(segment, "avg_logprob", None)
        )

        if value is not None:
            values.append(value)

    return sum(values) / len(values) if values else None
