"""
Visual element search for the Computer Use layer.

Turns OCR results into findable UI targets. Matching runs through:
    exact normalized text  -> case-insensitive -> fuzzy (difflib ratio).

Filler words ("button", "the", "that says", ...) are stripped from the
target before matching so "click the settings button" still finds a
"Settings" label.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .ocr import OcrWord

_FILLER = re.compile(
    r"\b(?:the|a|an|button|buttons|link|links|icon|icons|"
    r"tab|tabs|option|options|menu|menus|field|fields|"
    r"box|boxes|bar|image|images|picture|pictures|"
    r"says|reads|named|called|labeled|that|which|please|on|"
    r"with|text|label)\b",
    re.IGNORECASE,
)

_PUNCT = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~।॥")

# A "have" row/word target that is this close (or closer) than the best
# match is still ambiguous and should trigger a clarification question.
_AMBIGUITY_DELTA = 0.06


@dataclass
class ElementMatch:
    """A visible text element that matches a requested target."""

    text: str
    box: tuple[int, int, int, int]
    score: float
    matched: str

    def safe_click_point(
        self,
        screen_width: int = 0,
        screen_height: int = 0,
        margin: int = 60,
    ) -> tuple[int, int]:
        """Return the center of the element, kept clear of screen edges."""

        x, y, width, height = self.box

        center_x = x + width // 2
        center_y = y + height // 2

        if center_x < margin:
            center_x = margin
        if center_y < margin:
            center_y = margin

        if screen_width and center_x > screen_width - margin:
            center_x = screen_width - margin
        if screen_height and center_y > screen_height - margin:
            center_y = screen_height - margin

        return center_x, center_y


def normalize(text: str) -> str:
    """Fold a label to a normalized, matchable form."""

    value = (text or "").lower()
    value = "".join(char for char in value if char not in _PUNCT)
    value = _FILLER.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip()

    return value


def _fuzzy_score(target: str, candidate: str) -> float:
    """A 0..1 similarity made tolerant to extra OCR junk."""

    ratio = SequenceMatcher(None, target, candidate).ratio()

    tokens_target = set(target.split())
    tokens_candidate = set(candidate.split())

    if not tokens_target:
        return ratio

    overlap = len(tokens_target & tokens_candidate) / len(tokens_target)

    return max(ratio, overlap)


def _row_groups(words: list[OcrWord]) -> list[list[OcrWord]]:
    """Group OCR words into rows so multi-word buttons match cleanly."""

    ordered = sorted(words, key=lambda word: (word.box[1], word.box[0]))

    rows: list[list[OcrWord]] = []

    for word in ordered:
        _, y, _, height = word.box
        anchor = y + height / 2

        if rows:
            last_row_y = rows[-1][0].box[1]
            last_row_h = rows[-1][0].box[3]
            _, last_bound = last_row_y, last_row_y + last_row_h

            if last_row_y - height * 0.4 <= anchor <= last_bound + height * 0.4:
                rows[-1].append(word)
                continue

        rows.append([word])

    return rows


def _row_union(words: list[OcrWord]) -> tuple[str, tuple[int, int, int, int]]:
    """Join OCR words in a row into one label with a merged bounding box."""

    ordered = sorted(words, key=lambda word: word.box[0])
    text = " ".join(word.text for word in ordered).strip()

    left = min(word.box[0] for word in ordered)
    top = min(word.box[1] for word in ordered)
    right = max(word.box[0] + word.box[2] for word in ordered)
    bottom = max(word.box[1] + word.box[3] for word in ordered)

    return text, (left, top, right - left, bottom - top)


def find_elements(
    words: list[OcrWord],
    target: str,
    threshold: float = 0.72,
) -> list[ElementMatch]:
    """
    Find visible OCR elements matching a target label.

    Returns matches sorted by descending score, or an empty list.
    """

    if not words or not target:
        return []

    needle = normalize(target)

    if not needle:
        return []

    matches: list[ElementMatch] = []
    seen: set[tuple[int, int, int, int]] = set()

    def record(label: str, box: tuple[int, int, int, int], score: float) -> None:
        if box in seen or not label:
            return
        seen.add(box)
        matches.append(
            ElementMatch(
                text=label,
                box=box,
                score=max(0.0, min(1.0, score)),
                matched=target,
            )
        )

    # Pattern to prefer clicking visually bigger, more confident text.
    def weight(word: OcrWord) -> float:
        return 0.9 + 0.1 * word.confidence

    for word in words:
        raw = word.text
        norm = normalize(raw)

        if norm == needle:
            record(raw, word.box, 1.0)
        elif norm and (norm in needle or needle in norm):
            record(raw, word.box, 0.96)
        elif norm:
            score = _fuzzy_score(needle, norm)
            if score >= threshold:
                record(raw, word.box, score * weight(word))

    # Multi-word targets usually live on one row.
    if len(needle.split()) > 1:
        for group in _row_groups(words):
            if len(group) < 2:
                continue

            label, box = _row_union(group)
            norm = normalize(label)

            if norm == needle:
                record(label, box, 1.0)
            elif norm and (norm in needle or needle in norm):
                record(label, box, 0.97)
            elif norm:
                score = _fuzzy_score(needle, norm)
                if score >= threshold:
                    record(label, box, score)

    matches.sort(key=lambda match: match.score, reverse=True)

    return matches


def pick_target(
    matches: list[ElementMatch],
) -> tuple[ElementMatch | None, bool]:
    """
    Choose the best match.

    Returns (match, ambiguous). When the top two candidates are almost
    equally plausible, the caller must ask the user instead of guessing.
    """

    if not matches:
        return None, False

    best = matches[0]

    if len(matches) > 1:
        second = matches[1]

        if (best.score - second.score) <= _AMBIGUITY_DELTA and best.score > 0.9:
            return None, True

    return best, False


def describe(words: list[OcrWord], limit: int = 12) -> str:
    """Summarize what is visible for read-only screen questions."""

    visible = [
        word.text for word in words
        if word.confidence >= 0.45
    ]

    if not visible:
        return ""

    if len(visible) > limit:
        visible = visible[:limit]

    return ", ".join(visible)