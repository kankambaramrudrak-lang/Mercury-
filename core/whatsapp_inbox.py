"""Loopback-only, signature-verified Meta webhook receiver for inbound text."""

from __future__ import annotations

import hashlib
import hmac
import json
import queue
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from core.contacts import ContactBook

MAX_WEBHOOK_BYTES = 64 * 1024
INBOX_LIMIT = 50
MESSAGE_WINDOW_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class IncomingWhatsAppMessage:
    local_id: int
    contact_name: str
    phone_number: str
    message_id: str
    text: str
    received_at: int
    replied: bool = False


class WhatsAppInbox:
    """Hold recent opted-in text messages in memory; never log message contents."""

    def __init__(self, contacts: ContactBook, clock: Callable[[], float] = time.time) -> None:
        self.contacts = contacts
        self._clock = clock
        self._messages: list[IncomingWhatsAppMessage] = []
        self._next_id = 1
        self._lock = threading.Lock()
        self.notifications: queue.Queue[int] = queue.Queue()

    @staticmethod
    def verify_token(supplied: str, expected: str) -> bool:
        return bool(supplied and expected and hmac.compare_digest(supplied, expected))

    @staticmethod
    def verify_signature(raw_body: bytes, signature: str, app_secret: str) -> bool:
        if not app_secret or not signature.startswith("sha256="):
            return False
        expected = "sha256=" + hmac.new(
            app_secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    def accept_payload(self, raw_body: bytes, signature: str, app_secret: str) -> int:
        if len(raw_body) > MAX_WEBHOOK_BYTES or not self.verify_signature(raw_body, signature, app_secret):
            return 0
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 0
        if not isinstance(payload, dict):
            return 0
        accepted = 0
        for entry in payload.get("entry", []):
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes", []):
                value = change.get("value", {}) if isinstance(change, dict) else {}
                messages = value.get("messages", []) if isinstance(value, dict) else []
                for message in messages:
                    if not isinstance(message, dict) or message.get("type") != "text":
                        continue
                    sender = message.get("from")
                    external_id = message.get("id")
                    text = message.get("text", {}).get("body") if isinstance(message.get("text"), dict) else None
                    try:
                        received_at = int(message.get("timestamp", ""))
                    except (TypeError, ValueError):
                        continue
                    if (
                        not isinstance(sender, str)
                        or not sender.isdigit()
                        or not isinstance(external_id, str)
                        or not external_id
                        or not isinstance(text, str)
                        or not text.strip()
                        or received_at > self._clock() + 300
                    ):
                        continue
                    phone_number = f"+{sender}"
                    contact = self.contacts.resolve(phone_number)
                    if contact is None or not self.contacts.is_allowed(phone_number, "whatsapp"):
                        continue
                    with self._lock:
                        if any(item.message_id == external_id for item in self._messages):
                            continue
                        item = IncomingWhatsAppMessage(
                            self._next_id,
                            contact[0],
                            phone_number,
                            external_id,
                            text.strip()[:4096],
                            received_at,
                        )
                        self._next_id += 1
                        self._messages.append(item)
                        self._messages = self._messages[-INBOX_LIMIT:]
                    self.notifications.put(item.local_id)
                    accepted += 1
        return accepted

    def list_messages(self, include_replied: bool = False) -> str:
        with self._lock:
            messages = [item for item in self._messages if include_replied or not item.replied]
        if not messages:
            return "There are no unread WhatsApp messages in this session."
        return "\n".join(
            f"Message {item.local_id} from {item.contact_name}: {item.text}"
            for item in messages
        )

    def get(self, local_id: int) -> IncomingWhatsAppMessage | None:
        with self._lock:
            return next((item for item in self._messages if item.local_id == local_id), None)

    def is_replyable(self, local_id: int) -> bool:
        item = self.get(local_id)
        if item is None or item.replied:
            return False
        age = self._clock() - item.received_at
        return 0 <= age <= MESSAGE_WINDOW_SECONDS

    def latest_replyable(self, name_or_number: str) -> IncomingWhatsAppMessage | None:
        contact = self.contacts.resolve(name_or_number)
        if contact is None:
            return None
        with self._lock:
            candidates = [
                item
                for item in self._messages
                if item.phone_number == contact[1]
                and not item.replied
                and 0 <= self._clock() - item.received_at <= MESSAGE_WINDOW_SECONDS
            ]
        return max(candidates, key=lambda item: item.received_at, default=None)

    def mark_replied(self, local_id: int) -> None:
        with self._lock:
            self._messages = [
                IncomingWhatsAppMessage(
                    item.local_id,
                    item.contact_name,
                    item.phone_number,
                    item.message_id,
                    item.text,
                    item.received_at,
                    True,
                )
                if item.local_id == local_id
                else item
                for item in self._messages
            ]


class WhatsAppWebhookServer:
    """Expose only a loopback callback listener; a user-managed HTTPS tunnel is required."""

    def __init__(
        self,
        inbox: WhatsAppInbox,
        verify_token: str,
        app_secret: str,
        port: int = 8765,
    ) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("Webhook port must be a valid TCP port")
        self.inbox = inbox
        self.verify_token = verify_token
        self.app_secret = app_secret
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.verify_token or not self.app_secret:
            raise RuntimeError("Webhook verify token and Meta app secret are required")
        inbox = self.inbox
        verify_token = self.verify_token
        app_secret = self.app_secret

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: object) -> None:
                return

            def do_GET(self) -> None:
                if urlsplit(self.path).path != "/whatsapp/webhook":
                    self.send_error(404)
                    return
                query = parse_qs(urlsplit(self.path).query)
                mode = query.get("hub.mode", [""])[0]
                supplied = query.get("hub.verify_token", [""])[0]
                challenge = query.get("hub.challenge", [""])[0]
                if mode != "subscribe" or not challenge or not inbox.verify_token(supplied, verify_token):
                    self.send_error(403)
                    return
                body = challenge.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                if urlsplit(self.path).path != "/whatsapp/webhook":
                    self.send_error(404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "-1"))
                except ValueError:
                    length = -1
                if not 0 <= length <= MAX_WEBHOOK_BYTES:
                    self.send_error(413)
                    return
                raw_body = self.rfile.read(length)
                signature = self.headers.get("X-Hub-Signature-256", "")
                accepted = inbox.accept_payload(raw_body, signature, app_secret)
                if not inbox.verify_signature(raw_body, signature, app_secret):
                    self.send_error(401)
                    return
                body = json.dumps({"accepted": accepted}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="hercules-whatsapp-webhook", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
