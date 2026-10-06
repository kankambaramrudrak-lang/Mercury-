import builtins
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from main import (
    TEST_SPEECH_TEXT,
    reply_for,
    report_recognition,
    run,
    speak_response,
)
from tasks import TaskCommands, TaskStore


class ReplyTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.temp_directory.name) / "tasks.sqlite3")
        self.commands = TaskCommands(self.store)

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_greetings_receive_hercules_reply(self):
        for greeting in ("hello", "Hi!", "hey there", "good morning"):
            with self.subTest(greeting=greeting):
                self.assertEqual(reply_for(greeting, self.commands), "Hello! I'm Hercules.")

    def test_non_greetings_get_supported_scope_reply(self):
        self.assertIn("I didn't understand", reply_for("what is the weather", self.commands))
        self.assertIn("I didn't understand", reply_for("this is a test", self.commands))

    def test_task_command_replies_use_task_store(self):
        self.assertEqual(reply_for("Add task buy milk", self.commands), "Added task 1: buy milk.")
        self.assertEqual(
            reply_for("List tasks", self.commands),
            "You have one open task. Task 1: buy milk.",
        )

    def test_spoken_reply_is_printed_once_and_speaks_same_text(self):
        engine = Mock()
        output = StringIO()

        with redirect_stdout(output):
            speak_response(engine, "Hello! I'm Hercules.")

        self.assertEqual(output.getvalue(), "Hello! I'm Hercules.\n")
        engine.say.assert_called_once_with("Hello! I'm Hercules.")
        engine.runAndWait.assert_called_once_with()

    def test_recognition_output_is_hidden_unless_debug_is_enabled(self):
        output = StringIO()

        with redirect_stdout(output):
            report_recognition("add task private detail", debug=False)
        self.assertEqual(output.getvalue(), "")

        with redirect_stdout(output):
            report_recognition("add task private detail", debug=True)
        self.assertEqual(output.getvalue(), "Recognized words: add task private detail\n")

    def test_speech_test_option_does_not_import_microphone(self):
        engine = Mock()
        fake_tts = types.ModuleType("pyttsx3")
        fake_tts.init = Mock(return_value=engine)
        original_import = builtins.__import__

        def import_without_microphone(name, *args, **kwargs):
            if name == "sounddevice":
                raise AssertionError("--test-speech must not import sounddevice")
            return original_import(name, *args, **kwargs)

        output = StringIO()
        with (
            patch("sys.argv", ["main.py", "--test-speech"]),
            patch.dict(sys.modules, {"pyttsx3": fake_tts}),
            patch("builtins.__import__", side_effect=import_without_microphone),
            redirect_stdout(output),
        ):
            result = run()

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), f"{TEST_SPEECH_TEXT}\n")
        fake_tts.init.assert_called_once_with("sapi5")
        engine.say.assert_called_once_with(TEST_SPEECH_TEXT)
        engine.runAndWait.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
