"""Connect microphone capture, local recognition, routing, and speech output."""

from __future__ import annotations

import queue
from collections.abc import Callable
from typing import Protocol

from audio.recognition import RecognitionResult, SpeechRecognizer
from audio.speech_to_text import create_speech_recognizer
from core.command_match import match_known_command
from core.whatsapp_inbox import WhatsAppInbox
from core.router import CommandRouter
from core.settings import Settings, load_settings
from tools.reminders import ReminderScheduler
from tools.scheduled_calls import ScheduledCallScheduler, dispatch_due_calls
from core.communications import TwilioVoiceClient
from tools.project_builder import ProjectBuilder


class Microphone(Protocol):
    def run(
        self,
        on_audio: Callable[[bytes], None],
        on_status: Callable[[str], None],
        on_tick: Callable[[], None] | None = None,
    ) -> None: ...


class Speaker(Protocol):
    def speak(self, text: str) -> None: ...

    def speak_private(self, text: str) -> None: ...


def run_voice_mode(
    router: CommandRouter,
    microphone: Microphone | None = None,
    recognizer: SpeechRecognizer | None = None,
    speaker: Speaker | None = None,
    settings: Settings | None = None,
    reminder_scheduler: ReminderScheduler | None = None,
    whatsapp_inbox: WhatsAppInbox | None = None,
    scheduled_call_scheduler: ScheduledCallScheduler | None = None,
    twilio_client: TwilioVoiceClient | None = None,
    project_builder: ProjectBuilder | None = None,
) -> None:
    """Run the voice pipeline, with injectable components for safe tests."""
    settings = load_settings() if settings is None else settings
    if microphone is None:
        from audio.microphone import AlwaysListeningMicrophone

        device = None if settings.microphone_device == "default" else settings.microphone_device
        microphone = AlwaysListeningMicrophone(device=device)
    if recognizer is None:
        recognizer = create_speech_recognizer(settings)
    if speaker is None:
        from audio.speech_output import SpeechOutput

        speaker = SpeechOutput()

    pending_text: str | None = None

    def route_command(text: str) -> None:
        matched = match_known_command(text)
        if matched.ambiguous:
            speaker.speak("I wasn't sure which command you meant. Please repeat the command.")
            return
        speaker.speak(router.handle(matched.text))

    def route_audio(audio: bytes) -> None:
        nonlocal pending_text
        result: RecognitionResult = recognizer.recognize(audio)
        if pending_text is not None:
            if not result.text or result.confidence < recognizer.confidence_threshold:
                speaker.speak("Please answer yes or no.")
                return
            answer = result.text.strip().lower().strip(" .,!?")
            if answer == "yes":
                confirmed_text = pending_text
                pending_text = None
                route_command(confirmed_text)
            elif answer == "no":
                pending_text = None
                speaker.speak("Okay. Please repeat your command.")
            else:
                speaker.speak("Please answer yes or no.")
            return

        if not result.text:
            speaker.speak("I didn't catch that. Please repeat your command.")
            return

        if result.confidence < recognizer.confidence_threshold:
            pending_text = result.text
            speaker.speak_private(f"Did you say {result.text}? Please say yes or no.")
            return

        route_command(result.text)

    def on_tick() -> None:
        if project_builder is not None:
            while True:
                try:
                    project_notice = project_builder.notifications.get_nowait()
                except queue.Empty:
                    break
                speaker.speak(project_notice)
        if scheduled_call_scheduler is not None and twilio_client is not None:
            dispatch_due_calls(scheduled_call_scheduler, twilio_client, speaker.speak)
        if reminder_scheduler is not None:
            for reminder in reminder_scheduler.drain():
                try:
                    if reminder.kind == "timer":
                        speaker.speak("Your timer is finished.")
                    else:
                        speaker.speak(f"Reminder: {reminder.message}.")
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
                    speaker.speak(
                        f"New WhatsApp message from {message.contact_name}. "
                        "Ask me to read your WhatsApp messages."
                    )

    microphone.run(route_audio, speaker.speak, on_tick)
