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
from datetime import datetime
from pathlib import Path


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
WM_CLOSE = 0x0010

VK = {
    "BACKSPACE": 0x08,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "SHIFT": 0x10,
    "CTRL": 0x11,
    "ALT": 0x12,
    "ESC": 0x1B,
    "SPACE": 0x20,
    "PAGE_UP": 0x21,
    "PAGE_DOWN": 0x22,
    "END": 0x23,
    "HOME": 0x24,
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
    "home": "HOME",
    "end": "END",
    "page up": "PAGE_UP",
    "page down": "PAGE_DOWN",
    "pageup": "PAGE_UP",
    "pagedown": "PAGE_DOWN",
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
    # Remove articles to allow phrases like "increase the volume" to match "increase volume"
    text = re.sub(r"\b(?:the|a|an)\b", "", text)
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


def _wheel(delta: int) -> bool:
    """Scroll the mouse wheel (delivered to the window under the pointer)."""

    if _dry_run():
        return True

    user32 = ctypes.windll.user32

    try:
        inputs = (_INPUT * 1)()
        inputs[0].type = _INPUT_MOUSE
        inputs[0].union.mi.dx = 0
        inputs[0].union.mi.dy = 0
        inputs[0].union.mi.mouseData = delta & 0xFFFFFFFF
        inputs[0].union.mi.dwFlags = MOUSEEVENTF_WHEEL
        inputs[0].union.mi.time = 0
        inputs[0].union.mi.dwExtraInfo = 0

        sent = user32.SendInput(
            1,
            ctypes.byref(inputs),
            ctypes.sizeof(_INPUT),
        )
        return sent == 1
    except Exception:
        return False


_WNDENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_bool,
    ctypes.c_void_p,
    ctypes.c_void_p,
)

# The screenshot file FRIDAY opened last (used to target its viewer window).
_screenshot_opened: str | None = None


def _find_screenshot_window() -> int | None:
    """Find the top-level window that is showing a FRIDAY screenshot."""

    needle = "friday"

    if _screenshot_opened:
        stem = Path(_screenshot_opened).stem.lower()
        if stem.startswith("friday"):
            needle = stem

    found = []

    @_WNDENUMPROC
    def _callback(hwnd, lparam):
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True

        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True

        buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.lower()

        if needle in title and any(
            ext in title
            for ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif", " - photos", " - paint")
        ):
            found.append(int(hwnd))
            return False

        return True

    ctypes.windll.user32.EnumWindows(_callback, 0)
    return found[0] if found else None


def close_screenshot_viewer() -> bool:
    """Gracefully close the window that is showing a FRIDAY screenshot."""

    if _dry_run():
        return True

    hwnd = _find_screenshot_window()
    if not hwnd:
        return False

    return bool(ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))


# ---------------------------------------------------------------- context actions

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _window_title(hwnd) -> str:
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _window_process_name(hwnd) -> str:
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(
        hwnd,
        ctypes.byref(pid),
    )

    if not pid.value:
        return ""

    handle = ctypes.windll.kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        pid.value,
    )

    if not handle:
        return ""

    try:
        buffer = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(1024)

        if ctypes.windll.kernel32.QueryFullProcessImageNameW(
            handle,
            0,
            buffer,
            ctypes.byref(size),
        ):
            return os.path.basename(buffer.value).lower()
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)

    return ""


def _find_app_window(fragment: str) -> int | None:
    """Find a visible top-level window whose title or process matches."""

    fragment = (fragment or "").lower().replace(".exe", "")

    if not fragment:
        return None

    found = []

    @_WNDENUMPROC
    def _callback(hwnd, lparam):
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True

        if (
            fragment in _window_title(hwnd).lower()
            or fragment in _window_process_name(hwnd).lower()
        ):
            found.append(int(hwnd))
            return False

        return True

    ctypes.windll.user32.EnumWindows(_callback, 0)
    return found[0] if found else None


def _foreground_process_fragment() -> str:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return ""
    return _window_process_name(hwnd).replace(".exe", "").lower()


