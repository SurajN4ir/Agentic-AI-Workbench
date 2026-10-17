"""
tests/test_knowledge/test_ocr.py
================================
Unit tests for the pluggable OCR interface and pipeline.
"""

from unittest.mock import MagicMock

from app.knowledge.ocr.base import OCRResult
from app.knowledge.ocr.pipeline import OCRPipeline
from app.knowledge.ocr.tesseract_engine import TesseractOCREngine
from PIL import Image


class TestOCREngine:
    def test_tesseract_engine_availability_check(self) -> None:
        """Tesseract engine checks binary availability without throwing unhandled exceptions."""
        engine = TesseractOCREngine()
        available = engine.is_available()
        assert isinstance(available, bool)

    def test_tesseract_graceful_handling_when_unavailable(self) -> None:
        """When Tesseract is unavailable, extract_text returns empty result gracefully."""
        engine = TesseractOCREngine()
        engine._available = False

        img = Image.new("RGB", (100, 100), color="white")
        res = engine.extract_text(img)

        assert res.text == ""
        assert res.confidence == 0.0
        assert res.engine == "tesseract_unavailable"

    def test_pipeline_with_mock_engine(self) -> None:
        """OCRPipeline correctly delegates image processing to the configured engine."""
        mock_engine = MagicMock()
        mock_engine.extract_text.return_value = OCRResult(
            text="Recognized Text 123",
            confidence=0.95,
            engine="mock_engine",
        )

        pipeline = OCRPipeline(primary_engine=mock_engine)
        img = Image.new("RGB", (50, 50), color="white")

        res = pipeline.process_image(img)
        assert res.text == "Recognized Text 123"
        assert res.confidence == 0.95
        assert res.engine == "mock_engine"
        assert pipeline.extract_text(img) == "Recognized Text 123"
