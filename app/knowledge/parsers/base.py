"""
app/knowledge/parsers/base.py
=============================
Abstract base interface for document parsers.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class DocumentSection(BaseModel):
    """Represents a coherent structural section extracted from a document."""

    text: str = Field(..., description="Text content of the extracted section")
    section_type: str = Field(
        default="paragraph",
        description="Type of section: 'paragraph', 'table', 'heading', 'code', 'page'",
    )
    page_number: int | None = Field(default=None, description="Source page number if applicable (1-indexed)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional structural metadata")


class BaseDocumentParser(ABC):
    """Abstract parser interface for extracting sections from files."""

    @abstractmethod
    def extract_sections(self, file_path: Path) -> list[DocumentSection]:
        """Extracts structured, layout-aware sections from the given document file."""
        ...