def _click_first_list_item(hwnd: int, x_frac: float, y_frac: float) -> None:
    if _dry_run():
        return

    rect = _RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))

    width = max(1, rect.right - rect.left)
    height = max(1, rect.bottom - rect.top)

    x = rect.left + int(width * x_frac)
    y = rect.top + int(height * y_frac)

    ctypes.windll.user32.SetCursorPos(x, y)
    time.sleep(0.15)

    _mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.05)
    _mouse(MOUSEEVENTF_LEFTUP)


# Fraction of the window (width, height) where the first item usually sits.
_FIRST_ITEM_SCHEMES = {
    "whatsapp": (0.10, 0.22),
    "whatsup": (0.10, 0.22),
    "watsapp": (0.10, 0.22),
    "telegram": (0.08, 0.16),
    "discord": (0.12, 0.10),
    "instagram": (0.10, 0.18),
    "messenger": (0.10, 0.18),
    "signal": (0.10, 0.18),
    "line": (0.10, 0.15),
}

_DEFAULT_FIRST_ITEM = (0.10, 0.20)


def open_first_chat(
    app_name: str | None,
    language: str = "en",
) -> str | None:
    """
    Open the first chat/conversation inside a messenger app.

    Finds the messenger window (by the app that was just opened, or the
    foreground app), focuses it, and clicks the first item in its list.
    Returns a spoken response, or None when no such window is found.
    """

    fragment = app_name or _foreground_process_fragment()

    if not app_name and not any(
        key in fragment
        for key in _FIRST_ITEM_SCHEMES
    ):
        return None

    hwnd = _find_app_window(fragment)

    if not hwnd:

        if app_name:

            if language == "te":

                return (
                    f"{app_name} "
                    f"తెరిచి ఉంటే మొదటి "
                    f"chat తెరవగలను బాస్."
                )

            if language == "hi":

                return (
                    f"{app_name} "
                    f"खुला हो तो पहली "
                    f"चैट खोल सकती हूँ बॉस."
                )

            return (
                f"I couldn't find the {app_name} "
                f"window to open the first chat, Boss."
            )

        return None

    ctypes.windll.user32.ShowWindow(hwnd, 9)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.25)

    scheme = next(
        (
            value
            for key, value in _FIRST_ITEM_SCHEMES.items()
            if key in fragment
        ),
        _DEFAULT_FIRST_ITEM,
    )

    _click_first_list_item(hwnd, scheme[0], scheme[1])

    if language == "te":
        return "మొదటి chat తెరిచాను బాస్."

    if language == "hi":
        return "पहली चैट खोल दी बॉस."

    return "Opened the first chat, Boss."


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
        "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods "
        "-ErrorAction Stop | Invoke-CimMethod -MethodName WmiSetBrightness "
        f"-Arguments @{{Timeout=1;Brightness={level}}} | Out-Null"
    )
    try:
        result = _run_powershell(script, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def _set_clipboard(value: str) -> bool:
    if _dry_run():
        return True

    try:
        # PowerShell needs the script block syntax to use $args
        script = "& { Set-Clipboard -Value $args[0] }"
        result = _run_powershell(script, value, timeout=5)
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


# ---------------------------------------------------------------- typing

_INPUT_MOUSE = 0
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("union", _INPUTUNION),
    ]


def _type_unicode(text: str) -> bool:
    """Type text into the focused window using SendInput (no clipboard)."""

    if not text:
        return False

    if _dry_run():
        return True

    user32 = ctypes.windll.user32

    try:

        for char in text:

            scan = ord(char)
            inputs = (_INPUT * 2)()

            for index, flags in ((0, 0), (1, _KEYEVENTF_KEYUP)):
                inputs[index].type = _INPUT_KEYBOARD
                inputs[index].union.ki.wVk = 0
                inputs[index].union.ki.wScan = scan
                inputs[index].union.ki.dwFlags = (
                    _KEYEVENTF_UNICODE | flags
                )
                inputs[index].union.ki.time = 0
                inputs[index].union.ki.dwExtraInfo = 0

            sent = user32.SendInput(
                2,
                ctypes.byref(inputs),
                ctypes.sizeof(_INPUT),
            )

            if sent != 2:
                return False

            time.sleep(0.01)

        return True

    except Exception:
        return False


