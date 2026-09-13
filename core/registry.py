"""
F.R.I.D.A.Y. Tool Registry

Central registry for all capabilities available to F.R.I.D.A.Y.
Tools can be registered here and discovered by the task router.
"""

from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[..., Any]
    requires_confirmation: bool = False


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        requires_confirmation: bool = False,
    ) -> None:
        """Register a tool with F.R.I.D.A.Y."""
        self._tools[name] = Tool(
            name=name,
            description=description,
            handler=handler,
            requires_confirmation=requires_confirmation,
        )

    def get(self, name: str) -> Tool | None:
        """Get a registered tool by name."""
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def names(self) -> list[str]:
        """Return the names of all registered tools."""
        return list(self._tools.keys())

    def describe(self) -> str:
        """Return a human-readable description of all registered tools."""
        if not self._tools:
            return "No tools are currently available."

        lines = []

        for tool in self._tools.values():
            confirmation = (
                " [confirmation required]"
                if tool.requires_confirmation
                else ""
            )

            lines.append(
                f"- {tool.name}: {tool.description}{confirmation}"
            )

        return "\n".join(lines)