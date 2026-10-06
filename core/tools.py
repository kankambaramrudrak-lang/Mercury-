"""Small registry for the local actions Hercules is allowed to run."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import partial
from typing import Callable, Literal, Mapping

from tools.tasks import TaskStore, count_tasks

RiskLevel = Literal["run", "log", "confirm"]
ToolFunction = Callable[..., object]


@dataclass(frozen=True)
class Tool:
    """A named action with a short description and declared parameters."""

    name: str
    description: str
    parameters: Mapping[str, str]
    risk_level: RiskLevel
    function: ToolFunction


class ToolRegistry:
    """Only invoke functions that have been explicitly registered."""

    def __init__(self, confirmation_handler: Callable[[str, str], bool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._confirmation_handler = confirmation_handler

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def execute(self, name: str, **parameters: object) -> object:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool is not registered: {name}")
        if tool.risk_level == "confirm":
            if self._confirmation_handler is None:
                return "Deletion is disabled because button confirmation is unavailable. The task is unchanged."
            details = "Approve this action?"
            if name == "delete_task":
                details = f"Delete task {parameters.get('task_number', 'unknown')}?"
            try:
                approved = bool(self._confirmation_handler(f"Confirm {name}", details))
            except Exception:
                approved = False
            logging.getLogger("hercules.confirmations").info("tool=%s approved=%s", name, approved)
            if not approved:
                return "Action cancelled or timed out. No changes were made."
        return tool.function(**parameters)


def build_task_registry(
    store: TaskStore,
    confirmation_handler: Callable[[str, str], bool] | None = None,
) -> ToolRegistry:
    """Register the supported local task actions against the supplied store."""

    registry = ToolRegistry(confirmation_handler)

    def add_task(description: str) -> str:
        task = store.add(description)
        return f"Added task {task.id}: {task.description}."

    def list_tasks() -> str:
        tasks = store.list_open()
        if not tasks:
            return "You have no open tasks."
        if len(tasks) == 1:
            task = tasks[0]
            return f"You have one open task. Task {task.id}: {task.description}."
        details = " ".join(f"Task {task.id}: {task.description}." for task in tasks)
        return f"You have {len(tasks)} open tasks. {details}"

    def complete_task(task_number: int) -> str:
        if store.complete(task_number):
            return f"Completed task {task_number}."
        return f"I couldn't find open task {task_number}. Say 'List tasks' to hear your open tasks."

    def update_task(task_number: int, description: str) -> str:
        task = store.update(task_number, description)
        if task is None:
            return f"I couldn't find open task {task_number}. Say 'List tasks' to hear your open tasks."
        return f"Updated task {task.id}: {task.description}."

    def delete_task(task_number: int) -> str:
        if store.delete(task_number):
            return f"Deleted task {task_number}."
        return f"I couldn't find open task {task_number}. No task was deleted."

    registrations = (
        Tool("add_task", "Add a task to the local task list.", {"description": "string"}, "run", add_task),
        Tool("list_tasks", "List open local tasks.", {}, "run", list_tasks),
        Tool("complete_task", "Mark an open local task complete.", {"task_number": "integer"}, "run", complete_task),
        Tool("update_task", "Change an open local task description.", {"task_number": "integer", "description": "string"}, "run", update_task),
        Tool("delete_task", "Delete a local task after button confirmation.", {"task_number": "integer"}, "confirm", delete_task),
        Tool("count_tasks", "Count open local tasks.", {}, "run", partial(count_tasks, store)),
    )
    for tool in registrations:
        registry.register(tool)
    return registry
