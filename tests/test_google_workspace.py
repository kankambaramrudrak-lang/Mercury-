import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from core.google_workspace import (
    CALENDAR_READONLY,
    GMAIL_COMPOSE,
    GMAIL_READONLY,
    GMAIL_SEND,
    GoogleOAuth,
    GoogleWorkspaceClient,
)
from core.tools import build_task_registry


class FakeSecretStore:
    def __init__(self):
        self.values = {}

    def get(self, username):
        return self.values.get(username)

    def set(self, username, value):
        self.values[username] = value


class GoogleWorkspaceTests(unittest.TestCase):
    def test_google_oauth_flow_stores_token_in_secret_store(self):
        with tempfile.TemporaryDirectory() as directory:
            credentials_path = Path(directory) / "client.json"
            credentials_path.write_text(
                json.dumps({"installed": {"client_id": "desktop-client-id"}}),
                encoding="utf-8",
            )
            store = FakeSecretStore()
            calls = []

            class Credentials:
                valid = True

                def to_json(self):
                    return '{"token":"local-test-token"}'

            class Flow:
                def run_local_server(self, **kwargs):
                    calls.append(("oauth", kwargs))
                    return Credentials()

            def flow_factory(path, scopes):
                calls.append(("flow", path, scopes))
                return Flow()

            def service_builder(api, version, **kwargs):
                calls.append(("service", api, version, kwargs))
                return "fake service"

            oauth = GoogleOAuth(
                credentials_path,
                store,
                flow_factory=flow_factory,
                service_builder=service_builder,
            )
            result = oauth.service("gmail", "v1", (GMAIL_READONLY,))

        self.assertEqual(result, "fake service")
        self.assertTrue(any(value == '{"token":"local-test-token"}' for value in store.values.values()))
        self.assertEqual(calls[0][0], "flow")
        self.assertEqual(calls[1], ("oauth", {"port": 0, "open_browser": True}))

    def test_email_search_uses_readonly_scope_and_returns_short_metadata(self):
        gmail = Mock()
        gmail.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "message-1"}]
        }
        gmail.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            "snippet": "Short private preview",
            "payload": {"headers": [
                {"name": "From", "value": "sam@example.com"},
                {"name": "Subject", "value": "Hello"},
            ]},
        }
        requested = []
        client = GoogleWorkspaceClient(
            lambda api, version, scopes: requested.append((api, version, scopes)) or gmail
        )

        result = client.search_email("from:sam@example.com", 3)

        self.assertIn("sam@example.com", result)
        self.assertIn("Subject: Hello", result)
        self.assertEqual(requested, [("gmail", "v1", (GMAIL_READONLY,))])
        gmail.users.return_value.messages.return_value.list.assert_called_once_with(
            userId="me", q="from:sam@example.com", maxResults=3
        )

    def test_calendar_query_is_readonly_and_limits_results(self):
        calendar = Mock()
        calendar.events.return_value.list.return_value.execute.return_value = {
            "items": [{"summary": "Planning", "start": {"dateTime": "2026-10-29T10:00:00Z"}}]
        }
        requested = []
        client = GoogleWorkspaceClient(
            lambda api, version, scopes: requested.append((api, version, scopes)) or calendar
        )

        result = client.upcoming_events(50)

        self.assertIn("Planning", result)
        self.assertEqual(requested, [("calendar", "v3", (CALENDAR_READONLY,))])
        arguments = calendar.events.return_value.list.call_args.kwargs
        self.assertEqual(arguments["maxResults"], 10)
        self.assertEqual(arguments["orderBy"], "startTime")

    def test_draft_and_send_encode_message_and_use_narrow_scopes(self):
        gmail = Mock()
        requested = []
        client = GoogleWorkspaceClient(
            lambda api, version, scopes: requested.append((api, version, tuple(scopes))) or gmail
        )

        self.assertEqual(
            client.create_draft("sam@example.com", "Hello", "Draft body"),
            "Email draft created. It has not been sent.",
        )
        self.assertEqual(client.send_email("sam@example.com", "Hello", "Send body"), "Email sent.")

        draft_raw = gmail.users.return_value.drafts.return_value.create.call_args.kwargs["body"]["message"]["raw"]
        sent_raw = gmail.users.return_value.messages.return_value.send.call_args.kwargs["body"]["raw"]
        draft_message = base64.urlsafe_b64decode(draft_raw + "=" * (-len(draft_raw) % 4)).decode("utf-8")
        sent_message = base64.urlsafe_b64decode(sent_raw + "=" * (-len(sent_raw) % 4)).decode("utf-8")
        self.assertIn("Draft body", draft_message)
        self.assertIn("Send body", sent_message)
        self.assertEqual(requested, [("gmail", "v1", (GMAIL_COMPOSE,)), ("gmail", "v1", (GMAIL_SEND,))])

    def test_send_and_draft_need_confirmation_and_refuse_invalid_recipient(self):
        gmail = Mock()
        seen = []
        from unittest.mock import MagicMock

        store = MagicMock()
        client = GoogleWorkspaceClient(lambda *_args: gmail)
        registry = build_task_registry(
            store,
            confirmation_handler=lambda title, details: seen.append((title, details)) or False,
            google_workspace=client,
        )

        invalid = registry.execute(
            "send_email", recipient="not an email", subject="Hello", body="Do not send"
        )
        refused = registry.execute(
            "send_email", recipient="sam@example.com", subject="Hello", body="Do not send"
        )

        self.assertIn("valid recipient", invalid)
        self.assertIn("cancelled", refused)
        self.assertEqual(len(seen), 1)
        self.assertIn("sam@example.com", seen[0][1])
        self.assertIn("Do not send", seen[0][1])
        gmail.users.return_value.messages.return_value.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
