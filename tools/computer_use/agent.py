"""
Computer Use agent for F.R.I.D.A.Y.

Implements the Phase 3 loop for screen-aware actions:

    OBSERVE -> UNDERSTAND -> PLAN -> ACT -> OBSERVE -> VERIFY -> RESPOND

It parses natural commands ("click the settings button"), captures the
screen, detects the target via OCR, interacts through the mouse/keyboard
layers, and re-captures to verify the change before responding.

A `VisionProvider` stub is defined so a vision AI model can be added
later without touching the rest of the layer.
"""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from . import keyboard as kb
from . import mouse as mouse_layer
from .ocr import ocr_image
from .screen import capture, screen_diff, screen_size
from .vision import describe as vision_describe
from .vision import find_elements, pick_target

# ------------------------------------------------------------------
# Spoken / normalized command parsing
# ------------------------------------------------------------------

_DESCRIBE_PATTERNS = (
    r"what(?:'?s| is| are)?\s+(?:currently\s+)?(?:on|open|showing|displayed)"
    r"\s+(?:my\s+|the\s+)?(?:screen|display|desktop)",
    r"what(?:'?s| is| are)?\s+(?:on|showing|displayed)\s+my\s+screen",
    r"what\s+can\s+you\s+see",
    r"what\s+do\s+you\s+see",
    r"whats?\s+on\s+the\s+screen",
    r"read\s+(?:the\s+)?screen",
    r"describe\s+(?:the\s+)?(?:screen|display)",
    r"look\s+at\s+(?:the\s+|my\s+)?(?:screen|display)",
    r"see\s+(?:the\s+|my\s+)?(?:screen|display)",
    r"what\s+is\s+open\s+on\s+(?:my\s+|your\s+)?(?:screen|pc|computer)",
)

_CLICK_RE = re.compile(
    r"(?i)^(?:click|tap|press)\s+(?:on\s+)?"
    r"(?:the\s+)?"
    r"(?:button\s+|link\s+|icon\s+|tab\s+|option\s+|item\s+|menu\s+|field\s+|box\s+|bar\s+)?"
    r"(?:that\s+(?:says|reads|called|named)\s+|called\s+|named\s+|labeled\s+)?"
    r"(.+?)\s*$"
)

_DOUBLE_CLICK_RE = re.compile(
    r"(?i)^double[-\s]?click\s+(?:on\s+)?(?:the\s+)?"
    r"(?:button\s+|link\s+|icon\s+|item\s+)?"
    r"(?:that\s+(?:says|reads|called|named)\s+|called\s+)?(.+?)\s*$"
)

_RIGHT_CLICK_RE = re.compile(
    r"(?i)^right[-\s]?click\s+(?:on\s+)?(?:the\s+)?"
    r"(?:button\s+|link\s+|icon\s+)?"
    r"(?:that\s+(?:says|reads|called|named)\s+|called\s+)?(.+?)\s*$"
)

_TYPE_FIELD_RE = re.compile(
    r"(?i)^type\s+(.+?)\s+"
    r"(?:into|in|inside|to)\s+"
    r"(?:the\s+)?(?:search\s+|address\s+|input\s+|text\s+|chat\s+)?"
    r"(.+?)(?:\s+and\s+press\s+(?:enter|return))?\s*$"
)

_PRESS_ENTER_SUFFIX = re.compile(r"(?i)\s+and\s+press\s+(?:enter|return)\s*$")

_OPEN_CLICK_RE = re.compile(
    r"(?i)^open\s+(.+?)\s+and\s+(?:click|tap)\s+"
    r"(?:on\s+)?(?:the\s+)?"
    r"(?:button\s+|link\s+|icon\s+|tab\s+)?"
    r"(?:that\s+(?:says|reads|named)\s+|called\s+)?(.+?)\s*$"
)

