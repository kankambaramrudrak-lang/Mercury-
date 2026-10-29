"""Read-only, bounded text search inside Mercury's configured workspace."""

from __future__ import annotations

import re
import os
from collections import Counter
from pathlib import Path

from tools.document_extract import extract_document_text

_TEXT_SUFFIXES = {
    ".c", ".cfg", ".cpp", ".cs", ".css", ".csv", ".go", ".html", ".ini",
    ".java", ".js", ".json", ".jsx", ".log", ".md", ".ps1", ".py", ".rst",
    ".rs", ".sh", ".sql", ".svg", ".toml", ".ts", ".tsx", ".txt", ".xml",
    ".yaml", ".yml",
}
_DOCUMENT_SUFFIXES = {".docx", ".pdf", ".pptx", ".xlsx"}
_SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__", "node_modules",
    "model", "data", ".cache", ".pytest_cache", ".mypy_cache",
}
_SECRET_NAMES = {".env", "credentials", "credentials.json", "secrets", "secrets.json", "id_rsa"}
_WORD = re.compile(r"[a-z0-9]{2,}")
_STOP_WORDS = {
    "about", "and", "are", "can", "does", "for", "from", "how", "in", "is", "it",
    "me", "my", "of", "on", "say", "the", "this", "to", "what", "where", "which",
    "with", "you", "your",
}
_EXPANSIONS = {
    "start": {"run", "runs", "launch", "open"},
    "starting": {"run", "runs", "launch", "open"},
    "run": {"start", "runs", "launch", "open"},
    "launch": {"run", "start", "open"},
    "voice": {"microphone", "audio"},
    "instructions": {"setup", "run", "steps"},
}
_EXPANSION_WEIGHT = 2
_DIRECT_WEIGHT = 3
_MAX_FILE_BYTES = 1_000_000
_MAX_FILES_SCANNED = 5000
_MAX_RESULTS = 5
_MAX_RESULT_CHARS = 4500


class WorkspaceSearch:
    """Search plain-text files without leaving the selected workspace."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()

    def search(self, query: str) -> str:
        words = tuple(dict.fromkeys(_WORD.findall(query.casefold())))
        weighted_terms: dict[str, int] = {}
        for word in words:
            if word in _STOP_WORDS:
                continue
            weighted_terms[word] = max(weighted_terms.get(word, 0), _DIRECT_WEIGHT)
            for expanded in _EXPANSIONS.get(word, ()):
                expansion_weight = 8 if word in {"start", "starting"} and expanded == "run" else _EXPANSION_WEIGHT
                weighted_terms[expanded] = max(weighted_terms.get(expanded, 0), expansion_weight)
        if not weighted_terms:
            return "Give me a few words to search for in your workspace."

        matches: list[tuple[int, str, list[tuple[int, str]]]] = []
        scanned = 0
        try:
            for current, directories, filenames in os.walk(self.workspace, followlinks=False):
                directories[:] = [
                    directory
                    for directory in directories
                    if directory.casefold() not in _SKIP_DIRS and not directory.startswith(".")
                ]
                directories.sort(key=str.casefold)
                filenames.sort(key=str.casefold)
                for filename in filenames:
                    if scanned >= _MAX_FILES_SCANNED:
                        break
                    path = Path(current) / filename
                    if not self._is_searchable(path):
                        continue
                    if "readme" in words and "readme" not in path.name.casefold():
                        continue
                    scanned += 1
                    try:
                        if path.stat().st_size > _MAX_FILE_BYTES:
                            continue
                        if path.suffix.casefold() in _TEXT_SUFFIXES:
                            content = path.read_text(encoding="utf-8")
                        else:
                            extracted = extract_document_text(path)
                            if extracted is None:
                                continue
                            content = extracted
                    except (OSError, UnicodeError):
                        continue
                    if "\x00" in content:
                        continue

                    lines = content.splitlines()
                    excerpts: list[tuple[int, str]] = []
                    filename_words = Counter(_WORD.findall(path.name.casefold()))
                    score = sum(filename_words[word] * 4 for word in words)
                    line_hits: list[tuple[int, int]] = []
                    for line_index, line in enumerate(lines):
                        line_words = Counter(_WORD.findall(line.casefold()))
                        line_score = sum(
                            line_words[term] * weight
                            for term, weight in weighted_terms.items()
                        )
                        if "start" in words and re.match(r"^\s*#{1,6}\s*run\b", line, re.IGNORECASE):
                            line_score += 30
                        if line_score:
                            score += line_score
                            line_hits.append((line_score, line_index))
                    selected_lines: set[int] = set()
                    for _line_score, line_index in sorted(line_hits, key=lambda hit: (-hit[0], hit[1])):
                        selected_lines.update(range(line_index, min(line_index + 4, len(lines))))
                        if len(selected_lines) >= 4:
                            break
                    excerpts = [
                        (line_index + 1, lines[line_index].strip()[:500])
                        for line_index in sorted(selected_lines)[:4]
                    ]
                    if excerpts:
                        relative = path.resolve().relative_to(self.workspace).as_posix()
                        matches.append((score, relative, excerpts))
                if scanned >= _MAX_FILES_SCANNED:
                    break
        except OSError:
            return "I couldn't read the configured workspace."

        if not matches:
            return "I couldn't find those words in the workspace's searchable text files."
        matches.sort(key=lambda item: (-item[0], item[1].casefold()))
        parts: list[str] = []
        size = 0
        for _score, relative, excerpts in matches[:_MAX_RESULTS]:
            section = "\n".join(f"{relative}:{number}: {line}" for number, line in excerpts)
            if size + len(section) > _MAX_RESULT_CHARS:
                section = section[: max(0, _MAX_RESULT_CHARS - size)]
            if section:
                parts.append(section)
                size += len(section)
            if size >= _MAX_RESULT_CHARS:
                break
        return "\n".join(parts)

    def _is_searchable(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
            relative = resolved.relative_to(self.workspace)
        except (ValueError, OSError, RuntimeError):
            return False
        if any(part.casefold() in _SKIP_DIRS for part in relative.parts[:-1]):
            return False
        if any(part.startswith(".") for part in relative.parts):
            return False
        filename = path.name.casefold()
        if (
            filename in _SECRET_NAMES
            or filename.startswith(".env.")
            or any(marker in filename for marker in ("secret", "credential", "token"))
        ):
            return False
        if path.suffix.casefold() in {".key", ".pem", ".p12", ".pfx"}:
            return False
        return path.suffix.casefold() in _TEXT_SUFFIXES | _DOCUMENT_SUFFIXES
