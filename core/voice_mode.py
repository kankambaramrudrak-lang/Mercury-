"""Connect microphone capture, local recognition, routing, and speech output."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from core.router import CommandRouter


class Microphone(Protocol):
    def run(self, on_audio: Callable[[bytes], None]) -> None: ...


class Recognizer(Protocol):
    def transcribe(self, audio: bytes) -> str: ...


class Speaker(Protocol):
    def speak(self, text: str) -> None: ...


def run_voice_mode(
    router: CommandRouter,
    microphone: Microphone | None = None,
    recognizer: Recognizer | None = None,
    speaker: Speaker | None = None,
) -> None:
    """Run the voice pipeline, with injectable components for safe tests."""
    if microphone is None:
        from audio.microphone import PushToTalkMicrophone

        microphone = PushToTalkMicrophone()
    if recognizer is None:
        from audio.speech_to_text import VoskSpeechRecognizer

        recognizer = VoskSpeechRecognizer()
    if speaker is None:
        from audio.speech_output import SpeechOutput

        speaker = SpeechOutput()

    def route_audio(audio: bytes) -> None:
        text = recognizer.transcribe(audio)
        if not text:
            speaker.speak("I didn't catch that. Please repeat your command.")
            return
        speaker.speak(router.handle(text))

    microphone.run(route_audio)
