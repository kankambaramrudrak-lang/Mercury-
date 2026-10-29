"""Optional Gmail and Calendar client using Google's official APIs and OAuth."""

from __future__ import annotations

import base64
import json
import re
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Protocol, Sequence

GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_COMPOSE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
CALENDAR_READONLY = "https://www.googleapis.com/auth/calendar.events.readonly"
READ_SCOPES = (GMAIL_READONLY, CALENDAR_READONLY)
_EMAIL = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")


class SecretStore(Protocol):
    def get(self, username: str) -> str | None: ...

    def set(self, username: str, value: str) -> None: ...


class WindowsCredentialStore:
    """Keep OAuth refresh tokens in Windows Credential Manager via keyring."""

    def __init__(self, service_name: str = "Hercules Google OAuth") -> None:
        import keyring

        backend = keyring.get_keyring()
        backend_module = type(backend).__module__.casefold()
        if "windows" not in backend_module or getattr(backend, "priority", 0) <= 0:
            raise RuntimeError("A Windows Credential Manager keyring backend is required")
        self._keyring = keyring
        self._service_name = service_name

    def get(self, username: str) -> str | None:
        return self._keyring.get_password(self._service_name, username)

    def set(self, username: str, value: str) -> None:
        self._keyring.set_password(self._service_name, username, value)


class GoogleOAuth:
    """Obtain official desktop-app OAuth credentials and securely retain tokens."""

    def __init__(
        self,
        credentials_path: str | Path,
        secret_store: SecretStore,
        *,
        flow_factory: Callable[..., object] | None = None,
        service_builder: Callable[..., object] | None = None,
        credentials_factory: Callable[..., object] | None = None,
        request_factory: Callable[[], object] | None = None,
    ) -> None:
        self.credentials_path = Path(credentials_path)
        self.secret_store = secret_store
        self._flow_factory = flow_factory
        self._service_builder = service_builder
        self._credentials_factory = credentials_factory
        self._request_factory = request_factory

    def service(self, api: str, version: str, scopes: Sequence[str]) -> object:
        requested_scopes = tuple(sorted(set(scopes)))
        client_id = self._client_id()
        token_key = f"{client_id}|{' '.join(requested_scopes)}"
        credentials = self._load_credentials(token_key, requested_scopes)
        return self._build_service(api, version, credentials)

    def _client_id(self) -> str:
        try:
            content = json.loads(self.credentials_path.read_text(encoding="utf-8"))
            client = content.get("installed") or content.get("web")
            client_id = client.get("client_id") if isinstance(client, dict) else None
        except (OSError, json.JSONDecodeError, AttributeError):
            client_id = None
        if not isinstance(client_id, str) or not client_id.strip():
            raise RuntimeError("Google OAuth credentials are missing or invalid")
        return client_id

    def _load_credentials(self, token_key: str, scopes: Sequence[str]) -> object:
        credentials_factory = self._credentials_factory
        serialized = self.secret_store.get(token_key)
        credentials = None
        if serialized:
            try:
                if credentials_factory is None:
                    from google.oauth2.credentials import Credentials

                    credentials_factory = Credentials.from_authorized_user_info
                credentials = credentials_factory(json.loads(serialized), scopes=scopes)
            except Exception:
                credentials = None

        if credentials is not None and getattr(credentials, "valid", False):
            return credentials

        if credentials is not None and getattr(credentials, "expired", False) and getattr(credentials, "refresh_token", None):
            request_factory = self._request_factory
            if request_factory is None:
                from google.auth.transport.requests import Request

                request_factory = Request
            try:
                credentials.refresh(request_factory())
            except Exception:
                credentials = None
            else:
                self.secret_store.set(token_key, credentials.to_json())
                return credentials

        flow_factory = self._flow_factory
        if flow_factory is None:
            from google_auth_oauthlib.flow import InstalledAppFlow

            flow_factory = InstalledAppFlow.from_client_secrets_file
        flow = flow_factory(str(self.credentials_path), scopes=list(scopes))
        credentials = flow.run_local_server(port=0, open_browser=True)
        self.secret_store.set(token_key, credentials.to_json())
        return credentials

    def _build_service(self, api: str, version: str, credentials: object) -> object:
        builder = self._service_builder
        if builder is None:
            from googleapiclient.discovery import build

            builder = build
        return builder(api, version, credentials=credentials, cache_discovery=False)


