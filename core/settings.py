"""Load Hercules' small, local TOML configuration."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.toml"


@dataclass(frozen=True)
class Settings:
    workspace_folder: Path
    app_whitelist: tuple[str, ...]
    microphone_device: str | int
    speech_model_size: str


def load_settings(path: str | Path = DEFAULT_SETTINGS_PATH) -> Settings:
    """Load settings from TOML and reject values with unexpected shapes."""
    settings_path = Path(path)
    with settings_path.open("rb") as settings_file:
        values = tomllib.load(settings_file)

    workspace = values.get("workspace_folder", ".")
    whitelist = values.get("app_whitelist", [])
    microphone = values.get("microphone_device", "default")
    model_size = values.get("speech_model_size", "small")

    if not isinstance(workspace, str):
        raise ValueError("workspace_folder must be a string")
    if not isinstance(whitelist, list) or any(not isinstance(item, str) for item in whitelist):
        raise ValueError("app_whitelist must be a list of strings")
    if not isinstance(microphone, (str, int)) or isinstance(microphone, bool):
        raise ValueError("microphone_device must be a device name, index, or 'default'")
    if not isinstance(model_size, str) or not model_size.strip():
        raise ValueError("speech_model_size must be a non-empty string")

    return Settings(
        workspace_folder=Path(workspace),
        app_whitelist=tuple(whitelist),
        microphone_device=microphone,
        speech_model_size=model_size,
    )
