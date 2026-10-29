import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from core.router import CommandRouter
from tools.tasks import TaskCommands, TaskStore
from tools.desktop import DesktopTools


class DesktopToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_directory.name) / "workspace"
        self.workspace.mkdir()

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_open_only_allowlisted_https_target(self):
        open_url = Mock(return_value=True)
        tools = DesktopTools(
            self.workspace,
            ("ChatGPT=https://chatgpt.com",),
            open_url=open_url,
        )

        self.assertEqual(tools.open_app("ChatGPT"), "Opening ChatGPT.")
        open_url.assert_called_once_with("https://chatgpt.com")
        self.assertIn("isn't on the approved app list", tools.open_app("Unknown"))

    def test_open_allowlisted_executable_without_shell(self):
        start_process = Mock()
        tools = DesktopTools(
            self.workspace,
            ("Editor=editor.exe",),
            start_process=start_process,
            find_executable=lambda name: "C:\\Apps\\editor.exe" if name == "editor.exe" else None,
        )

        self.assertEqual(tools.open_app("Editor"), "Opening Editor.")
        start_process.assert_called_once_with(["C:\\Apps\\editor.exe"], shell=False)

    def test_create_folder_inside_workspace_and_refuse_traversal(self):
        tools = DesktopTools(self.workspace)

        self.assertEqual(tools.create_folder("project notes"), "Created folder project notes.")
        self.assertTrue((self.workspace / "project notes").is_dir())
        self.assertIn("outside the workspace", tools.create_folder("../outside"))
        self.assertFalse((self.workspace.parent / "outside").exists())

    def test_create_folder_refuses_symlink_escape(self):
        outside = self.workspace.parent / "outside"
        outside.mkdir()
        link = self.workspace / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation is unavailable in this environment")
        tools = DesktopTools(self.workspace)

        self.assertIn("outside the workspace", tools.create_folder("linked/new folder"))
        self.assertFalse((outside / "new folder").exists())

    def test_search_web_uses_fixed_google_url_and_allowlisted_browser(self):
        controller = Mock()
        controller.open_new_tab.return_value = True
        browser_get = Mock(return_value=controller)
        tools = DesktopTools(self.workspace, browser_get=browser_get)

        self.assertEqual(
            tools.search_web("official Vosk model page", "edge"),
            "Opening the search in your browser.",
        )
        browser_get.assert_called_once_with("edge")
        self.assertEqual(
            controller.open_new_tab.call_args.args[0],
            "https://www.google.com/search?q=official+Vosk+model+page",
        )
        self.assertIn("Choose the default browser", tools.search_web("query", "custom"))

    def test_router_sends_desktop_commands_to_registered_tools(self):
        store = TaskStore(self.workspace / "tasks.sqlite3")
        controller = Mock()
        controller.open_new_tab.return_value = True
        desktop = DesktopTools(
            self.workspace,
            ("ChatGPT=https://chatgpt.com",),
            open_url=lambda _url: True,
            browser_get=lambda _name: controller,
        )
        router = CommandRouter(TaskCommands(store), desktop_tools=desktop)

        self.assertEqual(router.handle("Open ChatGPT"), "Opening ChatGPT.")
        self.assertEqual(router.handle("Create a folder called notes"), "Created folder notes.")
        self.assertEqual(
            router.handle("Search the web for local speech recognition in Edge"),
            "Opening the search in your browser.",
        )
        self.assertEqual(
            controller.open_new_tab.call_args.args[0],
            "https://www.google.com/search?q=local+speech+recognition",
        )


if __name__ == "__main__":
    unittest.main()
