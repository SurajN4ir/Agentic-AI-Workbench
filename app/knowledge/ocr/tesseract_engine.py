"""
app/knowledge/ocr/tesseract_engine.py
=====================================
Tesseract OCR engine implementation using pytesseract.
Gracefully handles environments where the native Tesseract binary is not installed.
"""

import logging
from pathlib import Path

import pytesseract
from PIL import Image

from app.knowledge.ocr.base import BaseOCREngine, OCRResult

logger = logging.getLogger("sovereign.knowledge.ocr.tesseract")


class TesseractOCREngine(BaseOCREngine):
    """Tesseract-based OCR extractor."""

    def __init__(self) -> None:
        self._available: bool | None = None

    def is_available(self) -> bool:
        if self._available is None:
            try:
                pytesseract.get_tesseract_version()
                self._available = True
            except Exception:
                self._available = False
        return self._available

    def extract_text(self, image: Image.Image | Path) -> OCRResult:
        if not self.is_available():
            logger.debug("Tesseract binary is not available on host system.")
            return OCRResult(text="", confidence=0.0, engine="tesseract_unavailable")

        try:
            pil_img = Image.open(image) if isinstance(image, Path) else image

            # Extract full text
            text = pytesseract.image_to_string(pil_img).strip()

            # Attempt confidence estimation via image_to_data
            conf = 0.85
            try:
                data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT)
                confs = [float(c) for c in data.get("conf", []) if float(c) > 0]
                if confs:
                    conf = min(max(sum(confs) / (len(confs) * 100.0), 0.0), 1.0)
            except Exception as conf_err:
                logger.debug("Tesseract conf calculation error: %s", conf_err)

            return OCRResult(
                text=text,
                confidence=round(conf, 2),
                engine="tesseract",
            )
        except Exception as e:
            logger.warning("Tesseract extraction error: %s", e)
            return OCRResult(text="", confidence=0.0, engine="tesseract_error")
