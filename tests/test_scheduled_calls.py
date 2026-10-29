import tempfile
import time
import unittest
from pathlib import Path

from core.router import CommandRouter
from core.tools import build_task_registry
from tools.scheduled_calls import ScheduledCallScheduler, ScheduledCallStore, dispatch_due_calls
from tools.tasks import TaskCommands, TaskStore


class FakeCallClient:
    def __init__(self):
        self.calls = []
        self.response = "Phone call started to Me."

    def preflight(self, recipient, announcement):
        return None if recipient.casefold() == "me" and announcement else "Call is not allowed."

    def confirmation_details(self, recipient, announcement):
        return f"Call {recipient} (+14155550123); may incur provider charges. Message: {announcement}"

    def call_contact(self, recipient, announcement):
        return self.call_contact_preapproved(recipient, announcement)

    def call_contact_preapproved(self, recipient, announcement):
        self.calls.append((recipient, announcement))
        return self.response


class ScheduledCallTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.now = [time.time()]
        database = Path(self.directory.name) / "assistant.sqlite3"
        self.store = ScheduledCallStore(database, clock=lambda: self.now[0])
        self.scheduler = ScheduledCallScheduler(self.store, clock=lambda: self.now[0])
        self.client = FakeCallClient()
        self.approvals = []
        self.tasks = TaskStore(database)
        registry = build_task_registry(
            self.tasks,
            confirmation_handler=lambda title, details: self.approvals.append((title, details)) or True,
            twilio_client=self.client,
            scheduled_call_store=self.store,
        )
        self.router = CommandRouter(TaskCommands(self.tasks), registry=registry)

    def tearDown(self):
        self.scheduler.stop()
        self.directory.cleanup()

    def test_scheduling_requires_approval_and_shows_exact_call_content(self):
        result = self.router.handle("Call me in ten minutes saying your meeting starts soon")

        self.assertIn("Phone call scheduled to me", result)
        self.assertEqual(len(self.approvals), 1)
        title, details = self.approvals[0]
        self.assertEqual(title, "Confirm schedule_call")
        self.assertIn("may incur provider charges", details)
        self.assertIn("your meeting starts soon", details)
        self.assertIn("+14155550123", details)
        self.assertEqual(self.store.claim_due(self.now[0]), [])
        self.assertEqual(self.store.claim_due(self.now[0] + 600)[0].recipient, "me")

    def test_rejected_confirmation_does_not_save_call(self):
        registry = build_task_registry(
            self.tasks,
            confirmation_handler=lambda _title, _details: False,
            twilio_client=self.client,
            scheduled_call_store=self.store,
        )

        result = registry.execute(
            "schedule_call", recipient="Me", announcement="Call me", delay_seconds=60
        )

        self.assertIn("cancelled", result)
        self.assertEqual(self.store.claim_due(self.now[0] + 100), [])
        self.assertEqual(self.client.calls, [])

    def test_due_call_runs_once_and_reports_result(self):
        self.store.add("Me", "This is your reminder.", 5)
        self.now[0] += 5
        self.scheduler.poll_once()
        self.scheduler.poll_once()
        replies = []

        dispatch_due_calls(self.scheduler, self.client, replies.append)
        self.scheduler.poll_once()

        self.assertEqual(self.client.calls, [("Me", "This is your reminder.")])
        self.assertEqual(replies, ["Phone call started to Me."])
        with self.store._connect() as connection:
            status = connection.execute("SELECT status FROM scheduled_calls").fetchone()[0]
        self.assertEqual(status, "completed")

    def test_failed_due_call_is_not_retried(self):
        self.store.add("Me", "This is your reminder.", 5)
        self.now[0] += 5
        self.scheduler.poll_once()
        self.client.response = "Provider rejected the call."

        dispatch_due_calls(self.scheduler, self.client, lambda _message: None)
        self.scheduler.poll_once()
        dispatch_due_calls(self.scheduler, self.client, lambda _message: None)

        self.assertEqual(len(self.client.calls), 1)
        with self.store._connect() as connection:
            status = connection.execute("SELECT status FROM scheduled_calls").fetchone()[0]
        self.assertEqual(status, "failed")

    def test_user_can_list_and_cancel_pending_calls(self):
        scheduled = self.store.add("Me", "Private message", 60)
        listed = self.router.handle("List scheduled calls")
        self.assertIn("scheduled call 1 to me", listed.casefold())
        self.assertNotIn("Private message", listed)
        self.assertEqual(
            self.router.handle("Cancel call one"),
            f"Cancelled scheduled phone call {scheduled.id}.",
        )
        self.assertEqual(self.router.handle("List scheduled calls"), "You have no scheduled phone calls.")
        self.assertFalse(self.store.cancel(scheduled.id))

    def test_invalid_call_delays_are_rejected(self):
        for delay in (0, 4, -1, 31_536_001, True):
            with self.subTest(delay=delay), self.assertRaises(ValueError):
                self.store.add("Me", "Call", delay)


if __name__ == "__main__":
    unittest.main()
