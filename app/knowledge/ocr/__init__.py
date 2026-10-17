"""
app/knowledge/ocr/__init__.py
=============================
Pluggable OCR and layout extraction engine.
"""

from app.knowledge.ocr.base import BaseOCREngine, OCRResult
from app.knowledge.ocr.pipeline import OCRPipeline, get_ocr_pipeline

__all__ = [
    "BaseOCREngine",
    "OCRPipeline",
    "OCRResult",
    "get_ocr_pipeline",
]
