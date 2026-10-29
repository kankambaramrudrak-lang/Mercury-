"""Prompt for API credentials without echoing or writing them to project files."""

from __future__ import annotations

import re
from collections.abc import Callable

from core.communications import SecretStore


def setup_whatsapp(
    secret_store: SecretStore,
    input_fn: Callable[[str], str] = input,
    secret_input: Callable[[str], str] | None = None,
) -> str:
    if secret_input is None:
        from getpass import getpass

        secret_input = getpass
    phone_number_id = input_fn("Meta WhatsApp Business phone number ID: ").strip()
    access_token = secret_input("Meta WhatsApp access token (hidden): ").strip()
    app_secret = secret_input("Meta app secret for inbound webhooks (hidden, optional): ").strip()
    verify_token = secret_input("Webhook verification token (hidden, optional): ").strip()
    if not re.fullmatch(r"[0-9]{5,32}", phone_number_id) or not access_token:
        return "The phone number ID or access token is invalid. Nothing was stored."
    if bool(app_secret) != bool(verify_token):
        return "Provide both webhook secrets or leave both blank. Nothing was stored."
    secret_store.set("phone_number_id", phone_number_id)
    secret_store.set("access_token", access_token)
    if app_secret and verify_token:
        secret_store.set("app_secret", app_secret)
        secret_store.set("verify_token", verify_token)
    return "WhatsApp credentials stored in Windows Credential Manager."


def setup_twilio(
    secret_store: SecretStore,
    input_fn: Callable[[str], str] = input,
    secret_input: Callable[[str], str] | None = None,
) -> str:
    if secret_input is None:
        from getpass import getpass

        secret_input = getpass
    account_sid = input_fn("Twilio Account SID: ").strip()
    auth_token = secret_input("Twilio Auth Token (hidden): ").strip()
    from_number = input_fn("Twilio caller number in E.164 format: ").strip()
    if (
        not re.fullmatch(r"AC[0-9a-fA-F]{32}", account_sid)
        or not auth_token
        or not re.fullmatch(r"\+[1-9][0-9]{7,14}", from_number)
    ):
        return "The Twilio SID, token, or caller number is invalid. Nothing was stored."
    secret_store.set("account_sid", account_sid)
    secret_store.set("auth_token", auth_token)
    secret_store.set("from_number", from_number)
    return "Twilio credentials stored in Windows Credential Manager."
