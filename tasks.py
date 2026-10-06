"""Private local task storage and voice-command handling."""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class Task:
    id: int
    description: str


class TaskStore:
    """Store open tasks in a local SQLite database."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0
                )"""
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def add(self, description: str) -> Task:
        description = description.strip()
        if not description:
            raise ValueError("Task description cannot be empty")
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO tasks (description) VALUES (?)", (description,)
            )
            task_id = int(cursor.lastrowid)
        return Task(task_id, description)

    def list_open(self) -> list[Task]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id, description FROM tasks WHERE completed = 0 ORDER BY id"
            ).fetchall()
        return [Task(int(task_id), str(description)) for task_id, description in rows]

    def get_open(self, task_id: int) -> Task | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, description FROM tasks WHERE id = ? AND completed = 0",
                (task_id,),
            ).fetchone()
        return Task(int(row[0]), str(row[1])) if row else None

    def update(self, task_id: int, description: str) -> Task | None:
        description = description.strip()
        if not description:
            raise ValueError("Task description cannot be empty")
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET description = ? WHERE id = ? AND completed = 0",
                (description, task_id),
            )
            if cursor.rowcount != 1:
                return None
        return Task(task_id, description)

    def complete(self, task_id: int) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET completed = 1 WHERE id = ? AND completed = 0",
                (task_id,),
            )
        return cursor.rowcount == 1

    def delete(self, task_id: int) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM tasks WHERE id = ? AND completed = 0", (task_id,)
            )
        return cursor.rowcount == 1


_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_ONES = {word for word, value in _NUMBER_WORDS.items() if 1 <= value <= 9}
_TENS = {word for word, value in _NUMBER_WORDS.items() if 20 <= value <= 90}


def _parse_task_number(value: str) -> int | None:
    value = value.strip().lower().strip(" .,!?;:")
    if value.startswith("number "):
        value = value[7:].strip()
    if value.isdecimal():
        number = int(value)
        return number if number > 0 else None

    tokens = value.replace("-", " ").split()
    if not tokens or any(token not in _NUMBER_WORDS and token != "hundred" and token != "and" for token in tokens):
        return None
    if "hundred" not in tokens:
        if len(tokens) == 1:
            number = _NUMBER_WORDS[tokens[0]]
        elif len(tokens) == 2 and tokens[0] in _TENS and tokens[1] in _ONES:
            number = _NUMBER_WORDS[tokens[0]] + _NUMBER_WORDS[tokens[1]]
        else:
            return None
        return number if number > 0 else None

    hundred_index = tokens.index("hundred")
    prefix = tokens[:hundred_index]
    suffix = tokens[hundred_index + 1 :]
    if len(prefix) != 1 or prefix[0] not in _ONES:
        return None
    if suffix[:1] == ["and"]:
        suffix = suffix[1:]
    remainder = _parse_task_number(" ".join(suffix)) if suffix else 0
    if remainder is None or remainder >= 100:
        return None
    return _NUMBER_WORDS[prefix[0]] * 100 + remainder


class TaskCommands:
    """Interpret task commands and hold a delete confirmation for one turn."""

    def __init__(self, store: TaskStore) -> None:
        self.store = store
        self.pending_delete_id: int | None = None

    def handle(self, text: str) -> str | None:
        if self.pending_delete_id is not None:
            return self._handle_delete_confirmation(text)
        return self._handle_new_command(text)

    def cancel_pending_deletion(self) -> bool:
        """Clear an outstanding delete confirmation after unusable audio."""
        if self.pending_delete_id is None:
            return False
        self.pending_delete_id = None
        return True

    def _handle_delete_confirmation(self, text: str) -> str:
        task_id = self.pending_delete_id
        self.pending_delete_id = None
        match = re.fullmatch(
            r"\s*confirm\s+delete\s+task\b(.*?)\s*[.!?]*\s*", text, re.IGNORECASE
        )
        confirmed_id = _parse_task_number(match.group(1)) if match else None
        if confirmed_id != task_id:
            return "Deletion canceled. The exact task confirmation did not match; nothing was deleted."
        if self.store.delete(task_id):
            return f"Deleted task {task_id}."
        return f"Deletion canceled. Task {task_id} is no longer open. Nothing was deleted."

    def _handle_new_command(self, text: str) -> str | None:
        return _handle_new_task_command(text, self.store, self)


