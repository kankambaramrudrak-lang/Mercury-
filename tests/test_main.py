import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from main import DATABASE_PATH, TEST_SPEECH_TEXT, main


class MainModeTests(unittest.TestCase):
    def test_text_option_selects_text_mode_without_real_database(self):
        with (
            patch("main.TaskStore") as task_store,
            patch("main.ReminderStore") as reminder_store,
            patch("main.ReminderScheduler") as reminder_scheduler,
            patch("audio.speech_output.SpeechOutput") as speech_output,
            patch("main.run_text_mode") as text_mode,
            patch("main.configure_confirmation_log") as configure_log,
        ):
            result = main(["--text"])

        self.assertEqual(result, 0)
        task_store.assert_called_once_with(DATABASE_PATH)
        reminder_store.assert_called_once_with(DATABASE_PATH)
        reminder_scheduler.assert_called_once_with(reminder_store.return_value)
        speech_output.assert_called_once_with()
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

    def test_doctor_mode_does_not_start_the_assistant(self):
        with (
            patch("core.doctor.diagnose", return_value=[]) as diagnose,
            patch("core.doctor.print_diagnostics", return_value=0) as report,
            patch("main.TaskStore") as task_store,
        ):
            result = main(["--doctor"])

        self.assertEqual(result, 0)
        diagnose.assert_called_once_with()
        report.assert_called_once_with([])
        task_store.assert_not_called()

    def test_recognition_debug_option_is_removed(self):
        errors = StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
            main(["--debug-recognition"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("unrecognized arguments", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
