"""
Keyboard control for the Computer Use layer.

Reuses the existing `pc_control` keyboard plumbing (SendInput unicode
typing, keybd_event taps and Ctrl/Alt/Win combos).
"""

from __future__ import annotations

import re

from pc_control import (
    _combo,
    _tap_key,
    _type_unicode,
    PRESSABLE_KEYS,
    VK,
)

# Extra spoken keys mapped to the same virtual-key table.
_EXTRA_KEYS = {
    "enter": "ENTER",
    "return": "ENTER",
    "escape": "ESC",
    "esc": "ESC",
    "tab": "TAB",
    "space": "SPACE",
    "spacebar": "SPACE",
    "backspace": "BACKSPACE",
    "left": "LEFT",
    "right": "RIGHT",
    "up": "UP",
    "down": "DOWN",
    "home": "HOME",
    "end": "END",
    "page up": "PAGE_UP",
    "page down": "PAGE_DOWN",
    "ctrl": "CTRL",
    "control": "CTRL",
    "alt": "ALT",
    "shift": "SHIFT",
    "f4": "F4",
}

_VK_NAME = {name.lower(): name for name in VK}
_PK_NAME = {name.lower(): name for name in PRESSABLE_KEYS}


def resolve_key(name: str) -> tuple[int, str] | None:
    """Map a spoken key to (VK code, canonical name) or None."""

    key = re.sub(r"\s+", " ", (name or "").strip().lower())

    if not key:
        return None

    if key.endswith(" key"):
        key = key[:-4].strip()

    if key in _PK_NAME:
        canonical = PRESSABLE_KEYS[key]
        return VK[canonical], canonical

    if key in _EXTRA_KEYS:
        canonical = _EXTRA_KEYS[key]
        if canonical is None:
            return None
        return VK[canonical], canonical

    if key in _VK_NAME:
        canonical = _VK_NAME[key]
        return VK[canonical], canonical

    return None


def press_key(name: str, times: int = 1) -> bool:
    """Press a key by its spoken name. Returns False when unknown."""

    resolved = resolve_key(name)

    if not resolved:
        return False

    vk, _ = resolved
    _tap_key(vk, times)

    return True


def type_text(text: str) -> bool:
    """Type text into the focused control using unicode SendInput."""

    return _type_unicode(text)


def key_combo(*keys: str) -> bool:
    """Press a chord such as ('ALT', 'LEFT') for 'go back'."""

    canonical = []

    for key in keys:
        resolved = resolve_key(key)

        if not resolved:
            return False

        canonical.append(resolved[1])

    _combo(*canonical)

    return True


def go_back() -> None:
    """Alt+Left, the standard browser/backward gesture."""

    _combo("ALT", "LEFT")