"""
app/knowledge/parsers/unified.py
================================
Unified document parser coordinating file ingestion across all supported formats.
Computes SHA-256 content hashes for document deduplication.
"""

import hashlib
import logging
from functools import lru_cache
from pathlib import Path

from app.knowledge.parsers.base import BaseDocumentParser, DocumentSection
from app.knowledge.parsers.docx_parser import DocxParser
from app.knowledge.parsers.pdf_parser import PDFParser
from app.knowledge.parsers.spreadsheet_parser import SpreadsheetParser
from app.knowledge.parsers.text_parser import TextParser

logger = logging.getLogger("sovereign.knowledge.unified_parser")


def compute_file_sha256(file_path: Path) -> str:
    """Computes SHA-256 cryptographic digest of a file for deduplication."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class UnifiedDocumentParser:
    """Dispatches document extraction to format-specific layout-aware parsers."""

    def __init__(self) -> None:
        self.pdf_parser = PDFParser()
        self.docx_parser = DocxParser()
        self.spreadsheet_parser = SpreadsheetParser()
        self.text_parser = TextParser()

    def parse(self, file_path: Path) -> tuple[str, list[DocumentSection]]:
        """Parses a document file.

        Returns:
            (sha256_hash, list_of_sections)
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_hash = compute_file_sha256(file_path)
        ext = file_path.suffix.lower()

        parser: BaseDocumentParser
        if ext == ".pdf":
            parser = self.pdf_parser
        elif ext in {".docx", ".doc"}:
            parser = self.docx_parser
        elif ext in {".csv", ".xlsx"}:
            parser = self.spreadsheet_parser
        else:
            parser = self.text_parser

        sections = parser.extract_sections(file_path)
        logger.info(
            "Parsed '%s' (%s): extracted %d layout sections (hash: %s...)",
            file_path.name,
            ext,
            len(sections),
            file_hash[:8],
        )
        return file_hash, sections


@lru_cache(maxsize=1)
def get_unified_parser() -> UnifiedDocumentParser:
    """Returns singleton UnifiedDocumentParser."""
    return UnifiedDocumentParser()
