import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.router import CommandRouter
from core.tools import build_task_registry
from tools.project_builder import ProjectBuilder
from tools.tasks import TaskCommands, TaskStore


class InlineThread:
    def __init__(self, *, target, args, **_kwargs):
        self.target = target
        self.args = args

    def start(self):
        self.target(*self.args)


class ProjectBuilderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.directory.name)
        self.calls = []
        self.approvals = []

        def run_command(args, *, cwd, **kwargs):
            args = list(args)
            self.calls.append((args, Path(cwd), kwargs))
            if args[0] == "git" and args[1] == "init":
                (Path(cwd) / ".git").mkdir(exist_ok=True)
            if args[0] == "codex":
                (Path(cwd) / "main.py").write_text("print('hello')\n", encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout="Tests passed.", stderr="")
            if args[1:3] == ["diff", "--no-ext-diff"]:
                return SimpleNamespace(returncode=0, stdout="diff --git a/main.py b/main.py\n+print('hello')\n", stderr="")
            if args[1:3] == ["status", "--short"]:
                return SimpleNamespace(returncode=0, stdout=" A main.py\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        self.run_command = run_command

    def tearDown(self):
        self.directory.cleanup()

    def _builder(self, decisions=(True, True)):
        decisions = iter(decisions)
        def confirm(title, details):
            self.approvals.append((title, details))
            return next(decisions)

        return ProjectBuilder(
            self.workspace,
            confirm,
            model="llama3.2:3b",
            codex_path="codex",
            run_command=self.run_command,
            thread_factory=InlineThread,
        )

    def _finish_questionnaire(self, builder):
        self.assertEqual(builder.begin("A voice journal app"), "What should I name the project?")
        self.assertEqual(builder.answer("Voice Journal"), "What look or theme should it have?")
        self.assertEqual(builder.answer("Calm and simple"), "What are the main features you want?")
        self.assertEqual(builder.answer("Record and search entries"), "Which language or framework should it use?")
        self.assertEqual(builder.answer("Python and Tkinter"), "When do you need it? You can say 'no deadline'.")
        return builder.answer("No deadline")

    def test_project_spec_and_code_checkpoint_require_separate_approvals(self):
        builder = self._builder()

        result = self._finish_questionnaire(builder)

        project = self.workspace / "voice-journal"
        self.assertIn("local coding agent has started", result)
        self.assertEqual([title for title, _ in self.approvals], [
            "Approve project specification",
            "Review generated project checkpoint",
        ])
        self.assertIn("Record and search entries", (project / "SPEC.md").read_text(encoding="utf-8"))
        self.assertTrue((project / "main.py").exists())
        self.assertIn("--sandbox", next(args for args, _cwd, _kwargs in self.calls if args[0] == "codex"))
        command = next(args for args, _cwd, _kwargs in self.calls if args[0] == "codex")
        self.assertIn("--oss", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("workspace-write", command)
        self.assertIn("Tests passed", self.approvals[1][1])
        self.assertIn("checkpoint is saved", builder.notifications.get_nowait())

    def test_rejecting_specification_creates_no_project_folder(self):
        builder = self._builder(decisions=(False,))

        result = self._finish_questionnaire(builder)

        self.assertIn("No folder was created", result)
        self.assertFalse((self.workspace / "voice-journal").exists())
        self.assertFalse(any(args[0] == "codex" for args, _cwd, _kwargs in self.calls))

    def test_rejecting_code_checkpoint_leaves_changes_uncommitted(self):
        builder = self._builder(decisions=(True, False))

        self._finish_questionnaire(builder)

        commits = [args for args, _cwd, _kwargs in self.calls if args[0] == "git" and args[1] == "commit"]
        self.assertEqual(len(commits), 1)
        self.assertIn("remain uncommitted", builder.notifications.get_nowait())

    def test_questionnaire_can_be_cancelled_without_creating_files(self):
        builder = self._builder()
        builder.begin("A voice journal app")

        result = builder.answer("cancel project")

        self.assertIn("cancelled", result)
        self.assertFalse(builder.active)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_voice_text_routes_through_the_multiturn_project_questionnaire(self):
        builder = self._builder()
        tasks = TaskStore(self.workspace / "tasks.sqlite3")
        registry = build_task_registry(tasks, project_builder=builder)
        router = CommandRouter(TaskCommands(tasks), registry=registry, project_builder=builder)

        self.assertEqual(router.handle("Start project for a recipe app"), "What should I name the project?")
        self.assertIn("look or theme", router.handle("Recipe Box"))
        self.assertEqual(router.handle("cancel project"), "Project planning cancelled. No folder was created.")
        self.assertFalse((self.workspace / "recipe-box").exists())


if __name__ == "__main__":
    unittest.main()