class GoogleWorkspaceClient:
    """Read Gmail and Calendar; create drafts or send only through explicit tools."""

    def __init__(self, service_provider: Callable[[str, str, Sequence[str]], object]) -> None:
        self._service_provider = service_provider

    def search_email(self, query: str, limit: int = 5) -> str:
        query = query.strip()
        if not query or len(query) > 250:
            return "Give me an email search query of 1 to 250 characters."
        limit = max(1, min(int(limit), 10))
        try:
            gmail = self._service_provider("gmail", "v1", (GMAIL_READONLY,))
            response = gmail.users().messages().list(userId="me", q=query, maxResults=limit).execute()
            messages = response.get("messages", [])
            found = []
            for item in messages:
                message = gmail.users().messages().get(
                    userId="me",
                    id=item["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ).execute()
                headers = {
                    header.get("name", "").casefold(): header.get("value", "")
                    for header in message.get("payload", {}).get("headers", [])
                }
                snippet = " ".join(str(message.get("snippet", "")).split())[:350]
                found.append(
                    f"From: {headers.get('from', 'unknown')}; Date: {headers.get('date', 'unknown')}; "
                    f"Subject: {headers.get('subject', '(no subject)')}; Preview: {snippet}"
                )
            return "\n".join(found) if found else "No matching emails found."
        except Exception:
            return "I couldn't access Gmail. Check the Google connection and Gmail API setup."

    def upcoming_events(self, limit: int = 5) -> str:
        limit = max(1, min(int(limit), 10))
        try:
            from datetime import datetime, timezone

            calendar = self._service_provider("calendar", "v3", (CALENDAR_READONLY,))
            response = calendar.events().list(
                calendarId="primary",
                timeMin=datetime.now(timezone.utc).isoformat(),
                maxResults=limit,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = response.get("items", [])
            if not events:
                return "There are no upcoming calendar events."
            lines = []
            for event in events:
                start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", "unknown time")
                lines.append(f"{start}: {event.get('summary', '(untitled event)')}")
            return "\n".join(lines)
        except Exception:
            return "I couldn't access Google Calendar. Check the Google connection and Calendar API setup."

    def create_draft(self, recipient: str, subject: str, body: str) -> str:
        message = self._email_message(recipient, subject, body)
        if isinstance(message, str):
            return message
        try:
            gmail = self._service_provider("gmail", "v1", (GMAIL_COMPOSE,))
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
            gmail.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
            return "Email draft created. It has not been sent."
        except Exception:
            return "I couldn't create the Gmail draft. Check the Google connection and Gmail API setup."

    def send_email(self, recipient: str, subject: str, body: str) -> str:
        message = self._email_message(recipient, subject, body)
        if isinstance(message, str):
            return message
        try:
            gmail = self._service_provider("gmail", "v1", (GMAIL_SEND,))
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
            gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
            return "Email sent."
        except Exception:
            return "I couldn't send the email. Check the Google connection and Gmail API setup."

    def email_preflight(self, recipient: str, subject: str, body: str) -> str | None:
        message = self._email_message(recipient, subject, body)
        return message if isinstance(message, str) else None

    def email_confirmation(self, action: str, recipient: str, subject: str, body: str) -> str:
        return f"{action} to: {recipient}\nSubject: {subject}\n\nMessage:\n{body}"

    @staticmethod
    def _email_message(recipient: str, subject: str, body: str) -> EmailMessage | str:
        recipient = recipient.strip()
        subject = subject.strip()
        if not _EMAIL.fullmatch(recipient) or len(recipient) > 254:
            return "I need one valid recipient email address. Nothing was sent."
        if not subject or len(subject) > 250 or "\r" in subject or "\n" in subject:
            return "I need a subject of 1 to 250 characters without line breaks. Nothing was sent."
        if len(body) > 10_000:
            return "Email text is too long. Keep it under 10,000 characters. Nothing was sent."
        message = EmailMessage()
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        return message

\n