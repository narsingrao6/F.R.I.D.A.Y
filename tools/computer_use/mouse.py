"""
Mouse control for the Computer Use layer.

Thin wrappers over the existing `pc_control` low-level mouse helpers so
Computer Use never duplicates the Win32 plumbing.
"""

from __future__ import annotations

import ctypes
import time

from pc_control import (
    _dry_run,
    _mouse,
    _wheel,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_RIGHTDOWN,
    MOUSEEVENTF_RIGHTUP,
)


def move(x: int, y: int) -> None:
    """Move the pointer to absolute screen coordinates."""

    if _dry_run():
        return

    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.12)


def left_click(x: int | None = None, y: int | None = None) -> None:
    """Move to (x, y) if given, then left-click."""

    if x is not None and y is not None:
        move(x, y)

    _mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.06)
    _mouse(MOUSEEVENTF_LEFTUP)


def double_click(x: int | None = None, y: int | None = None) -> None:
    """Move to (x, y) if given, then double left-click."""

    if x is not None and y is not None:
        move(x, y)

    for _ in range(2):
        _mouse(MOUSEEVENTF_LEFTDOWN)
        time.sleep(0.05)
        _mouse(MOUSEEVENTF_LEFTUP)
        time.sleep(0.08)


def right_click(x: int | None = None, y: int | None = None) -> None:
    """Move to (x, y) if given, then right-click."""

    if x is not None and y is not None:
        move(x, y)

    _mouse(MOUSEEVENTF_RIGHTDOWN)
    time.sleep(0.05)
    _mouse(MOUSEEVENTF_RIGHTUP)


def scroll(delta: int) -> bool:
    """Scroll the wheel. Positive delta scrolls up, negative down."""

    return _wheel(int(delta))


def scroll_until_found(
    scan: "object",
    finder: "object",
    target: str,
    direction: str = "down",
    max_steps: int = 6,
) -> "object | None":
    """
    Repeatedly scroll and re-scan until a visible element appears.

    Returns the first ElementMatch found, else None. This is the
    'scroll down until you see Downloads' behaviour.
    """

    from .ocr import ocr_image
    from .screen import capture
    from .vision import find_elements

    delta = -540 if direction == "down" else 540

    found = None

    for _ in range(max_steps):
        words = ocr_image(capture()).words

        if not words:
            return None

        matches = find_elements(words, target)

        if matches:
            return matches[0]

        if not scroll(delta):
            return None

        time.sleep(0.45)

    return None


def drag(x1: int, y1: int, x2: int, y2: int, steps: int = 10) -> None:
    """Press the left button at (x1, y1) and drag to (x2, y2)."""

    if _dry_run():
        return

    move(x1, y1)
    _mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.15)

    for index in range(1, steps + 1):
        t = index / steps
        cx = int(x1 + (x2 - x1) * t)
        cy = int(y1 + (y2 - y1) * t)
        ctypes.windll.user32.SetCursorPos(cx, cy)
        time.sleep(0.02)

    time.sleep(0.1)
    _mouse(MOUSEEVENTF_LEFTUP)