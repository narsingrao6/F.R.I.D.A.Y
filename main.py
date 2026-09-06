"""
F.R.I.D.A.Y. - multilingual voice assistant entry point.

Pipeline:

    microphone -> Whisper transcript -> local language/style analysis
    -> Gemini (Groq #1 -> Groq #2 -> Ollama on failure)
    -> response-text language detection -> Edge TTS voice -> speech
"""

import os, sys, subprocess

# --- auto-relaunch with project venv when double-clicked ----------------
_venv_py = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        ".venv", "Scripts", "python.exe")
if sys.platform == "win32" and os.path.isfile(_venv_py):
    _this = os.path.abspath(__file__)
    # If we are NOT already running inside the venv, relaunch with it.
    if os.path.normcase(sys.executable) != os.path.normcase(_venv_py):
        # CREATE_NO_WINDOW: don't pop a second console window.
        # The child inherits the parent's console handles for print output.
        subprocess.Popen([_venv_py, "-u", _this] + sys.argv[1:],
                         cwd=os.path.dirname(_this),
                         creationflags=0x08000000)  # CREATE_NO_WINDOW
        sys.exit()
# ------------------------------------------------------------------------

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
    "exit", "quit", "goodbye", "good bye",
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
        except KeyboardInterrupt:
            request_shutdown()
            break
        except (EOFError, RuntimeError):
            # No console attached (e.g. running via pythonw.exe)
            break


class WebviewApi:
    def __init__(self, text_queue):
        self.text_queue = text_queue
        self.window = None
        self.ui_state = {
            "phase": "idle",
            "messages": [],
            "micOn": True
        }

    def get_updates(self):
        updates = {
            "phase": self.ui_state["phase"],
            "messages": self.ui_state["messages"].copy(),
            "micOn": self.ui_state.get("micOn", True)
        }
        self.ui_state["messages"].clear()
        return updates

    def set_phase(self, phase):
        self.ui_state["phase"] = phase

    def push_message(self, kind, text):
        self.ui_state["messages"].append({"kind": kind, "text": text})

    def send_command(self, text):
        from voice.language import analyze
        result = analyze(text)
        self.text_queue.put((text, result.code, result, True))

    def toggle_mic(self):
        current = self.ui_state.get("micOn", True)
        self.ui_state["micOn"] = not current
        print(f"UI requested mic toggle. Now: {'ON' if self.ui_state['micOn'] else 'OFF'}")
        if not self.ui_state["micOn"]:
            self.text_queue.put(("", "en"))

    def interrupt(self):
        print("UI requested interrupt.")
        from voice.speaker import stop_speaking
        stop_speaking()

    def halt(self):
        print("UI requested halt.")
        from voice.audio import request_shutdown
        from voice.speaker import stop_speaking
        stop_speaking()
        request_shutdown()


def _friday_logic(api, text_queue):
    import threading
    import queue
    import time
    import json
    from voice.audio import is_shutting_down
    
    listener = VoiceListener()
    brain = FridayBrain()
    interrupter = InterruptionController()
    
    time.sleep(1)
    api.push_message('friday', 'F.R.I.D.A.Y. is online, Boss.')
    api.set_phase('idle')
    
    try:
        while not is_shutting_down():
            if not api.ui_state.get("micOn", True):
                api.set_phase('idle')
                try:
                    item = text_queue.get(timeout=0.5)
                    command, language = item[0], item[1]
                    result = item[2] if len(item) > 2 else None
                    skip_push = item[3] if len(item) > 3 else False
                    if command:
                        listener.last_result = result
                        print(f"You (typed): {command}")
                except queue.Empty:
                    command = ""
                    skip_push = False
            else:
                api.set_phase('listening')
                try:
                    item = text_queue.get_nowait()
                    command, language = item[0], item[1]
                    result = item[2] if len(item) > 2 else None
                    skip_push = item[3] if len(item) > 3 else False
                    if command:
                        listener.last_result = result
                        print(f"You (typed): {command}")
                except queue.Empty:
                    command, language = listener.listen(text_queue=text_queue)
                    skip_push = False

            if not command:
                continue

            if not skip_push:
                api.push_message('user', command)

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

            api.set_phase('thinking')
            
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
                api.push_message('friday', answer)
                api.set_phase('speaking')
                speak(answer, hint=language)

            finally:
                interrupter.stop()
                api.set_phase('idle')

            if interrupter.was_interrupted():
                print("F.R.I.D.A.Y.: Go ahead, Boss.")
                api.set_phase('listening')

    except KeyboardInterrupt:
        print("\nF.R.I.D.A.Y.: Shutting down, Boss.")
    except Exception as e:
        import traceback
        print("\nError in background thread:")
        traceback.print_exc()

    finally:
        from voice.audio import request_shutdown, shutdown_audio, mic_hub
        request_shutdown()
        interrupter.stop()
        listener.close()
        shutdown_audio()
        mic_hub.release()
        print("F.R.I.D.A.Y.: Offline.")
        if api.window:
            api.window.destroy()

def main():
    import threading
    import queue
    import webview
    import os
    import logging

    # Suppress harmless but noisy COM warnings from pywebview's internal logger
    logging.getLogger('pywebview').setLevel(logging.CRITICAL)
    
    _install_signal_handlers()

    text_queue = queue.Queue()
    t = threading.Thread(target=text_worker, args=(text_queue,), daemon=True)
    t.start()

    print("F.R.I.D.A.Y.: You can speak, or type a command and press Enter at any time.")
    
    # Start webview
    api = WebviewApi(text_queue)
    
    import pathlib
    import sys
    
    if getattr(sys, 'frozen', False):
        # Running as compiled PyInstaller executable
        base_dir = sys._MEIPASS
    else:
        # Running from source
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
    ui_path = os.path.join(base_dir, "ui", "dist", "index.html")
    if not os.path.exists(ui_path):
        print(f"UI not built. Could not find {ui_path}. Please run 'npm run build' in the ui folder.")
        return
        
    window_url = pathlib.Path(ui_path).as_uri()
    window = webview.create_window('F.R.I.D.A.Y.', window_url, js_api=api, width=1200, height=800, frameless=False, easy_drag=False)
    api.window = window
    
    logic_thread = threading.Thread(target=_friday_logic, args=(api, text_queue), daemon=True)
    
    # Start logic thread once the webview is ready
    def on_loaded():
        logic_thread.start()
        
    window.events.loaded += on_loaded
    
    webview.start()

if __name__ == "__main__":
    main()
