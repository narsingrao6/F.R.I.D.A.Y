import re
from dataclasses import dataclass, field
from typing import Optional, Any

@dataclass
class IntentResult:
    intent: Optional[str] = None
    confidence: float = 0.0
    entities: dict = field(default_factory=dict)
    language: str = "en"
    normalized_text: str = ""
    is_ambiguous: bool = False
    clarification: Optional[str] = None

class NLUAnalyzer:
    def __init__(self):
        self.norm_rules = [
            (r"\bcheyyi\b|\bcheyi\b|\bcheyy\b", "chey"),
            (r"\bkaro\b", "kar"),
            (r"\bkholo\b", "khol"),
            (r"\bpencho\b|\bpenchu\b", "pench"),
            (r"\btagginchu\b|\bthagginchu\b|\btaginchu\b", "taginchu"),
            (r"\bbadhao\b", "badha"),
            (r"\bkam karo\b", "kam kar"),
            (r"\bband karo\b", "band kar"),
            (r"\bteesuko\b|\btheesuko\b", "teesko"),
        ]
        
        self.intents = {
            "open_and_click": [
                r"(?i)\bopen\s+(.+?)\s+and\s+(?:click|tap)\s+"
                r"(?:on\s+)?(?:the\s+)?"
                r"(?:button\s+|link\s+|icon\s+|tab\s+|option\s+|item\s+)?"
                r"(?:that\s+(?:says|reads|named|called)\s+|called\s+|named\s+)?"
                r"(.+?)\s*$",
            ],
            "open_application": [
                r"(?i)\b(?:open|launch|start)\s+(.+?)(?:\s+(?:please|now))?$",
                r"(?i)\b(.+?)\s+(?:open|launch|start|khol|kholo|chey)\b",
                r"(?i)i want\s+(.+)",
                r"(?i)i need\s+(.+)",
                r"(?i)can you start\s+(.+)",
            ],
            "close_application": [
                r"(?i)\b(?:close|shut|quit|exit|kill|stop)\s+(.+?)$",
                r"(?i)\b(.+?)\s+(?:close|shut|band|kar|chey)\b",
                r"(?i)can you shut\s+(.+)",
            ],
            "increase_brightness": [
                r"(?i)\b(?:increase|raise|turn up)\s+(?:the\s+)?brightness\b",
                r"(?i)\b(?:make|turn)\s+(?:the\s+)?(?:screen|display)\s+(?:brighter)\b",
                r"(?i)\b(?:brighten)\s+(?:the\s+)?(?:screen|display)\b",
                r"(?i)\b(?:brightness|screen bright)\s+(?:pench|badha|zyada|up)\b",
                r"(?i)screen\s+(?:is\s+)?(?:too\s+)?dark",
            ],
            "decrease_brightness": [
                r"(?i)\b(?:decrease|lower|turn down)\s+(?:the\s+)?brightness\b",
                r"(?i)\b(?:make|turn)\s+(?:the\s+)?(?:screen|display)\s+(?:dimmer|darker)\b",
                r"(?i)\b(?:dim)\s+(?:the\s+)?(?:screen|display)\b",
                r"(?i)\b(?:brightness|screen bright)\s+(?:taginchu|kam|down)\b",
                r"(?i)screen\s+(?:is\s+)?(?:too\s+)?bright",
            ],
            "increase_volume": [
                r"(?i)\b(?:increase|raise|turn up)\s+(?:the\s+)?(?:volume|sound|awaz)\b",
                r"(?i)\b(?:make|turn)\s+(?:it\s+)?louder\b",
                r"(?i)\b(?:volume|sound|awaz)\s+(?:pench|badha|zyada|up)\b",
                r"(?i)can you increase my volume",
            ],
            "decrease_volume": [
                r"(?i)\b(?:decrease|lower|turn down)\s+(?:the\s+)?(?:volume|sound|awaz)\b",
                r"(?i)\b(?:make|turn)\s+(?:it\s+)?quieter\b",
                r"(?i)\b(?:volume|sound|awaz)\s+(?:taginchu|kam|down)\b",
            ],
            "mute": [
                r"(?i)\bmute\b",
                r"(?i)\b(?:sound|volume|awaz)\s+(?:mute|off|band)\b",
            ],
            "unmute": [
                r"(?i)\bunmute\b",
                r"(?i)\b(?:sound|volume|awaz)\s+(?:unmute|on|chalu)\b",
            ],
            "play_pause": [
                r"(?i)\b(?:play|pause|resume)\s*(?:media|music|video|playback|song|track)?\b",
            ],
            "next_media": [
                r"(?i)\b(?:next|skip)\s*(?:media|music|video|playback|song|track)?\b",
            ],
            "previous_media": [
                r"(?i)\b(?:previous|last|go back)\s*(?:media|music|video|playback|song|track)\b",
            ],
            "show_desktop": [
                r"(?i)\b(?:show|go to)\s+(?:desktop|home screen)\b",
            ],
            "minimize_window": [
                r"(?i)\bminimize\s+(?:the\s+)?(?:window|windows)\b",
            ],
            "maximize_window": [
                r"(?i)\bmaximize\s+(?:the\s+)?(?:window|windows)\b",
            ],
            "switch_window": [
                r"(?i)\b(?:switch|change)\s+(?:the\s+)?(?:window|windows)\b",
], 
            "click": [
                r"(?i)\b(?:click|mouse click)\b",
            ],
            "click_element": [
                r"(?i)\b(?:click|tap)\s+(?:on\s+)?(?:the\s+)?"
                r"(?!(?:enter|esc|escape|tab|space|spacebar|backspace|delete|home|end)\b)"
                r"(?:button\s+|link\s+|icon\s+|tab\s+|option\s+|item\s+)?"
                r"(?:that\s+(?:says|reads|named|called)\s+|called\s+|named\s+)?"
                r"(.+?)\s*$",
            ],
            "double_click": [
                r"(?i)\bdouble\s+click\b",
            ],
            "double_click_element": [
                r"(?i)\bdouble\s*[- ]?\s*click\s+(?:on\s+)?(?:the\s+)?"
                r"(?:button\s+|link\s+|icon\s+|item\s+)?"
                r"(?:that\s+(?:says|reads|named|called)\s+|called\s+)?"
                r"(.+?)\s*$",
            ],
            "right_click": [
                r"(?i)\bright\s+click\b",
            ],
            "right_click_element": [
                r"(?i)\bright\s*[- ]?\s*click\s+(?:on\s+)?(?:the\s+)?"
                r"(?:button\s+|link\s+|icon\s+|item\s+)?"
                r"(?:that\s+(?:says|reads|named|called)\s+|called\s+)?"
                r"(.+?)\s*$",
            ],
            "scroll_up": [
                r"(?i)\b(?:scroll|page)\s+up\b",
            ],
            "scroll_down": [
                r"(?i)\b(?:scroll|page)\s+down\b",
            ],
            "take_screenshot": [
                r"(?i)\b(?:take|capture)\s+(?:a\s+)?(?:screenshot|screen)\b",
                r"(?i)\bscreenshot\s+(?:teesko|lo)\b",
            ],
            "lock_pc": [
                r"(?i)\block\s+(?:my\s+|the\s+)?(?:pc|computer|screen)\b",
                r"(?i)\b(?:pc|computer)\s+lock\s+(?:chey|kar)\b",
            ],
            "shutdown": [
                r"(?i)\b(?:shut down|shutdown)\b",
            ],
            "restart": [
                r"(?i)\b(?:restart|reboot)\b",
            ],
            "sleep": [
                r"(?i)\bsleep\b",
            ],
            "logout": [
                r"(?i)\b(?:logout|log out)\b",
            ],
            "screen_type": [
                r"(?i)\btype\s+(.+?)\s+(?:into|in|inside|to)\s+(.+?)\s*$",
            ],
            "type_text": [
                r"(?i)\b(?:type|write|enter text)\s+(.+)\b",
            ],
            "press_key": [
                r"(?i)\b(?:press|hit)\s+(?:the\s+)?(?:key\s+)?([a-z0-9\s]+?)(?:\s+key)?\b",
            ]
        }

    def analyze(self, text: str, detected_language: str) -> IntentResult:
        command = text
        text = text.lower().strip()
        
        for pattern, replacement in self.norm_rules:
            text = re.sub(pattern, replacement, text)
            
        best_intent = None
        best_confidence = 0.0
        best_entities = {}
        
        for intent_name, patterns in self.intents.items():
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    entities = {}
                    if match.groups():
                        if intent_name in ("open_application", "close_application", "open_and_click"):
                            app_name = match.group(1).strip()
                            app_name = re.sub(r"^(the|my|a|an)\s+", "", app_name)
                            entities["application"] = app_name
                            if intent_name == "open_and_click":
                                entities["target"] = match.group(2).strip()
                        elif intent_name in (
                            "click_element",
                            "double_click_element",
                            "right_click_element",
                        ):
                            entities["target"] = match.group(1).strip()
                        elif intent_name == "type_text":
                            original_match = re.search(pattern, command, re.IGNORECASE)
                            entities["text"] = original_match.group(1).strip() if original_match else match.group(1).strip()
                        elif intent_name == "screen_type":
                            entities["text"] = match.group(1).strip()
                            entities["field"] = match.group(2).strip()
                        elif intent_name == "press_key":
                            entities["key"] = match.group(1).strip()
                    
                    if match.span() == (0, len(text)):
                        confidence = 0.95
                    else:
                        confidence = 0.85
                        
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_intent = intent_name
                        best_entities = entities
                        
        if best_intent:
            if "chey" in text or "teesko" in text or "pench" in text or "taginchu" in text:
                if detected_language == "hi":
                    detected_language = "te"
            elif "kar" in text or "khol" in text or "badha" in text or "kam" in text:
                if detected_language == "te":
                    detected_language = "hi"
                    
        return IntentResult(
            intent=best_intent,
            confidence=best_confidence,
            entities=best_entities,
            language=detected_language,
            normalized_text=text
        )

