import json
import tempfile
import unittest
import time
from pathlib import Path
from unittest.mock import MagicMock

from core.communications import TwilioVoiceClient, WhatsAppCloudClient
from core.contacts import ContactBook
from core.tools import build_task_registry
from core.whatsapp_inbox import WhatsAppInbox


class FakeSecretStore:
    def __init__(self, **values):
        self.values = values

    def get(self, username):
        return self.values.get(username)

    def set(self, username, value):
        self.values[username] = value


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.payload


class CommunicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.contacts_path = self.root / "contacts.json"
        self.contacts_path.write_text(
            json.dumps(
                {
                    "Sam": {"phone": "+14155550123", "whatsapp_opt_in": True, "call_opt_in": True},
                    "Me": {"phone": "+14155550987", "whatsapp_opt_in": True, "call_opt_in": True},
                }
            ),
            encoding="utf-8",
        )
        self.contacts = ContactBook(self.contacts_path)
        self.inbox = WhatsAppInbox(self.contacts)
        message = {
            "entry": [{"changes": [{"value": {"messages": [{
                "from": "14155550123",
                "id": "wamid.incoming",
                "timestamp": str(int(time.time())),
                "type": "text",
                "text": {"body": "Hello"},
            }]}}]}]
        }
        body = json.dumps(message).encode("utf-8")
        import hashlib
        import hmac

        app_secret = "test-secret"
        signature = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
        self.inbox.accept_payload(body, signature, app_secret)

    def tearDown(self):
        self.temporary.cleanup()

    def test_contact_book_resolves_only_explicitly_allowlisted_numbers(self):
        self.assertEqual(self.contacts.resolve("sam"), ("Sam", "+14155550123"))
        self.assertEqual(self.contacts.resolve("+14155550123"), ("Sam", "+14155550123"))
        self.assertIsNone(self.contacts.resolve("+14155550124"))
        self.assertTrue(self.contacts.is_allowed("Sam", "whatsapp"))
        self.assertFalse(self.contacts.is_allowed("Unknown", "call"))

    def test_whatsapp_send_is_approved_and_uses_meta_graph_api(self):
        captured = []
        store = FakeSecretStore(access_token="fake-meta-token", phone_number_id="123456789")

        def open_request(request, timeout):
            captured.append((request, timeout))
            return FakeResponse({"messages": [{"id": "wamid.fake"}]})

        client = WhatsAppCloudClient(
            "123456789", "v26.0", self.contacts, store, self.inbox, urlopen=open_request
        )
        approvals = []
        registry = build_task_registry(
            MagicMock(),
            confirmation_handler=lambda title, details: approvals.append((title, details)) or True,
            whatsapp_client=client,
            whatsapp_inbox=self.inbox,
        )

        result = registry.execute(
            "reply_whatsapp_message", message_id=1, text="Running five minutes late"
        )

        self.assertEqual(result, "WhatsApp message sent to Sam.")
        request, timeout = captured[0]
        self.assertEqual(timeout, 30)
        self.assertEqual(request.full_url, "https://graph.facebook.com/v26.0/123456789/messages")
        self.assertEqual(request.headers["Authorization"], "Bearer fake-meta-token")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["to"], "14155550123")
        self.assertEqual(payload["text"]["body"], "Running five minutes late")
        self.assertEqual(payload["context"]["message_id"], "wamid.incoming")
        self.assertIn("Running five minutes late", approvals[0][1])

    def test_whatsapp_rejects_nonallowlisted_and_cancelled_messages(self):
        requests = []
        client = WhatsAppCloudClient(
            "123456789",
            "v26.0",
            self.contacts,
            FakeSecretStore(access_token="token"),
            self.inbox,
            urlopen=lambda request, **_: requests.append(request),
        )
        approvals = []
        registry = build_task_registry(
            MagicMock(),
            confirmation_handler=lambda title, details: approvals.append((title, details)) or False,
            whatsapp_client=client,
            whatsapp_inbox=self.inbox,
        )

        unknown = registry.execute(
            "reply_whatsapp_message", message_id=999, text="Do not send"
        )
        cancelled = registry.execute(
            "reply_whatsapp_message", message_id=1, text="Do not send"
        )

        self.assertIn("missing", unknown)
        self.assertIn("cancelled", cancelled)
        self.assertEqual(approvals.__len__(), 1)
        self.assertEqual(requests, [])

    def test_twilio_call_requires_approval_and_sends_nonrecorded_twiml(self):
        captured = []
        store = FakeSecretStore(
            account_sid="AC" + "a" * 32,
            auth_token="fake-twilio-token",
            from_number="+14155550987",
        )

        def open_request(request, timeout):
            captured.append((request, timeout))
            return FakeResponse({"sid": "CA" + "b" * 32})

        client = TwilioVoiceClient(self.contacts, store, urlopen=open_request)
        approvals = []
        registry = build_task_registry(
            MagicMock(),
            confirmation_handler=lambda title, details: approvals.append((title, details)) or True,
            twilio_client=client,
        )

        result = registry.execute(
            "call_contact", recipient="Me", announcement="Mercury reminder: your meeting starts soon."
        )

        self.assertEqual(result, "Phone call started to Me.")
        request, _ = captured[0]
        form = request.data.decode("ascii")
        self.assertIn("Record=false", form)
        self.assertIn("TimeLimit=60", form)
        self.assertIn("Mercury+reminder", form)
        self.assertIn("may incur provider charges", approvals[0][1])

    def test_twilio_unknown_recipient_and_cancelled_call_never_reach_network(self):
        requests = []
        store = FakeSecretStore(
            account_sid="AC" + "a" * 32,
            auth_token="token",
            from_number="+14155550987",
        )
        client = TwilioVoiceClient(self.contacts, store, urlopen=lambda request, **_: requests.append(request))
        registry = build_task_registry(
            MagicMock(), confirmation_handler=lambda _title, _details: False, twilio_client=client
        )

        unknown = registry.execute("call_contact", recipient="Unknown", announcement="Call me")
        cancelled = registry.execute("call_contact", recipient="Sam", announcement="Call me")

        self.assertIn("allowlist", unknown)
        self.assertIn("cancelled", cancelled)
        self.assertEqual(requests, [])


if __name__ == "__main__":
    unittest.main()
