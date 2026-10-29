"""Load Mercury's small, local TOML configuration."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.toml"


@dataclass(frozen=True)
class Settings:
    workspace_folder: Path
    app_whitelist: tuple[str, ...]
    microphone_device: str | int
    speech_recognizer: str
    speech_model_size: str
    vosk_confidence_threshold: float
    faster_whisper_confidence_threshold: float
    local_ai_enabled: bool = False
    local_ai_model: str = "llama3.2:3b"
    local_ai_url: str = "http://localhost:11434"
    install_whitelist: tuple[str, ...] = ()
    google_enabled: bool = False
    google_credentials_file: Path = Path("secrets/google-oauth-client.json")
    contacts_file: Path = Path("data/contacts.json")
    whatsapp_enabled: bool = False
    whatsapp_graph_version: str = "v26.0"
    whatsapp_webhook_enabled: bool = False
    whatsapp_webhook_port: int = 8765
    twilio_enabled: bool = False


def load_settings(path: str | Path = DEFAULT_SETTINGS_PATH) -> Settings:
    """Load settings from TOML and reject values with unexpected shapes."""
    settings_path = Path(path)
    with settings_path.open("rb") as settings_file:
        values = tomllib.load(settings_file)

    workspace = values.get("workspace_folder", ".")
    whitelist = values.get("app_whitelist", [])
    microphone = values.get("microphone_device", "default")
    recognizer = values.get("speech_recognizer", "vosk")
    model_size = values.get("speech_model_size", "small")
    vosk_threshold = values.get("vosk_confidence_threshold", 0.65)
    whisper_threshold = values.get("faster_whisper_confidence_threshold", 0.45)
    local_ai_enabled = values.get("local_ai_enabled", False)
    local_ai_model = values.get("local_ai_model", "llama3.2:3b")
    local_ai_url = values.get("local_ai_url", "http://localhost:11434")
    install_whitelist = values.get("install_whitelist", [])
    google_enabled = values.get("google_enabled", False)
    google_credentials_file = values.get("google_credentials_file", "secrets/google-oauth-client.json")
    contacts_file = values.get("contacts_file", "data/contacts.json")
    whatsapp_enabled = values.get("whatsapp_enabled", False)
    whatsapp_graph_version = values.get("whatsapp_graph_version", "v26.0")
    whatsapp_webhook_enabled = values.get("whatsapp_webhook_enabled", False)
    whatsapp_webhook_port = values.get("whatsapp_webhook_port", 8765)
    twilio_enabled = values.get("twilio_enabled", False)

    if not isinstance(workspace, str):
        raise ValueError("workspace_folder must be a string")
    if not isinstance(whitelist, list) or any(not isinstance(item, str) for item in whitelist):
        raise ValueError("app_whitelist must be a list of 'name=target' strings")
    if any("=" not in item or not item.split("=", 1)[0].strip() or not item.split("=", 1)[1].strip() for item in whitelist):
        raise ValueError("Each app_whitelist entry must have the form 'name=target'")
    if not isinstance(install_whitelist, list) or any(
        not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", item)
        for item in install_whitelist
    ):
        raise ValueError("install_whitelist must be a list of valid winget package IDs")
    if len({item.casefold() for item in install_whitelist}) != len(install_whitelist):
        raise ValueError("install_whitelist package IDs must be unique")
    aliases = [item.split("=", 1)[0].strip().casefold() for item in whitelist]
    if len(aliases) != len(set(aliases)):
        raise ValueError("app_whitelist names must be unique")
    if not isinstance(microphone, (str, int)) or isinstance(microphone, bool):
        raise ValueError("microphone_device must be a device name, index, or 'default'")
    if not isinstance(recognizer, str) or recognizer not in {"vosk", "faster-whisper"}:
        raise ValueError("speech_recognizer must be 'vosk' or 'faster-whisper'")
    if not isinstance(model_size, str) or not model_size.strip():
        raise ValueError("speech_model_size must be a non-empty string")
    if not isinstance(local_ai_enabled, bool):
        raise ValueError("local_ai_enabled must be true or false")
    if not isinstance(google_enabled, bool):
        raise ValueError("google_enabled must be true or false")
    if not isinstance(google_credentials_file, str) or not google_credentials_file.strip():
        raise ValueError("google_credentials_file must be a non-empty path")
    if not isinstance(contacts_file, str) or not contacts_file.strip():
        raise ValueError("contacts_file must be a non-empty path")
    if not isinstance(whatsapp_enabled, bool) or not isinstance(twilio_enabled, bool) or not isinstance(whatsapp_webhook_enabled, bool):
        raise ValueError("WhatsApp and Twilio enable settings must be true or false")
    if whatsapp_webhook_enabled and not whatsapp_enabled:
        raise ValueError("whatsapp_webhook_enabled requires whatsapp_enabled")
    if not isinstance(whatsapp_graph_version, str) or not re.fullmatch(r"v[0-9]+\.[0-9]+", whatsapp_graph_version):
        raise ValueError("whatsapp_graph_version must look like v26.0")
    if type(whatsapp_webhook_port) is not int or not 1 <= whatsapp_webhook_port <= 65535:
        raise ValueError("whatsapp_webhook_port must be between 1 and 65535")
    if not isinstance(local_ai_model, str) or not local_ai_model.strip():
        raise ValueError("local_ai_model must be a non-empty string")
    parsed_ai_url = urlsplit(local_ai_url) if isinstance(local_ai_url, str) else None
    if (
        parsed_ai_url is None
        or parsed_ai_url.scheme != "http"
        or parsed_ai_url.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed_ai_url.path not in {"", "/"}
        or parsed_ai_url.query
        or parsed_ai_url.fragment
    ):
        raise ValueError("local_ai_url must be a local HTTP endpoint")
    for name, threshold in (
        ("vosk_confidence_threshold", vosk_threshold),
        ("faster_whisper_confidence_threshold", whisper_threshold),
    ):
        if isinstance(threshold, bool) or not isinstance(threshold, (float, int)) or not 0 <= threshold <= 1:
            raise ValueError(f"{name} must be a number from 0 to 1")

    workspace_path = Path(workspace)
    if not workspace_path.is_absolute():
        workspace_path = settings_path.resolve().parent / workspace_path
    google_credentials_path = Path(google_credentials_file)
    if not google_credentials_path.is_absolute():
        google_credentials_path = settings_path.resolve().parent / google_credentials_path
    contacts_path = Path(contacts_file)
    if not contacts_path.is_absolute():
        contacts_path = settings_path.resolve().parent / contacts_path

    return Settings(
        workspace_folder=workspace_path.resolve(),
        app_whitelist=tuple(whitelist),
        microphone_device=microphone,
        speech_recognizer=recognizer,
        speech_model_size=model_size,
        vosk_confidence_threshold=float(vosk_threshold),
        faster_whisper_confidence_threshold=float(whisper_threshold),
        local_ai_enabled=local_ai_enabled,
        local_ai_model=local_ai_model,
        local_ai_url=local_ai_url.rstrip("/"),
        install_whitelist=tuple(install_whitelist),
        google_enabled=google_enabled,
        google_credentials_file=google_credentials_path.resolve(),
        contacts_file=contacts_path.resolve(),
        whatsapp_enabled=whatsapp_enabled,
        whatsapp_graph_version=whatsapp_graph_version,
        whatsapp_webhook_enabled=whatsapp_webhook_enabled,
        whatsapp_webhook_port=whatsapp_webhook_port,
        twilio_enabled=twilio_enabled,
    )