def handle_task_command(text: str, store: TaskStore) -> str | None:
    """Handle a single task command without retaining confirmation state."""
    return TaskCommands(store).handle(text)


def _handle_new_task_command(
    text: str, store: TaskStore, commands: TaskCommands
) -> str | None:
    add_match = re.fullmatch(
        r"\s*add\s+task(?:\s+(.*?))?\s*[.!?]*\s*", text, re.IGNORECASE
    )
    if add_match:
        description = (add_match.group(1) or "").strip()
        if not description:
            return "What should I add? Say 'Add task' followed by a short description."
        task = store.add(description)
        return f"Added task {task.id}: {task.description}."

    normalized = " ".join(text.lower().strip().split()).rstrip(".!?")
    if normalized == "list tasks":
        tasks = store.list_open()
        if not tasks:
            return "You have no open tasks."
        if len(tasks) == 1:
            task = tasks[0]
            return f"You have one open task. Task {task.id}: {task.description}."
        details = " ".join(f"Task {task.id}: {task.description}." for task in tasks)
        return f"You have {len(tasks)} open tasks. {details}"

    complete_match = re.fullmatch(r"\s*complete\s+task\b(.*?)\s*[.!?]*\s*", text, re.IGNORECASE)
    if complete_match:
        number_text = complete_match.group(1).strip()
        task_id = _parse_task_number(number_text)
        if task_id is None:
            return "I need a clear task number. Say 'Complete task' followed by one task number."
        if store.complete(task_id):
            return f"Completed task {task_id}."
        return f"I couldn't find open task {task_id}. Say 'List tasks' to hear your open tasks."

    update_match = re.fullmatch(
        r"\s*update\s+task\b(.*?)\s+to\s+(.+?)\s*[.!?]*\s*", text, re.IGNORECASE
    )
    if update_match:
        task_id = _parse_task_number(update_match.group(1))
        description = update_match.group(2).strip()
        if task_id is None:
            return "I need a clear task number. Say 'Update task' followed by one number and the new description."
        if not description:
            return f"What should I change task {task_id} to? Repeat the update with its new description."
        task = store.update(task_id, description)
        if task is None:
            return f"I couldn't find open task {task_id}. Say 'List tasks' to hear your open tasks."
        return f"Updated task {task.id}: {task.description}."

    delete_match = re.fullmatch(
        r"\s*delete\s+task\b(.*?)\s*[.!?]*\s*", text, re.IGNORECASE
    )
    if delete_match:
        task_id = _parse_task_number(delete_match.group(1))
        if task_id is None:
            return "I need a clear task number. Nothing was deleted. Say 'Delete task' followed by one number."
        task = store.get_open(task_id)
        if task is None:
            return f"I couldn't find open task {task_id}. Nothing was deleted."
        commands.pending_delete_id = task_id
        return (
            f"Task {task.id} is {task.description}. To delete it, say exactly: "
            f"'Confirm delete task {task.id}'."
        )

    if normalized.startswith("add task"):
        return "What should I add? Say 'Add task' followed by a short description."
    if normalized.startswith("list task"):
        return "Please say 'List tasks' to hear your open tasks."
    if normalized.startswith("complete task"):
        return "I need a clear task number. Say 'Complete task' followed by one task number."
    if normalized.startswith("update task"):
        return "Say 'Update task' followed by one task number, 'to', and the new description."
    if normalized.startswith("delete task"):
        return "I need a clear task number. Nothing was deleted. Say 'Delete task' followed by one number."
    if normalized.startswith("confirm delete task"):
        return "There is no deletion waiting for confirmation."
    return None
