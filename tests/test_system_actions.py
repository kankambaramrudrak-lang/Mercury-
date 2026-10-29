import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.tools import build_task_registry
from tools.system_actions import SystemActions
from tools.tasks import TaskStore


class SystemActionTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_directory.name) / "workspace"
        self.workspace.mkdir()
        self.database_path = Path(self.temp_directory.name) / "tasks.sqlite3"

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_install_runs_only_allowlisted_exact_winget_command_after_approval(self):
        commands = []
        approvals = []

        def runner(command, **kwargs):
            commands.append((command, kwargs))
            return SimpleNamespace(returncode=0)

        actions = SystemActions(
            self.workspace,
            ("Microsoft.PowerToys",),
            run_command=runner,
        )
        registry = build_task_registry(
            TaskStore(self.database_path),
            confirmation_handler=lambda title, details: approvals.append((title, details)) or True,
            system_actions=actions,
        )

        response = registry.execute("install_app", package_id="microsoft.powertoys")

        self.assertEqual(response, "Installation completed.")
        self.assertEqual(len(commands), 1)
        self.assertFalse(commands[0][1]["shell"])
        self.assertEqual(commands[0][0][:5], ["winget", "install", "--id", "Microsoft.PowerToys", "--exact"])
        self.assertIn("Exact command: winget install --id Microsoft.PowerToys --exact", approvals[0][1])

    def test_unapproved_install_and_unlisted_package_never_run(self):
        commands = []
        actions = SystemActions(
            self.workspace,
            ("Contoso.App",),
            run_command=lambda command, **_: commands.append(command),
        )
        registry = build_task_registry(
            TaskStore(self.database_path),
            confirmation_handler=lambda _title, _details: False,
            system_actions=actions,
        )

        response = registry.execute("install_app", package_id="Contoso.App")
        denied = registry.execute("install_app", package_id="Unknown.App")

        self.assertIn("cancelled", response)
        self.assertIn("not on the approved install list", denied)
        self.assertEqual(commands, [])

    def test_delete_confirmation_shows_full_path_and_item_count(self):
        folder = self.workspace / "notes"
        folder.mkdir()
        (folder / "one.txt").write_text("one", encoding="utf-8")
        (folder / "two.txt").write_text("two", encoding="utf-8")
        details = []
        moved = []
        actions = SystemActions(
            self.workspace,
            send_to_trash=moved.append,
        )
        registry = build_task_registry(
            TaskStore(self.database_path),
            confirmation_handler=lambda _title, text: details.append(text) or True,
            system_actions=actions,
        )

        response = registry.execute("delete_path", relative_path="notes")

        self.assertEqual(response, "Moved notes to the Recycle Bin.")
        self.assertIn(str(folder.resolve()), details[0])
        self.assertIn("Items including this item: 3", details[0])
        self.assertEqual(moved, [str(folder.resolve())])

    def test_delete_refuses_workspace_escape_and_unapproved_delete(self):
        outside = Path(self.temp_directory.name) / "outside.txt"
        outside.write_text("keep", encoding="utf-8")
        inside = self.workspace / "keep.txt"
        inside.write_text("keep", encoding="utf-8")
        moved = []
        actions = SystemActions(self.workspace, send_to_trash=moved.append)
        registry = build_task_registry(
            TaskStore(self.database_path),
            confirmation_handler=lambda _title, _details: False,
            system_actions=actions,
        )

        escaped = registry.execute("delete_path", relative_path="../outside.txt")
        missing = registry.execute("delete_path", relative_path="missing.txt")
        cancelled = registry.execute("delete_path", relative_path="keep.txt")

        self.assertIn("outside the workspace", escaped)
        self.assertIn("outside the workspace", missing)
        self.assertIn("cancelled", cancelled)
        self.assertEqual(moved, [])
        self.assertTrue(outside.exists())
        self.assertTrue(inside.exists())


if __name__ == "__main__":
    unittest.main()