_SCREEN_PRONOUNS = {
    "it", "that", "this", "there", "here",
    "the button", "that button", "the item", "that item",
}


def _serialize_screen_target(
    intent: IntentResult,
    context_manager,
    prefix: str,
) -> str | None:
    """Serialize a click/double/right target, resolving pronouns via context."""

    target = intent.entities.get("target", "").strip()

    if target in _SCREEN_PRONOUNS:
        last = context_manager.get_metadata("last_screen_target")
        if not last:
            intent.is_ambiguous = True
            intent.clarification = (
                "Which element should I click on the screen?"
            )
            return None
        target = last

    context_manager.set_metadata("last_screen_target", target)
    return f"{prefix} {target}"


def serialize_intent(intent: IntentResult, context_manager) -> str | None:
    i = intent.intent
    e = intent.entities
    
    if i in ("open_application", "close_application"):
        app = e.get("application")
        if app in {"it", "this", "that", "there", "the app", "the browser", "the window", "that app", "it please"}:
            last_app = context_manager.get_metadata("last_opened_app")
            if not last_app:
                intent.is_ambiguous = True
                if i == "open_application":
                    intent.clarification = "Which application would you like me to open?"
                else:
                    intent.clarification = "Which application would you like me to close?"
                return None
            app = last_app
            e["application"] = app

    if i == "open_application":
        app = e.get("application")
        context_manager.set_metadata("last_opened_app", app)
        return f"open {app}"

    elif i == "open_and_click":
        app = e.get("application")
        target = e.get("target")
        context_manager.set_metadata("last_opened_app", app)
        return f"open {app} and click {target}"

    elif i == "click_element":
        return _serialize_screen_target(intent, context_manager, "click")

    elif i == "double_click_element":
        return _serialize_screen_target(
            intent,
            context_manager,
            "double click",
        )

    elif i == "right_click_element":
        return _serialize_screen_target(
            intent,
            context_manager,
            "right click",
        )

    elif i == "screen_type":
        return f"type {e.get('text', '')} in {e.get('field', '')}"
        
    elif i == "close_application":
        app = e.get("application")
        return f"close {app}"
        
    elif i == "increase_brightness": return "increase brightness"
    elif i == "decrease_brightness": return "decrease brightness"
    elif i == "increase_volume": return "increase volume"
    elif i == "decrease_volume": return "decrease volume"
    elif i == "mute": return "mute"
    elif i == "unmute": return "unmute"
    elif i == "play_pause": return "play media"
    elif i == "next_media": return "next track"
    elif i == "previous_media": return "previous track"
    elif i == "show_desktop": return "show desktop"
    elif i == "minimize_window": return "minimize window"
    elif i == "maximize_window": return "maximize window"
    elif i == "switch_window": return "switch window" 
    elif i == "click": return "click"
    elif i == "double_click": return "double click"
    elif i == "right_click": return "right click"
    elif i == "scroll_up": return "scroll up"
    elif i == "scroll_down": return "scroll down"
    elif i == "take_screenshot": return "take screenshot"
    elif i == "lock_pc": return "lock pc"
    elif i == "shutdown": return "shutdown"
    elif i == "restart": return "restart"
    elif i == "sleep": return "sleep"
    elif i == "logout": return "logout"
    elif i == "type_text": return f"type {e.get('text', '')}"
    elif i == "press_key": return f"press {e.get('key', e.get('text', ''))}"
        
    return None

