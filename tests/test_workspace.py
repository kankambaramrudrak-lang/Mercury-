import tempfile
import unittest
from pathlib import Path

from tools.workspace import WorkspaceSearch


class WorkspaceSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_search_finds_relevant_text_without_exposing_secret_or_ignored_files(self):
        (self.root / "notes.txt").write_text("The blue river crosses town.\nAnother line.", encoding="utf-8")
        (self.root / "credentials.json").write_text("blue river secret", encoding="utf-8")
        ignored = self.root / ".venv"
        ignored.mkdir()
        (ignored / "notes.txt").write_text("blue river ignored", encoding="utf-8")

        result = WorkspaceSearch(self.root).search("blue river")

        self.assertIn("notes.txt:1: The blue river crosses town.", result)
        self.assertNotIn("credentials", result)
        self.assertNotIn("ignored", result)

    def test_search_does_not_follow_a_file_symlink_outside_workspace(self):
        outside = self.root.parent / f"{self.root.name}-outside.txt"
        outside.write_text("private phrase", encoding="utf-8")
        link = self.root / "link.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            outside.unlink(missing_ok=True)
            self.skipTest("Symlink creation is unavailable in this environment")
        try:
            result = WorkspaceSearch(self.root).search("private phrase")
            self.assertIn("couldn't find", result)
        finally:
            outside.unlink(missing_ok=True)

    def test_search_expands_common_wording_and_keeps_following_command_lines(self):
        (self.root / "README.md").write_text(
            "## Run\n\n```powershell\npython main.py\n```\n",
            encoding="utf-8",
        )

        result = WorkspaceSearch(self.root).search(
            "What does the README say about how to start Mercury voice mode?"
        )

        self.assertIn("README.md:1: ## Run", result)
        self.assertIn("README.md:4: python main.py", result)


if __name__ == "__main__":
    unittest.main()
