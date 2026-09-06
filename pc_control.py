"""
Local Windows controls for F.R.I.D.A.Y.

This module handles explicit PC-control commands without sending them to the
AI brain: volume, brightness, media keys, window shortcuts, clipboard,
screenshots, mouse clicks, and simple typing into the active window.
"""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
import time
from pathlib import Path


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800

VK = {
    "BACKSPACE": 0x08,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "SHIFT": 0x10,
    "CTRL": 0x11,
    "ALT": 0x12,
    "ESC": 0x1B,
    "SPACE": 0x20,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "PRINTSCREEN": 0x2C,
    "LWIN": 0x5B,
    "A": 0x41,
    "C": 0x43,
    "D": 0x44,
    "M": 0x4D,
    "S": 0x53,
    "V": 0x56,
    "X": 0x58,
    "Y": 0x59,
    "Z": 0x5A,
    "F4": 0x73,
    "VOLUME_MUTE": 0xAD,
    "VOLUME_DOWN": 0xAE,
    "VOLUME_UP": 0xAF,
    "MEDIA_NEXT": 0xB0,
    "MEDIA_PREV": 0xB1,
    "MEDIA_STOP": 0xB2,
    "MEDIA_PLAY_PAUSE": 0xB3,
}

PRESSABLE_KEYS = {
    "enter": "ENTER",
    "return": "ENTER",
    "escape": "ESC",
    "esc": "ESC",
    "tab": "TAB",
    "space": "SPACE",
    "backspace": "BACKSPACE",
    "left": "LEFT",
    "right": "RIGHT",
    "up": "UP",
    "down": "DOWN",
}

WAKE_WORD = re.compile(
    r"^(?:hey\s+)?(?:friday|fraiday|fry\s*day|fryday)[,.\s]*",
    re.IGNORECASE,
)


def _dry_run() -> bool:
    return os.environ.get("FRIDAY_DRY_RUN_PC_CONTROL") == "1"


def _norm(text: str) -> str:
    text = WAKE_WORD.sub("", text or "").lower()
    text = re.sub(r"[^a-z0-9% ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for wrong in ("vloume", "volum", "valume", "volium", "wolume"):
        text = text.replace(wrong, "volume")
    return text


def _has(text: str, *phrases: str) -> bool:
    return any(phrase in text for phrase in phrases)


def _first_number(text: str) -> int | None:
    match = re.search(r"\b(\d{1,3})\b", text)
    if not match:
        return None
    return max(0, min(100, int(match.group(1))))


def _steps_from_text(text: str, default: int = 4) -> int:
    value = _first_number(text)
    if value is None:
        return default
    return max(1, min(50, round(value / 2)))


def _tap_key(vk: int, times: int = 1, delay: float = 0.035) -> None:
    if _dry_run():
        return

    user32 = ctypes.windll.user32
    for _ in range(max(1, times)):
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(delay)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(delay)


def _combo(*keys: str) -> None:
    if _dry_run():
        return

    user32 = ctypes.windll.user32
    codes = [VK[key] for key in keys]
    for code in codes:
        user32.keybd_event(code, 0, 0, 0)
        time.sleep(0.012)
    for code in reversed(codes):
        user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.012)


def _mouse(flags: int, data: int = 0) -> None:
    if _dry_run():
        return
    ctypes.windll.user32.mouse_event(flags, 0, 0, data, 0)


def _run_powershell(script: str, *args: str, timeout: int = 5) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )


def _get_brightness() -> int | None:
    if _dry_run():
        return 50

    script = (
        "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness "
        "-ErrorAction Stop | Select-Object -First 1 -ExpandProperty CurrentBrightness"
    )
    try:
        result = _run_powershell(script, timeout=4)
        if result.returncode != 0:
            return None
        match = re.search(r"\d+", result.stdout)
        return int(match.group(0)) if match else None
    except Exception:
        return None


