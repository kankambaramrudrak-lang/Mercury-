import tempfile
import unittest
from pathlib import Path

from core.settings import load_settings


class SettingsTests(unittest.TestCase):
    def test_loads_workspace_and_safe_local_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.toml"
            settings_file.write_text(
                'workspace_folder = "."\n'
                'app_whitelist = []\n'
                'microphone_device = "default"\n'
                'speech_model_size = "small"\n',
                encoding="utf-8",
            )

            settings = load_settings(settings_file)

        self.assertEqual(settings.workspace_folder, settings_file.parent.resolve())
        self.assertEqual(settings.app_whitelist, ())
        self.assertEqual(settings.microphone_device, "default")
        self.assertEqual(settings.speech_recognizer, "vosk")
        self.assertEqual(settings.speech_model_size, "small")
        self.assertEqual(settings.vosk_confidence_threshold, 0.65)
        self.assertEqual(settings.faster_whisper_confidence_threshold, 0.45)
        self.assertFalse(settings.google_enabled)
        self.assertEqual(settings.google_credentials_file, (settings_file.parent / "secrets/google-oauth-client.json").resolve())
        self.assertFalse(settings.whatsapp_enabled)
        self.assertFalse(settings.twilio_enabled)
        self.assertEqual(settings.whatsapp_graph_version, "v26.0")

    def test_loads_recognizer_choice_and_thresholds(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.toml"
            settings_file.write_text(
                'speech_recognizer = "faster-whisper"\n'
                'speech_model_size = "small.en"\n'
                "vosk_confidence_threshold = 0.7\n"
                "faster_whisper_confidence_threshold = 0.4\n",
                encoding="utf-8",
            )

            settings = load_settings(settings_file)

        self.assertEqual(settings.speech_recognizer, "faster-whisper")
        self.assertEqual(settings.speech_model_size, "small.en")
        self.assertEqual(settings.vosk_confidence_threshold, 0.7)
        self.assertEqual(settings.faster_whisper_confidence_threshold, 0.4)

    def test_rejects_invalid_whitelist_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.toml"
            settings_file.write_text('app_whitelist = "all"\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "app_whitelist"):
                load_settings(settings_file)

    def test_rejects_ambiguous_app_whitelist_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.toml"
            settings_file.write_text(
                'app_whitelist = ["Browser=chrome.exe", "browser=edge.exe"]\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unique"):
                load_settings(settings_file)

    def test_rejects_out_of_range_confidence_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.toml"
            settings_file.write_text("vosk_confidence_threshold = 1.2\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "vosk_confidence_threshold"):
                load_settings(settings_file)

    def test_validates_exact_winget_install_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.toml"
            settings_file.write_text('install_whitelist = ["Microsoft.PowerToys"]\n', encoding="utf-8")
            settings = load_settings(settings_file)
            self.assertEqual(settings.install_whitelist, ("Microsoft.PowerToys",))

            settings_file.write_text('install_whitelist = ["*", "Contoso.App"]\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "winget package IDs"):
                load_settings(settings_file)

    def test_local_ai_defaults_and_rejects_nonlocal_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.toml"
            settings_file.write_text(
                'local_ai_enabled = true\n'
                'local_ai_model = "llama3.2:3b"\n'
                'local_ai_url = "http://localhost:11434"\n',
                encoding="utf-8",
            )
            settings = load_settings(settings_file)
            self.assertTrue(settings.local_ai_enabled)
            self.assertEqual(settings.local_ai_model, "llama3.2:3b")
            self.assertEqual(settings.local_ai_url, "http://localhost:11434")

            settings_file.write_text('local_ai_url = "https://example.com"\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "local HTTP endpoint"):
                load_settings(settings_file)


if __name__ == "__main__":
    unittest.main()
