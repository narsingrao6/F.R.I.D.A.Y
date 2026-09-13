"""
F.R.I.D.A.Y. - multilingual voice assistant entry point.

Pipeline:
    microphone -> Whisper transcript -> local language/style analysis
    -> memory -> local commands / Gemini (Groq #1 -> Groq #2 -> Ollama)
    -> response-text language detection -> Edge TTS voice -> speech
"""

import os
import re
import sys
import subprocess
import signal
import socket
import time

# Force IPv4 globally for all network requests (aiohttp/requests/etc)
# Windows IPv6 is often broken or heavily delayed, causing 45s timeouts
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(*args, **kwargs):
    responses = _orig_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET]
socket.getaddrinfo = _ipv4_getaddrinfo
import string


# ------------------------------------------------------------------------
# Auto-relaunch with project venv when double-clicked
# ------------------------------------------------------------------------

_venv_py = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".venv",
    "Scripts",
    "python.exe",
)

if __name__ == "__main__":

    if sys.platform == "win32" and os.path.isfile(_venv_py):

        _this = os.path.abspath(__file__)

        _project = os.path.dirname(_this)
        _log_path = os.path.join(_project, "friday_boot.log")

        # If we are NOT already running inside the venv, relaunch with it.
        if os.path.normcase(sys.executable) != os.path.normcase(_venv_py):
            # CREATE_NO_WINDOW: don't pop a second console window. The
            # relaunched process is fully logged so a silent startup
            # failure is never invisible again.
            with open(_log_path, "a", encoding="utf-8") as _log:
                _log.write(
                    "\n=== FRIDAY relaunch "
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
                )
                _log.flush()

                _child = subprocess.Popen(
                    [_venv_py, "-u", _this] + sys.argv[1:],
                    cwd=_project,
                    creationflags=0x08000000,
                    stdout=_log,
                    stderr=_log,
                    stdin=subprocess.DEVNULL,
                )
                _log.write(f"Spawned child pid={_child.pid}\n")
                _log.flush()

                # Block here so we can record exactly how the child
                # exits (0 = clean, 0xC0000005 = native crash, etc.).
                try:
                    _rc = _child.wait()
                    _log.write(
                        "CHILD EXITED rc="
                        f"{_rc} (0x{_rc & 0xFFFFFFFF:08X})\n"
                    )
                except Exception:
                    pass
            sys.exit()


# ------------------------------------------------------------------------
# Project imports
# ------------------------------------------------------------------------

from voice.audio import (
    request_shutdown,
    is_shutting_down,
    mic_hub,
)

from voice.listener import VoiceListener

from voice.speaker import (
    speak,
    stop_speaking,
    shutdown_audio,
)

from brain import FridayBrain
from commands import handle_local_command
from interruption import InterruptionController
from memory import MemoryManager
from app_launcher import handle_app_command
from pc_control import handle_pc_control_command
from browser import handle_browser_command
from messaging import handle_messaging_command
from tools.computer_use import (
    handle_computer_use_command,
    handle_screen_vision_command,
)
from commands import _matches_system_command, _execute_system_action


# ------------------------------------------------------------------------
# F.R.I.D.A.Y. Core orchestration
# ------------------------------------------------------------------------

from core import (
    ContextManager,
    PermissionManager,
    TaskExecutor,
    TaskPlanner,
    TaskRouter,
    TaskVerifier,
    ToolRegistry,
)


# ------------------------------------------------------------------------
# Exit phrases
# ------------------------------------------------------------------------

# Whole-utterance matches only, so:
# "how do I exit vim"
# will NOT shut down F.R.I.D.A.Y.

EXIT_PHRASES = {
    "exit",
    "quit",
    "goodbye",
    "good bye",
    "bye friday",
    "friday bye",
    "friday exit",
    "friday stop listening",

    # Telugu / Hindi
    "aagipo",
    "band cheyyi",
    "band karo",
    "bandh karo",
    "alvida",
    "sari bye",
    "వీడ్కోలు",
    "బై",
    "अलविदा",
}


