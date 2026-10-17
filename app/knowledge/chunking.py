"""
app/knowledge/chunking.py
=========================
Layout-aware recursive document chunker for RAG ingestion.
Preserves table integrity, tracks section headings as breadcrumbs,
and maintains page numbers and structural metadata.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.knowledge.parsers.base import DocumentSection


class DocumentChunkDraft(BaseModel):
    """Draft chunk produced before embedding and database persistence."""

    chunk_index: int
    content: str
    section_type: str = "paragraph"
    page_number: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def chunk_sections(
    sections: list[DocumentSection],
    target_chunk_size: int = 600,
    chunk_overlap: int = 100,
) -> list[DocumentChunkDraft]:
    """Chunks structured document sections while preserving table and layout boundaries."""
    chunks: list[DocumentChunkDraft] = []
    chunk_idx = 0
    current_heading = ""

    for section in sections:
        text = section.text.strip()
        if not text:
            continue

        # If heading, update current heading context and record as anchor
        if section.section_type == "heading":
            current_heading = text
            # If the heading itself is short, we can also store it as context for following paragraphs
            chunks.append(
                DocumentChunkDraft(
                    chunk_index=chunk_idx,
                    content=text,
                    section_type="heading",
                    page_number=section.page_number,
                    metadata={**section.metadata, "heading_context": current_heading},
                )
            )
            chunk_idx += 1
            continue

        # For tables, keep intact unless extraordinarily large
        if section.section_type == "table":
            table_content = f"Context: {current_heading}\n{text}" if current_heading else text
            chunks.append(
                DocumentChunkDraft(
                    chunk_index=chunk_idx,
                    content=table_content,
                    section_type="table",
                    page_number=section.page_number,
                    metadata={**section.metadata, "heading_context": current_heading},
                )
            )
            chunk_idx += 1
            continue

        # For standard paragraphs / code / scanned pages
        prefix = f"[{current_heading}] " if current_heading and len(current_heading) < 60 else ""
        augmented_text = prefix + text

        if len(augmented_text) <= target_chunk_size:
            chunks.append(
                DocumentChunkDraft(
                    chunk_index=chunk_idx,
                    content=augmented_text,
                    section_type=section.section_type,
                    page_number=section.page_number,
                    metadata={**section.metadata, "heading_context": current_heading},
                )
            )
            chunk_idx += 1
        else:
            # Recursive split with overlap
            sub_chunks = _split_text_with_overlap(augmented_text, target_chunk_size, chunk_overlap)
            for sub in sub_chunks:
                chunks.append(
                    DocumentChunkDraft(
                        chunk_index=chunk_idx,
                        content=sub,
                        section_type=section.section_type,
                        page_number=section.page_number,
                        metadata={**section.metadata, "heading_context": current_heading},
                    )
                )
                chunk_idx += 1

    return chunks


def _split_text_with_overlap(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Splits a long string into overlapping pieces on sentence or word boundaries."""
    if len(text) <= chunk_size:
        return [text]

    result: list[str] = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]

        # Try to break on newline or period if possible
        if end < len(text):
            last_break = max(chunk.rfind("\n"), chunk.rfind(". "), chunk.rfind(" "))
            if last_break > chunk_size // 2:
                chunk = chunk[: last_break + 1]
                end = start + len(chunk)

        clean_chunk = chunk.strip()
        if clean_chunk:
            result.append(clean_chunk)

        if end >= len(text):
            break

        start = max(end - overlap, start + 1)

    return result
