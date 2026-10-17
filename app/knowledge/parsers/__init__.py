"""
app/knowledge/parsers/__init__.py
=================================
Layout-aware document parsers for PDF, Word, spreadsheets, and text.
"""

from app.knowledge.parsers.base import BaseDocumentParser, DocumentSection
from app.knowledge.parsers.unified import UnifiedDocumentParser, get_unified_parser

__all__ = [
    "BaseDocumentParser",
    "DocumentSection",
    "UnifiedDocumentParser",
    "get_unified_parser",
]
