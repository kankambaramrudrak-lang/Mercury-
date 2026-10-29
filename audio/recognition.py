"""Shared speech-recognition result and interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RecognitionResult:
    text: str
    confidence: float


class SpeechRecognizer(Protocol):
    confidence_threshold: float

    def recognize(self, audio: bytes) -> RecognitionResult: ...
