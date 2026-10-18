"""
app/knowledge/ocr/pipeline.py
=============================
Composite OCR pipeline dispatching between primary engine (Tesseract)
and local open-weight vision models (e.g. Qwen 2.5/3.5 VL).
"""

import logging
from functools import lru_cache
from pathlib import Path

from PIL import Image

from app.knowledge.ocr.base import BaseOCREngine, OCRResult
from app.knowledge.ocr.tesseract_engine import TesseractOCREngine
from app.knowledge.ocr.vision_engine import VisionModelOCREngine

logger = logging.getLogger("sovereign.knowledge.ocr.pipeline")


class OCRPipeline:
    """Manages text extraction from images and scanned document pages with automatic engine fallback."""

    def __init__(
        self,
        primary_engine: BaseOCREngine | None = None,
        secondary_engine: BaseOCREngine | None = None,
    ) -> None:
        self.primary_engine = primary_engine or TesseractOCREngine()
        self.secondary_engine = secondary_engine or VisionModelOCREngine()

    def process_image(self, image: Image.Image | Path) -> OCRResult:
        """Processes an image using available OCR engines in priority order."""
        # 1. Try primary engine (Tesseract)
        if self.primary_engine.is_available():
            res = self.primary_engine.extract_text(image)
            if res.text.strip():
                logger.info("OCR extracted %d characters via primary engine (%s)", len(res.text), res.engine)
                return res

        # 2. Try secondary engine (Local Vision Model)
        if self.secondary_engine.is_available():
            logger.info("Primary OCR unavailable or empty; falling back to local vision engine (%s)", getattr(self.secondary_engine, "model_tag", "vision"))
            res = self.secondary_engine.extract_text(image)
            if res.text.strip():
                logger.info("OCR extracted %d characters via secondary vision engine (%s)", len(res.text), res.engine)
                return res

        # 3. Neither engine succeeded
        return OCRResult(
            text="",
            confidence=0.0,
            engine="ocr_unavailable",
        )

    def extract_text(self, image: Image.Image | Path) -> str:
        """Convenience method returning plain text string."""
        res = self.process_image(image)
        return res.text


@lru_cache(maxsize=1)
def get_ocr_pipeline() -> OCRPipeline:
    """Returns singleton OCRPipeline."""
    return OCRPipeline()
