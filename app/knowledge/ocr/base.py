"""
app/knowledge/ocr/base.py
=========================
Abstract interfaces and data structures for pluggable OCR engines.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image
from pydantic import BaseModel, Field


class OCRResult(BaseModel):
    """Result of optical character recognition processing."""

    text: str = Field(default="", description="Extracted text content")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Average confidence score")
    engine: str = Field(default="unknown", description="Name of the OCR engine used")


class BaseOCREngine(ABC):
    """Abstract interface for pluggable OCR implementations."""

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if the required OCR binaries or services are installed and ready."""
        ...

    @abstractmethod
    def extract_text(self, image: Image.Image | Path) -> OCRResult:
        """Extracts text from an image or image file path."""
        ...
