"""Official outbound WhatsApp Cloud API and Twilio Voice clients."""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Protocol
from xml.sax.saxutils import escape

from core.contacts import ContactBook
from core.whatsapp_inbox import WhatsAppInbox


class SecretStore(Protocol):
    def get(self, username: str) -> str | None: ...

    def set(self, username: str, value: str) -> None: ...


class WhatsAppCloudClient:
    """Send an approved text message through Meta's official Graph API."""

    def __init__(
        self,
        phone_number_id: str,
        graph_version: str,
        contacts: ContactBook,
        secret_store: SecretStore,
        inbox: WhatsAppInbox | None = None,
        *,
        urlopen: Callable[..., object] | None = None,
    ) -> None:
        self.phone_number_id = phone_number_id.strip()
        self.graph_version = graph_version.strip()
        self.contacts = contacts
        self.secret_store = secret_store
        self.inbox = inbox
        self._urlopen = urllib.request.urlopen if urlopen is None else urlopen

    def preflight(self, recipient: str, text: str) -> str | None:
        if not self.phone_number_id:
            self.phone_number_id = self.secret_store.get("phone_number_id") or ""
        if not re.fullmatch(r"[0-9]{5,32}", self.phone_number_id):
            return "WhatsApp Business phone number ID is not configured. Nothing was sent."
        if not re.fullmatch(r"v[0-9]+\.[0-9]+", self.graph_version):
            return "WhatsApp Graph API version is not configured. Nothing was sent."
        if not self.contacts.is_allowed(recipient, "whatsapp"):
            return "That recipient is not in your WhatsApp opt-in allowlist. Nothing was sent."
        if self.inbox is None or self.inbox.latest_replyable(recipient) is None:
            return "No incoming WhatsApp message is open for reply. Outside the 24-hour window, an approved template is required."
        if not text.strip() or len(text) > 4096:
            return "Message text must contain 1 to 4096 characters. Nothing was sent."
        if not self.secret_store.get("access_token"):
            return "WhatsApp access token is not configured in Windows Credential Manager. Nothing was sent."
        return None

    def confirmation_details(self, recipient: str, text: str) -> str:
        contact = self.contacts.resolve(recipient)
        display_name = contact[0] if contact else recipient
        return f"Reply to {display_name} on WhatsApp?\n\nMessage:\n{text}"

    def send_message(self, recipient: str, text: str) -> str:
        refusal = self.preflight(recipient, text)
        if refusal:
            return refusal
        contact = self.contacts.resolve(recipient)
        assert contact is not None
        token = self.secret_store.get("access_token")
        assert token is not None
        latest = self.inbox.latest_replyable(recipient) if self.inbox is not None else None
        if latest is None:
            return "No incoming WhatsApp message is open for reply. Nothing was sent."
        return self._send_reply(contact, latest.message_id, text)

    def reply_preflight(self, message_id: int, text: str) -> str | None:
        if self.inbox is None:
            return "WhatsApp inbox is not running. Nothing was sent."
        if not re.fullmatch(r"[0-9]{5,32}", self.phone_number_id):
            return "WhatsApp Business phone number ID is not configured. Nothing was sent."
        if not re.fullmatch(r"v[0-9]+\.[0-9]+", self.graph_version):
            return "WhatsApp Graph API version is not configured. Nothing was sent."
        message = self.inbox.get(message_id)
        if message is None or not self.inbox.is_replyable(message_id):
            return "That WhatsApp message is missing, already answered, or outside the 24-hour reply window. Nothing was sent."
        if not self.contacts.is_allowed(message.phone_number, "whatsapp"):
            return "That sender is not in your WhatsApp opt-in allowlist. Nothing was sent."
        if not self.secret_store.get("access_token"):
            return "WhatsApp access token is not configured in Windows Credential Manager. Nothing was sent."
        if not text.strip() or len(text) > 4096:
            return "Message text must contain 1 to 4096 characters. Nothing was sent."
        return None

    def reply_confirmation_details(self, message_id: int, text: str) -> str:
        message = self.inbox.get(message_id) if self.inbox is not None else None
        if message is None:
            return "The WhatsApp message is no longer available. Nothing will be sent."
        return f"Reply to {message.contact_name} on WhatsApp?\n\nMessage:\n{text}"

    def reply_to_message(self, message_id: int, text: str) -> str:
        refusal = self.reply_preflight(message_id, text)
        if refusal:
            return refusal
        assert self.inbox is not None
        message = self.inbox.get(message_id)
        assert message is not None
        contact = self.contacts.resolve(message.phone_number)
        assert contact is not None
        result = self._send_reply(contact, message.message_id, text)
        if result.startswith("WhatsApp message sent"):
            self.inbox.mark_replied(message_id)
        return result

    def _send_reply(self, contact: tuple[str, str], message_id: str, text: str) -> str:
        token = self.secret_store.get("access_token")
        if token is None:
            return "WhatsApp access token is not configured in Windows Credential Manager. Nothing was sent."
        url = f"https://graph.facebook.com/{self.graph_version}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": contact[1].lstrip("+"),
            "type": "text",
            "text": {"preview_url": False, "body": text},
            "context": {"message_id": message_id},
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("messages"):
                return f"WhatsApp message sent to {contact[0]}."
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            pass
        return "I couldn't send the WhatsApp message. Check the connection, permissions, and messaging rules."


