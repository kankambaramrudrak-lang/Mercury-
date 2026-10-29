"""Private explicit contact allowlist used by outbound account integrations."""

from __future__ import annotations

import json
import re
from pathlib import Path

_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")


class ContactBook:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._contacts: dict[str, tuple[str, str, bool, bool]] = {}
        if not self.path.exists():
            return
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(values, dict):
            return
        for name, details in values.items():
            if not isinstance(details, dict):
                continue
            phone_number = details.get("phone")
            if (
                isinstance(name, str)
                and name.strip()
                and isinstance(phone_number, str)
                and _E164.fullmatch(phone_number.strip())
            ):
                self._contacts[name.strip().casefold()] = (
                    name.strip(),
                    phone_number.strip(),
                    details.get("whatsapp_opt_in") is True,
                    details.get("call_opt_in") is True,
                )

    def resolve(self, name_or_number: str) -> tuple[str, str] | None:
        value = name_or_number.strip()
        if _E164.fullmatch(value):
            match = next((entry for entry in self._contacts.values() if entry[1] == value), None)
            return match[:2] if match else None
        entry = self._contacts.get(value.casefold())
        return entry[:2] if entry else None

    def is_allowed(self, name_or_number: str, channel: str) -> bool:
        entry = self.resolve(name_or_number)
        if entry is None:
            return False
        contact = self._contacts.get(entry[0].casefold())
        if contact is None:
            return False
        if channel == "whatsapp":
            return contact[2]
        if channel == "call":
            return contact[3]
        return False

    def names(self) -> tuple[str, ...]:
        return tuple(contact[0] for contact in self._contacts.values())
