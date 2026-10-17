"""
app/knowledge/parsers/docx_parser.py
====================================
Layout-aware Word (.docx) document parser using python-docx.
Extracts headings, paragraphs, and formats tables into clean Markdown representations.
"""

import logging
from pathlib import Path

from docx import Document

from app.knowledge.parsers.base import BaseDocumentParser, DocumentSection

logger = logging.getLogger("sovereign.knowledge.docx_parser")


class DocxParser(BaseDocumentParser):
    """Parses Microsoft Word (.docx) documents into structured sections."""

    def extract_sections(self, file_path: Path) -> list[DocumentSection]:
        sections: list[DocumentSection] = []

        try:
            doc = Document(str(file_path))
        except Exception as e:
            logger.error("Failed to read DOCX %s: %s", file_path, e)
            return sections

        # Extract paragraphs and headings
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            style_name = para.style.name.lower() if para.style else ""
            sec_type = "heading" if "heading" in style_name or "title" in style_name else "paragraph"

            sections.append(
                DocumentSection(
                    text=text,
                    section_type=sec_type,
                    metadata={"style": style_name},
                )
            )

        # Extract tables as formatted Markdown tables
        for table_idx, table in enumerate(doc.tables):
            rows: list[list[str]] = []
            for row in table.rows:
                row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                if any(row_cells):
                    rows.append(row_cells)

            if not rows:
                continue

            # Convert to Markdown table format
            col_count = len(rows[0])
            header = "| " + " | ".join(rows[0]) + " |"
            divider = "| " + " | ".join(["---"] * col_count) + " |"
            body = ["| " + " | ".join(row) + " |" for row in rows[1:]]

            table_md = "\n".join([header, divider] + body)
            sections.append(
                DocumentSection(
                    text=table_md,
                    section_type="table",
                    metadata={"table_index": table_idx + 1},
                )
            )

        return sections
