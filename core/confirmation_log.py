"""Configure a private, local log for button confirmation decisions."""

from __future__ import annotations

import logging
from pathlib import Path

CONFIRMATION_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "confirmation.log"


def configure_confirmation_log() -> None:
    """Write only formatted tool-name/approval records to the ignored log."""
    path = CONFIRMATION_LOG_PATH.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("hercules.confirmations")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in logger.handlers:
        if getattr(handler, "baseFilename", None) == str(path):
            return

    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)
