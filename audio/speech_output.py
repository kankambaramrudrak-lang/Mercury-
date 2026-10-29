"""Windows local text-to-speech that prints assistant replies."""

from __future__ import annotations

from typing import Protocol, cast


class SpeechEngine(Protocol):
    def say(self, text: str | None, name: str | None = None) -> str | None: ...

    def runAndWait(self) -> None: ...


class SpeechOutput:
    """Print a reply once, then speak that exact text through Windows SAPI."""

    def __init__(self, engine: SpeechEngine | None = None) -> None:
        if engine is None:
            import pyttsx3

            engine = cast(SpeechEngine, pyttsx3.init("sapi5"))
        self._engine = engine

    def speak(self, text: str) -> None:
        print(text, flush=True)
        self.speak_private(text)

    def speak_private(self, text: str) -> None:
        """Speak sensitive confirmation text without printing it."""
        self._engine.say(text)
        self._engine.runAndWait()
