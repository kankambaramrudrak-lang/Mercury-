"""Bounded, read-only text extraction for common workspace documents."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree

MAX_DOCUMENT_BYTES = 1_000_000
MAX_ARCHIVE_EXPANDED_BYTES = 16_000_000
MAX_EXTRACTED_CHARS = 1_000_000
_WORD_XML = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_SHEET_XML = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def extract_document_text(path: Path, content: bytes | None = None) -> str | None:
    """Return text from supported document formats; return None if unsupported or unreadable."""
    try:
        data = path.read_bytes() if content is None else content
    except OSError:
        return None
    if len(data) > MAX_DOCUMENT_BYTES:
        return None
    suffix = path.suffix.casefold()
    try:
        if suffix == ".pdf":
            return _extract_pdf(data)
        if suffix in {".docx", ".pptx", ".xlsx"}:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if len(archive.infolist()) > 200 or sum(item.file_size for item in archive.infolist()) > MAX_ARCHIVE_EXPANDED_BYTES:
                    return None
                if suffix == ".docx":
                    return _extract_word(archive)
                if suffix == ".pptx":
                    return _extract_powerpoint(archive)
                return _extract_spreadsheet(archive)
    except Exception:
        return None
    return None


def _read_xml(archive: zipfile.ZipFile, name: str) -> ElementTree.Element | None:
    try:
        data = archive.read(name)
    except (KeyError, OSError, zipfile.BadZipFile):
        return None
    if len(data) > MAX_ARCHIVE_EXPANDED_BYTES:
        return None
    return ElementTree.fromstring(data)


def _extract_word(archive: zipfile.ZipFile) -> str | None:
    root = _read_xml(archive, "word/document.xml")
    if root is None:
        return None
    paragraphs = []
    for paragraph in root.iter(f"{{{_WORD_XML}}}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{{{_WORD_XML}}}t"))
        if text.strip():
            paragraphs.append(text)
    return _bounded("\n".join(paragraphs))


def _extract_powerpoint(archive: zipfile.ZipFile) -> str | None:
    slides = sorted(
        (name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")),
        key=lambda name: int(name.rsplit("slide", 1)[1].split(".", 1)[0])
        if name.rsplit("slide", 1)[1].split(".", 1)[0].isdigit()
        else 0,
    )
    chunks = []
    for name in slides:
        root = _read_xml(archive, name)
        if root is not None:
            chunks.extend(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
    return _bounded("\n".join(chunks))


def _extract_spreadsheet(archive: zipfile.ZipFile) -> str | None:
    shared_values: list[str] = []
    shared = _read_xml(archive, "xl/sharedStrings.xml")
    if shared is not None:
        for item in shared:
            shared_values.append("".join(node.text or "" for node in item.iter(f"{{{_SHEET_XML}}}t")))

    sheet_names = sorted(
        (name for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")),
        key=lambda name: int(name.rsplit("sheet", 1)[1].split(".", 1)[0])
        if name.rsplit("sheet", 1)[1].split(".", 1)[0].isdigit()
        else 0,
    )
    rows: list[str] = []
    for sheet_name in sheet_names:
        root = _read_xml(archive, sheet_name)
        if root is None:
            continue
        for row in root.iter(f"{{{_SHEET_XML}}}row"):
            values = []
            for cell in row.findall(f"{{{_SHEET_XML}}}c"):
                value = cell.find(f"{{{_SHEET_XML}}}v")
                inline = cell.find(f"{{{_SHEET_XML}}}is")
                if cell.get("t") == "s" and value is not None:
                    try:
                        values.append(shared_values[int(value.text or "")])
                    except (ValueError, IndexError):
                        continue
                elif inline is not None:
                    values.append("".join(node.text or "" for node in inline.iter(f"{{{_SHEET_XML}}}t")))
                elif value is not None:
                    values.append(value.text or "")
            if values:
                rows.append(" | ".join(values))
    return _bounded("\n".join(rows))


def _extract_pdf(data: bytes) -> str | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        pages = []
        for page in reader.pages[:100]:
            text = page.extract_text() or ""
            pages.append(text)
            if sum(map(len, pages)) >= MAX_EXTRACTED_CHARS:
                break
        return _bounded("\n".join(pages))
    except Exception:
        return None


def _bounded(text: str) -> str:
    return text[:MAX_EXTRACTED_CHARS]
