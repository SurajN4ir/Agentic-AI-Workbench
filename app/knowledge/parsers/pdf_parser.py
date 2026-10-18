"""
app/knowledge/parsers/pdf_parser.py
===================================
Digital and OCR-augmented PDF parser using pypdfium2.
Extracts native text page-by-page and detects scanned pages.
"""

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pypdfium2
from PIL import Image

from app.knowledge.parsers.base import BaseDocumentParser, DocumentSection

logger = logging.getLogger("sovereign.knowledge.pdf_parser")


class PDFParser(BaseDocumentParser):
    """Layout-aware PDF document parser using pypdfium2."""

    def __init__(self, ocr_fallback_fn: Callable[[Image.Image], str] | None = None) -> None:
        if ocr_fallback_fn is not None:
            self.ocr_fallback_fn: Callable[[Image.Image], str] | None = ocr_fallback_fn
        else:
            from app.knowledge.ocr.pipeline import get_ocr_pipeline
            self.ocr_fallback_fn = get_ocr_pipeline().extract_text

    def extract_sections(self, file_path: Path) -> list[DocumentSection]:
        sections: list[DocumentSection] = []

        try:
            pdf = pypdfium2.PdfDocument(str(file_path))
        except Exception as e:
            logger.error("Failed to open PDF %s: %s", file_path, e)
            return sections

        for page_idx, page in enumerate(pdf):
            page_num = page_idx + 1
            text_page = page.get_textpage()
            raw_text = text_page.get_text_range().strip()

            # If page has substantial text, extract digital blocks
            if len(raw_text) >= 20:
                blocks = [b.strip() for b in re.split(r"\n\s*\n|\n", raw_text) if b.strip()]
                for b in blocks:
                    sec_type = "paragraph"
                    if "|" in b or "\t" in b:
                        sec_type = "table"
                    elif len(b) < 80 and not b.endswith((".", ":", ";")):
                        sec_type = "heading"

                    sections.append(
                        DocumentSection(
                            text=b,
                            section_type=sec_type,
                            page_number=page_num,
                            metadata={"source_page": page_num},
                        )
                    )
            elif self.ocr_fallback_fn is not None:
                # Scanned or image-only page: render to image and run OCR
                logger.info("Page %d of %s has minimal digital text; invoking OCR fallback", page_num, file_path.name)
                try:
                    pil_image: Any = page.render(scale=2.0).to_pil()
                    ocr_text = self.ocr_fallback_fn(pil_image).strip()
                    if ocr_text:
                        sections.append(
                            DocumentSection(
                                text=ocr_text,
                                section_type="scanned_page",
                                page_number=page_num,
                                metadata={"source_page": page_num, "ocr_applied": True},
                            )
                        )
                except Exception as ocr_err:
                    logger.warning("OCR failed on page %d: %s", page_num, ocr_err)
            elif raw_text:
                # Minimal text without OCR fallback
                sections.append(
                    DocumentSection(
                        text=raw_text,
                        section_type="paragraph",
                        page_number=page_num,
                        metadata={"source_page": page_num},
                    )
                )

        return sections
