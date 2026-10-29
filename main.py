"""Start Mercury and select its interaction mode."""

from __future__ import annotations

import argparse
import queue
from pathlib import Path
from typing import Sequence

from core.confirm import ask_confirmation
from core.confirmation_log import configure_confirmation_log
from core.router import CommandRouter
from core.settings import load_settings
from core.tools import build_task_registry
from core.text_mode import run_text_mode
from tools.tasks import TaskCommands, TaskStore
from tools.desktop import DesktopTools
from tools.workspace import WorkspaceSearch
from core.local_ai import LocalOllamaAssistant
from tools.reminders import ReminderScheduler, ReminderStore
from tools.system_actions import SystemActions
from core.google_workspace import GoogleOAuth, GoogleWorkspaceClient, WindowsCredentialStore
from core.contacts import ContactBook
from core.communications import TwilioVoiceClient, WhatsAppCloudClient
from core.whatsapp_inbox import WhatsAppInbox, WhatsAppWebhookServer
from core.account_setup import setup_twilio, setup_whatsapp
from tools.scheduled_calls import ScheduledCallScheduler, ScheduledCallStore, dispatch_due_calls
from tools.project_builder import ProjectBuilder
from core.confirm import process_pending_confirmations


DATABASE_PATH = Path(__file__).parent / "data" / "hercules.sqlite3"
TEST_SPEECH_TEXT = "This is a Mercury speech output test."


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local Mercury voice assistant")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--text", action="store_true", help="type commands instead of using the microphone")
    modes.add_argument("--test-speech", action="store_true", help="test the local Windows speech output")
    modes.add_argument("--list-devices", action="store_true", help="list audio devices and exit")
    modes.add_argument("--setup-whatsapp", action="store_true", help="securely store Meta WhatsApp API credentials")
    modes.add_argument("--setup-twilio", action="store_true", help="securely store Twilio Voice API credentials")
    modes.add_argument("--doctor", action="store_true", help="check local configuration without recording audio or reading account secrets")
    args = parser.parse_args(argv)

    if args.list_devices:
        from audio.microphone import list_audio_devices

        list_audio_devices()
        return 0

    if args.doctor:
        from core.doctor import diagnose, print_diagnostics

        return print_diagnostics(diagnose())

    if args.test_speech:
        from audio.speech_output import SpeechOutput

        SpeechOutput().speak(TEST_SPEECH_TEXT)
        return 0

    if args.setup_whatsapp or args.setup_twilio:
        try:
            account_name = "Hercules WhatsApp" if args.setup_whatsapp else "Hercules Twilio"
            credential_store = WindowsCredentialStore(account_name)
            result = (
                setup_whatsapp(credential_store)
                if args.setup_whatsapp
                else setup_twilio(credential_store)
            )
        except Exception:
            print("Secure Windows Credential Manager storage is unavailable. No credentials were stored.")
            return 1
        print(result)
        return 0 if "stored in Windows" in result else 1

    configure_confirmation_log()
    settings = load_settings()
    task_store = TaskStore(DATABASE_PATH)
    project_builder = ProjectBuilder(
        settings.workspace_folder,
        ask_confirmation,
        model=settings.local_ai_model,
    )
    reminder_store = ReminderStore(DATABASE_PATH)
    reminder_scheduler = ReminderScheduler(reminder_store)
    system_actions = SystemActions(
        settings.workspace_folder,
        settings.install_whitelist,
    )
    google_workspace = None
    if settings.google_enabled:
        google_oauth = GoogleOAuth(settings.google_credentials_file, WindowsCredentialStore())
        google_workspace = GoogleWorkspaceClient(google_oauth.service)
    contacts = ContactBook(settings.contacts_file)
    whatsapp_client = None
    whatsapp_inbox = None
    whatsapp_webhook = None
    if settings.whatsapp_enabled:
        whatsapp_store = WindowsCredentialStore("Hercules WhatsApp")
        whatsapp_inbox = WhatsAppInbox(contacts)
        whatsapp_client = WhatsAppCloudClient(
            whatsapp_store.get("phone_number_id") or "",
            settings.whatsapp_graph_version,
            contacts,
            whatsapp_store,
            whatsapp_inbox,
        )
        if settings.whatsapp_webhook_enabled:
            try:
                whatsapp_webhook = WhatsAppWebhookServer(
                    whatsapp_inbox,
                    whatsapp_store.get("verify_token") or "",
                    whatsapp_store.get("app_secret") or "",
                    settings.whatsapp_webhook_port,
                )
                whatsapp_webhook.start()
            except Exception:
                print("WhatsApp webhook did not start. Check its secrets and local port settings.")
                whatsapp_webhook = None
    twilio_client = None
    scheduled_call_store = None
    scheduled_call_scheduler = None
    if settings.twilio_enabled:
        twilio_client = TwilioVoiceClient(
            contacts,
            WindowsCredentialStore("Hercules Twilio"),
        )
        scheduled_call_store = ScheduledCallStore(DATABASE_PATH)
        scheduled_call_scheduler = ScheduledCallScheduler(scheduled_call_store)
    desktop_tools = DesktopTools(settings.workspace_folder, settings.app_whitelist)
    workspace_search = WorkspaceSearch(settings.workspace_folder)
    registry = build_task_registry(
        task_store,
        confirmation_handler=ask_confirmation,
        desktop_tools=desktop_tools,
        workspace_search=workspace_search,
        reminder_store=reminder_store,
        system_actions=system_actions,
        google_workspace=google_workspace,
        whatsapp_client=whatsapp_client,
        whatsapp_inbox=whatsapp_inbox,
        twilio_client=twilio_client,
        scheduled_call_store=scheduled_call_store,
        project_builder=project_builder,
    )
    assistant = (
        LocalOllamaAssistant(registry, settings.local_ai_model, settings.local_ai_url).respond
        if settings.local_ai_enabled
        else None
    )
    router = CommandRouter(
        TaskCommands(task_store),
        registry=registry,
        confirmation_handler=ask_confirmation,
        desktop_tools=desktop_tools,
        assistant=assistant,
        project_builder=project_builder,
    )
    if args.text:
        from audio.speech_output import SpeechOutput

        speech_output = SpeechOutput()
        reminder_scheduler.start()
        if scheduled_call_scheduler is not None:
            scheduled_call_scheduler.start()

        def text_reminder_tick() -> None:
            process_pending_confirmations()
            while True:
                try:
                    project_notice = project_builder.notifications.get_nowait()
                except queue.Empty:
                    break
                speech_output.speak(project_notice)
            if scheduled_call_scheduler is not None and twilio_client is not None:
                dispatch_due_calls(scheduled_call_scheduler, twilio_client, speech_output.speak)
            for reminder in reminder_scheduler.drain():
                text = (
                    "Your timer is finished."
                    if reminder.kind == "timer"
                    else f"Reminder: {reminder.message}."
                )
                try:
                    speech_output.speak(text)
                except Exception:
                    reminder_scheduler.release(reminder)
                    raise
                else:
                    reminder_scheduler.acknowledge(reminder)
            if whatsapp_inbox is not None:
                while True:
                    try:
                        local_id = whatsapp_inbox.notifications.get_nowait()
                    except queue.Empty:
                        break
                    message = whatsapp_inbox.get(local_id)
                    if message is not None:
                        speech_output.speak(
                            f"New WhatsApp message from {message.contact_name}. "
                            "Ask me to read your WhatsApp messages."
                        )

        try:
            run_text_mode(router, on_tick=text_reminder_tick)
        finally:
            reminder_scheduler.stop()
            if scheduled_call_scheduler is not None:
                scheduled_call_scheduler.stop()
            if whatsapp_webhook is not None:
                whatsapp_webhook.stop()
        return 0

    from core.voice_mode import run_voice_mode

    reminder_scheduler.start()
    if scheduled_call_scheduler is not None:
        scheduled_call_scheduler.start()
    try:
        run_voice_mode(
            router,
            settings=settings,
            reminder_scheduler=reminder_scheduler,
            whatsapp_inbox=whatsapp_inbox,
            scheduled_call_scheduler=scheduled_call_scheduler,
            twilio_client=twilio_client,
            project_builder=project_builder,
        )
    finally:
        reminder_scheduler.stop()
        if scheduled_call_scheduler is not None:
            scheduled_call_scheduler.stop()
        if whatsapp_webhook is not None:
            whatsapp_webhook.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