GOODBYE = {
    "en": "Understood, Boss.",
    "te": "అలాగే బాస్, తర్వాత కలుద్దాం.",
    "hi": "ठीक है Boss, फिर मिलेंगे。",
}


# ------------------------------------------------------------------------
# Signal handling
# ------------------------------------------------------------------------

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


# ------------------------------------------------------------------------
# Command helpers
# ------------------------------------------------------------------------

def _is_exit_command(text: str) -> bool:
    cleaned = text.lower().strip().strip(
        string.punctuation + " "
    )

    return cleaned in EXIT_PHRASES


def _is_repeat_command(text: str) -> bool:
    cleaned = text.lower().strip()

    if not cleaned:
        return False

    if cleaned in {
        "again",
        "once more",
        "one more time",
        "repeat",
        "do it again",
        "do that again",
        "do it once more",
        "do the same",
        "do the same again",
    }:
        return True

    return any(
        phrase in cleaned
        for phrase in (
            "repeat that",
            "repeat it",
            "repeat again",
            "do that again",
            "do it again",
            "do the same again",
            "do the same",
            "once more",
            "ek baar aur",
            "malli cheyy",
            "malli cheyyi",
            "phir se",
            "phir se karo",
            "dubara karo",
            "again do",
        )
    )


def _matches_full_power(text: str) -> bool:
    """Detect a request to give F.R.I.D.A.Y. full access."""

    cleaned = text.lower().strip()

    if not cleaned:
        return False

    if _matches_full_power_off(text):
        return False

    if re.match(
        r"^(?:what|how|why|when|which|where|is|are|do you)",
        cleaned,
    ):
        return False

    if cleaned in {
        "admin mode",
        "admin",
        "admin mode on",
        "god mode",
        "full access",
        "master mode",
        "super user",
        "unlock all",
    }:
        return True

    return any(
        phrase in cleaned
        for phrase in (
            "full power",
            "full access",
            "full control",
            "admin mode",
            "give it powers",
            "give friday powers",
            "give yourself powers",
            "give it full power",
            "give friday full power",
            "give yourself full power",
            "give it full access",
            "give friday full access",
            "grant you full access",
            "grant full access",
            "you have full control",
            "unlock all powers",
            "unlock everything",
            "activate full power",
            "super power mode",
            "full power ivvu",
            "full power ivi",
            "full power karo",
            "full access ivvu",
            "full access do",
            "full access karo",
            "poora power do",
            "poori shakti do",
        )
    )


def _matches_full_power_off(text: str) -> bool:
    """Detect a request to revoke F.R.I.D.A.Y.'s full access."""

    cleaned = text.lower().strip()

    if not cleaned:
        return False

    return any(
        phrase in cleaned
        for phrase in (
            "revoke full access",
            "remove full power",
            "remove full access",
            "disable full access",
            "disable admin mode",
            "turn off full access",
            "turn off the powers",
            "take away the powers",
            "remove the powers",
            "revoke the powers",
            "revoke powers",
            "reset the permissions",
            "lock everything down",
            "stop admin mode",
            "full access band",
            "full power band",
            "power band chey",
            "full access hatavandi",
        )
    )


def _style_hint(result):
    """Only send a style note for non-English speech."""

    if result.code == "en" and not result.is_mixed:
        return None

    return result.label()


# ------------------------------------------------------------------------
# Terminal text worker
# ------------------------------------------------------------------------

def text_worker(text_queue):
    """Background thread to read text commands from the terminal."""

    from voice.language import analyze
    from voice.audio import (
        is_shutting_down,
        request_shutdown,
    )

    while not is_shutting_down():

        try:
            # We don't print a prompt here to avoid messing up
            # the voice logs.
            #
            # The user can just start typing at any time.
            cmd = input().strip()

            if cmd:
                result = analyze(cmd)

                text_queue.put(
                    (
                        cmd,
                        result.code,
                        result,
                    )
                )

        except KeyboardInterrupt:
            request_shutdown()
            break

        except (EOFError, RuntimeError):
            # No console attached, e.g. running via pythonw.exe
            break


