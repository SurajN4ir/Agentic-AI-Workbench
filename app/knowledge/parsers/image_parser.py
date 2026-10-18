"""
app/knowledge/parsers/image_parser.py
=====================================
Image and diagram parser for industrial document intelligence.
Extracts OCR text and image metadata from .png, .jpg, .jpeg, .tiff, .bmp, .webp files.
Integrates with the OCR pipeline (Tesseract / local vision models).
"""

import logging
from pathlib import Path

from PIL import Image

from app.knowledge.ocr.pipeline import get_ocr_pipeline
from app.knowledge.parsers.base import BaseDocumentParser, DocumentSection

logger = logging.getLogger("sovereign.knowledge.image_parser")


class ImageParser(BaseDocumentParser):
    """Layout-aware image parser supporting optical character recognition and visual metadata extraction."""

    def __init__(self) -> None:
        self.ocr_pipeline = get_ocr_pipeline()

    def extract_sections(self, file_path: Path) -> list[DocumentSection]:
        sections: list[DocumentSection] = []

        try:
            with Image.open(file_path) as img:
                width, height = img.size
                img_format = img.format or file_path.suffix.upper().lstrip(".")
                mode = img.mode

                meta = {
                    "source_file": file_path.name,
                    "width": width,
                    "height": height,
                    "format": img_format,
                    "mode": mode,
                }

                # Attempt OCR text extraction
                ocr_text = ""
                try:
                    ocr_res = self.ocr_pipeline.process_image(img)
                    ocr_text = ocr_res.text.strip()
                    meta["ocr_engine"] = ocr_res.engine
                    meta["ocr_confidence"] = ocr_res.confidence
                except Exception as ocr_err:
                    logger.warning("OCR extraction error on %s: %s", file_path.name, ocr_err)
                    meta["ocr_error"] = str(ocr_err)

                if ocr_text:
                    # Split extracted text into paragraphs if multi-line
                    paragraphs = [p.strip() for p in ocr_text.split("\n\n") if p.strip()]
                    for p in paragraphs:
                        sec_type = "image_table" if ("|" in p or "\t" in p) else "image_ocr"
                        sections.append(
                            DocumentSection(
                                text=p,
                                section_type=sec_type,
                                page_number=1,
                                metadata=meta,
                            )
                        )
                else:
                    # If image has no detectable text, record structural image metadata section
                    meta_summary = (
                        f"Visual Asset: {file_path.name} | Dimensions: {width}x{height} | "
                        f"Format: {img_format} | Color Mode: {mode}"
                    )
                    sections.append(
                        DocumentSection(
                            text=meta_summary,
                            section_type="image_metadata",
                            page_number=1,
                            metadata=meta,
                        )
                    )

        except Exception as exc:
            logger.error("Failed to parse image '%s': %s", file_path, exc)

        return sections
