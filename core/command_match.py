"""Conservative fuzzy matching for supported command prefixes only."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

KNOWN_COMMAND_PHRASES = (
    "confirm delete task",
    "complete task",
    "update task",
    "delete task",
    "count tasks",
    "list tasks",
    "add task",
    "create folder",
    "make a new folder",
    "search the web",
    "search web",
    "open",
    "search workspace",
    "search files",
    "schedule call",
    "list scheduled calls",
    "cancel scheduled call",
    "start project",
    "call",
)
_TOKEN = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)*")


@dataclass(frozen=True)
class CommandMatch:
    text: str
    ambiguous: bool = False
    fuzzy: bool = False


def match_known_command(
    text: str,
    phrases: tuple[str, ...] = KNOWN_COMMAND_PHRASES,
    minimum_similarity: float = 0.82,
    ambiguity_margin: float = 0.08,
) -> CommandMatch:
    """Correct only a known initial command phrase, preserving its entire tail."""
    tokens = list(_TOKEN.finditer(text))
    normalized_tokens = [match.group().lower() for match in tokens]
    ordered_phrases = sorted(phrases, key=lambda phrase: len(phrase.split()), reverse=True)

    for phrase in ordered_phrases:
        expected = phrase.split()
        if normalized_tokens[: len(expected)] == expected:
            return CommandMatch(text)

    candidates: list[tuple[float, str, int]] = []
    for phrase in phrases:
        expected = phrase.split()
        if len(normalized_tokens) < len(expected):
            continue
        observed = " ".join(normalized_tokens[: len(expected)])
        similarity = SequenceMatcher(None, observed, phrase).ratio()
        if similarity >= minimum_similarity:
            candidates.append((similarity, phrase, len(expected)))

    if not candidates:
        return CommandMatch(text)
    candidates.sort(reverse=True)
    if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < ambiguity_margin:
        return CommandMatch(text, ambiguous=True)

    _score, phrase, phrase_length = candidates[0]
    tail = text[tokens[phrase_length - 1].end() :]
    return CommandMatch(phrase + tail, fuzzy=True)
