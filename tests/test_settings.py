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

        self.assertEqual(settings.workspace_folder, Path("."))
        self.assertEqual(settings.app_whitelist, ())
        self.assertEqual(settings.microphone_device, "default")
        self.assertEqual(settings.speech_model_size, "small")

    def test_rejects_invalid_whitelist_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.toml"
            settings_file.write_text('app_whitelist = "all"\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "app_whitelist"):
                load_settings(settings_file)


if __name__ == "__main__":
    unittest.main()
