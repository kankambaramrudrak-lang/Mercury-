import threading
import time
import unittest

from core.confirm import ConfirmationService
from core.tools import Tool, ToolRegistry


class ConfirmationServiceTests(unittest.TestCase):
    def test_approval_and_cancellation_return_fake_button_decisions(self):
        approved = ConfirmationService(presenter=lambda _title, _details, _timeout: True)
        cancelled = ConfirmationService(presenter=lambda _title, _details, _timeout: False)

        self.assertTrue(approved.ask_confirmation("Review", "Details"))
        self.assertFalse(cancelled.ask_confirmation("Review", "Details"))

    def test_timeout_refuses_and_expired_queued_request_is_not_presented(self):
        presented = []
        service = ConfirmationService(
            presenter=lambda *_args: presented.append(True) or True,
            timeout_seconds=0.02,
        )
        result = []
        worker = threading.Thread(target=lambda: result.append(service.ask_confirmation("Review", "Details")))
        worker.start()
        worker.join(timeout=1)

        self.assertEqual(result, [False])
        service.process_pending_requests()
        self.assertEqual(presented, [])

    def test_worker_request_is_queued_and_presented_on_main_thread(self):
        presentation_threads = []
        service = ConfirmationService(
            presenter=lambda *_args: presentation_threads.append(threading.get_ident()) or True,
        )
        result = []
        worker = threading.Thread(target=lambda: result.append(service.ask_confirmation("Review", "Details")))
        worker.start()
        deadline = time.monotonic() + 1
        while service._requests.empty() and time.monotonic() < deadline:
            time.sleep(0.001)

        service.process_pending_requests()
        worker.join(timeout=1)

        self.assertEqual(result, [True])
        self.assertEqual(presentation_threads, [threading.main_thread().ident])


class ConfirmationGateTests(unittest.TestCase):
    def test_confirmation_gate_runs_only_after_approval_and_logs_no_arguments(self):
        registry = ToolRegistry(lambda _title, _details: True)
        calls = []
        registry.register(
            Tool(
                "delete_task",
                "Delete one task.",
                {"task_number": "integer", "description": "string"},
                "confirm",
                lambda **_parameters: calls.append("ran") or "done",
            )
        )

        with self.assertLogs("hercules.confirmations", level="INFO") as captured:
            result = registry.execute("delete_task", task_number=7, description="private words")

        self.assertEqual(result, "done")
        self.assertEqual(calls, ["ran"])
        self.assertEqual(captured.output, ["INFO:hercules.confirmations:tool=delete_task approved=True"])
        self.assertNotIn("private words", captured.output[0])

    def test_cancellation_and_missing_handler_refuse_without_running_tool(self):
        calls = []
        tool = Tool("risky", "Risky action", {}, "confirm", lambda: calls.append(True))
        cancelled = ToolRegistry(lambda _title, _details: False)
        cancelled.register(tool)
        missing = ToolRegistry()
        missing.register(tool)

        self.assertIn("cancelled", cancelled.execute("risky").lower())
        self.assertIn("disabled", missing.execute("risky").lower())
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
