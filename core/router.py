"""
F.R.I.D.A.Y. Task Router

The router decides which registered tool should handle a user request.

This is the first basic layer of F.R.I.D.A.Y.'s orchestration system.
"""

from dataclasses import dataclass
from typing import Any

import re

from .registry import ToolRegistry


@dataclass
class RouteResult:
    """Result returned by the router."""

    tool_name: str | None
    confidence: float
    reason: str


class TaskRouter:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def route(self, command: str) -> RouteResult:
        """
        Decide which tool should handle a command.

        This first version intentionally uses simple rules.
        Later, F.R.I.D.A.Y. can use an AI planner for more advanced routing.
        """

        if not command or not command.strip():
            return RouteResult(
                tool_name=None,
                confidence=0.0,
                reason="No command was provided.",
            )

        text = command.lower().strip()

        # ---------------------------------------------------------
        # SCREEN VISION (read-only)
        # ---------------------------------------------------------
        sv_keywords = (
            "what is on my screen",
            "whats on my screen",
            "what's on my screen",
            "what do you see on my screen",
            "what do you see",
            "what can you see",
            "what is showing on my screen",
            "read the screen",
            "describe the screen",
            "describe my screen",
            "describe the display",
            "look at the screen",
            "what is open on my screen",
        )

        if any(phrase in text for phrase in sv_keywords):
            if self.registry.get("screen_vision"):
                return RouteResult(
                    tool_name="screen_vision",
                    confidence=0.95,
                    reason="Command is a read-only screen description request.",
                )

        # ---------------------------------------------------------
        # COMPUTER USE (screen-aware clicking / typing / dragging)
        # ---------------------------------------------------------
        cu_media = ("track", "song", "music", "video")
        cu_click = bool(re.match(
            r"(?:double\s+[- ]?|right\s+[- ]?)?(?:click|tap)\s+(?:on\s+)?(?:the\s+)?\S+",
            text,
        ))
        cu_open_click = bool(re.search(r"\bopen\b.*\band\s+(?:click|tap)\b", text))
        cu_type_field = bool(re.search(r"\btype\s+.+\s+(?:into|in|inside|to)\s+.+", text))
        cu_scroll = bool(re.search(
            r"\bscroll\b.+?(?:until|till|you\s+see|you\s+find|to\s+see|to\s+find|down\s+to|up\s+to)",
            text,
        ))
        cu_drag = bool(re.search(r"\bdrag\b.*\bto\b", text))
        cu_back = bool(re.match(r"(?:go\s+)?back\b", text)) and not any(mw in text for mw in cu_media)

        if cu_click or cu_open_click or cu_type_field or cu_scroll or cu_drag or cu_back:
            if self.registry.get("computer_use"):
                return RouteResult(
                    tool_name="computer_use",
                    confidence=0.95,
                    reason="Command targets a visual element on the screen.",
                )

        # ---------------------------------------------------------
        # PC CONTROL
        # ---------------------------------------------------------
        pc_keywords = (
            "volume", "mute", "unmute", "sound", "louder", "quieter", "awaz",
            "brightness", "brighter", "dimmer",
            "play", "pause", "resume", "next", "skip", "previous", "last track", "last song", "go back track", "stop media", "stop music", "stop playback", "stop video",
            "desktop", "window", "windows",
            "lock pc", "lock computer", "lock the pc", "lock the computer", "lock screen",
            "copy", "paste", "cut", "select all", "select everything", "undo", "redo", "save", "clipboard",
            "type", "write", "enter text",
            "screenshot", "capture screen",
            "mouse", "click", "double click", "right click", "scroll",
            "press key", "keyboard", "press",
        )

        if any(keyword in text for keyword in pc_keywords):
            if self.registry.get("pc_control"):
                return RouteResult(
                    tool_name="pc_control",
                    confidence=0.90,
                    reason="Command appears to be a PC control request.",
                )

        # ---------------------------------------------------------
        # MESSAGING
        # ---------------------------------------------------------
        messaging_patterns = (
            re.compile(
                r"^(?:send|sending)\b.*\b(?:message|text)\b",
                re.IGNORECASE,
            ),
            re.compile(r"^(?:send\s+a|send)\s+whatsapp", re.IGNORECASE),
            re.compile(r"^message\b", re.IGNORECASE),
            re.compile(r"^whatsapp\b", re.IGNORECASE),
        )

        if any(
            pattern.match(text)
            for pattern in messaging_patterns
        ):
            if self.registry.get("messaging"):
                return RouteResult(
                    tool_name="messaging",
                    confidence=0.90,
                    reason="Command appears to be a messaging request.",
                )

        # ---------------------------------------------------------
        # SYSTEM CONTROL
        # ---------------------------------------------------------
        system_keywords = (
            "shutdown",
            "shut down",
            "restart",
            "reboot",
            "sleep",
            "log out",
            "logout",
        )

        if any(keyword in text for keyword in system_keywords):
            if self.registry.get("system_control"):
                return RouteResult(
                    tool_name="system_control",
                    confidence=0.95,
                    reason="Command appears to control the Windows system.",
                )

        # ---------------------------------------------------------
        # BROWSER / SEARCH
        # ---------------------------------------------------------
        browser_keywords = (
            "search",
            "searching",
            "google",
            "youtube",
            "website",
            "browser",
            "look up",
            "lookup",
            "find online",
        )

        if any(keyword in text for keyword in browser_keywords):
            if self.registry.get("browser"):
                return RouteResult(
                    tool_name="browser",
                    confidence=0.85,
                    reason="Command appears to require browser access.",
                )

        # ---------------------------------------------------------
        # APPLICATION CONTROL
        # ---------------------------------------------------------
        app_keywords = (
            "open",
            "launch",
            "start",
            "close",
            "quit",
            "exit",
        )

        if any(keyword in text for keyword in app_keywords):
            if self.registry.get("app_control"):
                return RouteResult(
                    tool_name="app_control",
                    confidence=0.85,
                    reason="Command appears to control an application.",
                )

        # ---------------------------------------------------------
        # FILES
        # ---------------------------------------------------------
        file_keywords = (
            "file",
            "folder",
            "document",
            "download",
            "rename",
            "move file",
            "delete file",
            "create folder",
        )

        if any(keyword in text for keyword in file_keywords):
            if self.registry.get("files"):
                return RouteResult(
                    tool_name="files",
                    confidence=0.80,
                    reason="Command appears to involve files or folders.",
                )

        # ---------------------------------------------------------
        # OTHERWISE → NO ROUTE
        # ---------------------------------------------------------
        return RouteResult(
            tool_name=None,
            confidence=0.0,
            reason="No registered tool matched this command.",
        )

    def execute(self, command: str) -> Any:
        """
        Route and execute a command.

        This method will later become part of F.R.I.D.A.Y.'s
        full planning/execution pipeline.
        """

        result = self.route(command)

        if result.tool_name is None:
            return None

        tool = self.registry.get(result.tool_name)

        if tool is None:
            return None

        return tool.handler(command)