"""Small registry for the local actions Mercury is allowed to run."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import partial
from typing import Callable, Literal, Mapping

from tools.tasks import TaskStore, count_tasks
from tools.desktop import DesktopTools
from tools.workspace import WorkspaceSearch
from tools.reminders import ReminderStore
from tools.system_actions import SystemActions
from core.google_workspace import GoogleWorkspaceClient
from core.communications import TwilioVoiceClient, WhatsAppCloudClient
from core.whatsapp_inbox import WhatsAppInbox
from tools.scheduled_calls import ScheduledCallStore, describe_call_time
from tools.project_builder import ProjectBuilder

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
    confirmation_details: Callable[..., str] | None = None
    confirmation_preflight: Callable[..., str | None] | None = None


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

    def schemas(self) -> list[dict[str, object]]:
        """Return the registered actions as JSON-compatible Ollama tools."""
        schemas: list[dict[str, object]] = []
        for tool in self._tools.values():
            properties: dict[str, object] = {}
            for name, description in tool.parameters.items():
                alternatives = description.split("|")
                if description.casefold() in {"integer", "int"}:
                    property_schema: dict[str, object] = {"type": "integer"}
                else:
                    property_schema = {"type": "string"}
                    if len(alternatives) > 1:
                        property_schema["enum"] = alternatives
                property_schema["description"] = description
                properties[name] = property_schema
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": list(tool.parameters),
                        },
                    },
                }
            )
        return schemas

    def execute(self, tool_name: str, **parameters: object) -> object:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool is not registered: {tool_name}")
        self._validate_parameters(tool, parameters)
        if tool.risk_level == "confirm":
            if tool.confirmation_preflight is not None:
                try:
                    refusal = tool.confirmation_preflight(**parameters)
                except Exception:
                    return "The requested action could not be checked safely. No action was run."
                if refusal:
                    return refusal
            if self._confirmation_handler is None:
                if tool_name == "delete_task":
                    return "Deletion is disabled because button confirmation is unavailable. The task is unchanged."
                return "Button confirmation is disabled or unavailable. No action was run."
            try:
                details = tool.confirmation_details(**parameters) if tool.confirmation_details else "Approve this action?"
                if tool_name == "delete_task" and tool.confirmation_details is None:
                    details = f"Delete task {parameters.get('task_number', 'unknown')}?"
                approved = bool(self._confirmation_handler(f"Confirm {tool_name}", details))
            except Exception:
                approved = False
            logging.getLogger("hercules.confirmations").info("tool=%s approved=%s", tool_name, approved)
            if not approved:
                return "Action cancelled or timed out. No changes were made."
        return tool.function(**parameters)

    @staticmethod
    def _validate_parameters(tool: Tool, parameters: Mapping[str, object]) -> None:
        expected = set(tool.parameters)
        supplied = set(parameters)
        if supplied != expected:
            raise ValueError(f"Invalid parameters for tool {tool.name}")
        for name, value in parameters.items():
            definition = tool.parameters[name].casefold()
            if definition in {"integer", "int"}:
                valid = type(value) is int and abs(value) <= 1_000_000_000
            else:
                valid = isinstance(value, str) and len(value) <= 2000
            if not valid:
                raise ValueError(f"Invalid value for parameter {name} of tool {tool.name}")


def build_task_registry(
    store: TaskStore,
    confirmation_handler: Callable[[str, str], bool] | None = None,
    desktop_tools: DesktopTools | None = None,
    workspace_search: WorkspaceSearch | None = None,
    reminder_store: ReminderStore | None = None,
    system_actions: SystemActions | None = None,
    google_workspace: GoogleWorkspaceClient | None = None,
    whatsapp_client: WhatsAppCloudClient | None = None,
    whatsapp_inbox: WhatsAppInbox | None = None,
    twilio_client: TwilioVoiceClient | None = None,
    scheduled_call_store: ScheduledCallStore | None = None,
    project_builder: ProjectBuilder | None = None,
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
    if desktop_tools is not None:
        desktop_registrations = (
            Tool(
                "open_app",
                "Open an explicitly allowlisted app or website destination.",
                {"name": "string"},
                "run",
                desktop_tools.open_app,
            ),
            Tool(
                "create_folder",
                "Create a folder inside the configured workspace.",
                {"name": "relative path"},
                "run",
                desktop_tools.create_folder,
            ),
            Tool(
                "search_web",
                "Open a Google search in an explicitly selected browser.",
                {"query": "string", "browser": "default|chrome|edge|firefox"},
                "run",
                desktop_tools.search_web,
            ),
        )
        for tool in desktop_registrations:
            registry.register(tool)
    if workspace_search is not None:
        registry.register(
            Tool(
                "search_workspace",
                "Find relevant lines in searchable text files inside the configured workspace.",
                {"query": "string"},
                "run",
                workspace_search.search,
            )
        )
    if reminder_store is not None:
        def create_reminder(message: str, delay_seconds: int) -> str:
            reminder = reminder_store.add(message, delay_seconds, "reminder")
            return f"Reminder {reminder.id} set for {message}."

        def create_timer(delay_seconds: int) -> str:
            reminder = reminder_store.add("Timer finished.", delay_seconds, "timer")
            return f"Timer {reminder.id} set for {delay_seconds} seconds."

        registry.register(
            Tool(
                "create_reminder",
                "Schedule a local reminder after a delay in seconds.",
                {"message": "string", "delay_seconds": "integer"},
                "run",
                create_reminder,
            )
        )
        registry.register(
            Tool(
                "create_timer",
                "Start a local timer for a delay in seconds.",
                {"delay_seconds": "integer"},
                "run",
                create_timer,
            )
        )
    if system_actions is not None:
        registry.register(
            Tool(
                "install_app",
                "Install a package by exact winget ID from the approved package list.",
                {"package_id": "string"},
                "confirm",
                system_actions.install_app,
                system_actions.install_confirmation,
                lambda package_id: (
                    None
                    if system_actions.install_command(package_id) is not None
                    else f"Package {package_id} is not on the approved install list. Nothing was installed."
                ),
            )
        )
        registry.register(
            Tool(
                "delete_path",
                "Move a file or folder inside the configured workspace to the Recycle Bin.",
                {"relative_path": "string"},
                "confirm",
                system_actions.delete_path,
                system_actions.delete_confirmation,
                lambda relative_path: (
                    None
                    if system_actions.item_count(relative_path) is not None
                    else "That item is missing or outside the workspace. Nothing was moved."
                ),
            )
        )
    if google_workspace is not None:
        email_parameters = {"recipient": "string", "subject": "string", "body": "string"}
        registry.register(
            Tool(
                "search_emails",
                "Search the connected Gmail inbox and return sender, date, subject, and a short preview.",
                {"query": "string", "limit": "integer"},
                "run",
                google_workspace.search_email,
            )
        )
        registry.register(
            Tool(
                "upcoming_calendar_events",
                "Read upcoming events from the connected primary Google Calendar.",
                {"limit": "integer"},
                "run",
                google_workspace.upcoming_events,
            )
        )
        registry.register(
            Tool(
                "create_email_draft",
                "Create a Gmail draft after button confirmation; it is not sent.",
                email_parameters,
                "confirm",
                google_workspace.create_draft,
                partial(google_workspace.email_confirmation, "Create this Gmail draft"),
                google_workspace.email_preflight,
            )
        )
        registry.register(
            Tool(
                "send_email",
                "Send a Gmail message only after button confirmation of its exact recipient, subject, and body.",
                email_parameters,
                "confirm",
                google_workspace.send_email,
                partial(google_workspace.email_confirmation, "Send this Gmail message"),
                google_workspace.email_preflight,
            )
        )
    if whatsapp_client is not None:
        registry.register(
            Tool(
                "reply_whatsapp_message",
                "Reply to a received, allowlisted WhatsApp text inside the 24-hour window after button approval.",
                {"message_id": "integer", "text": "string"},
                "confirm",
                whatsapp_client.reply_to_message,
                whatsapp_client.reply_confirmation_details,
                whatsapp_client.reply_preflight,
            )
        )
    if whatsapp_inbox is not None:
        registry.register(
            Tool(
                "read_whatsapp_messages",
                "Read recent opted-in WhatsApp text messages received during this Mercury session.",
                {},
                "run",
                whatsapp_inbox.list_messages,
            )
        )
    if twilio_client is not None:
        registry.register(
            Tool(
                "call_contact",
                "Place a non-recorded Twilio call to an allowlisted contact and read a short message after button approval.",
                {"recipient": "contact name or allowlisted number", "announcement": "string"},
                "confirm",
                twilio_client.call_contact,
                twilio_client.confirmation_details,
                twilio_client.preflight,
            )
        )
        if scheduled_call_store is not None:
            def schedule_call(recipient: str, announcement: str, delay_seconds: int) -> str:
                scheduled = scheduled_call_store.add(recipient, announcement, delay_seconds)
                return f"Phone call scheduled to {recipient} for {describe_call_time(scheduled.due_at)}."

            def scheduled_call_details(recipient: str, announcement: str, delay_seconds: int) -> str:
                due_at = time.time() + delay_seconds
                return (
                    f"Schedule this phone call for {describe_call_time(due_at)}?\n\n"
                    f"{twilio_client.confirmation_details(recipient, announcement)}"
                )

            registry.register(
                Tool(
                    "schedule_call",
                    "Schedule a one-time, non-recorded call to an allowlisted contact after button approval.",
                    {"recipient": "string", "announcement": "string", "delay_seconds": "integer"},
                    "confirm",
                    schedule_call,
                    scheduled_call_details,
                    lambda recipient, announcement, delay_seconds: (
                        twilio_client.preflight(recipient, announcement)
                        or (
                            "A scheduled call must be at least five seconds and within 365 days. No call was scheduled."
                            if type(delay_seconds) is not int or not 5 <= delay_seconds <= 31_536_000
                            else None
                        )
                    ),
                )
            )

            def list_scheduled_calls() -> str:
                calls = scheduled_call_store.pending()
                if not calls:
                    return "You have no scheduled phone calls."
                return " ".join(
                    f"Scheduled call {item.id} to {item.recipient} for {describe_call_time(item.due_at)}."
                    for item in calls
                )

            def cancel_scheduled_call(call_id: int) -> str:
                if scheduled_call_store.cancel(call_id):
                    return f"Cancelled scheduled phone call {call_id}."
                return f"I couldn't find pending scheduled phone call {call_id}; it was not changed."

            registry.register(
                Tool("list_scheduled_calls", "List future approved phone calls without reading their message content.", {}, "run", list_scheduled_calls)
            )
            registry.register(
                Tool(
                    "cancel_scheduled_call",
                    "Cancel a future phone call that has not started.",
                    {"call_id": "integer"},
                    "run",
                    cancel_scheduled_call,
                )
            )
    if project_builder is not None:
        registry.register(
            Tool(
                "start_project",
                "Start a guided project-planning questionnaire. No project folder is created until its specification is approved.",
                {"description": "short project idea"},
                "run",
                project_builder.begin,
            )
        )
    return registry
