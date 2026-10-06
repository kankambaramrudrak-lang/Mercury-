"""The shared command route for typed and recognized text."""

from __future__ import annotations

import re

from tools.tasks import TaskCommands


class CommandRouter:
    """Route all command text through one ``handle`` method."""

    def __init__(self, tasks: TaskCommands) -> None:
        self._tasks = tasks

    def handle(self, text: str) -> str:
        task_reply = self._tasks.handle(text)
        if task_reply is not None:
            return task_reply

        normalized = text.strip().lower().strip(".,!? ")
        if re.search(r"\b(hello|hi|hey|good morning|good afternoon|good evening)\b", normalized):
            return "Hello! I'm Hercules."
        return (
            "I didn't understand. Say 'Add task' followed by a description, "
            "'List tasks', 'Complete task' followed by a number, or "
            "'Update task' followed by a number and new description. "
            "Deletion is unavailable until button confirmation is implemented."
        )
