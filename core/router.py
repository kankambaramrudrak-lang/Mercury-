"""The shared command route for typed and recognized text."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Callable

from core.tools import ToolRegistry, build_task_registry
from tools.desktop import DesktopTools
from tools.tasks import TaskCommands, _parse_task_number
from tools.project_builder import ProjectBuilder


class CommandRouter:
    """Route all command text through one ``handle`` method."""

    def __init__(
        self,
        tasks: TaskCommands,
        registry: ToolRegistry | None = None,
        confirmation_handler: Callable[[str, str], bool] | None = None,
        desktop_tools: DesktopTools | None = None,
        assistant: Callable[[str], str] | None = None,
        project_builder: ProjectBuilder | None = None,
    ) -> None:
        self._desktop_tools = desktop_tools
        self._assistant = assistant
        self._project_builder = project_builder
        self._registry = registry or build_task_registry(tasks.store, confirmation_handler, desktop_tools)

    def handle(self, text: str) -> str:
        normalized = text.strip().lower().strip(".,!? ")
        if self._project_builder is not None and self._project_builder.active:
            return self._project_builder.answer(text)

        project_match = re.fullmatch(r"\s*start\s+(?:a\s+)?project(?:\s+(?:for|to|about))?\s*(.*?)\s*[.!?]*\s*", text, re.IGNORECASE)
        if project_match and self._registry.get("start_project") is not None:
            return str(self._registry.execute("start_project", description=project_match.group(1).strip()))
        if re.search(r"\b(hello|hi|hey|good morning|good afternoon|good evening)\b", normalized):
            return "Hello! I'm Mercury."

        add_match = re.fullmatch(r"\s*add\s+task(?:\s+(.*?))?\s*[.!?]*\s*", text, re.IGNORECASE)
        if add_match:
            description = (add_match.group(1) or "").strip()
            if not description:
                return "What should I add? Say 'Add task' followed by a short description."
            return str(self._registry.execute("add_task", description=description))

        if normalized == "list tasks":
            return str(self._registry.execute("list_tasks"))

        if normalized == "list scheduled calls" and self._registry.get("list_scheduled_calls") is not None:
            return str(self._registry.execute("list_scheduled_calls"))

        cancel_call = re.fullmatch(r"\s*cancel\s+(?:scheduled\s+)?call\s+(.*?)\s*[.!?]*\s*", text, re.IGNORECASE)
        if cancel_call and self._registry.get("cancel_scheduled_call") is not None:
            call_id = _parse_task_number(cancel_call.group(1))
            if call_id is None:
                return "Say 'Cancel call' followed by one clear scheduled-call number."
            return str(self._registry.execute("cancel_scheduled_call", call_id=call_id))

        if normalized in {"count tasks", "how many tasks"}:
            count = int(self._registry.execute("count_tasks"))
            if count == 1:
                return "You have one open task."
            return f"You have {count} open tasks."

        reminder_match = re.fullmatch(
            r"\s*remind\s+me\s+in\s+(.+?)\s+(seconds?|minutes?|hours?)\s+to\s+(.+?)\s*[.!?]*\s*",
            text,
            re.IGNORECASE,
        )
        if reminder_match:
            amount = _parse_task_number(reminder_match.group(1))
            unit = reminder_match.group(2).lower().rstrip("s")
            message = reminder_match.group(3).strip()
            if amount is None or not message:
                return "Please say, 'Remind me in 10 minutes to call Sam.'"
            seconds = amount * {"second": 1, "minute": 60, "hour": 3600}[unit]
            return str(self._registry.execute("create_reminder", message=message, delay_seconds=seconds))

        timer_match = re.fullmatch(
            r"\s*(?:set\s+)?(?:a\s+)?timer\s+for\s+(.+?)\s+(seconds?|minutes?|hours?)\s*[.!?]*\s*",
            text,
            re.IGNORECASE,
        )
        if timer_match:
            amount = _parse_task_number(timer_match.group(1))
            unit = timer_match.group(2).lower().rstrip("s")
            if amount is None:
                return "Please say, 'Set a timer for 5 minutes.'"
            seconds = amount * {"second": 1, "minute": 60, "hour": 3600}[unit]
            return str(self._registry.execute("create_timer", delay_seconds=seconds))

        if self._desktop_tools is not None:
            folder_match = re.fullmatch(
                r"\s*(?:create|make)\s+(?:a\s+)?(?:new\s+)?folder(?:\s+called)?\s+(.+?)\s*[.!?]*\s*",
                text,
                re.IGNORECASE,
            )
            if folder_match:
                return str(self._registry.execute("create_folder", name=folder_match.group(1).strip()))

            web_match = re.fullmatch(
                r"\s*search\s+(?:the\s+)?web\s+for\s+(.+?)(?:\s+in\s+(default|chrome|edge|firefox))?\s*[.!?]*\s*",
                text,
                re.IGNORECASE,
            )
            if web_match:
                return str(
                    self._registry.execute(
                        "search_web",
                        query=web_match.group(1).strip(),
                        browser=(web_match.group(2) or "default").lower(),
                    )
                )

            open_match = re.fullmatch(r"\s*open\s+(?:the\s+)?(?:app\s+)?(.+?)\s*[.!?]*\s*", text, re.IGNORECASE)
            if open_match:
                return str(self._registry.execute("open_app", name=open_match.group(1).strip()))

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
                return "I need a clear task number. Say 'Delete task' followed by one number; I'll ask you to approve it with a button."
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
        if normalized.startswith("remind me"):
            return "Please say, 'Remind me in 10 minutes to call Sam.'"
        if normalized.startswith("set timer") or normalized.startswith("timer"):
            return "Please say, 'Set a timer for 5 minutes.'"

        if self._registry.get("schedule_call") is not None:
            call_phrase = re.fullmatch(
                r"\s*(?:schedule\s+)?call\s+(?:to\s+)?(.+?)\s+(?:in\s+)?(tomorrow\s+morning|the\s+morning|morning)"
                r"(?:\s+saying\s+(.+?))?\s*[.!?]*\s*",
                text,
                re.IGNORECASE,
            )
            if call_phrase:
                recipient = call_phrase.group(1).strip()
                when = call_phrase.group(2).casefold()
                announcement = (call_phrase.group(3) or "This is Mercury calling as you requested.").strip()
                now = datetime.now().astimezone()
                due = now.replace(hour=9, minute=0, second=0, microsecond=0)
                if "tomorrow" in when or due <= now:
                    due += timedelta(days=1)
                delay_seconds = max(5, int((due - now).total_seconds()))
                return str(
                    self._registry.execute(
                        "schedule_call",
                        recipient=recipient,
                        announcement=announcement,
                        delay_seconds=delay_seconds,
                    )
                )

            call_delay = re.fullmatch(
                r"\s*(?:schedule\s+)?call\s+(?:to\s+)?(.+?)\s+in\s+(.+?)\s+"
                r"(seconds?|minutes?|hours?)(?:\s+saying\s+(.+?))?\s*[.!?]*\s*",
                text,
                re.IGNORECASE,
            )
            if call_delay:
                amount = _parse_task_number(call_delay.group(2))
                unit = call_delay.group(3).casefold().rstrip("s")
                recipient = call_delay.group(1).strip()
                announcement = (call_delay.group(4) or "This is Mercury calling as you requested.").strip()
                if amount is None:
                    return "Please say, 'Call me in 10 minutes,' or 'Call me tomorrow morning.'"
                delay_seconds = amount * {"second": 1, "minute": 60, "hour": 3600}[unit]
                return str(
                    self._registry.execute(
                        "schedule_call",
                        recipient=recipient,
                        announcement=announcement,
                        delay_seconds=delay_seconds,
                    )
                )
        if self._assistant is not None:
            return self._assistant(text)
        return (
            "I didn't understand. Say 'Add task' followed by a description, "
            "'List tasks', 'Complete task' followed by a number, or "
            "'Update task' followed by a number and new description, or "
            "'Count tasks', 'Remind me in 10 minutes to call Sam', or 'Set a timer for 5 minutes'. "
            "Deleting a task requires button approval."
        )
