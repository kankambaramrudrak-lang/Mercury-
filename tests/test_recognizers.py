import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from unittest.mock import patch

from audio.faster_whisper import FasterWhisperSpeechRecognizer, build_initial_prompt
from audio.recognition import RecognitionResult
from audio.speech_to_text import create_speech_recognizer
from core.settings import Settings


class FakeWhisperModel:
    def __init__(self):
        self.audio = None
        self.options = None

    def transcribe(self, audio, **options):
        self.audio = audio
        self.options = options
        segments = [SimpleNamespace(text="List tasks", avg_logprob=-0.1, no_speech_prob=0.1)]
        return iter(segments), object()


class FasterWhisperTests(unittest.TestCase):
    def test_constructs_small_en_int8_and_returns_confidence(self):
        model = FakeWhisperModel()
        factory_calls = []

        def model_factory(*args, **kwargs):
            factory_calls.append((args, kwargs))
            return model

        recognizer = FasterWhisperSpeechRecognizer(
            model_factory=model_factory,
            initial_prompt="known commands",
        )
        audio = np.array([0, 16384, -16384], dtype=np.int16).tobytes()
        result = recognizer.recognize(audio)

        self.assertEqual(factory_calls, [(('small.en',), {"device": "cpu", "compute_type": "int8"})])
        self.assertEqual(result.text, "List tasks")
        self.assertAlmostEqual(result.confidence, np.exp(-0.1) * 0.9)
        np.testing.assert_allclose(model.audio, [0.0, 0.5, -0.5])
        self.assertEqual(model.options, {"language": "en", "initial_prompt": "known commands"})

    def test_initial_prompt_reads_phrases_without_printing_them(self):
        with tempfile.TemporaryDirectory() as directory:
            commands = Path(directory) / "commands.txt"
            commands.write_text("List tasks\nAdd task groceries\n", encoding="utf-8")

            prompt = build_initial_prompt(commands)

        self.assertEqual(prompt, "Mercury command examples: List tasks; Add task groceries")

    def test_configured_backend_selects_only_the_requested_recognizer(self):
        settings = Settings(
            workspace_folder=Path("."),
            app_whitelist=(),
            microphone_device="default",
            speech_recognizer="faster-whisper",
            speech_model_size="small.en",
            vosk_confidence_threshold=0.65,
            faster_whisper_confidence_threshold=0.45,
        )
        with patch("audio.faster_whisper.FasterWhisperSpeechRecognizer") as whisper_factory:
            result = create_speech_recognizer(settings)

        self.assertIs(result, whisper_factory.return_value)
        whisper_factory.assert_called_once_with(confidence_threshold=0.45)

    def test_vosk_configuration_rejects_an_unavailable_model_size(self):
        settings = Settings(
            workspace_folder=Path("."),
            app_whitelist=(),
            microphone_device="default",
            speech_recognizer="vosk",
            speech_model_size="large",
            vosk_confidence_threshold=0.65,
            faster_whisper_confidence_threshold=0.45,
        )

        with self.assertRaisesRegex(ValueError, "Vosk model size"):
            create_speech_recognizer(settings)


if __name__ == "__main__":
    unittest.main()