def _paste_text(value: str) -> bool:
    if not value:
        return False

    # Direct unicode typing is more reliable than the clipboard path.
    if _type_unicode(value):
        return True

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


def _latest_screenshot() -> str | None:
    """Return the most recently captured screenshot, if any."""

    folder = Path(_screenshot_path())

    if not folder.is_dir():
        return None

    try:
        files = [
            entry for entry in folder.glob("*.png")
            if entry.is_file()
        ]
    except OSError:
        return None

    if not files:
        return None

    return str(
        max(
            files,
            key=lambda item: item.stat().st_mtime,
        )
    )


def _capture_screenshot() -> str | None:
    """Capture the whole desktop to a PNG and return its path."""

    if _dry_run():
        return None

    try:
        from PIL import ImageGrab
    except Exception:
        return None

    try:
        folder = Path(_screenshot_path())
        folder.mkdir(parents=True, exist_ok=True)

        out = folder / (
            f"FRIDAY_{datetime.now():%Y-%m-%d_%H-%M-%S}.png"
        )

        image = ImageGrab.grab(all_screens=True)

        try:
            image.save(out)
        finally:
            image.close()

        return str(out)

    except Exception:
        return None


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

    global _screenshot_opened

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

    # Media keys. "play music" is deliberately NOT here: the Boss may mean
    # a player or a playlist, so it must fall through to the AI instead of
    # blindly toggling the media key.
    if _has(text, "play pause", "pause music", "pause video", "pause media", "resume media"):
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
    if _has(
        text,
        "close screenshot",
        "close the screenshot",
        "close screenshot window",
        "close the screenshot window",
        "close image",
        "close the image",
        "close picture",
        "close the picture",
        "close photo",
        "close the photo",
        "close image viewer",
        "close photo viewer",
        "close the image viewer",
        "close the photo viewer",
    ):
        if close_screenshot_viewer():
            return "Screenshot window closed, Boss."
        return "I couldn't find the screenshot window, Boss."

    if _has(text, "show screenshot", "show me screenshot", "open screenshot", "show the screenshot", "view screenshot", "display screenshot", "latest screenshot"):
        latest = _latest_screenshot()
        if latest:
            try:
                os.startfile(latest)
                _screenshot_opened = latest
            except Exception:
                pass
            return "Here is the latest screenshot, Boss."
        return "I don't have a screenshot saved yet, Boss."

    if _has(text, "take screenshot", "take a screenshot", "capture screen"):
        path = _capture_screenshot()
        if path:
            try:
                os.startfile(path)
                _screenshot_opened = path
            except Exception:
                pass
            return f"Screenshot taken and opened, Boss. Saved at {path}."
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

    if _has(text, "scroll to top", "scroll to the top", "scroll all the way up", "very top", "go to top", "top of the page", "top of page", "scroll to beginning"):
        _tap_key(VK["HOME"])
        return "Scrolled to the top, Boss."

    if _has(text, "scroll to bottom", "scroll to the bottom", "scroll all the way down", "very bottom", "go to bottom", "bottom of the page", "bottom of page", "scroll to end", "scroll to the end"):
        _tap_key(VK["END"])
        return "Scrolled to the bottom, Boss."

    if _has(text, "page up", "page up please", "go up a page"):
        _tap_key(VK["PAGE_UP"])
        return "Scrolled up a page, Boss."

    if _has(text, "page down", "page down please", "go down a page"):
        _tap_key(VK["PAGE_DOWN"])
        return "Scrolled down a page, Boss."

    if _has(text, "keep scrolling", "continue scrolling", "scroll down more", "scroll down a lot", "scroll up more", "scroll up a lot"):
        _wheel(-900 if _has(text, "down") else 900)
        return "Scrolled further, Boss."

    if _has(text, "scroll up", "scroll upward"):
        _wheel(360)
        return "Scrolled up, Boss."

    if _has(text, "scroll down", "scroll downward"):
        _wheel(-360)
        return "Scrolled down, Boss."

    match = re.match(r"press\s+(.+)$", text)
    if match:
        key = PRESSABLE_KEYS.get(match.group(1).strip())
        if key:
            _tap_key(VK[key])
            return f"Pressed {match.group(1).strip()}, Boss."

    return None