def _set_brightness(level: int) -> bool:
    level = max(0, min(100, int(level)))
    if _dry_run():
        return True

    script = (
        "$level=[int]$args[0]; "
        "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods "
        "-ErrorAction Stop | Invoke-CimMethod -MethodName WmiSetBrightness "
        "-Arguments @{Timeout=1;Brightness=$level} | Out-Null"
    )
    try:
        result = _run_powershell(script, str(level), timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def _set_clipboard(value: str) -> bool:
    if _dry_run():
        return True

    try:
        result = _run_powershell("Set-Clipboard -Value $args[0]", value, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def _get_clipboard() -> str | None:
    if _dry_run():
        return "Dry run clipboard text."

    try:
        result = _run_powershell("Get-Clipboard -Raw", timeout=5)
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception:
        return None


def _paste_text(value: str) -> bool:
    if not value:
        return False
    if not _set_clipboard(value):
        return False
    _combo("CTRL", "V")
    return True


def _volume_to(target: int) -> None:
    target = max(0, min(100, int(target)))
    if target <= 0:
        _tap_key(VK["VOLUME_DOWN"], 50)
        return
    if target >= 100:
        _tap_key(VK["VOLUME_UP"], 50)
        return
    _tap_key(VK["VOLUME_DOWN"], 50)
    _tap_key(VK["VOLUME_UP"], max(1, round(target / 2)))


def _screenshot_path() -> str:
    pictures = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Pictures"
    return str(pictures / "Screenshots")


def _strip_type_prefix(command: str) -> str | None:
    cleaned = WAKE_WORD.sub("", command or "").strip()
    match = re.match(
        r"(?is)^(?:type|write|enter text|paste text|type this|write this)\s+(.+)$",
        cleaned,
    )
    if not match:
        return None
    return match.group(1).strip()


def handle_pc_control_command(command: str, language: str = "en") -> str | None:
    """
    Execute an explicit local PC-control command.

    Returns a spoken response, or None if the command is not a PC-control
    request. The language parameter is accepted for the same public shape as
    the other local command handlers; responses stay short and direct.
    """

    if not command:
        return None

    text = _norm(command)
    if not text:
        return None

    # Volume and sound.
    if _has(text, "unmute", "sound on", "audio on"):
        _tap_key(VK["VOLUME_MUTE"])
        return "Sound is back on, Boss."

    if text == "mute" or _has(text, "mute volume", "mute sound", "sound off", "audio off"):
        _tap_key(VK["VOLUME_MUTE"])
        return "Muted, Boss."

    if _has(text, "set volume", "volume to", "volume at", "make volume", "sound to"):
        target = _first_number(text)
        if target is not None:
            _volume_to(target)
            return f"Volume set near {target} percent, Boss."

    if _has(text, "increase volume", "volume up", "raise volume", "sound up", "louder", "awaz badhao", "volume badhao", "volume penchu"):
        _tap_key(VK["VOLUME_UP"], _steps_from_text(text))
        return "Volume increased, Boss."

    if _has(text, "decrease volume", "volume down", "lower volume", "reduce volume", "quieter", "awaz kam", "volume kam", "volume tagginchu"):
        _tap_key(VK["VOLUME_DOWN"], _steps_from_text(text))
        return "Volume decreased, Boss."

    # Brightness via monitor WMI, when the display exposes it.
    if _has(text, "set brightness", "brightness to", "brightness at", "make brightness"):
        target = _first_number(text)
        if target is not None:
            if _set_brightness(target):
                return f"Brightness set to {target} percent, Boss."
            return "Brightness control is not available on this display, Boss."

    if _has(text, "increase brightness", "brightness up", "raise brightness", "brighter"):
        current = _get_brightness()
        if current is None:
            return "Brightness control is not available on this display, Boss."
        target = min(100, current + max(5, _first_number(text) or 10))
        if _set_brightness(target):
            return f"Brightness increased to {target} percent, Boss."
        return "Brightness control is not available on this display, Boss."

    if _has(text, "decrease brightness", "brightness down", "lower brightness", "reduce brightness", "dimmer"):
        current = _get_brightness()
        if current is None:
            return "Brightness control is not available on this display, Boss."
        target = max(0, current - max(5, _first_number(text) or 10))
        if _set_brightness(target):
            return f"Brightness decreased to {target} percent, Boss."
        return "Brightness control is not available on this display, Boss."

    # Media keys.
    if _has(text, "play pause", "pause music", "play music", "pause video", "play video", "pause media", "resume media"):
        _tap_key(VK["MEDIA_PLAY_PAUSE"])
        return "Toggled playback, Boss."

    if _has(text, "next song", "next track", "next video", "skip song", "skip track"):
        _tap_key(VK["MEDIA_NEXT"])
        return "Skipped forward, Boss."

    if _has(text, "previous song", "previous track", "last song", "last track", "go back track"):
        _tap_key(VK["MEDIA_PREV"])
        return "Went back, Boss."

    if _has(text, "stop music", "stop media", "stop playback", "stop video"):
        _tap_key(VK["MEDIA_STOP"])
        return "Playback stopped, Boss."

    # Window and desktop shortcuts.
    if _has(text, "show desktop", "go to desktop"):
        _combo("LWIN", "D")
        return "Desktop shown, Boss."

    if _has(text, "minimize all", "hide all windows"):
        _combo("LWIN", "M")
        return "All windows minimized, Boss."

    if _has(text, "restore windows", "bring back windows"):
        _combo("LWIN", "SHIFT", "M")
        return "Windows restored, Boss."

    if _has(text, "maximize window", "maximize this window", "maximize current window"):
        _combo("LWIN", "UP")
        return "Window maximized, Boss."

    if _has(text, "minimize window", "minimize this window", "minimize current window"):
        _combo("LWIN", "DOWN")
        return "Window minimized, Boss."

    if _has(text, "close window", "close current window", "close this window"):
        _combo("ALT", "F4")
        return "Window close command sent, Boss."

    if _has(text, "lock pc", "lock computer", "lock the pc", "lock the computer", "lock screen"):
        if not _dry_run():
            ctypes.windll.user32.LockWorkStation()
        return "Locked, Boss."

    # Clipboard and editing shortcuts.
    if text in {"copy", "copy this", "copy selected", "copy selection"}:
        _combo("CTRL", "C")
        return "Copied, Boss."

    if text in {"paste", "paste it", "paste this"}:
        _combo("CTRL", "V")
        return "Pasted, Boss."

    if text in {"cut", "cut this", "cut selected", "cut selection"}:
        _combo("CTRL", "X")
        return "Cut, Boss."

    if text in {"select all", "select everything"}:
        _combo("CTRL", "A")
        return "Selected all, Boss."

    if text in {"undo", "undo that"}:
        _combo("CTRL", "Z")
        return "Undone, Boss."

    if text in {"redo", "redo that"}:
        _combo("CTRL", "Y")
        return "Redone, Boss."

    if text in {"save", "save this", "save file", "save current file"}:
        _combo("CTRL", "S")
        return "Saved, Boss."

    if _has(text, "read clipboard", "what is on clipboard", "whats on clipboard"):
        value = _get_clipboard()
        if not value:
            return "The clipboard looks empty, Boss."
        if len(value) > 180:
            value = value[:180].rstrip() + "..."
        return f"Clipboard says: {value}"

    if _has(text, "clear clipboard", "empty clipboard"):
        if _set_clipboard(""):
            return "Clipboard cleared, Boss."
        return "I could not clear the clipboard, Boss."

    typed = _strip_type_prefix(command)
    if typed is not None:
        if _paste_text(typed):
            return "Typed it, Boss."
        return "I could not type that, Boss."

    # Screenshots, pointer clicks and scrolling.
    if _has(text, "take screenshot", "capture screen", "screenshot"):
        _combo("LWIN", "PRINTSCREEN")
        return f"Screenshot command sent, Boss. Check {_screenshot_path()}."

    if text in {"click", "left click", "mouse click"}:
        _mouse(MOUSEEVENTF_LEFTDOWN)
        time.sleep(0.025)
        _mouse(MOUSEEVENTF_LEFTUP)
        return "Clicked, Boss."

    if text in {"double click", "double left click"}:
        for _ in range(2):
            _mouse(MOUSEEVENTF_LEFTDOWN)
            time.sleep(0.025)
            _mouse(MOUSEEVENTF_LEFTUP)
            time.sleep(0.08)
        return "Double clicked, Boss."

    if text in {"right click", "mouse right click"}:
        _mouse(MOUSEEVENTF_RIGHTDOWN)
        time.sleep(0.025)
        _mouse(MOUSEEVENTF_RIGHTUP)
        return "Right clicked, Boss."

    if _has(text, "scroll up"):
        _mouse(MOUSEEVENTF_WHEEL, 360)
        return "Scrolled up, Boss."

    if _has(text, "scroll down"):
        _mouse(MOUSEEVENTF_WHEEL, -360)
        return "Scrolled down, Boss."

    match = re.match(r"press\s+(.+)$", text)
    if match:
        key = PRESSABLE_KEYS.get(match.group(1).strip())
        if key:
            _tap_key(VK[key])
            return f"Pressed {match.group(1).strip()}, Boss."

    return None
