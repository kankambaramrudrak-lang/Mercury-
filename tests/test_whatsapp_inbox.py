import hashlib
import hmac
import json
import tempfile
import time
import unittest
from pathlib import Path

from core.contacts import ContactBook
from core.whatsapp_inbox import WhatsAppInbox


class WhatsAppInboxTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.contacts_file = Path(self.temporary.name) / "contacts.json"
        self.contacts_file.write_text(
            json.dumps(
                {
                    "Sam": {"phone": "+14155550123", "whatsapp_opt_in": True},
                    "No consent": {"phone": "+14155550124", "whatsapp_opt_in": False},
                }
            ),
            encoding="utf-8",
        )
        self.contacts = ContactBook(self.contacts_file)
        self.now = int(time.time())
        self.inbox = WhatsAppInbox(self.contacts, clock=lambda: self.now)
        self.secret = "fake-meta-app-secret"

    def tearDown(self):
        self.temporary.cleanup()

    def _payload(self, sender="14155550123", message_id="wamid.fake-1", text="Hi Mercury"):
        return json.dumps(
            {
                "object": "whatsapp_business_account",
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": sender,
                                "id": message_id,
                                "timestamp": str(self.now),
                                "type": "text",
                                "text": {"body": text},
                            }]
                        }
                    }]
                }],
            }
        ).encode("utf-8")

    def _signature(self, body):
        digest = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def test_signature_required_and_valid_event_is_readable(self):
        body = self._payload()

        self.assertEqual(self.inbox.accept_payload(body, "sha256=bad", self.secret), 0)
        self.assertEqual(self.inbox.accept_payload(body, self._signature(body), self.secret), 1)
        self.assertIn("Message 1 from Sam: Hi Mercury", self.inbox.list_messages())
        self.assertEqual(self.inbox.notifications.get_nowait(), 1)

    def test_nonallowlisted_senders_duplicates_and_nontext_are_ignored(self):
        body = self._payload(sender="14155550124")
        signature = self._signature(body)
        self.assertEqual(self.inbox.accept_payload(body, signature, self.secret), 0)
        self.assertEqual(self.inbox.accept_payload(body, signature, self.secret), 0)

        accepted = self._payload(message_id="wamid.image")
        data = json.loads(accepted)
        data["entry"][0]["changes"][0]["value"]["messages"][0]["type"] = "image"
        accepted = json.dumps(data).encode()
        self.assertEqual(self.inbox.accept_payload(accepted, self._signature(accepted), self.secret), 0)

    def test_only_inbound_messages_inside_24_hour_window_can_be_replied_to(self):
        body = self._payload()
        self.inbox.accept_payload(body, self._signature(body), self.secret)
        self.assertTrue(self.inbox.is_replyable(1))
        self.now += 24 * 60 * 60 + 1
        self.assertFalse(self.inbox.is_replyable(1))

    def test_contact_verification_token_uses_constant_time_comparison(self):
        self.assertTrue(self.inbox.verify_token("same-token", "same-token"))
        self.assertFalse(self.inbox.verify_token("wrong", "same-token"))


if __name__ == "__main__":
    unittest.main()
