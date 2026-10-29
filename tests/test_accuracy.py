import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch
import sys

from accuracy.run import PHRASE_COUNT, _capture_phrase, run_benchmark
from audio.recognition import RecognitionResult


class FakeRecognizer:
    confidence_threshold = 0.5

    def __init__(self, results):
        self.results = iter(results)
        self.audio_inputs = []

    def recognize(self, audio):
        self.audio_inputs.append(audio)
        return next(self.results)


class AccuracyRunTests(unittest.TestCase):
    def test_capture_uses_countdown_instead_of_enter_input(self):
        audio = SimpleNamespace(tobytes=lambda: b"fake audio")
        sounddevice = SimpleNamespace(
            rec=lambda *args, **kwargs: audio,
            wait=lambda: None,
        )
        output = StringIO()

        with (
            patch.dict(sys.modules, {"sounddevice": sounddevice}),
            patch("accuracy.run.time.sleep") as sleep,
            redirect_stdout(output),
        ):
            captured = _capture_phrase(1)

        self.assertEqual(captured, b"fake audio")
        self.assertEqual(sleep.call_count, 3)
        self.assertIn("Recording now for 8 seconds", output.getvalue())

    def test_benchmark_reports_aggregate_diagnostics_without_transcripts(self):
        phrases = [f"phrase {index}" for index in range(PHRASE_COUNT)]
        transcripts = [phrase if index == 0 else "private transcript" for index, phrase in enumerate(phrases)]
        recognizer = FakeRecognizer(
            [RecognitionResult(text, 0.9) for text in transcripts]
        )
        recorded = []
        output = StringIO()

        with redirect_stdout(output):
            understood = run_benchmark(
                phrases,
                recognizer,
                lambda: recorded.append(b"fake audio") or b"fake audio",
            )

        self.assertEqual(understood, 1)
        self.assertEqual(recorded, [b"fake audio"] * PHRASE_COUNT)
        self.assertNotIn("private transcript", output.getvalue())
        self.assertIn("Speech detected: 50/50", output.getvalue())
        self.assertIn("Confidence passed: 50/50", output.getvalue())
        self.assertTrue(output.getvalue().endswith("Exact phrase matches: 1/50\n"))

    def test_benchmark_separates_empty_and_low_confidence_results(self):
        phrases = [f"phrase {index}" for index in range(PHRASE_COUNT)]
        results = [RecognitionResult("", 0.0), RecognitionResult("different words", 0.1)]
        results.extend(RecognitionResult(phrase, 0.9) for phrase in phrases[2:])
        output = StringIO()

        with redirect_stdout(output):
            understood = run_benchmark(phrases, FakeRecognizer(results), lambda: b"fake audio")

        self.assertEqual(understood, PHRASE_COUNT - 2)
        self.assertIn("Speech detected: 49/50", output.getvalue())
        self.assertIn("Confidence passed: 48/50", output.getvalue())
        self.assertIn(f"Exact phrase matches: {PHRASE_COUNT - 2}/50", output.getvalue())
        self.assertNotIn("different words", output.getvalue())

    def test_benchmark_refuses_non_50_phrase_input(self):
        recognizer = FakeRecognizer([])

        with self.assertRaisesRegex(ValueError, "exactly 50"):
            run_benchmark([], recognizer, lambda: b"fake audio", lambda _text: None)


if __name__ == "__main__":
    unittest.main()