class TwilioVoiceClient:
    """Place a short, non-recorded outbound call using Twilio's REST API."""

    def __init__(
        self,
        contacts: ContactBook,
        secret_store: SecretStore,
        *,
        urlopen: Callable[..., object] | None = None,
    ) -> None:
        self.contacts = contacts
        self.secret_store = secret_store
        self._urlopen = urllib.request.urlopen if urlopen is None else urlopen

    def preflight(self, recipient: str, announcement: str) -> str | None:
        if not self.contacts.is_allowed(recipient, "call"):
            return "That phone number is not in your call opt-in allowlist. No call was placed."
        sid = self.secret_store.get("account_sid")
        token = self.secret_store.get("auth_token")
        from_number = self.secret_store.get("from_number")
        if not sid or not re.fullmatch(r"AC[0-9a-fA-F]{32}", sid):
            return "Twilio account SID is not configured in Windows Credential Manager. No call was placed."
        if not token or not from_number or not re.fullmatch(r"\+[1-9][0-9]{7,14}", from_number):
            return "Twilio credentials or caller number are not configured. No call was placed."
        if not announcement.strip() or len(announcement) > 1000:
            return "Call announcement must contain 1 to 1000 characters. No call was placed."
        return None

    def confirmation_details(self, recipient: str, announcement: str) -> str:
        contact = self.contacts.resolve(recipient)
        display_name = contact[0] if contact else recipient
        destination = f"{display_name} ({contact[1]})" if contact else display_name
        return (
            f"Place a Twilio phone call to {destination}? This may incur provider charges.\n\n"
            f"The call will read this message and will not be recorded:\n{announcement}"
        )

    def call_contact(self, recipient: str, announcement: str) -> str:
        refusal = self.preflight(recipient, announcement)
        if refusal:
            return refusal
        return self._place_call(recipient, announcement)

    def call_contact_preapproved(self, recipient: str, announcement: str) -> str:
        """Place a call previously approved with its exact recipient and message."""
        refusal = self.preflight(recipient, announcement)
        if refusal:
            return refusal
        return self._place_call(recipient, announcement)

    def _place_call(self, recipient: str, announcement: str) -> str:
        contact = self.contacts.resolve(recipient)
        assert contact is not None
        sid = self.secret_store.get("account_sid")
        token = self.secret_store.get("auth_token")
        from_number = self.secret_store.get("from_number")
        assert sid is not None and token is not None and from_number is not None
        account = urllib.parse.quote(sid, safe="")
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account}/Calls.json"
        twiml = f"<Response><Say>{escape(announcement)}</Say></Response>"
        form = urllib.parse.urlencode(
            {"To": contact[1], "From": from_number, "Twiml": twiml, "Record": "false", "TimeLimit": "60"}
        ).encode("ascii")
        authorization = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
        request = urllib.request.Request(
            url,
            data=form,
            headers={"Authorization": f"Basic {authorization}", "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with self._urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("sid"):
                return f"Phone call started to {contact[0]}."
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            pass
        return "I couldn't place the phone call. Check the provider connection, permissions, and account balance."
