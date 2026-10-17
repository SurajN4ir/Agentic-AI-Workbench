"""
app/knowledge/parsers/text_parser.py
====================================
Parses plain text, Markdown, code, and structured text files.
"""

import logging
import re
from pathlib import Path

from app.knowledge.parsers.base import BaseDocumentParser, DocumentSection

logger = logging.getLogger("sovereign.knowledge.text_parser")


class TextParser(BaseDocumentParser):
    """Parses text, markdown, code, and configuration files into coherent blocks."""

    def extract_sections(self, file_path: Path) -> list[DocumentSection]:
        sections: list[DocumentSection] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception as e:
            logger.error("Failed to read text file %s: %s", file_path, e)
            return sections

        if not content:
            return sections

        ext = file_path.suffix.lower()
        sec_type = "code" if ext in {".py", ".ts", ".js", ".sql", ".sh", ".json", ".yaml", ".yml"} else "paragraph"

        # Split by double newlines or markdown headers
        raw_blocks = re.split(r"\n\s*\n", content)
        for block in raw_blocks:
            clean_block = block.strip()
            if not clean_block:
                continue

            current_type = sec_type
            if clean_block.startswith("#") and len(clean_block.splitlines()[0]) < 100:
                current_type = "heading"

            sections.append(
                DocumentSection(
                    text=clean_block,
                    section_type=current_type,
                    metadata={"extension": ext},
                )
            )

        return sections
