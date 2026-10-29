"""Offline Vosk speech recognition; transcripts remain in memory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from audio.microphone import SAMPLE_RATE
from audio.recognition import RecognitionResult, SpeechRecognizer
from core.settings import Settings


MODEL_PATH = Path(__file__).resolve().parent.parent / "model" / "vosk-model-small-en-us-0.15"


class VoskSpeechRecognizer:
    """Convert captured bytes to text without printing or persisting it."""

    def __init__(
        self,
        model: Any | None = None,
        recognizer_factory: Callable[[Any, int], Any] | None = None,
        model_path: Path = MODEL_PATH,
        confidence_threshold: float = 0.65,
    ) -> None:
        if model is None:
            from vosk import Model, SetLogLevel

            # Keep model internals from filling the console with diagnostics.
            SetLogLevel(-1)
            model = Model(str(model_path))
        if recognizer_factory is None:
            from vosk import KaldiRecognizer

            recognizer_factory = KaldiRecognizer
        self._model = model
        self._recognizer_factory = recognizer_factory
        self.confidence_threshold = confidence_threshold

    def recognize(self, audio: bytes) -> RecognitionResult:
        if not audio:
            return RecognitionResult("", 0.0)
        recognizer = self._recognizer_factory(self._model, SAMPLE_RATE)
        recognizer.SetWords(True)
        recognizer.AcceptWaveform(audio)
        result = json.loads(recognizer.FinalResult())
        words = result.get("result", [])
        confidences = [float(word["conf"]) for word in words if "conf" in word]
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return RecognitionResult(str(result.get("text", "")), confidence)

    def transcribe(self, audio: bytes) -> str:
        """Compatibility helper for callers that only need the transcript."""
        return self.recognize(audio).text


def create_speech_recognizer(settings: Settings) -> SpeechRecognizer:
    """Build the configured recognizer; faster-whisper may fetch its model on first use."""
    if settings.speech_recognizer == "vosk":
        if settings.speech_model_size != "small":
            raise ValueError("The configured local Vosk model size must be 'small'")
        return VoskSpeechRecognizer(
            confidence_threshold=settings.vosk_confidence_threshold,
        )
    if settings.speech_recognizer == "faster-whisper":
        if settings.speech_model_size != "small.en":
            raise ValueError("Set speech_model_size = 'small.en' for faster-whisper")
        from audio.faster_whisper import FasterWhisperSpeechRecognizer

        return FasterWhisperSpeechRecognizer(
            confidence_threshold=settings.faster_whisper_confidence_threshold,
        )
    raise ValueError("Unsupported speech_recognizer setting")
