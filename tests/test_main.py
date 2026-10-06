import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from main import DATABASE_PATH, TEST_SPEECH_TEXT, main


class MainModeTests(unittest.TestCase):
    def test_text_option_selects_text_mode_without_real_database(self):
        with (
            patch("main.TaskStore") as task_store,
            patch("main.run_text_mode") as text_mode,
            patch("main.configure_confirmation_log") as configure_log,
        ):
            result = main(["--text"])

        self.assertEqual(result, 0)
        task_store.assert_called_once_with(DATABASE_PATH)
        text_mode.assert_called_once()
        configure_log.assert_called_once_with()

    def test_test_speech_selects_fake_speech_output(self):
        with (
            patch("audio.speech_output.SpeechOutput") as speech_output,
            patch("main.TaskStore") as task_store,
        ):
            result = main(["--test-speech"])

        self.assertEqual(result, 0)
        speech_output.return_value.speak.assert_called_once_with(TEST_SPEECH_TEXT)
        task_store.assert_not_called()

    def test_recognition_debug_option_is_removed(self):
        errors = StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
            main(["--debug-recognition"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("unrecognized arguments", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
