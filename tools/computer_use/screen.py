"""
Screen capture for the Computer Use layer.

Builds on the existing `pc_control` screenshot helpers but returns an
in-memory PIL image so OCR, vision and verification can process it.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime
from pathlib import Path

from pc_control import _dry_run, _screenshot_path


def virtual_desktop_origin() -> tuple[int, int]:
    """Return the (left, top) of the virtual desktop in screen pixels."""

    if _dry_run():
        return 0, 0

    import ctypes

    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    user32 = ctypes.windll.user32
    return (
        int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN)),
    )


def capture() -> object | None:
    """
    Capture the whole virtual desktop.

    Returns a PIL RGB image, or None when capture is unavailable
    (dry-run, no display, or an unexpected failure).
    """

    if _dry_run():
        return None

    from PIL import ImageGrab

    last_error = None

    for attempt in range(2):
        try:
            image = ImageGrab.grab(all_screens=True)
            if image:
                return image.convert("RGB")
        except Exception as error:  # pragma: no cover - platform dependent
            last_error = error
            time.sleep(0.2)
            continue

    if last_error is not None:
        print(f"[SCREEN] capture failed: {type(last_error).__name__}: {last_error}")

    return None


def save(image) -> str | None:
    """Save a PIL image to the FRIDAY screenshot folder, return its path."""

    if image is None:
        return None

    try:
        folder = Path(_screenshot_path())
        folder.mkdir(parents=True, exist_ok=True)

        out = folder / (
            f"FRIDAY_CV_{datetime.now():%Y-%m-%d_%H-%M-%S}_"
            f"{uuid.uuid4().hex[:6]}.png"
        )

        image.save(out)
        return str(out)
    except Exception as error:
        print(f"[SCREEN] save failed: {type(error).__name__}: {error}")

    return None


def screen_size(image=None) -> tuple[int, int]:
    """Return the (width, height) of the captured screen."""

    if image is not None:
        return image.size

    if _dry_run():
        return 1920, 1080

    import ctypes

    user32 = ctypes.windll.user32
    return (
        int(user32.GetSystemMetrics(0)),
        int(user32.GetSystemMetrics(1)),
    )


def _downsample(image, max_side: int = 220) -> object:
    """Shrink an image for cheap comparison (used by screen_diff)."""

    width, height = image.size
    scale = min(1.0, max_side / max(width, height))

    if scale >= 1.0:
        return image

    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size)


def screen_diff(before, after, tolerance: int = 16) -> float:
    """Return the fraction (0..1) of pixels that changed between two shots."""

    if before is None or after is None:
        return 0.0

    small_a = _downsample(before)
    small_b = _downsample(after)

    if small_a.size != small_b.size:
        small_b = small_b.resize(small_a.size)

    try:
        a = small_a.convert("L")
        b = small_b.convert("L")

        data_a = list(a.getdata())
        data_b = list(b.getdata())

        changed = sum(
            1
            for left, right in zip(data_a, data_b)
            if abs(int(left) - int(right)) > tolerance
        )

        total = len(data_a)

        return changed / total if total else 0.0
    except Exception:
        return 0.0