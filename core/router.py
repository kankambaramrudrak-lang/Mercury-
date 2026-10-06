"""The shared command route for typed and recognized text."""

from __future__ import annotations

import re
from typing import Callable

from core.tools import ToolRegistry, build_task_registry
from tools.tasks import TaskCommands, _parse_task_number


class CommandRouter:
    """Route all command text through one ``handle`` method."""

    def __init__(
        self,
        tasks: TaskCommands,
        registry: ToolRegistry | None = None,
        confirmation_handler: Callable[[str, str], bool] | None = None,
    ) -> None:
        self._registry = registry or build_task_registry(tasks.store, confirmation_handler)

    def handle(self, text: str) -> str:
        normalized = text.strip().lower().strip(".,!? ")
        if re.search(r"\b(hello|hi|hey|good morning|good afternoon|good evening)\b", normalized):
            return "Hello! I'm Hercules."

        add_match = re.fullmatch(r"\s*add\s+task(?:\s+(.*?))?\s*[.!?]*\s*", text, re.IGNORECASE)
        if add_match:
            description = (add_match.group(1) or "").strip()
            if not description:
                return "What should I add? Say 'Add task' followed by a short description."
            return str(self._registry.execute("add_task", description=description))

        if normalized == "list tasks":
            return str(self._registry.execute("list_tasks"))

        if normalized in {"count tasks", "how many tasks"}:
            count = int(self._registry.execute("count_tasks"))
            if count == 1:
                return "You have one open task."
            return f"You have {count} open tasks."

        complete_match = re.fullmatch(r"\s*complete\s+task\b(.*?)\s*[.!?]*\s*", text, re.IGNORECASE)
        if complete_match:
            task_number = _parse_task_number(complete_match.group(1))
            if task_number is None:
                return "I need a clear task number. Say 'Complete task' followed by one task number."
            return str(self._registry.execute("complete_task", task_number=task_number))

        update_match = re.fullmatch(
            r"\s*update\s+task\b(.*?)\s+to\s+(.+?)\s*[.!?]*\s*", text, re.IGNORECASE
        )
        if update_match:
            task_number = _parse_task_number(update_match.group(1))
            description = update_match.group(2).strip()
            if task_number is None:
                return "I need a clear task number. Say 'Update task' followed by one number and the new description."
            if not description:
                return f"What should I change task {task_number} to? Repeat the update with its new description."
            return str(self._registry.execute("update_task", task_number=task_number, description=description))

        if re.fullmatch(r"\s*(?:delete|confirm\s+delete)\s+task\b.*", text, re.IGNORECASE):
            number_match = re.search(r"task\b(.*?)\s*[.!?]*\s*$", text, re.IGNORECASE)
            task_number = _parse_task_number(number_match.group(1)) if number_match else None
            if task_number is None:
                return "Deletion is disabled until Phase 3 adds button confirmation. No task was changed."
            return str(self._registry.execute("delete_task", task_number=task_number))

        if normalized.startswith("add task"):
            return "What should I add? Say 'Add task' followed by a short description."
        if normalized.startswith("list task"):
            return "Please say 'List tasks' to hear your open tasks."
        if normalized.startswith("complete task"):
            return "I need a clear task number. Say 'Complete task' followed by one task number."
        if normalized.startswith("update task"):
            return "Say 'Update task' followed by one task number, 'to', and the new description."
        if normalized.startswith("count task"):
            return "Please say 'Count tasks' to count your open tasks."
        return (
            "I didn't understand. Say 'Add task' followed by a description, "
            "'List tasks', 'Complete task' followed by a number, or "
            "'Update task' followed by a number and new description, or "
            "'Count tasks'. "
            "Deletion is unavailable until button confirmation is implemented."
        )
