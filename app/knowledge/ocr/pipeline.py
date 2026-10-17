"""
app/knowledge/ocr/pipeline.py
=============================
Composite OCR pipeline dispatching between primary engine (Tesseract)
and optional local vision models.
"""

import logging
from functools import lru_cache
from pathlib import Path

from PIL import Image

from app.knowledge.ocr.base import BaseOCREngine, OCRResult
from app.knowledge.ocr.tesseract_engine import TesseractOCREngine

logger = logging.getLogger("sovereign.knowledge.ocr.pipeline")


class OCRPipeline:
    """Manages text extraction from images and scanned document pages."""

    def __init__(self, primary_engine: BaseOCREngine | None = None) -> None:
        self.primary_engine = primary_engine or TesseractOCREngine()

    def process_image(self, image: Image.Image | Path) -> OCRResult:
        """Processes an image and returns recognized text."""
        return self.primary_engine.extract_text(image)

    def extract_text(self, image: Image.Image | Path) -> str:
        """Convenience method returning plain text string."""
        res = self.process_image(image)
        return res.text


@lru_cache(maxsize=1)
def get_ocr_pipeline() -> OCRPipeline:
    """Returns singleton OCRPipeline."""
    return OCRPipeline()