# ------------------------------------------------------------------------
# Webview API
# ------------------------------------------------------------------------

class WebviewApi:

    def __init__(self, text_queue):
        self.text_queue = text_queue
        self.window = None
        self.overlay_window = None

        self.ui_state = {
            "phase": "idle",
            "messages": [],
            "overlay_messages": [],
            "micOn": True,
        }

    def get_updates(self):
        updates = {
            "phase": self.ui_state["phase"],
            "messages": self.ui_state["messages"].copy(),
            "micOn": self.ui_state.get(
                "micOn",
                True,
            ),
        }

        self.ui_state["messages"].clear()

        return updates

    def get_overlay_updates(self):
        updates = {
            "phase": self.ui_state["phase"],
            "messages": self.ui_state["overlay_messages"].copy(),
            "micOn": self.ui_state.get("micOn", True),
        }
        self.ui_state["overlay_messages"].clear()
        return updates

    def move_overlay(self, x, y):
        if self.overlay_window:
            self.overlay_window.move(int(x), int(y))

    def move_overlay_by(self, dx, dy):
        if self.overlay_window:
            self.overlay_window.move(self.overlay_window.x + int(dx), self.overlay_window.y + int(dy))

    def get_overlay_position(self):
        if self.overlay_window:
            return {"x": self.overlay_window.x, "y": self.overlay_window.y}
        return {"x": 0, "y": 0}

    def resize_overlay(self, width, height):
        if self.overlay_window:
            self.overlay_window.resize(int(width), int(height))

    def hide_overlay(self):
        if self.overlay_window:
            self.overlay_window.hide()

    def show_overlay(self):
        if self.overlay_window:
            self.overlay_window.show()

    def set_phase(self, phase):
        self.ui_state["phase"] = phase

    def push_message(self, kind, text):
        msg = {
            "kind": kind,
            "text": text,
        }
        self.ui_state["messages"].append(msg)
        self.ui_state["overlay_messages"].append(msg)

    def send_command(self, text):
        from voice.language import analyze

        result = analyze(text)

        self.text_queue.put(
            (
                text,
                result.code,
                result,
                True,
            )
        )

    def toggle_mic(self):
        current = self.ui_state.get(
            "micOn",
            True,
        )

        self.ui_state["micOn"] = not current

        print(
            "UI requested mic toggle. Now: "
            f"{'ON' if self.ui_state['micOn'] else 'OFF'}"
        )

        if not self.ui_state["micOn"]:
            self.text_queue.put(
                (
                    "",
                    "en",
                )
            )

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


# ------------------------------------------------------------------------
# Main F.R.I.D.A.Y. logic
# ------------------------------------------------------------------------

