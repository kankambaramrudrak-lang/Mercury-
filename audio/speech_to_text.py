"""Offline Vosk speech recognition; transcripts remain in memory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from audio.microphone import SAMPLE_RATE


MODEL_PATH = Path(__file__).resolve().parent.parent / "model" / "vosk-model-small-en-us-0.15"


class VoskSpeechRecognizer:
    """Convert captured bytes to text without printing or persisting it."""

    def __init__(
        self,
        model: Any | None = None,
        recognizer_factory: Callable[[Any, int], Any] | None = None,
        model_path: Path = MODEL_PATH,
    ) -> None:
        if model is None:
            from vosk import Model

            model = Model(str(model_path))
        if recognizer_factory is None:
            from vosk import KaldiRecognizer

            recognizer_factory = KaldiRecognizer
        self._model = model
        self._recognizer_factory = recognizer_factory

    def transcribe(self, audio: bytes) -> str:
        if not audio:
            return ""
        recognizer = self._recognizer_factory(self._model, SAMPLE_RATE)
        recognizer.AcceptWaveform(audio)
        result = json.loads(recognizer.FinalResult())
        return str(result.get("text", ""))
