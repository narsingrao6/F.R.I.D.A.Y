"""
F.R.I.D.A.Y. Context Manager

Stores the current conversation and task state so different
F.R.I.D.A.Y. components can share the same context.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationTurn:
    """One user/assistant interaction."""

    user: str
    assistant: str = ""
    language: str = "en"


@dataclass
class TaskContext:
    """Shared context for the current F.R.I.D.A.Y. task."""

    user_command: str = ""
    language: str = "en"
    current_task: str = ""
    selected_tool: str | None = None
    last_result: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    history: list[ConversationTurn] = field(default_factory=list)


class ContextManager:
    def __init__(self, max_history: int = 20):
        self.context = TaskContext()
        self.max_history = max_history

    def update_command(
        self,
        command: str,
        language: str = "en",
    ) -> None:
        """Update the current user command and language."""

        self.context.user_command = command
        self.context.language = language
        self.context.current_task = command

    def set_tool(self, tool_name: str | None) -> None:
        """Store the currently selected tool."""

        self.context.selected_tool = tool_name

    def set_result(self, result: Any) -> None:
        """Store the result of the latest operation."""

        self.context.last_result = result

    def add_turn(
        self,
        user: str,
        assistant: str = "",
        language: str = "en",
    ) -> None:
        """Add a conversation turn to short-term context."""

        self.context.history.append(
            ConversationTurn(
                user=user,
                assistant=assistant,
                language=language,
            )
        )

        if len(self.context.history) > self.max_history:
            self.context.history = self.context.history[-self.max_history:]

    def set_metadata(self, key: str, value: Any) -> None:
        """Store additional task metadata."""

        self.context.metadata[key] = value

    def get_metadata(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """Retrieve task metadata."""

        return self.context.metadata.get(key, default)

    def recent_history(self, limit: int = 5) -> list[ConversationTurn]:
        """Return the most recent conversation turns."""

        return self.context.history[-limit:]

    def clear_task(self) -> None:
        """Clear the current task state while keeping conversation history."""

        self.context.user_command = ""
        self.context.current_task = ""
        self.context.selected_tool = None
        self.context.last_result = None
        self.context.metadata.clear()

    def clear_all(self) -> None:
        """Completely reset the context."""

        self.context = TaskContext()

    def summary(self) -> str:
        """Return a compact human-readable context summary."""

        lines = [
            f"Command: {self.context.user_command or 'None'}",
            f"Language: {self.context.language}",
            f"Task: {self.context.current_task or 'None'}",
            f"Tool: {self.context.selected_tool or 'None'}",
        ]

        if self.context.last_result is not None:
            lines.append(
                f"Last result: {self.context.last_result}"
            )

        return "\n".join(lines)