def _friday_logic(api, text_queue):

    import threading
    import queue
    import json
    import traceback

    from voice.audio import is_shutting_down

    # Show the UI is alive immediately, before any heavy init that
    # could hang. This guarantees the HUD never sits blank/stuck.
    api.set_phase("idle")
    api.push_message(
        "friday",
        "F.R.I.D.A.Y. is starting up, Boss.",
    )

    # Startup diagnostics: every stage prints with an elapsed timestamp
    # so a hang is immediately visible in the launcher console.
    import time as _time
    _startup_start = _time.perf_counter()
    _stage_count = 0

    def _stage(name):
        nonlocal _stage_count
        _stage_count += 1
        _elapsed = (
            _time.perf_counter() - _startup_start
        ) * 1000
        print(
            f"[STARTUP {_stage_count}] {name} "
            f"({_elapsed:.0f}ms)"
        )

    _stage("friday_logic entered")

    # ------------------------------------------------------------
    # Initialize core systems
    # ------------------------------------------------------------

    _stage("begin: VoiceListener()")
    try:
        listener = VoiceListener()
    except Exception as e:
        api.set_phase("error")
        api.push_message("friday", f"Voice init failed: {e}")
        traceback.print_exc()
        return
    _stage("done: VoiceListener()")

    _stage("begin: FridayBrain()")
    try:
        brain = FridayBrain()
    except Exception as e:
        api.set_phase("error")
        api.push_message("friday", f"Brain init failed: {e}")
        traceback.print_exc()
        return
    _stage("done: FridayBrain()")

    # Persistent memory system
    _stage("begin: MemoryManager()")
    try:
        memory = MemoryManager()
    except Exception as e:
        api.set_phase("error")
        api.push_message("friday", f"Memory init failed: {e}")
        traceback.print_exc()
        return
    _stage("done: MemoryManager()")

    # ------------------------------------------------------------
    # F.R.I.D.A.Y. Core orchestration
    # ------------------------------------------------------------

    try:
        registry = ToolRegistry()

        # Existing application launcher registered as a core tool.
        registry.register(
            "app_control",
            "Open, launch, close, and manage Windows applications",
            handle_app_command,
        )

        registry.register(
            "pc_control",
            "Control PC volume, brightness, and basic window state",
            handle_pc_control_command,
        )

        registry.register(
            "browser",
            "Search the web, open websites, and run browser searches",
            handle_browser_command,
        )

        registry.register(
            "messaging",
            "Send WhatsApp messages to a contact",
            handle_messaging_command,
        )

        # ------------------------------------------------------------
        # Phase 3: Computer Vision + Computer Use
        # ------------------------------------------------------------
        def screen_vision_handler(command, language="en"):
            return handle_screen_vision_command(command, language=language, context=context)
        def computer_use_handler(command, language="en"):
            return handle_computer_use_command(command, language=language, context=context)
        registry.register(
            "screen_vision",
            "Read-only screen understanding: describe what is on the screen",
            screen_vision_handler,
        )
        registry.register(
            "computer_use",
            "Screen-aware computer use: click, type, scroll, drag on the visible UI",
            computer_use_handler,
        )

        def system_control_handler(command, language="en"):
            action = _matches_system_command(command)
            if not action:
                return "Unknown system action."
            return _execute_system_action(action, language)

        registry.register(
            "system_control",
            "Restart, shutdown, sleep, or log out of the PC",
            system_control_handler,
        )

        # Create core orchestration objects.
        router = TaskRouter(registry)
        planner = TaskPlanner()
        permissions = PermissionManager()
        executor = TaskExecutor(registry, router, permissions=permissions)
        verifier = TaskVerifier()
        context = ContextManager()

        verifier.register(
            "computer_use",
            lambda result=False: (
                bool(result)
                if isinstance(result, bool)
                else bool(result and not str(result).lower().startswith(("couldn't", "could not", "unable", "error", "failed", "can't", "cannot")))
            ),
        )

        # Interruption / barge-in controller
        _stage("begin: InterruptionController()")
        interrupter = InterruptionController()
        _stage("done: all core systems")

    except Exception as e:
        api.set_phase("error")
        api.push_message("friday", f"Tool init failed: {e}")
        traceback.print_exc()
        return

    # Remembers the last request so "do that again" can repeat it.
    last_command: str | None = None
    last_command_lang: str = "en"

    # Full-access mode turns every tool into a no-confirmation action.
    full_access = False

    # Finish startup instantly and push the online message right away.
    api.set_phase("idle")

    api.push_message(
        "friday",
        "F.R.I.D.A.Y. is online, Boss.",
    )

    _stage("online message pushed")

    # ------------------------------------------------------------
    # Main command loop
    # ------------------------------------------------------------

    try:

        while not is_shutting_down():

            # ----------------------------------------------------
            # Microphone OFF
            # ----------------------------------------------------

            if not api.ui_state.get(
                "micOn",
                True,
            ):

                api.set_phase("idle")

                try:

                    item = text_queue.get(
                        timeout=0.5
                    )

                    command = item[0]
                    language = item[1]

                    result = (
                        item[2]
                        if len(item) > 2
                        else None
                    )

                    skip_push = (
                        item[3]
                        if len(item) > 3
                        else False
                    )

                    if command:

                        listener.last_result = result

                        print(
                            f"You (typed): {command}"
                        )

                except queue.Empty:

                    command = ""
                    skip_push = False

            # ----------------------------------------------------
            # Microphone ON
            # ----------------------------------------------------

            else:

                api.set_phase("listening")

                try:

                    # First check whether the UI sent a
                    # typed command.
                    item = text_queue.get_nowait()

                    command = item[0]
                    language = item[1]

                    result = (
                        item[2]
                        if len(item) > 2
                        else None
                    )

                    skip_push = (
                        item[3]
                        if len(item) > 3
                        else False
                    )

                    if command:

                        listener.last_result = result

                        print(
                            f"You (typed): {command}"
                        )

                except queue.Empty:

                    # Otherwise listen to microphone.
                    command, language = listener.listen(
                        text_queue=text_queue
                    )

                    skip_push = False

            # ----------------------------------------------------
            # Ignore empty commands
            # ----------------------------------------------------

            if not command:
                continue

            # ----------------------------------------------------
            # Push user message to UI
            # ----------------------------------------------------

            if not skip_push:

                api.push_message(
                    "user",
                    command,
                )

            # ----------------------------------------------------
            # Unauthorized speaker
            # ----------------------------------------------------

            if command == "UNAUTHORIZED_SPEAKER":

                print(
                    "F.R.I.D.A.Y.: "
                    "Unauthorized speaker detected."
                )

                speak(
                    "Unauthorized speaker detected, Boss.",
                    hint="en",
                )

                continue

            # ----------------------------------------------------
            # Get latest language result
            # ----------------------------------------------------

            result = listener.last_result

            # ----------------------------------------------------
            # Update short-term context
            # ------------------------------------------------------------

            context.update_command(
                command,
                language=language,
            )

            # ----------------------------------------------------
            # Exit command
            # ----------------------------------------------------

            if _is_exit_command(command):

                speak(
                    GOODBYE.get(
                        language,
                        GOODBYE["en"],
                    ),
                    hint=language,
                )

                break

            # ----------------------------------------------------
            # Full access: "give friday full power"
            # ----------------------------------------------------

            if _matches_full_power_off(command):

                from core.permission import PermissionLevel

                defaults = {
                    "pc_control": PermissionLevel.SAFE,
                    "app_control": PermissionLevel.SAFE,
                    "messaging": PermissionLevel.CONFIRM,
                    "browser": PermissionLevel.SAFE,
                    "files": PermissionLevel.CONFIRM,
                    "system_control": PermissionLevel.HIGH_RISK,
                }

                for tool_name, level in defaults.items():
                    permissions.set_level(tool_name, level)

                full_access = False

                print("[POWERS] Full access revoked")
                speak(
                    "Full access removed, Boss. "
                    "I will ask before risky actions again.",
                    hint="en",
                )

                continue

            if _matches_full_power(command):

                from core.permission import PermissionLevel

                if not full_access:

                    for tool_name in permissions.tools():
                        permissions.set_level(
                            tool_name,
                            PermissionLevel.SAFE,
                        )

                    full_access = True

                    print("[POWERS] Full access enabled")
                    speak(
                        "Full access granted, Boss. "
                        "I can now do anything you ask.",
                        hint="en",
                    )

                    continue

                speak(
                    "You already gave me full access, Boss.",
                    hint="en",
                )

                continue

            # ----------------------------------------------------
            # Repeat last action: "do that again"
            # ----------------------------------------------------

            if _is_repeat_command(command):

                if last_command is not None:

                    print(
                        f"[REPEAT] repeating: "
                        f"{last_command}"
                    )
                    command = last_command
                    language = last_command_lang

                else:

                    speak(
                        "You haven't asked me "
                        "to do anything yet, Boss.",
                        hint="en",
                    )

                    continue

            else:

                last_command = command
                last_command_lang = language

            # ----------------------------------------------------
            # Thinking phase
            # ----------------------------------------------------

            api.set_phase("thinking")

            # ====================================================
            # F.R.I.D.A.Y. ORCHESTRATION PIPELINE
            # ====================================================

            answer = None

            try:
                import core.nlu
                nlu_analyzer = core.nlu.NLUAnalyzer()
                intent_res = nlu_analyzer.analyze(command, language)

                if intent_res.is_ambiguous:
                    answer = intent_res.clarification
                elif intent_res.intent:
                    serialized = core.nlu.serialize_intent(intent_res, context)
                    if intent_res.is_ambiguous:
                        answer = intent_res.clarification
                    elif serialized:
                        print(f"[NLU] Converted: '{command}' -> '{serialized}' (Intent: {intent_res.intent})")
                        command = serialized
                        language = intent_res.language

            except Exception as error:
                # A broken NLU parse must never freeze the assistant.
                print(
                    f"[NLU] analysis failed "
                    f"({type(error).__name__}): {error}"
                )
            
            # 1. Check for pending confirmations FIRST
            try:
                pending_tool = context.get_metadata("pending_tool")
                pending_cmd = context.get_metadata("pending_command")
                
                if pending_tool:
                    context.set_metadata("pending_tool", None)
                    context.set_metadata("pending_command", None)
                    
                    from commands import _is_confirmation_yes
                    if _is_confirmation_yes(command):
                        print(f"[EXECUTOR] executing confirmed tool: {pending_tool}")
                        from core.permission import PermissionLevel
                        old_level = permissions.get_level(pending_tool)
                        permissions.set_level(pending_tool, PermissionLevel.SAFE)
                        
                        plan = planner.create_plan(pending_cmd, language)
                        exec_result = executor.execute_plan(plan)
                        
                        permissions.set_level(pending_tool, old_level)
                        
                        if exec_result.success:
                            answer = exec_result.results[-1]
                            verify_res = verifier.verify(pending_tool, answer)
                            print(f"[VERIFIER] { 'success' if verify_res.success else 'verification failure' }")
                            context.set_result(answer)
                        else:
                            answer = f"Error: {exec_result.error}"
                            print("[VERIFIER] failure")
                    else:
                        if language == "te": answer = "క్యాన్సిల్ చేశాను."
                        elif language == "hi": answer = "कैंसिल कर दिया।"
                        else: answer = "Cancelled."
                
                # 2. Try routing if no answer yet
                if answer is None:
                    route = router.route(command)
                    
                    if route.tool_name is not None:
                        context.set_tool(route.tool_name)
                        print(f"[ROUTER] {route.tool_name}")
                        
                        plan = planner.create_plan(command, language)
                        print(f"[PLANNER] {len(plan.steps)} step")
                        
                        exec_result = executor.execute_plan(plan)
                        print(f"[EXECUTOR] {route.tool_name}")
                        
                        if getattr(exec_result, "requires_confirmation", False):
                            context.set_metadata("pending_tool", exec_result.tool_name)
                            context.set_metadata("pending_command", command)
                            
                            if exec_result.tool_name == "system_control":
                                from commands import _matches_system_command, _get_confirmation_prompt
                                action = _matches_system_command(command)
                                answer = _get_confirmation_prompt(action, language)
                            else:
                                answer = "Are you sure you want to do that?"
                            print("[VERIFIER] confirmation required")
                        elif not exec_result.success:
                            answer = f"Error: {exec_result.error}"
                            print("[VERIFIER] failure")
                        else:
                            answer = exec_result.results[-1]
                            verify_res = verifier.verify(route.tool_name, answer)
                            print(f"[VERIFIER] { 'success' if verify_res.success else 'verification failure' }")
                            context.set_result(answer)

            except Exception as error:
                # A tool failure must never freeze the assistant; fall
                # through to local commands / the AI brain.
                print(
                    f"[EXECUTOR] tool pipeline failed "
                    f"({type(error).__name__}): {error}"
                )

            # ====================================================
            # MEMORY SYSTEM
            # ====================================================

            try:
                memory.consider(command)
            except Exception as error:
                print(
                    "F.R.I.D.A.Y.: "
                    "Memory consideration failed "
                    f"({type(error).__name__})."
                )

            # ====================================================
            # LOCAL COMMANDS FIRST
            # ====================================================

            if answer is None:
                try:
                    answer = handle_local_command(
                        command,
                        language,
                        memory=memory,
                    )
                except Exception as error:
                    print(
                        f"[LOCAL] command failed "
                        f"({type(error).__name__}): {error}"
                    )

            # ====================================================
            # AI BRAIN
            # ====================================================

            if answer is None:
                try:
                    answer = brain.ask(
                        command,
                        style=_style_hint(result),
                        language=language,
                        memory=memory,
                    )
                except Exception as e:
                    print(f"Brain execution failed: {e}")
                    answer = "I couldn't determine which tool should handle that."

            # ----------------------------------------------------
            # Store assistant response in short-term context
            # ----------------------------------------------------

            context.add_turn(
                user=command,
                assistant=answer,
                language=language,
            )

            # ----------------------------------------------------
            # Print answer
            # ----------------------------------------------------

            try:

                print(
                    "F.R.I.D.A.Y.:",
                    answer,
                )

            except UnicodeEncodeError:

                print(
                    "F.R.I.D.A.Y.:",
                    answer.encode(
                        "ascii",
                        "replace",
                    ).decode("ascii"),
                )

            # ----------------------------------------------------
            # Listen for barge-in while speaking
            # ----------------------------------------------------

            interrupter.reset()

            interrupter.tune(
                listener.recognizer.energy_threshold
            )

            interrupter.start()

            try:

                api.push_message(
                    "friday",
                    answer,
                )

                api.set_phase(
                    "speaking"
                )

                speak(
                    answer,
                    hint=language,
                )

            finally:

                interrupter.stop()

                api.set_phase(
                    "idle"
                )

            # ----------------------------------------------------
            # Interruption response
            # ----------------------------------------------------

            if interrupter.was_interrupted():

                print(
                    "F.R.I.D.A.Y.: "
                    "Go ahead, Boss."
                )

                api.set_phase(
                    "listening"
                )

    # ----------------------------------------------------------------
    # Clean shutdown
    # ----------------------------------------------------------------

    except KeyboardInterrupt:

        print(
            "\nF.R.I.D.A.Y.: "
            "Shutting down, Boss."
        )

    except Exception as e:

        import traceback

        print(
            "\nError in background thread:"
        )

        traceback.print_exc()

        try:
            api.set_phase("error")
            api.push_message(
                "friday",
                f"Something went wrong: {e}",
            )
        except Exception:
            pass

    finally:

        from voice.audio import (
            request_shutdown,
            mic_hub,
        )

        from voice.speaker import shutdown_audio

        request_shutdown()

        interrupter.stop()

        listener.close()

        shutdown_audio()

        mic_hub.release()

        print(
            "F.R.I.D.A.Y.: Offline."
        )

        if api.window:

            api.window.destroy()


