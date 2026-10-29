import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from audio.recognition import RecognitionResult
from audio.speech_output import SpeechOutput
from audio.speech_to_text import VoskSpeechRecognizer
from core.command_match import CommandMatch, match_known_command
from core.settings import Settings
from core.text_mode import run_text_mode
from core.voice_mode import run_voice_mode
from tools.reminders import Reminder


class FakeRouter:
    def __init__(self, reply="Assistant reply."):
        self.received = []
        self.reply = reply

    def handle(self, text):
        self.received.append(text)
        return self.reply


class FakeMicrophone:
    def run(self, on_audio, on_status, on_tick=None):
        on_status("Mercury is ready and listening. Say a command. Press Esc to quit.")
        if on_tick is not None:
            on_tick()
        on_audio(b"fake audio bytes")


class FakeSequenceMicrophone:
    def __init__(self, audio_items):
        self.audio_items = audio_items

    def run(self, on_audio, on_status, on_tick=None):
        on_status("Mercury is ready and listening. Say a command. Press Esc to quit.")
        if on_tick is not None:
            on_tick()
        for audio in self.audio_items:
            on_audio(audio)


class FakeRecognizer:
    confidence_threshold = 0.5

    def __init__(self, *results):
        self.results = list(results)
        self.received_audio = []

    def recognize(self, audio):
        self.received_audio.append(audio)
        return self.results.pop(0)


class FakeSpeaker:
    def __init__(self):
        self.replies = []
        self.private_replies = []

    def speak(self, text):
        self.replies.append(text)

    def speak_private(self, text):
        self.private_replies.append(text)


class FakeSpeechEngine:
    def __init__(self):
        self.spoken = []

    def say(self, text, name=None):
        self.spoken.append(text)

    def runAndWait(self):
        pass


class FakeReminderScheduler:
    def __init__(self, *items):
        self.items = list(items)

    def drain(self):
        items, self.items = self.items, []
        return items

    def acknowledge(self, _reminder):
        pass

    def release(self, _reminder):
        pass


class FakeVoskRecognizer:
    def __init__(self, model, sample_rate):
        self.sample_rate = sample_rate
        self.audio = None
        self.words_enabled = False

    def SetWords(self, enabled):
        self.words_enabled = enabled

    def AcceptWaveform(self, audio):
        self.audio = audio

    def FinalResult(self):
        return '{"text": "hello Mercury", "result": [{"conf": 0.9}]}'


