"""
Local OCR for the Computer Use layer.

Uses RapidOCR on top of onnxruntime for completely free, local text
detection. A small provider interface keeps the door open for a future
vision-aware AI model (see `VisionProvider` in agent.py).

An OCR provider returns a list of OcrWord records:
    text        the recognized string
    box         (x, y, width, height) in screen pixels
    confidence  0..1 (RapidOCR returns a 0..1 score)
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class OcrWord:
    """One recognized text region."""

    text: str
    box: tuple[int, int, int, int]  # x, y, width, height
    confidence: float = 0.0

    def center(self) -> tuple[int, int]:
        x, y, width, height = self.box
        return int(x + width / 2), int(y + height / 2)


@dataclass
class OcrScan:
    """Result of a full-screen OCR pass."""

    words: list[OcrWord] = field(default_factory=list)
    error: str | None = None

    @property
    def text_lines(self) -> str:
        """Joined text for quick reads like 'what is on my screen'."""

        return " | ".join(word.text for word in self.words)


class OCRProvider(ABC):
    """Interface that future recognition backends implement."""

    name: str = "abstract"

    @abstractmethod
    def available(self) -> bool:
        """Whether this provider can run on this machine right now."""

    @abstractmethod
    def scan(self, image) -> Sequence[OcrWord]:
        """Run OCR and return recognized words."""


class RapidOcrProvider(OCRProvider):
    """RapidOCR / onnxruntime backend. Free, local, offline."""

    name = "rapidocr"

    def __init__(self):
        self._engine = None
        self._failed = False

    def available(self) -> bool:
        if self._failed:
            return False

        if self._engine is not None:
            return True

        try:
            import numpy as np  # noqa: F401
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
            return True
        except Exception as error:
            self._failed = True
            print(
                f"[OCR] RapidOCR unavailable: "
                f"{type(error).__name__}: {error}"
            )
            return False

    def scan(self, image) -> list[OcrWord]:
        if not self.available() or image is None:
            return []

        try:
            import numpy as np

            prepared = image.convert("RGB")
            array = np.asarray(prepared)[:, :, ::-1]

            result, _ = self._engine(array)

            if not result:
                return []

            words = []

            for item in result:
                box, text, score = item[0], item[1], item[2]

                xs = [point[0] for point in box]
                ys = [point[1] for point in box]

                x = int(min(xs))
                y = int(min(ys))
                width = int(max(xs) - x)
                height = int(max(ys) - y)

                try:
                    confidence = max(0.0, min(1.0, float(score)))
                except (TypeError, ValueError):
                    confidence = 0.0

                label = str(text).strip()

                if label:
                    words.append(
                        OcrWord(
                            text=label,
                            box=(x, y, width, height),
                            confidence=confidence,
                        )
                    )

            return words

        except Exception as error:
            print(f"[OCR] scan failed: {type(error).__name__}: {error}")
            return []

    def reset(self) -> None:
        self._engine = None
        self._failed = False


class OcrEngine:
    """Facade with a small cache so one command uses one OCR pass."""

    def __init__(self, provider: OCRProvider | None = None):
        self.provider = provider or RapidOcrProvider()
        self._last_words: list[OcrWord] = []
        self._last_time: float = 0.0

    def available(self) -> bool:
        return self.provider.available()

    def scan_words(self, image, ttl: float = 2.0) -> list[OcrWord]:
        """OCR an image, reusing the previous result within `ttl` seconds."""

        now = time.time()

        if image is None and self._last_words and (now - self._last_time) < ttl:
            return self._last_words

        if image is None:
            return []

        words = list(self.provider.scan(image))
        self._last_words = words
        self._last_time = now

        return words


## Module-level shared engine (lazy-loads RapidOCR once).
_shared_engine: OcrEngine | None = None


def get_engine() -> OcrEngine:
    """Return a process-wide OCR engine (loaded lazily, reused across calls)."""

    global _shared_engine

    if _shared_engine is None:
        _shared_engine = OcrEngine()

    return _shared_engine


def _box_sort_key(word: OcrWord):
    """Order words top-to-bottom, then left-to-right for reading order."""

    x, y, width, height = word.box
    return (y // 20, x)


def ocr_image(image) -> OcrScan:
    """Convenience: run OCR on an image and return an OcrScan."""

    engine = get_engine()

    if image is None:
        return OcrScan(error="No image was available.")

    if not engine.available():
        return OcrScan(
            words=[],
            error=(
                "OCR engine is not available on this system. "
                "Install rapidocr-onnxruntime to enable screen reading."
            ),
        )

    try:
        words = engine.scan_words(image)
        words.sort(key=_box_sort_key)
        return OcrScan(words=words)
    except Exception as error:
        return OcrScan(
            words=[],
            error=f"{type(error).__name__}: {error}",
        )