# ------------------------------------------------------------------------
# Application entry point
# ------------------------------------------------------------------------

def main():

    import threading
    import queue
    import webview
    import logging

    # Suppress harmless but noisy COM warnings from pywebview's
    # internal logger.
    logging.getLogger(
        "pywebview"
    ).setLevel(
        logging.CRITICAL
    )

    _install_signal_handlers()

    # ------------------------------------------------------------
    # Shared command queue
    # ------------------------------------------------------------

    text_queue = queue.Queue()

    # ------------------------------------------------------------
    # Terminal input worker
    # ------------------------------------------------------------

    t = threading.Thread(
        target=text_worker,
        args=(text_queue,),
        daemon=True,
    )

    t.start()

    print(
        "F.R.I.D.A.Y.: "
        "You can speak, or type a command "
        "and press Enter at any time."
    )

    # ------------------------------------------------------------
    # Create UI API
    # ------------------------------------------------------------

    api = WebviewApi(
        text_queue
    )

    # ------------------------------------------------------------
    # Locate UI
    # ------------------------------------------------------------

    import pathlib

    if getattr(
        sys,
        "frozen",
        False,
    ):

        # Running as compiled PyInstaller executable
        base_dir = sys._MEIPASS

    else:

        # Running from source
        base_dir = os.path.dirname(
            os.path.abspath(__file__)
        )

    ui_path = os.path.join(
        base_dir,
        "ui",
        "dist",
        "index.html",
    )

    # ------------------------------------------------------------
    # Check UI build
    # ------------------------------------------------------------

    if not os.path.exists(ui_path):

        print(
            f"UI not built. Could not find {ui_path}. "
            "Please run 'npm run build' in the ui folder."
        )

        return

    # ------------------------------------------------------------
    # Create WebView
    # ------------------------------------------------------------

    window_url = pathlib.Path(
        ui_path
    ).as_uri()

    window = webview.create_window(
        "F.R.I.D.A.Y.",
        window_url,
        js_api=api,
        width=1200,
        height=800,
        frameless=False,
        easy_drag=False,
    )

    api.window = window

    overlay_path = os.path.join(base_dir, "overlay.html")
    if os.path.exists(overlay_path):
        overlay_url = pathlib.Path(overlay_path).as_uri()
        overlay_window = webview.create_window(
            "F.R.I.D.A.Y. Core",
            overlay_url,
            js_api=api,
            width=100,
            height=100,
            frameless=True,
            transparent=True,
            on_top=True,
            easy_drag=False,
        )
        api.overlay_window = overlay_window

    # ------------------------------------------------------------
    # Background logic thread
    # ------------------------------------------------------------

    # IMPORTANT: the logic thread is started directly, NOT from a
    # window's `loaded` event. If that event never fires (WebView2
    # first-run, runtime issues), starting from `loaded` leaves the HUD
    # stuck on its loading screen with no logic running. Starting
    # unconditionally guarantees initialization always happens.
    # All window/overlay manipulation has been removed from this thread
    # (it previously called hide()/evaluate_js() from here, which raced
    # the GUI loop and bounced focus between the on-top overlay and the
    # main window, freezing the UI as "not responding").
    logic_thread = threading.Thread(
        target=_friday_logic,
        args=(
            api,
            text_queue,
        ),
        daemon=True,
    )
    logic_thread.start()

    # ------------------------------------------------------------
    # Start WebView
    # ------------------------------------------------------------

    # Hide the always-on-top overlay once it is loaded so it can never
    # sit over the main window or steal its focus/activation. This runs
    # on the GUI thread via the overlay's `loaded` callback (no focus
    # bounce, no race with the loop startup).
    if api.overlay_window is not None:
        def _hide_overlay():
            try:
                api.overlay_window.hide()
            except Exception:
                pass
        api.overlay_window.events.loaded += _hide_overlay

    # DIAGNOSTIC heartbeat: proves the process stays alive inside the
    # GUI loop even if the window is somehow invisible. When relaunched
    # by the bootstrap, these prints land in friday_boot.log.
    def _beat():
        n = 0
        while True:
            time.sleep(10)
            n += 1
            print(
                f"HEARTBEAT {n} alive at {time.strftime('%H:%M:%S')}",
                flush=True,
            )

    threading.Thread(target=_beat, daemon=True).start()

    print("MAIN: entering webview.start()", flush=True)
    try:
        webview.start()
        print("MAIN: webview.start() returned - GUI loop ended", flush=True)
    except Exception as e:
        print(
            "MAIN: webview.start() raised: "
            f"{type(e).__name__}: {e}",
            flush=True,
        )
        raise
    print("MAIN: main() exiting", flush=True)


# ------------------------------------------------------------------------
# Python entry point
# ------------------------------------------------------------------------

if __name__ == "__main__":
    main()