class ModeTests(unittest.TestCase):
    def test_text_mode_routes_commands_and_exits(self):
        router = FakeRouter()
        commands = iter(("List tasks", "exit"))
        replies = []

        run_text_mode(router, lambda prompt: next(commands), replies.append)

        self.assertEqual(router.received, ["List tasks"])
        self.assertIn("Assistant reply.", replies)
        self.assertEqual(replies[-1], "Goodbye.")

    def test_voice_mode_routes_high_confidence_result(self):
        router = FakeRouter()
        recognizer = FakeRecognizer(RecognitionResult("hello Mercury", 0.9))
        speaker = FakeSpeaker()
        console = StringIO()

        with redirect_stdout(console):
            run_voice_mode(router, FakeMicrophone(), recognizer, speaker)

        self.assertEqual(router.received, ["hello Mercury"])
        self.assertEqual(recognizer.received_audio, [b"fake audio bytes"])
        self.assertEqual(
            speaker.replies,
            ["Mercury is ready and listening. Say a command. Press Esc to quit.", "Assistant reply."],
        )
        self.assertEqual(console.getvalue(), "")

    def test_voice_mode_speaks_add_task_clarification(self):
        clarification = "What should I add? Say 'Add task' followed by a short description."
        router = FakeRouter(clarification)
        recognizer = FakeRecognizer(RecognitionResult("Add task", 0.9))
        speaker = FakeSpeaker()

        run_voice_mode(router, FakeMicrophone(), recognizer, speaker)

        self.assertEqual(router.received, ["Add task"])
        self.assertEqual(speaker.replies[-1], clarification)

    def test_voice_mode_speaks_due_reminders_on_main_loop_tick(self):
        class TickOnlyMicrophone:
            def run(self, _on_audio, on_status, on_tick=None):
                on_status("Ready")
                if on_tick is not None:
                    on_tick()

        speaker = FakeSpeaker()
        scheduler = FakeReminderScheduler(
            Reminder(1, "call Sam", 1_000.0, "reminder"),
            Reminder(2, "Timer finished.", 1_000.0, "timer"),
        )

        run_voice_mode(
            FakeRouter(),
            TickOnlyMicrophone(),
            FakeRecognizer(),
            speaker,
            reminder_scheduler=scheduler,
        )

        self.assertEqual(speaker.replies[-2:], ["Reminder: call Sam.", "Your timer is finished."])

    def test_low_confidence_waits_for_yes_without_printing_pending_text(self):
        router = FakeRouter()
        microphone = FakeSequenceMicrophone((b"first audio", b"yes audio"))
        recognizer = FakeRecognizer(
            RecognitionResult("List tasks", 0.2),
            RecognitionResult("yes", 0.9),
        )
        speaker = FakeSpeaker()
        console = StringIO()

        with redirect_stdout(console):
            run_voice_mode(router, microphone, recognizer, speaker)

        self.assertEqual(router.received, ["List tasks"])
        self.assertEqual(speaker.private_replies, ["Did you say List tasks? Please say yes or no."])
        self.assertEqual(
            speaker.replies,
            ["Mercury is ready and listening. Say a command. Press Esc to quit.", "Assistant reply."],
        )
        self.assertNotIn("List tasks", console.getvalue())

    def test_low_confidence_no_discards_pending_command(self):
        router = FakeRouter()
        recognizer = FakeRecognizer(
            RecognitionResult("Delete task two", 0.2),
            RecognitionResult("no", 0.9),
        )
        speaker = FakeSpeaker()

        run_voice_mode(router, FakeSequenceMicrophone((b"first", b"no")), recognizer, speaker)

        self.assertEqual(router.received, [])
        self.assertEqual(
            speaker.replies,
            [
                "Mercury is ready and listening. Say a command. Press Esc to quit.",
                "Okay. Please repeat your command.",
            ],
        )
        self.assertEqual(speaker.private_replies, ["Did you say Delete task two? Please say yes or no."])

    def test_command_match_changes_only_known_prefix(self):
        corrected = match_known_command("ad task buy   oat milk")
        numbered = match_known_command("compleet task one or two")
        unrelated = match_known_command("please add task buy milk")

        self.assertEqual(corrected.text, "add task buy   oat milk")
        self.assertTrue(corrected.fuzzy)
        self.assertEqual(numbered.text, "complete task one or two")
        self.assertTrue(numbered.fuzzy)
        self.assertEqual(unrelated.text, "please add task buy milk")

    def test_ambiguous_phrase_match_is_refused(self):
        result = match_known_command(
            "commnd task", phrases=("command task", "command tasks"), ambiguity_margin=0.2
        )

        self.assertTrue(result.ambiguous)

    def test_ambiguous_recognition_is_not_routed(self):
        router = FakeRouter()
        recognizer = FakeRecognizer(RecognitionResult("commnd task", 0.95))
        speaker = FakeSpeaker()

        with patch("core.voice_mode.match_known_command", return_value=CommandMatch("", ambiguous=True)):
            run_voice_mode(router, FakeMicrophone(), recognizer, speaker)

        self.assertEqual(router.received, [])
        self.assertIn("repeat the command", speaker.replies[-1])

    def test_voice_mode_uses_configured_microphone_and_recognizer(self):
        settings = Settings(
            workspace_folder=Path("."),
            app_whitelist=(),
            microphone_device=3,
            speech_recognizer="faster-whisper",
            speech_model_size="small.en",
            vosk_confidence_threshold=0.65,
            faster_whisper_confidence_threshold=0.45,
        )
        recognizer = FakeRecognizer(RecognitionResult("hello", 0.9))

        with (
            patch("audio.microphone.AlwaysListeningMicrophone") as microphone_factory,
            patch("core.voice_mode.create_speech_recognizer", return_value=recognizer) as recognizer_factory,
        ):
            run_voice_mode(FakeRouter(), recognizer=None, speaker=FakeSpeaker(), settings=settings)

        microphone_factory.assert_called_once_with(device=3)
        recognizer_factory.assert_called_once_with(settings)

    def test_empty_recognition_asks_without_routing_text(self):
        router = FakeRouter()
        speaker = FakeSpeaker()

        run_voice_mode(
            router,
            FakeMicrophone(),
            FakeRecognizer(RecognitionResult("", 0.0)),
            speaker,
        )

        self.assertEqual(router.received, [])
        self.assertEqual(
            speaker.replies,
            [
                "Mercury is ready and listening. Say a command. Press Esc to quit.",
                "I didn't catch that. Please repeat your command.",
            ],
        )

    def test_speech_output_prints_public_reply_but_not_private_confirmation(self):
        engine = FakeSpeechEngine()
        console = StringIO()

        with redirect_stdout(console):
            output = SpeechOutput(engine)
            output.speak("Assistant reply.")
            output.speak_private("Did you say private transcript?")

        self.assertEqual(console.getvalue(), "Assistant reply.\n")
        self.assertEqual(engine.spoken, ["Assistant reply.", "Did you say private transcript?"])

    def test_vosk_adapter_returns_confidence_without_printing_text(self):
        created = []

        def factory(model, sample_rate):
            adapter = FakeVoskRecognizer(model, sample_rate)
            created.append(adapter)
            return adapter

        recognizer = VoskSpeechRecognizer(model=object(), recognizer_factory=factory)
        console = StringIO()

        with redirect_stdout(console):
            result = recognizer.recognize(b"fake audio bytes")

        self.assertEqual(result, RecognitionResult("hello Mercury", 0.9))
        self.assertEqual(created[0].sample_rate, 16_000)
        self.assertEqual(created[0].audio, b"fake audio bytes")
        self.assertTrue(created[0].words_enabled)
        self.assertEqual(console.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