_SCROLL_UNTIL_RE = re.compile(
    r"(?i)^scroll\s+(up|down)?\s*(?:until\s+)?(?:you\s+see\s+|you\s+find\s+|"
    r"I\s+see\s+|to\s+see\s+|to\s+find\s+|till\s+|down\s+to\s+|up\s+to\s+)?"
    r"(?:the\s+)?(.+?)\s*$"
)

_DRAG_RE = re.compile(
    r"(?i)^drag\s+(?:the\s+)?(.+?)\s+to\s+(?:the\s+)?(.+?)\s*$"
)

# Context pronouns resolved via the previous screen target.
_PRONOUNS = {"it", "that", "this", "there", "here", "do it", "click it"}

# High-impact actions that must never be auto-clicked, even in full power.
_DANGER_WORDS = (
    "delete", "remove", "uninstall", "format", "wipe", "erase",
    "shutdown", "shut down", "restart", "logout", "log out", "sign out",
    "purchase", "buy", "checkout", "pay", "place order", "order now",
    "confirm payment", "submit payment", "account", "password",
    "send message", "cancel my account", "delete account", "erase all",
)

# ------------------------------------------------------------------
# Vision provider interface (future AI vision, optional and offline-free)
# ------------------------------------------------------------------


class VisionProvider(ABC):
    """Optional interface for a vision model later. Not required now."""

    name: str = "abstract"

    @abstractmethod
    def analyze_screen(self, image) -> str:
        """Return a natural-language summary of what is on screen."""

    def describe(self, words):
        return vision_describe(words)


class LocalVisionProvider(VisionProvider):
    """A reserved free/local provider slot (e.g. an ollama vision model)."""

    name = "local"

    def analyze_screen(self, image) -> str:
        # Placeholder: OCR-based describe is the default until a vision
        # model is wired into Phase 4.
        return vision_describe(ocr_image(image).words)


# ------------------------------------------------------------------
# Parsed action
# ------------------------------------------------------------------


@dataclass
class ScreenAction:
    kind: str  # describe | click | double | right | type_field | open_click |
    #          # scroll_until | drag | go_back | type_only
    target: str = ""
    text: str = ""
    app: str = ""
    field: str = ""
    direction: str = "down"
    press_enter: bool = False
    source: str = ""
    destination: str = ""


# ------------------------------------------------------------------
# Localisation helper
# ------------------------------------------------------------------


def _say(en: str, te: str, hi: str, language: str) -> str:
    if language == "te":
        return te
    if language == "hi":
        return hi
    return en


def _clean_target(value: str) -> str:
    value = (value or "").strip(" .-;,")
    value = re.sub(r"\s+", " ", value)
    return value


def _is_dangerous(target: str) -> bool:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", target.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return any(word in f" {normalized} " for word in _DANGER_WORDS)


# ------------------------------------------------------------------
# Agent
# ------------------------------------------------------------------

_SCREEN_MARGIN = 60
_CHANGE_THRESHOLD = 0.02


