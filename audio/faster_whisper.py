"""Local faster-whisper adapter configured for the English small int8 model."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import numpy as np

from audio.microphone import SAMPLE_RATE
from audio.recognition import RecognitionResult

MODEL_NAME = "small.en"
COMMANDS_PATH = Path(__file__).resolve().parent.parent / "accuracy" / "commands.txt"


def build_initial_prompt(commands_path: str | Path = COMMANDS_PATH) -> str:
    phrases = [
        line.strip()
        for line in Path(commands_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return "Mercury command examples: " + "; ".join(phrases)


class FasterWhisperSpeechRecognizer:
    """Convert captured PCM bytes to text and a bounded confidence estimate."""

    def __init__(
        self,
        model: Any | None = None,
        model_factory: Callable[..., Any] | None = None,
        initial_prompt: str | None = None,
        commands_path: str | Path = COMMANDS_PATH,
        confidence_threshold: float = 0.45,
    ) -> None:
        if model is None:
            if model_factory is None:
                from faster_whisper import WhisperModel

                model_factory = WhisperModel
            model = model_factory(MODEL_NAME, device="cpu", compute_type="int8")
        self._model = model
        self._initial_prompt = (
            build_initial_prompt(commands_path) if initial_prompt is None else initial_prompt
        )
        self.confidence_threshold = confidence_threshold

    def recognize(self, audio: bytes) -> RecognitionResult:
        if not audio:
            return RecognitionResult("", 0.0)
        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _info = self._model.transcribe(
            samples,
            language="en",
            initial_prompt=self._initial_prompt,
        )
        completed_segments = list(segments)
        text = " ".join(str(segment.text).strip() for segment in completed_segments).strip()
        if not completed_segments:
            return RecognitionResult(text, 0.0)

        scores = []
        for segment in completed_segments:
            log_probability = min(0.0, float(segment.avg_logprob))
            no_speech_probability = min(1.0, max(0.0, float(segment.no_speech_prob)))
            scores.append(math.exp(log_probability) * (1.0 - no_speech_probability))
        confidence = sum(scores) / len(scores)
        return RecognitionResult(text, confidence)
