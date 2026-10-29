import tempfile
import unittest
from pathlib import Path

from core.router import CommandRouter
from tools.reminders import ReminderScheduler, ReminderStore
from tools.tasks import TaskCommands, TaskStore


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.now = [1_000.0]
        path = Path(self.temp_directory.name) / "assistant.sqlite3"
        self.store = ReminderStore(path, clock=lambda: self.now[0])
        self.scheduler = ReminderScheduler(self.store, clock=lambda: self.now[0])
        tasks = TaskStore(path)
        from core.tools import build_task_registry

        registry = build_task_registry(tasks, reminder_store=self.store)
        self.router = CommandRouter(TaskCommands(tasks), registry=registry)

    def tearDown(self):
        self.scheduler.stop()
        self.temp_directory.cleanup()

    def test_router_schedules_relative_reminder_and_timer(self):
        self.assertEqual(
            self.router.handle("Remind me in 10 minutes to call Sam"),
            "Reminder 1 set for call Sam.",
        )
        self.assertEqual(
            self.router.handle("Set a timer for five seconds"),
            "Timer 2 set for 5 seconds.",
        )
        pending = self.store.pending()
        self.assertEqual([item.message for item in pending], ["Timer finished.", "call Sam"])
        self.assertEqual(next(item.due_at for item in pending if item.message == "call Sam"), 1_600.0)

    def test_scheduler_queues_due_reminders_once(self):
        reminder = self.store.add("take a break", 5)
        self.now[0] += 5

        self.scheduler.poll_once()
        self.scheduler.poll_once()

        self.assertEqual(self.scheduler.drain(), [reminder])
        self.assertEqual(self.scheduler.drain(), [])
        self.assertEqual([item.message for item in self.store.pending()], ["take a break"])
        self.assertTrue(self.scheduler.acknowledge(reminder))
        self.assertEqual(self.store.pending(), [])

    def test_unacknowledged_due_entry_is_delivered_after_scheduler_restart(self):
        reminder = self.store.add("check the stove", 1)
        self.now[0] += 1
        self.scheduler.poll_once()
        self.assertEqual(self.scheduler.drain(), [reminder])

        restarted = ReminderScheduler(self.store, clock=lambda: self.now[0])
        restarted.poll_once()

        self.assertEqual(restarted.drain(), [reminder])
        self.assertTrue(restarted.acknowledge(reminder))

    def test_reminders_survive_reopening_store(self):
        self.store.add("check the oven", 30)
        reopened = ReminderStore(self.store.database_path, clock=lambda: self.now[0])

        self.assertEqual([item.message for item in reopened.pending()], ["check the oven"])

    def test_invalid_delays_and_empty_messages_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.add("", 10)
        with self.assertRaises(ValueError):
            self.store.add("too soon", 0)
        with self.assertRaises(ValueError):
            self.store.add("bad type", 5, "alarm")


if __name__ == "__main__":
    unittest.main()
