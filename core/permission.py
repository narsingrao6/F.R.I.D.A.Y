"""
F.R.I.D.A.Y. Permission Manager

Controls whether an action can execute immediately or requires
user confirmation.

This is a safety layer between planning and execution.
"""

from dataclasses import dataclass
from enum import Enum


class PermissionLevel(str, Enum):
    SAFE = "safe"
    CONFIRM = "confirm"
    HIGH_RISK = "high_risk"


@dataclass
class PermissionResult:
    allowed: bool
    requires_confirmation: bool
    level: PermissionLevel
    reason: str


class PermissionManager:
    def __init__(self):
        self._levels = {
            # Safe actions
            "pc_control": PermissionLevel.SAFE,
            "app_control": PermissionLevel.SAFE,
            "browser": PermissionLevel.SAFE,
            "files": PermissionLevel.CONFIRM,

            # Read-only screen understanding is safe.
            "screen_vision": PermissionLevel.SAFE,

            # Computer use clicks/types on the screen, so confirm first.
            "computer_use": PermissionLevel.CONFIRM,

            # Messaging sends real messages, so confirm first.
            "messaging": PermissionLevel.CONFIRM,

            # Sensitive system actions
            "system_control": PermissionLevel.HIGH_RISK,
        }

    def set_level(
        self,
        tool_name: str,
        level: PermissionLevel,
    ) -> None:
        """Set the permission level for a tool."""

        self._levels[tool_name] = level

    def get_level(self, tool_name: str) -> PermissionLevel:
        """Return the permission level of a tool."""

        return self._levels.get(
            tool_name,
            PermissionLevel.CONFIRM,
        )

    def check(self, tool_name: str) -> PermissionResult:
        """Check whether a tool can execute."""

        level = self.get_level(tool_name)

        if level == PermissionLevel.SAFE:
            return PermissionResult(
                allowed=True,
                requires_confirmation=False,
                level=level,
                reason="This action is considered safe.",
            )

        if level == PermissionLevel.CONFIRM:
            return PermissionResult(
                allowed=False,
                requires_confirmation=True,
                level=level,
                reason="This action requires confirmation.",
            )

        return PermissionResult(
            allowed=False,
            requires_confirmation=True,
            level=level,
            reason="This action is high-risk and requires explicit confirmation.",
        )

    def is_safe(self, tool_name: str) -> bool:
        """Return True when a tool can execute without confirmation."""

        return self.get_level(tool_name) == PermissionLevel.SAFE

    def requires_confirmation(self, tool_name: str) -> bool:
        """Return True when a tool requires confirmation."""

        return self.get_level(tool_name) != PermissionLevel.SAFE

    def tools(self) -> dict[str, PermissionLevel]:
        """Return the current permission configuration."""

        return self._levels.copy()