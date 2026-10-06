import unittest
from contextlib import redirect_stdout
from io import StringIO

from audio.speech_output import SpeechOutput
from audio.speech_to_text import VoskSpeechRecognizer
from core.text_mode import run_text_mode
from core.voice_mode import run_voice_mode


class FakeRouter:
    def __init__(self):
        self.received = []

    def handle(self, text):
        self.received.append(text)
        return "Assistant reply."


class FakeMicrophone:
    def run(self, on_audio):
        on_audio(b"fake audio bytes")


class FakeRecognizer:
    def __init__(self, text):
        self.text = text

    def transcribe(self, audio):
        self.received_audio = audio
        return self.text


class FakeSpeaker:
    def __init__(self):
        self.replies = []

    def speak(self, text):
        self.replies.append(text)


class FakeSpeechEngine:
    def __init__(self):
        self.spoken = []

    def say(self, text, name=None):
        self.spoken.append(text)

    def runAndWait(self):
        pass


class FakeVoskRecognizer:
    def __init__(self, model, sample_rate):
        self.sample_rate = sample_rate
        self.audio = None

    def AcceptWaveform(self, audio):
        self.audio = audio

    def FinalResult(self):
        return '{"text": "hello Hercules"}'


class ModeTests(unittest.TestCase):
    def test_text_mode_routes_commands_and_exits(self):
        router = FakeRouter()
        commands = iter(("List tasks", "exit"))
        replies = []

        run_text_mode(router, lambda prompt: next(commands), replies.append)

        self.assertEqual(router.received, ["List tasks"])
        self.assertIn("Assistant reply.", replies)
        self.assertEqual(replies[-1], "Goodbye.")

    def test_voice_mode_uses_fake_audio_and_speech_components(self):
        router = FakeRouter()
        microphone = FakeMicrophone()
        recognizer = FakeRecognizer("hello Hercules")
        speaker = FakeSpeaker()
        console = StringIO()

        with redirect_stdout(console):
            run_voice_mode(router, microphone, recognizer, speaker)

        self.assertEqual(router.received, ["hello Hercules"])
        self.assertEqual(recognizer.received_audio, b"fake audio bytes")
        self.assertEqual(speaker.replies, ["Assistant reply."])
        self.assertEqual(console.getvalue(), "")

    def test_empty_recognition_asks_without_routing_text(self):
        router = FakeRouter()
        speaker = FakeSpeaker()

        run_voice_mode(router, FakeMicrophone(), FakeRecognizer(""), speaker)

        self.assertEqual(router.received, [])
        self.assertEqual(speaker.replies, ["I didn't catch that. Please repeat your command."])

    def test_speech_output_uses_fake_engine_and_prints_reply(self):
        engine = FakeSpeechEngine()
        console = StringIO()

        with redirect_stdout(console):
            SpeechOutput(engine).speak("Assistant reply.")

        self.assertEqual(console.getvalue(), "Assistant reply.\n")
        self.assertEqual(engine.spoken, ["Assistant reply."])

    def test_vosk_adapter_uses_fake_recognizer_without_printing_text(self):
        created = []

        def factory(model, sample_rate):
            adapter = FakeVoskRecognizer(model, sample_rate)
            created.append(adapter)
            return adapter

        recognizer = VoskSpeechRecognizer(model=object(), recognizer_factory=factory)
        console = StringIO()

        with redirect_stdout(console):
            transcript = recognizer.transcribe(b"fake audio bytes")

        self.assertEqual(transcript, "hello Hercules")
        self.assertEqual(created[0].sample_rate, 16_000)
        self.assertEqual(created[0].audio, b"fake audio bytes")
        self.assertEqual(console.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
