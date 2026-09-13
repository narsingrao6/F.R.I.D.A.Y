"""
F.R.I.D.A.Y. Task Executor

Executes the steps produced by the task planner.

This layer is intentionally separated from planning and routing so
F.R.I.D.A.Y. can later support verification, permissions, retries,
and multi-step tasks.
"""

from dataclasses import dataclass
from typing import Any

from .planner import PlanStep, TaskPlan
from .registry import ToolRegistry
from .router import TaskRouter


from .permission import PermissionManager


@dataclass
class ExecutionResult:
    """Result of executing a task plan."""

    success: bool
    results: list[Any]
    error: str | None = None
    requires_confirmation: bool = False
    tool_name: str | None = None


class TaskExecutor:
    def __init__(self, registry: ToolRegistry, router: TaskRouter, permissions: PermissionManager = None):
        self.registry = registry
        self.router = router
        self.permissions = permissions

    def execute_step(self, step: PlanStep) -> Any:
        """Execute a single plan step."""

        if step.action == "route":
            command = step.arguments.get("command", "")
            language = step.arguments.get("language", "en")

            route = self.router.route(command)

            if route.tool_name is None:
                return None

            tool = self.registry.get(route.tool_name)

            if tool is None:
                raise RuntimeError(
                    f"Tool '{route.tool_name}' is not registered."
                )

            if self.permissions:
                perm_result = self.permissions.check(tool.name)
                if perm_result.requires_confirmation:
                    raise PermissionError(tool.name)
            elif tool.requires_confirmation:
                raise PermissionError(tool.name)

            return tool.handler(command, language=language)

        tool = self.registry.get(step.action)

        if tool is None:
            raise RuntimeError(
                f"Tool '{step.action}' is not registered."
            )

        if self.permissions:
            perm_result = self.permissions.check(tool.name)
            if perm_result.requires_confirmation:
                raise PermissionError(tool.name)
        elif tool.requires_confirmation:
            raise PermissionError(tool.name)

        return tool.handler(**step.arguments)

    def execute_plan(self, plan: TaskPlan) -> ExecutionResult:
        """Execute every step in a task plan."""

        if not plan.steps:
            return ExecutionResult(
                success=False,
                results=[],
                error="The task plan contains no steps.",
            )

        results = []

        try:
            for step in plan.steps:
                result = self.execute_step(step)
                results.append(result)

            return ExecutionResult(
                success=True,
                results=results,
            )

        except PermissionError as error:
            return ExecutionResult(
                success=False,
                results=results,
                error=f"Confirmation required for tool '{error}'",
                requires_confirmation=True,
                tool_name=str(error),
            )
        except Exception as error:
            return ExecutionResult(
                success=False,
                results=results,
                error=f"{type(error).__name__}: {error}",
            )