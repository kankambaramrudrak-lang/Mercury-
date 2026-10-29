import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from core.doctor import Diagnostic, diagnose, print_diagnostics


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self):
        return json.dumps(self.value).encode("utf-8")


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        settings = self.root / "settings.toml"
        settings.write_text(
            f'workspace_folder = "{self.root.as_posix()}"\n'
            'speech_recognizer = "faster-whisper"\n'
            'speech_model_size = "small.en"\n'
            'local_ai_enabled = true\n'
            'local_ai_model = "llama3.2:3b"\n',
            encoding="utf-8",
        )
        self.settings_path = settings

    def tearDown(self):
        self.directory.cleanup()

    def test_reports_ready_local_runtime_without_reading_account_credentials(self):
        results = diagnose(
            self.settings_path,
            module_exists=lambda _name: True,
            urlopen=lambda _url, timeout: FakeResponse({"models": [{"name": "llama3.2:3b"}]}),
            find_command=lambda name: "C:/tools/codex.exe" if name == "codex" else None,
        )
        statuses = {item.name: item.status for item in results}

        self.assertEqual(statuses["Settings"], "OK")
        self.assertEqual(statuses["Workspace"], "OK")
        self.assertEqual(statuses["Local Ollama model"], "OK")
        self.assertEqual(statuses["faster-whisper model"], "WARN")
        self.assertEqual(statuses["Microphone and speaker hardware"], "WARN")
        account = next(item for item in results if item.name == "Account integrations")
        self.assertIn("no credentials were inspected", account.detail)

    def test_missing_runtime_and_local_model_produce_nonzero_report(self):
        results = diagnose(
            self.settings_path,
            module_exists=lambda name: name not in {"numpy", "faster_whisper"},
            urlopen=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
            find_command=lambda _name: None,
        )
        output = StringIO()
        code = print_diagnostics(results, output.write)

        self.assertEqual(code, 1)
        report = output.getvalue()
        self.assertIn("[FAIL] Audio array package", report)
        self.assertIn("[FAIL] Local Ollama model", report)
        self.assertNotIn("offline", report)

    def test_invalid_settings_fail_without_exposing_error_contents(self):
        self.settings_path.write_text("local_ai_url = 'https://secret.example/token'\n", encoding="utf-8")

        results = diagnose(self.settings_path)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "FAIL")
        self.assertNotIn("secret.example", results[0].detail)

    def test_print_diagnostics_succeeds_when_only_warnings_are_present(self):
        output = StringIO()

        code = print_diagnostics([Diagnostic("Microphone", "WARN", "Not tested.")], output.write)

        self.assertEqual(code, 0)
        self.assertIn("0 issue(s)", output.getvalue())


if __name__ == "__main__":
    unittest.main()
