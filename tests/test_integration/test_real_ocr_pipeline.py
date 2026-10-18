"""
tests/test_integration/test_real_ocr_pipeline.py
================================================
Real-model integration tests for the Multimodal OCR Pipeline.
Verifies optical character recognition on actual synthetic industrial assets
(e.g. workspace/test_gauge.png) using the locally served open-weight vision model.
"""

from pathlib import Path

import pytest
from app.knowledge.ocr.pipeline import OCRPipeline
from app.knowledge.ocr.vision_engine import VisionModelOCREngine
from app.knowledge.parsers.image_parser import ImageParser

from tests.test_integration.helpers import is_ollama_reachable

pytestmark = pytest.mark.integration

GAUGE_IMAGE_PATH = Path("workspace/test_gauge.png")


@pytest.fixture(autouse=True)
def check_environment():
    if not is_ollama_reachable():
        pytest.skip("Local Ollama daemon is not reachable on 127.0.0.1:11434")
    if not GAUGE_IMAGE_PATH.exists():
        pytest.skip("workspace/test_gauge.png fixture does not exist")


def test_vision_engine_availability():
    engine = VisionModelOCREngine()
    assert engine.is_available() is True, "Vision model should be discovered and available in Ollama"


def test_vision_engine_ocr_transcription():
    engine = VisionModelOCREngine()
    result = engine.extract_text(GAUGE_IMAGE_PATH)

    assert result.confidence > 0.0
    assert "ollama_vision" in result.engine
    recognized_text = result.text.upper()

    assert "PRESSURE GAUGE" in recognized_text
    assert "PG-101" in recognized_text
    assert "150" in recognized_text


def test_ocr_pipeline_fallback_integration():
    pipeline = OCRPipeline()
    extracted = pipeline.extract_text(GAUGE_IMAGE_PATH).upper()

    assert "PRESSURE GAUGE" in extracted
    assert "PG-101" in extracted


def test_image_parser_extract_sections():
    parser = ImageParser()
    sections = parser.extract_sections(GAUGE_IMAGE_PATH)

    assert len(sections) > 0
    full_text = " ".join(s.text.upper() for s in sections)
    assert "PRESSURE GAUGE" in full_text
    assert "PG-101" in full_text