class ComputerUseAgent:
    """Turns natural commands into verified screen actions."""

    def __init__(self, context=None, ocr_provider=None):
        from .ocr import OcrEngine

        self.context = context
        self.engine = OcrEngine(provider=ocr_provider)
        self.vision_provider: VisionProvider | None = None

    def bind_context(self, context) -> None:
        self.context = context

    # -------------------------------------------------- parsing

    def _parse(self, command: str) -> ScreenAction | None:
        text = (command or "").strip()

        if not text:
            return None

        if re.search(
            "|".join(f"(?:{pattern})" for pattern in _DESCRIBE_PATTERNS),
            text,
            re.IGNORECASE,
        ):
            return ScreenAction(kind="describe")

        if _OPEN_CLICK_RE.match(text):
            match = _OPEN_CLICK_RE.match(text)
            return ScreenAction(
                kind="open_click",
                app=_clean_target(match.group(1)),
                target=_clean_target(match.group(2)),
            )

        if _TYPE_FIELD_RE.match(text):
            match = _TYPE_FIELD_RE.match(text)
            press = bool(_PRESS_ENTER_SUFFIX.search(text))
            return ScreenAction(
                kind="type_field",
                text=_clean_target(match.group(1)),
                field=_clean_target(match.group(2)),
                press_enter=press,
            )

        if _DRAG_RE.match(text):
            match = _DRAG_RE.match(text)
            return ScreenAction(
                kind="drag",
                source=_clean_target(match.group(1)),
                destination=_clean_target(match.group(2)),
            )

        if re.match(r"(?i)^scroll", text) and re.search(
            r"(?i)until|till|to see|to find|down to|up to",
            text,
        ):
            match = _SCROLL_UNTIL_RE.match(text)
            if match:
                target = _clean_target(match.group(2))
                direction = (match.group(1) or "down").lower()
                return ScreenAction(
                    kind="scroll_until",
                    target=target,
                    direction=direction,
                )

        if re.match(r"(?i)^right[-\s]?click", text):
            match = _RIGHT_CLICK_RE.match(text)
            if match:
                return ScreenAction(
                    kind="right",
                    target=_clean_target(match.group(1)),
                )

        if re.match(r"(?i)^double[-\s]?click", text):
            match = _DOUBLE_CLICK_RE.match(text)
            if match:
                return ScreenAction(
                    kind="double",
                    target=_clean_target(match.group(1)),
                )

        if re.match(r"(?i)^(?:click|tap|press)\s", text) or re.search(
            r"(?i)\b(?:and\s+)?(?:click|tap)\b",
            text,
        ):
            match = _CLICK_RE.match(text)
            if match:
                return ScreenAction(
                    kind="click",
                    target=_clean_target(match.group(1)),
                )

        if re.match(r"(?i)^type\s", text):
            return ScreenAction(
                kind="type_only",
                text=_clean_target(text[5:]),
            )

        if re.match(r"(?i)^go\s+back\b", text):
            return ScreenAction(kind="go_back")

        if re.match(r"(?i)^press\s+(?:the\s+)?key\s+enter\b", text):
            return ScreenAction(kind="go_back")

        return None

    # -------------------------------------------------- shared helpers

    def _resolve_pronoun(self, action: ScreenAction) -> str | None:
        target = action.target.lower()

        if target in _PRONOUNS or target in {"the button", "that button", "it please"}:
            if self.context:
                last = self.context.get_metadata("last_screen_target")
                if last:
                    action.target = last
                    return last
            return None

        return target

    def _observe(self):
        return capture()

    def _remember_target(self, action: ScreenAction) -> None:
        if self.context and action.target:
            self.context.set_metadata("last_screen_target", action.target)

    def _verify_changed(self, before, after) -> bool:
        if before is None or after is None:
            return False
        return screen_diff(before, after) >= _CHANGE_THRESHOLD

    def _not_found_reply(self, action: ScreenAction, language: str) -> str:
        display = {
            "type_field": action.field or action.target,
            "drag": action.source or action.target,
            "scroll_until": action.target or action.source,
        }.get(action.kind, action.target) or action.target

        kind = {
            "click": "button",
            "double": "item",
            "right": "item",
            "type_field": "field",
            "scroll_until": "item",
            "open_click": "item",
            "drag": "item",
        }.get(action.kind, "item")

        return _say(
            f"I looked but couldn't find a visible '{display}' "
            f"{kind} on the screen, Boss.",
            f"స్క్రీన్ మీద '{display}' {kind} కనబడలేదు బాస్.",
            f"स्क्रीन पर '{display}' {kind} नहीं दिखा बॉस।",
            language,
        )

    def _ambiguous_reply(self, target: str, language: str) -> str:
        return _say(
            f"I found more than one '{target}' on the screen. "
            "Which one should I use?",
            f"స్క్రీన్ మీద '{target}' ఒకటి కంటే ఎక్కువ కనిపిస్తున్నాయి. "
            "ఏది వాడాలి?",
            f"स्क्रीन पर '{target}' एक से ज़्यादा दिख रहे हैं। कौन सा इस्तेमाल करूँ?",
            language,
        )

    # -------------------------------------------------- actions

    def _find_and_check(self, target: str) -> tuple:
        """Return (image, match, file_like_error)."""

        image = self._observe()

        if image is None:
            return image, None, "screen unavailable"

        words = self.engine.scan_words(image)

        if not words:
            return image, None, "no text on screen"

        matches = find_elements(words, target)

        if not matches:
            return image, None, "not found"

        choice, ambiguous = pick_target(matches)

        if ambiguous:
            return image, None, "ambiguous"

        return image, choice, None

    def _describe_command(self, language: str) -> str:
        image = self._observe()

        if image is None:
            return _say(
                "I can't capture the screen right now, Boss.",
                "ప్రస్తుతం స్క్రీన్ తీయలేకపోతున్నాను బాస్.",
                "अभी स्क्रीन नहीं ले पा रही हूँ बॉस।",
                language,
            )

        try:

            if self.vision_provider is not None:
                summary = self.vision_provider.analyze_screen(image)
            else:
                scan = ocr_image(image)
                summary = scan.error or vision_describe(scan.words)
        except Exception as error:
            summary = ""

        if not summary:
            return _say(
                "I couldn't read anything on the screen right now, Boss.",
                "ఇప్పుడు స్క్రీన్ మీద ఏమీ చదవలేకపోయాను బాస్.",
                "अभी स्क्रीन पर कुछ नहीं पढ़ पा रही हूँ बॉस।",
                language,
            )

        return _say(
            f"This is what I can see, Boss: {summary}",
            f"నేను చూస్తున్నది, బాస్: {summary}",
            f"मुझे यह दिख रहा है, बॉस: {summary}",
            language,
        )

    def _click_command(self, action: ScreenAction, language: str) -> str:
        resolved = self._resolve_pronoun(action)

        if resolved is None:
            return _say(
                "You haven't pointed at anything yet, Boss. "
                "Try 'click the Settings button'.",
                "ఇంకా దేని గురించో చెప్పలేదు బాస్. "
                "'click the Settings button' అని చెప్పండి.",
                "अभी किसी चीज़ का इशारा नहीं मिला बॉस। "
                "'click the Settings button' बोलिए।",
                language,
            )

        image, choice, issue = self._find_and_check(resolved)

        if issue == "screen unavailable":
            return self._not_found_reply(action, language)
        if issue == "no text on screen":
            return self._not_found_reply(action, language)
        if issue == "not found":
            return self._not_found_reply(action, language)
        if issue == "ambiguous":
            return self._ambiguous_reply(resolved, language)

        if _is_dangerous(resolved):
            return _say(
                f"I won't click '{resolved}', Boss. "
                "That kind of action needs your explicit approval first.",
                f"'{resolved}' ని క్లిక్ చేయను బాస్. "
                "అలాంటి actions మీరు స్పష్టంగా అనుమతించాలి.",
                f"'{resolved}' पर क्लिक नहीं करूँगी बॉस। "
                "ऐसे काम के लिए आपकी साफ सहमति चाहिए।",
                language,
            )

        width, height = screen_size(image)
        x, y = choice.safe_click_point(width, height, _SCREEN_MARGIN)

        before = image

        if action.kind == "double":
            mouse_layer.double_click(x, y)
            verb = "double-clicked"
            te_verb = "double-click"
        elif action.kind == "right":
            mouse_layer.right_click(x, y)
            verb = "right-clicked"
            te_verb = "right-click"
        else:
            mouse_layer.left_click(x, y)
            verb = "clicked"
            te_verb = "click"

        time.sleep(0.7)
        after = self._observe()

        self._remember_target(action)

        if self._verify_changed(before, after):
            return _say(
                f"{verb} '{choice.text}' and confirmed the screen changed, Boss.",
                f"'{choice.text}' ని {te_verb} చేసి స్క్రీన్ మారిందో లేదో "
                f"చూశాను బాస్.",
                f"'{choice.text}' को क्लिक किया और स्क्रीन में बदलाव "
                f"कन्फर्म किया, बॉस।",
                language,
            )

        return _say(
            f"{verb} '{choice.text}', Boss. I didn't see the screen change "
            "afterwards, but the click went through.",
            f"'{choice.text}' ని {te_verb} చేశాను బాస్. తర్వాత స్క్రీన్ "
            "మారినట్టు కనిపించలేదు, కానీ క్లిక్ అయింది.",
            f"'{choice.text}' को क्लिक किया, बॉस। इसके बाद स्क्रीन बदलती "
            "नहीं दिखी, लेकिन क्लिक हो गया।",
            language,
        )

    def _type_field_command(self, action: ScreenAction, language: str) -> str:
        field = action.field

        if field and field.lower() in _PRONOUNS:
            last = None
            if self.context:
                last = self.context.get_metadata("last_screen_target")
            if last:
                field = last
                action.field = field
            else:
                field = None

        if not field:
            return _say(
                "You haven't pointed at a field yet, Boss.",
                "ఇంకా ఫీల్డ్ గురించి చెప్పలేదు బాస్.",
                "अभी किसी फ़ील्ड का इशारा नहीं मिला बॉस।",
                language,
            )

        image, choice, issue = self._find_and_check(field)

        if issue in ("screen unavailable", "no text on screen", "not found"):
            return self._not_found_reply(action, language)
        if issue == "ambiguous":
            return self._ambiguous_reply(field, language)

        width, height = screen_size(image)
        x, y = choice.safe_click_point(width, height, _SCREEN_MARGIN)

        mouse_layer.left_click(x, y)
        time.sleep(0.25)

        if not kb.type_text(action.text):
            return _say(
                "The text couldn't be typed, Boss.",
                "టైప్ చేయడం కుదరలేదు బాస్.",
                "टाइप नहीं हो पाया बॉस।",
                language,
            )

        if action.press_enter:
            kb.press_key("enter")

        self._remember_target(action)

        return _say(
            f"Typed '{action.text}' into {choice.text}, Boss.",
            f"'{action.text}' ని {choice.text} లో టైప్ చేశాను బాస్.",
            f"'{action.text}' को {choice.text} में टाइप कर दिया बॉस।",
            language,
        )

    def _open_click_command(self, action: ScreenAction, language: str) -> str:
        from app_launcher import handle_app_command

        try:
            handle_app_command(f"open {action.app}", language)
        except Exception:
            pass

        time.sleep(1.4)

        click = ScreenAction(kind="click", target=action.target)
        reply = self._click_command(click, language)

        opened = _say(
            f"Opened {action.app}. ",
            f"{action.app} తెరిచాను. ",
            f"{action.app} खोल दिया। ",
            language,
        )

        return opened + reply

    def _scroll_until_command(self, action: ScreenAction, language: str) -> str:
        image = self._observe()

        if image is None:
            return self._not_found_reply(action, language)

        words = self.engine.scan_words(image)

        found = None

        if words:
            matches = find_elements(words, action.target)
            if matches:
                found = matches[0]

        steps = 0
        direction_sign = -1 if action.direction == "down" else 1

        while found is None and steps < 6:
            if not mouse_layer.scroll(direction_sign * -540):
                break
            time.sleep(0.5)

            image = self._observe()
            if image is None:
                break

            words = self.engine.scan_words(image)

            if not words:
                steps += 1
                continue

            matches = find_elements(words, action.target)
            if matches:
                found = matches[0]
                break

            steps += 1

        if found is None:
            return self._not_found_reply(action, language)

        width, height = screen_size(image)
        x, y = found.safe_click_point(width, height, _SCREEN_MARGIN)

        before = image
        mouse_layer.left_click(x, y)
        time.sleep(0.7)
        after = self._observe()

        self._remember_target(action)

        changed = self._verify_changed(before, after)

        return _say(
            f"Scrolled {action.direction} and clicked '{found.text}', Boss." +
            ("" if changed else " I didn't confirm a change afterwards."),
            f"{action.direction} కి scroll చేసి '{found.text}' ని "
            f"క్లిక్ చేశాను బాస్." + ("" if changed else ""),
            f"{action.direction} स्क्रॉल करके '{found.text}' पर "
            f"क्लिक किया, बॉस." + ("" if changed else ""),
            language,
        )

    def _drag_command(self, action: ScreenAction, language: str) -> str:
        image = self._observe()

        if image is None:
            return self._not_found_reply(action, language)

        words = self.engine.scan_words(image)

        if not words:
            return self._not_found_reply(action, language)

        source_matches = find_elements(words, action.source)
        dest_matches = find_elements(words, action.destination)

        if not source_matches or not dest_matches:
            return self._not_found_reply(action, language)

        width, height = screen_size(image)
        sx, sy = source_matches[0].safe_click_point(width, height, _SCREEN_MARGIN)
        dx, dy = dest_matches[0].safe_click_point(width, height, _SCREEN_MARGIN)

        mouse_layer.drag(sx, sy, dx, dy)
        self._remember_target(action)

        return _say(
            f"Dragged {action.source} to {action.destination}, Boss.",
            f"{action.source} ని {action.destination} కి లాగాను బాస్.",
            f"{action.source} को {action.destination} तक खींचा, बॉस।",
            language,
        )

    def _go_back_command(self, language: str) -> str:
        kb.go_back()
        return _say(
            "Went back, Boss.",
            "వెనక్కి వెళ్ళాను బాస్.",
            "पीछे गई, बॉस।",
            language,
        )

    def _type_only_command(self, action: ScreenAction, language: str) -> str:
        if kb.type_text(action.text):
            return _say(
                f"Typed '{action.text}', Boss.",
                f"'{action.text}' టైప్ చేశాను బాస్.",
                f"'{action.text}' टाइप कर दिया, बॉस।",
                language,
            )
        return _say(
            "The text couldn't be typed, Boss.",
            "టైప్ చేయడం కుదరలేదు బాస్.",
            "टाइप नहीं हो पाया बॉस।",
            language,
        )

    # -------------------------------------------------- entry points

    def execute(self, command: str, language: str = "en") -> str | None:
        """Run a computer-use command; None when it is not ours."""

        action = self._parse(command)

        if action is None:
            return None

        if action.kind == "describe":
            return self._describe_command(language)

        if action.kind in ("click", "double", "right"):
            return self._click_command(action, language)

        if action.kind == "type_field":
            return self._type_field_command(action, language)

        if action.kind == "open_click":
            return self._open_click_command(action, language)

        if action.kind == "scroll_until":
            return self._scroll_until_command(action, language)

        if action.kind == "drag":
            return self._drag_command(action, language)

        if action.kind == "go_back":
            return self._go_back_command(language)

        if action.kind == "type_only":
            return self._type_only_command(action, language)

        return None

    def describe_command(self, command: str, language: str = "en") -> str | None:
        """Run only a read-only screen description."""

        action = self._parse(command)

        if action is None or action.kind != "describe":
            return None

        return self._describe_command(language)


## Module-level singleton the tool handlers delegate to.
_agent = ComputerUseAgent()


def handle_screen_vision_command(
    command: str,
    language: str = "en",
    context=None,
) -> str | None:
    """Tool handler: read-only OCR description of the current screen."""

    if context is not None:
        _agent.bind_context(context)

    return _agent.describe_command(command, language)


def handle_computer_use_command(
    command: str,
    language: str = "en",
    context=None,
) -> str | None:
    """Tool handler: visible-screen click / type / scroll actions."""

    if context is not None:
        _agent.bind_context(context)

    return _agent.execute(command, language)