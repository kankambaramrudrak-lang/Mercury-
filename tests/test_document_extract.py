import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from tools.document_extract import extract_document_text
from tools.workspace import WorkspaceSearch


class DocumentSearchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def _make_archive(self, path: Path, members: dict[str, str]) -> None:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in members.items():
                archive.writestr(name, content)

    def test_search_extracts_word_and_spreadsheet_text(self):
        self._make_archive(
            self.root / "notes.docx",
            {"word/document.xml": '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Project Mercury deadline Tuesday</w:t></w:r></w:p></w:body></w:document>'},
        )
        self._make_archive(
            self.root / "plan.xlsx",
            {
                "xl/sharedStrings.xml": '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Project</t></si><si><t>Mercury</t></si><si><t>deadline</t></si><si><t>Tuesday</t></si></sst>',
                "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c></row></sheetData></worksheet>',
            },
        )

        result = WorkspaceSearch(self.root).search("Mercury deadline")

        self.assertIn("notes.docx", result)
        self.assertIn("plan.xlsx", result)
        self.assertIn("Tuesday", result)

    def test_pdf_extraction_uses_bounded_text_api(self):
        class FakePage:
            def extract_text(self):
                return "Mercury project notes"

        class FakeReader:
            def __init__(self, _stream, strict):
                self.strict = strict
                self.pages = [FakePage()]

        fake_module = ModuleType("pypdf")
        fake_module.PdfReader = FakeReader
        with patch.dict("sys.modules", {"pypdf": fake_module}):
            text = extract_document_text(self.root / "notes.pdf", b"%PDF-fake")

        self.assertEqual(text, "Mercury project notes")

    def test_oversized_and_invalid_archives_are_skipped(self):
        invalid = self.root / "broken.docx"
        invalid.write_bytes(b"not a zip archive")
        huge_members = {"word/document.xml": "x" * (17_000_000)}
        oversized = io.BytesIO()
        with zipfile.ZipFile(oversized, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("word/document.xml", huge_members["word/document.xml"])
        self.assertIsNone(extract_document_text(invalid))
        self.assertIsNone(extract_document_text(self.root / "large.docx", oversized.getvalue()))

    def test_scanned_or_unavailable_pdf_extraction_returns_none(self):
        with patch.dict("sys.modules", {"pypdf": None}):
            result = extract_document_text(self.root / "scan.pdf", b"%PDF-fake")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
