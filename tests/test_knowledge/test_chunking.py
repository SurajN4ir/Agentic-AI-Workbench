"""
tests/test_knowledge/test_chunking.py
====================================
Tests for layout-aware recursive document chunking engine.
"""

from app.knowledge.chunking import chunk_sections
from app.knowledge.parsers.base import DocumentSection


class TestChunkingEngine:
    def test_preserves_table_integrity(self) -> None:
        """Markdown tables remain intact in single chunks to preserve structural data."""
        table_text = "| Param | Value |\n| --- | --- |\n| Temp | 150C |\n| Pressure | 2.5bar |"
        sections = [
            DocumentSection(text="Sensor Specs", section_type="heading"),
            DocumentSection(text=table_text, section_type="table"),
        ]

        chunks = chunk_sections(sections, target_chunk_size=100)
        table_chunks = [c for c in chunks if c.section_type == "table"]

        assert len(table_chunks) == 1
        assert "Sensor Specs" in table_chunks[0].content
        assert "| Temp | 150C |" in table_chunks[0].content

    def test_heading_breadcrumbs_applied_to_following_paragraphs(self) -> None:
        """Paragraphs inherit the current heading context as breadcrumbs."""
        sections = [
            DocumentSection(text="Security Protocols", section_type="heading"),
            DocumentSection(text="All ports must be bound to 127.0.0.1.", section_type="paragraph"),
            DocumentSection(text="Zero external network egress is allowed.", section_type="paragraph"),
        ]

        chunks = chunk_sections(sections, target_chunk_size=200)
        para_chunks = [c for c in chunks if c.section_type == "paragraph"]

        assert len(para_chunks) == 2
        assert "[Security Protocols]" in para_chunks[0].content
        assert "[Security Protocols]" in para_chunks[1].content

    def test_long_paragraph_recursive_splitting_with_overlap(self) -> None:
        """Long text blocks split on sentence/word boundaries with configured overlap."""
        long_text = "Word " * 150  # ~750 characters
        sections = [DocumentSection(text=long_text, section_type="paragraph")]

        chunks = chunk_sections(sections, target_chunk_size=200, chunk_overlap=40)
        assert len(chunks) >= 3

        # Consecutive chunks should have overlapping text
        chunk0_words = set(chunks[0].content.split()[-5:])
        chunk1_words = set(chunks[1].content.split()[:10])
        assert bool(chunk0_words.intersection(chunk1_words))
