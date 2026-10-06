import tempfile
import unittest
from pathlib import Path

from core.router import CommandRouter
from tools.tasks import TaskCommands, TaskStore


class RouterTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_directory.name) / "tasks.sqlite3"
        self.store = TaskStore(database_path)
        self.router = CommandRouter(TaskCommands(self.store))

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_add_and_list_tasks_through_handle(self):
        self.assertEqual(self.router.handle("Add task buy milk"), "Added task 1: buy milk.")
        self.assertEqual(
            self.router.handle("List tasks"),
            "You have one open task. Task 1: buy milk.",
        )

    def test_empty_list_through_handle(self):
        self.assertEqual(self.router.handle("List tasks"), "You have no open tasks.")

    def test_tasks_persist_across_router_instances(self):
        self.router.handle("Add task buy milk")
        reopened = CommandRouter(TaskCommands(TaskStore(self.store.database_path)))

        self.assertEqual(
            reopened.handle("List tasks"),
            "You have one open task. Task 1: buy milk.",
        )

    def test_complete_task_through_handle(self):
        self.router.handle("Add task buy milk")

        self.assertEqual(self.router.handle("Complete task one"), "Completed task 1.")
        self.assertEqual(self.router.handle("List tasks"), "You have no open tasks.")

    def test_unclear_completion_number_does_not_change_task(self):
        self.router.handle("Add task buy milk")

        response = self.router.handle("Complete task two or three")

        self.assertIn("clear task number", response)
        self.assertEqual([task.description for task in self.store.list_open()], ["buy milk"])

    def test_update_task_through_handle(self):
        self.router.handle("Add task buy milk")

        response = self.router.handle("Update task one to buy oat milk")

        self.assertEqual(response, "Updated task 1: buy oat milk.")
        self.assertEqual([task.description for task in self.store.list_open()], ["buy oat milk"])

    def test_unclear_update_number_does_not_change_task(self):
        self.router.handle("Add task buy milk")

        response = self.router.handle("Update task one or two to buy oat milk")

        self.assertIn("clear task number", response)
        self.assertEqual([task.description for task in self.store.list_open()], ["buy milk"])

    def test_delete_is_refused_and_task_is_unchanged(self):
        self.router.handle("Add task buy milk")

        response = self.router.handle("Delete task one")

        self.assertIn("button confirmation is unavailable", response)
        self.assertEqual([task.description for task in self.store.list_open()], ["buy milk"])

    def test_confirmation_phrase_cannot_delete_without_button(self):
        self.router.handle("Add task buy milk")

        response = self.router.handle("Confirm delete task one")

        self.assertIn("button confirmation is unavailable", response)
        self.assertEqual([task.description for task in self.store.list_open()], ["buy milk"])

    def test_count_tasks(self):
        from tools.tasks import count_tasks

        self.assertEqual(count_tasks(self.store), 0)
        self.store.add("buy milk")
        self.store.add("call Sam")
        self.assertEqual(count_tasks(self.store), 2)

if __name__ == "__main__":
    unittest.main()
