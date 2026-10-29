"""Read-only checks for Mercury's local runtime and selected features."""

from __future__ import annotations

import importlib.util
import json
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.settings import Settings, load_settings


@dataclass(frozen=True)
class Diagnostic:
    name: str
    status: str
    detail: str


def diagnose(
    settings_path: str | Path | None = None,
    *,
    module_exists: Callable[[str], bool] | None = None,
    urlopen: Callable[..., object] | None = None,
    find_command: Callable[[str], str | None] | None = None,
    settings_loader: Callable[..., Settings] = load_settings,
) -> list[Diagnostic]:
    """Inspect local config and dependencies without recording audio or reading secrets."""
    module_exists = module_exists or (lambda name: importlib.util.find_spec(name) is not None)
    urlopen = urllib.request.urlopen if urlopen is None else urlopen
    find_command = shutil.which if find_command is None else find_command
    try:
        settings = settings_loader() if settings_path is None else settings_loader(settings_path)
    except (OSError, ValueError) as error:
        return [Diagnostic("Settings", "FAIL", f"Settings could not be loaded: {type(error).__name__}.")]

    results = [Diagnostic("Settings", "OK", "Configuration is valid.")]
    workspace_ok = settings.workspace_folder.is_dir()
    results.append(
        Diagnostic(
            "Workspace",
            "OK" if workspace_ok else "FAIL",
            "Configured search/project folder exists." if workspace_ok else "Configured folder is missing.",
        )
    )

    required_modules = [
        ("Microphone audio package", "sounddevice"),
        ("Audio array package", "numpy"),
        ("Keyboard listener", "pynput"),
        ("Windows speech output package", "pyttsx3"),
        ("Selected speech recognizer", "vosk" if settings.speech_recognizer == "vosk" else "faster_whisper"),
    ]
    for label, module in required_modules:
        present = _module_present(module_exists, module)
        results.append(Diagnostic(label, "OK" if present else "FAIL", "Installed." if present else "Missing from this Python environment."))

    if settings.speech_recognizer == "vosk":
        model_path = Path(__file__).resolve().parent.parent / "model" / "vosk-model-small-en-us-0.15"
        present = model_path.is_dir() and (model_path / "conf" / "model.conf").is_file()
        results.append(
            Diagnostic(
                "Vosk speech model",
                "OK" if present else "FAIL",
                "Local model files found." if present else "Model folder is missing or incomplete.",
            )
        )
    else:
        results.append(Diagnostic("faster-whisper model", "WARN", "Model cache is not checked; first use may download it."))

    pypdf_present = _module_present(module_exists, "pypdf")
    results.append(
        Diagnostic(
            "PDF text extraction",
            "OK" if pypdf_present else "WARN",
            "pypdf is available." if pypdf_present else "pypdf is missing; PDF search will be skipped until dependencies are updated.",
        )
    )

    if settings.local_ai_enabled:
        try:
            with urlopen(f"{settings.local_ai_url}/api/tags", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = payload.get("models", []) if isinstance(payload, dict) else []
            names = {
                item.get("name")
                for item in models
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }
            installed = settings.local_ai_model in names or f"{settings.local_ai_model}:latest" in names
            results.append(
                Diagnostic(
                    "Local Ollama model",
                    "OK" if installed else "FAIL",
                    f"Configured local model '{settings.local_ai_model}' is available."
                    if installed
                    else f"Ollama is running, but '{settings.local_ai_model}' is not in its local model list.",
                )
            )
        except (OSError, TimeoutError, ValueError, urllib.error.URLError):
            results.append(Diagnostic("Local Ollama model", "FAIL", "Local Ollama did not respond. No external endpoint was contacted."))
    else:
        results.append(Diagnostic("Local Ollama model", "WARN", "Local conversational AI is disabled in settings."))

    codex_found = find_command("codex") is not None
    results.append(Diagnostic("Codex CLI", "OK" if codex_found else "WARN", "Found for guided project coding." if codex_found else "Not found; project specifications can still be created."))
    results.append(Diagnostic("Microphone and speaker hardware", "WARN", "Not tested. This check does not record audio or play sound."))
    results.append(Diagnostic("Account integrations", "WARN", _account_status(settings)))
    return results


def print_diagnostics(results: list[Diagnostic], output: Callable[[str], None] = print) -> int:
    """Print a concise local status report without secrets or speech content."""
    for result in results:
        output(f"[{result.status}] {result.name}: {result.detail}")
    failures = sum(result.status == "FAIL" for result in results)
    output(f"Health check finished: {failures} issue(s) need attention.")
    return 1 if failures else 0


def _module_present(module_exists: Callable[[str], bool], module: str) -> bool:
    try:
        return bool(module_exists(module))
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _account_status(settings: Settings) -> str:
    active = []
    if settings.google_enabled:
        active.append("Google APIs enabled; account credentials were not inspected")
    if settings.whatsapp_enabled:
        active.append("WhatsApp enabled; account credentials were not inspected")
    if settings.twilio_enabled:
        active.append("Twilio enabled; account credentials were not inspected")
    return "; ".join(active) if active else "Google, WhatsApp, and Twilio are disabled; no credentials were inspected."
