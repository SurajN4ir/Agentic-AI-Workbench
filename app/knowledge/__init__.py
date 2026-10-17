"""
app/knowledge/__init__.py
=========================
Knowledge ingestion, layout-aware parsing, pluggable OCR,
and pgvector RAG retrieval engine.
"""

from app.knowledge.models import DocumentChunk, KnowledgeDocument
from app.knowledge.service import KnowledgeService, get_knowledge_service

__all__ = [
    "DocumentChunk",
    "KnowledgeDocument",
    "KnowledgeService",
    "get_knowledge_service",
]
