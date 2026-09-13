"""
F.R.I.D.A.Y. Task Planner

The planner converts a user request into one or more executable steps.

This is the foundation for future multi-step reasoning and orchestration.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanStep:
    """A single action inside a task plan."""

    action: str
    description: str
    arguments: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False


@dataclass
class TaskPlan:
    """A complete plan generated for a user request."""

    goal: str
    steps: list[PlanStep] = field(default_factory=list)


class TaskPlanner:
    def __init__(self):
        pass

    def create_plan(self, command: str, language: str = "en") -> TaskPlan:
        """
        Create a basic plan from a user command.

        The current version creates a simple one-step plan.
        Later, an AI planner can break complex requests into
        multiple dependent steps.
        """

        command = command.strip()

        if not command:
            return TaskPlan(
                goal="",
                steps=[],
            )

        step = PlanStep(
            action="route",
            description=f"Process the request: {command}",
            arguments={
                "command": command,
                "language": language,
            },
        )

        return TaskPlan(
            goal=command,
            steps=[step],
        )

    def has_steps(self, plan: TaskPlan) -> bool:
        """Check whether a plan contains executable steps."""

        return bool(plan.steps)

    def describe(self, plan: TaskPlan) -> str:
        """Create a human-readable description of a plan."""

        if not plan.steps:
            return "No steps were planned."

        lines = [
            f"Goal: {plan.goal}",
            "",
            "Steps:",
        ]

        for index, step in enumerate(plan.steps, start=1):
            confirmation = (
                " [confirmation required]"
                if step.requires_confirmation
                else ""
            )

            lines.append(
                f"{index}. {step.description}{confirmation}"
            )

        return "\n".join(lines)