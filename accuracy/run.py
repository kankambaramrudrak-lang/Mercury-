"""Run the 50-phrase recognition check without showing transcripts."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from audio.recognition import SpeechRecognizer
from audio.speech_to_text import create_speech_recognizer
from core.settings import load_settings

COMMANDS_PATH = Path(__file__).with_name("commands.txt")
PHRASE_COUNT = 50
RECORD_SECONDS = 8


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)*", text.lower()))


def run_benchmark(
    phrases: Sequence[str],
    recognizer: SpeechRecognizer,
    capture_audio: Callable[[], bytes],
    output_fn: Callable[[str], None] = print,
) -> int:
    """Prompt for each test phrase and return the count understood."""
    if len(phrases) != PHRASE_COUNT:
        raise ValueError(f"The accuracy run needs exactly {PHRASE_COUNT} phrases")

    recognized_count = 0
    confidence_pass_count = 0
    understood = 0
    for index, phrase in enumerate(phrases, start=1):
        output_fn(f"Phrase {index}/{PHRASE_COUNT}: say '{phrase}'")
        result = recognizer.recognize(capture_audio())
        has_text = bool(result.text.strip())
        if has_text:
            recognized_count += 1
        confidence_passed = has_text and result.confidence >= recognizer.confidence_threshold
        if confidence_passed:
            confidence_pass_count += 1
        if confidence_passed and _normalize(result.text) == _normalize(phrase):
            understood += 1
    output_fn(f"Speech detected: {recognized_count}/{PHRASE_COUNT}")
    output_fn(f"Confidence passed: {confidence_pass_count}/{PHRASE_COUNT}")
    output_fn(f"Exact phrase matches: {understood}/{PHRASE_COUNT}")
    return understood


def _capture_phrase(device: str | int | None) -> bytes:
    import sounddevice as sd

    from audio.microphone import SAMPLE_RATE

    print("Get ready. Recording begins in three seconds.")
    for remaining in (3, 2, 1):
        print(f"{remaining}...")
        time.sleep(1)
    print(f"Recording now for {RECORD_SECONDS} seconds.")
    audio = sd.rec(
        int(RECORD_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=device,
    )
    sd.wait()
    return audio.tobytes()


def main() -> int:
    settings = load_settings()
    recognizer = create_speech_recognizer(settings)
    phrases = [
        line.strip()
        for line in COMMANDS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    device = None if settings.microphone_device == "default" else settings.microphone_device
    run_benchmark(phrases, recognizer, lambda: _capture_phrase(device))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
