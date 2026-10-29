import tempfile
import unittest
from pathlib import Path

from core.router import CommandRouter
from core.tools import build_task_registry
from tools.tasks import TaskCommands, TaskStore


class ToolRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.temp_directory.name) / "tasks.sqlite3")
        self.registry = build_task_registry(self.store)
        self.router = CommandRouter(TaskCommands(self.store), self.registry)

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_task_tools_and_count_function_are_registered(self):
        self.assertEqual(
            set(self.registry.names()),
            {"add_task", "list_tasks", "complete_task", "update_task", "delete_task", "count_tasks"},
        )
        delete_tool = self.registry.get("delete_task")
        self.assertIsNotNone(delete_tool)
        self.assertEqual(delete_tool.risk_level, "confirm")
        self.assertIn("description", self.registry.get("add_task").parameters)

    def test_router_executes_registered_task_operations(self):
        self.assertEqual(self.router.handle("Add task buy milk"), "Added task 1: buy milk.")
        self.assertEqual(self.router.handle("Update task one to buy oat milk"), "Updated task 1: buy oat milk.")
        self.assertEqual(self.router.handle("Count tasks"), "You have one open task.")
        self.assertEqual(self.router.handle("Complete task one"), "Completed task 1.")
        self.assertEqual(self.router.handle("List tasks"), "You have no open tasks.")

    def test_unregistered_tool_cannot_execute(self):
        with self.assertRaises(KeyError):
            self.registry.execute("run_arbitrary_action")

    def test_registry_schema_is_limited_to_registered_functions(self):
        schema_names = {
            schema["function"]["name"] for schema in self.registry.schemas()
        }
        self.assertEqual(schema_names, set(self.registry.names()))
        self.assertNotIn("shell", schema_names)

    def test_registry_validates_tool_argument_names_and_types(self):
        with self.assertRaises(ValueError):
            self.registry.execute("complete_task", task_number="one")
        with self.assertRaises(ValueError):
            self.registry.execute("complete_task", task_number=1, extra="ignored")

    def test_unrecognized_command_mentions_count_tasks(self):
        response = self.router.handle("do something unexpected")

        self.assertIn("Count tasks", response)
        self.assertIn("button approval", response)

    def test_confirm_tool_is_refused_without_calling_its_function(self):
        # Replace the function with a sentinel to verify the confirm gate blocks it.
        from dataclasses import replace

        tool = self.registry.get("delete_task")
        called = []
        self.registry._tools["delete_task"] = replace(tool, function=lambda **_: called.append(True))
        self.store.add("keep this task")

        response = self.router.handle("Delete task one")

        self.assertIn("button confirmation is unavailable", response)
        self.assertEqual(called, [])
        self.assertEqual([task.description for task in self.store.list_open()], ["keep this task"])


if __name__ == "__main__":
    unittest.main()
