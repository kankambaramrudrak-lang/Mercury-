import tempfile
import unittest
from pathlib import Path

from tasks import TaskCommands, TaskStore


class TaskCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "tasks.sqlite3"
        self.store = TaskStore(self.database_path)
        self.commands = TaskCommands(self.store)

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_add_task_stores_only_description(self):
        response = self.commands.handle("Add task buy milk")

        self.assertEqual(response, "Added task 1: buy milk.")
        self.assertEqual(self.store.list_open()[0].description, "buy milk")

    def test_list_tasks_speaks_open_tasks(self):
        self.store.add("buy milk")
        self.store.add("call the dentist")

        response = self.commands.handle("List tasks")

        self.assertEqual(
            response,
            "You have 2 open tasks. Task 1: buy milk. Task 2: call the dentist.",
        )

    def test_complete_task_removes_it_from_open_list(self):
        self.store.add("buy milk")

        response = self.commands.handle("Complete task 1")

        self.assertEqual(response, "Completed task 1.")
        self.assertEqual(self.store.list_open(), [])

    def test_tasks_persist_when_store_is_reopened(self):
        self.store.add("buy milk")

        reopened_store = TaskStore(self.database_path)

        self.assertEqual(reopened_store.list_open()[0].description, "buy milk")

    def test_unclear_task_number_prompts_without_completing_anything(self):
        self.store.add("buy milk")

        response = self.commands.handle("Complete task two or three")

        self.assertIn("clear task number", response)
        self.assertEqual([task.description for task in self.store.list_open()], ["buy milk"])

    def test_spoken_number_is_accepted(self):
        self.store.add("buy milk")

        response = self.commands.handle("Complete task one")

        self.assertEqual(response, "Completed task 1.")

    def test_update_task_changes_description(self):
        self.store.add("buy milk")

        response = self.commands.handle("Update task one to buy oat milk")

        self.assertEqual(response, "Updated task 1: buy oat milk.")
        self.assertEqual(self.store.list_open()[0].description, "buy oat milk")

    def test_delete_requires_exact_confirmation(self):
        self.store.add("buy milk")

        request = self.commands.handle("Delete task one")
        self.assertIn("Confirm delete task 1", request)
        self.assertEqual(len(self.store.list_open()), 1)

        response = self.commands.handle("Confirm delete task one")

        self.assertEqual(response, "Deleted task 1.")
        self.assertEqual(self.store.list_open(), [])

    def test_bare_yes_cancels_pending_delete(self):
        self.store.add("buy milk")
        self.commands.handle("Delete task 1")

        response = self.commands.handle("yes")

        self.assertIn("Deletion canceled", response)
        self.assertEqual([task.description for task in self.store.list_open()], ["buy milk"])

    def test_mismatched_confirmation_cancels_without_deleting(self):
        self.store.add("buy milk")
        self.store.add("call the dentist")
        self.commands.handle("Delete task 1")

        response = self.commands.handle("Confirm delete task 2")

        self.assertIn("Deletion canceled", response)
        self.assertEqual(
            [task.description for task in self.store.list_open()],
            ["buy milk", "call the dentist"],
        )


if __name__ == "__main__":
    unittest.main()
