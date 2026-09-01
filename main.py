"""
F.R.I.D.A.Y. - multilingual voice assistant entry point.

Pipeline:

    microphone -> Whisper transcript -> local language/style analysis
    -> Gemini (Groq #1 -> Groq #2 -> Ollama on failure)
    -> response-text language detection -> Edge TTS voice -> speech
"""

import signal
import string

from voice.audio import (
    request_shutdown,
    is_shutting_down,
    mic_hub,
)
from voice.listener import VoiceListener
from voice.speaker import speak, stop_speaking, shutdown_audio
from brain import FridayBrain
from commands import handle_local_command
from interruption import InterruptionController

# Whole-utterance matches only, so "how do I exit vim" is not a shutdown.
EXIT_PHRASES = {
    "exit", "quit", "shutdown", "shut down", "goodbye", "good bye",
    "bye friday", "friday bye", "friday exit", "friday stop listening",
    # Telugu / Hindi
    "aagipo", "band cheyyi", "band karo", "bandh karo",
    "alvida", "sari bye", "వీడ్కోలు", "బై", "अलविदा",
}

GOODBYE = {
    "en": "Understood, Boss.",
    "te": "అలాగే బాస్, తర్వాత కలుద్దాం.",
    "hi": "ठीक है Boss, फिर मिलेंगे।",
}

def _install_signal_handlers():
    """Ctrl+C must silence her instantly, then unwind cleanly."""

    def handler(signum, frame):
        request_shutdown()
        stop_speaking()

        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handler)

    try:
        signal.signal(signal.SIGTERM, handler)

    except (AttributeError, ValueError, OSError):
        # SIGTERM is not always available on Windows.
        pass


def _is_exit_command(text: str) -> bool:
    cleaned = text.lower().strip().strip(string.punctuation + " ")

    return cleaned in EXIT_PHRASES


def _style_hint(result):
    """Only send a style note for non-English speech."""
    if result.code == "en" and not result.is_mixed:
        return None

    return result.label()


def text_worker(text_queue):
    """Background thread to read text commands from the terminal."""
    from voice.language import analyze
    from voice.audio import is_shutting_down, request_shutdown
    
    while not is_shutting_down():
        try:
            # We don't print a prompt here to avoid messing up the voice logs.
            # The user can just start typing at any time.
            cmd = input().strip()
            if cmd:
                result = analyze(cmd)
                text_queue.put((cmd, result.code, result))
        except (EOFError, KeyboardInterrupt):
            request_shutdown()
            break


def main():
    import threading
    import queue
    
    _install_signal_handlers()

    listener = VoiceListener()
    brain = FridayBrain()
    interrupter = InterruptionController()

    text_queue = queue.Queue()
    t = threading.Thread(target=text_worker, args=(text_queue,), daemon=True)
    t.start()

    speak("F.R.I.D.A.Y. is online, Boss.")
    print("F.R.I.D.A.Y.: You can speak, or type a command and press Enter at any time.")

    try:
        while not is_shutting_down():
            try:
                command, language, result = text_queue.get_nowait()
                listener.last_result = result
                print(f"You (typed): {command}")
            except queue.Empty:
                command, language = listener.listen(text_queue=text_queue)

            if not command:
                continue

            if command == "UNAUTHORIZED_SPEAKER":
                print("F.R.I.D.A.Y.: Unauthorized speaker detected.")
                speak("Unauthorized speaker detected, Boss.", hint="en")
                continue

            result = listener.last_result

            if _is_exit_command(command):
                speak(
                    GOODBYE.get(language, GOODBYE["en"]),
                    hint=language,
                )
                break

            # Instant local answers first, in the same language.
            answer = handle_local_command(command, language)

            if answer is None:
                answer = brain.ask(
                    command,
                    style=_style_hint(result),
                    language=language,
                )

            print("F.R.I.D.A.Y.:", answer)

            # Listen for barge-in only while she is speaking.
            interrupter.reset()
            interrupter.tune(listener.recognizer.energy_threshold)
            interrupter.start()

            try:
                speak(answer, hint=language)

            finally:
                interrupter.stop()

            if interrupter.was_interrupted():
                print("F.R.I.D.A.Y.: Go ahead, Boss.")

    except KeyboardInterrupt:
        print("\nF.R.I.D.A.Y.: Shutting down, Boss.")

    finally:
        request_shutdown()
        interrupter.stop()
        listener.close()
        shutdown_audio()
        mic_hub.release()

        print("F.R.I.D.A.Y.: Offline.")


if __name__ == "__main__":
    main()

