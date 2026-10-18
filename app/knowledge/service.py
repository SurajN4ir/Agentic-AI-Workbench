"""
app/knowledge/service.py
========================
RAG Knowledge Base & pgvector vector retrieval service.
Coordinates layout-aware parsing, cryptographic deduplication,
batch embedding generation, and cosine similarity search.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.chunking import chunk_sections
from app.knowledge.models import DocumentChunk, KnowledgeDocument
from app.knowledge.parsers.unified import get_unified_parser
from app.models.base import BaseModelProvider
from app.models.registry import get_default_provider, get_model_for_role

logger = logging.getLogger("sovereign.knowledge.service")


def _lexical_tokens(text: str) -> list[str]:
    """Tokenizes text into words, alphanumeric equipment codes, and numbers."""
    return re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?", text.lower())


def _bm25_score(query_tokens: list[str], chunk_tokens: list[str], avg_doc_len: float, k1: float = 1.5, b: float = 0.75) -> float:
    """Computes BM25 term frequency score with equipment tag weighting."""
    if not chunk_tokens or not query_tokens:
        return 0.0
    doc_len = len(chunk_tokens)
    score = 0.0
    chunk_counts: dict[str, int] = {}
    for t in chunk_tokens:
        chunk_counts[t] = chunk_counts.get(t, 0) + 1

    for qt in query_tokens:
        count = chunk_counts.get(qt, 0)
        if count > 0:
            tag_weight = 2.0 if ("-" in qt or any(c.isdigit() for c in qt)) else 1.0
            tf_comp = (count * (k1 + 1)) / (count + k1 * (1 - b + b * (doc_len / max(avg_doc_len, 1.0))))
            score += tf_comp * tag_weight
    return score


@dataclass
class SearchResult:
    """Individual retrieved chunk with similarity score and citation metadata."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    content: str
    similarity: float
    section_type: str
    page_number: int | None
    metadata: dict[str, Any]

    def citation_header(self, index: int = 1) -> str:
        page_str = f" | Page {self.page_number}" if self.page_number else ""
        return f"[Source {index}: {self.filename}{page_str} | {self.section_type.upper()}] (Similarity: {self.similarity:.2f})"


class KnowledgeService:
    """Manages document ingestion, deduplication, embedding, and vector search."""

    def __init__(self, provider: BaseModelProvider | None = None) -> None:
        self.provider = provider or get_default_provider()
        self.embedding_model = get_model_for_role("embedding", default="all-minilm:l6-v2")

    async def ingest_file(
        self,
        db: AsyncSession,
        file_path: Path,
        filename: str,
        user_id: uuid.UUID | None = None,
        collection_id: str = "default",
    ) -> KnowledgeDocument:
        """Parses, deduplicates, chunks, embeds, and stores a document in the vector database."""
        # 1. Parse document sections and compute SHA-256
        parser = get_unified_parser()
        file_hash, sections = parser.parse(file_path)

        # 2. Check for existing document with same hash in this collection (Deduplication)
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.file_hash == file_hash,
            KnowledgeDocument.collection_id == collection_id,
        )
        existing = (await db.execute(stmt)).scalars().first()
        if existing is not None:
            logger.info(
                "Document '%s' already ingested (hash: %s...); returning existing record.", filename, file_hash[:8]
            )
            return existing

        # 3. Layout-aware chunking
        draft_chunks = chunk_sections(sections)
        if not draft_chunks:
            # Fallback if file was empty or unparseable
            draft_chunks = chunk_sections(
                [parser.text_parser.extract_sections(file_path)[0]] if file_path.stat().st_size > 0 else []
            )

        # 4. Generate batch embeddings
        texts_to_embed = [c.content for c in draft_chunks]
        if texts_to_embed:
            embed_res = await self.provider.embed(self.embedding_model, texts_to_embed)
            embeddings = embed_res.embeddings
        else:
            embeddings = []

        file_size = file_path.stat().st_size if file_path.exists() else 0
        ext = file_path.suffix.lower()

        # 5. Persist Document Record
        doc = KnowledgeDocument(
            id=uuid.uuid4(),
            collection_id=collection_id,
            filename=filename,
            file_type=ext,
            file_size_bytes=file_size,
            file_hash=file_hash,
            total_chunks=len(draft_chunks),
            user_id=user_id,
        )
        db.add(doc)
        await db.flush()

        # 6. Persist Document Chunks with Vectors
        dim = len(embeddings[0]) if embeddings else 384
        for idx, draft in enumerate(draft_chunks):
            vec = embeddings[idx] if idx < len(embeddings) else [0.0] * dim
            chunk = DocumentChunk(
                id=uuid.uuid4(),
                document_id=doc.id,
                chunk_index=draft.chunk_index,
                content=draft.content,
                section_type=draft.section_type,
                page_number=draft.page_number,
                metadata_json=draft.metadata,
                embedding=vec,
            )
            db.add(chunk)

        await db.commit()
        await db.refresh(doc)
        logger.info(
            "Ingested '%s': %d chunks saved with %d-dim embeddings.",
            filename,
            len(draft_chunks),
            len(embeddings[0]) if embeddings else 0,
        )
        return doc

    async def search(
        self,
        db: AsyncSession,
        query: str,
        top_k: int = 5,
        collection_id: str | None = None,
        min_similarity: float = 0.35,
    ) -> list[SearchResult]:
        """Performs hybrid dense vector and sparse BM25 search with Reciprocal Rank Fusion."""
        clean_query = query.strip()
        if not clean_query:
            return []

        # Generate embedding for search query
        embed_res = await self.provider.embed(self.embedding_model, [clean_query])
        if not embed_res.embeddings:
            return []

        query_vec = np.array(embed_res.embeddings[0], dtype=np.float32)
        query_norm: float = float(np.linalg.norm(query_vec))
        if query_norm == 0.0:
            query_norm = 1.0

        # Query chunks with joined document
        stmt = select(DocumentChunk, KnowledgeDocument).join(
            KnowledgeDocument,
            DocumentChunk.document_id == KnowledgeDocument.id,
        )
        if collection_id:
            stmt = stmt.where(KnowledgeDocument.collection_id == collection_id)

        rows = (await db.execute(stmt)).all()
        if not rows:
            return []

        # 1. Compute dense similarities and tokenize chunks for BM25
        chunk_dense_scores: list[tuple[float, Any, Any]] = []
        doc_tokens_list: list[list[str]] = []
        total_len = 0

        for chunk, doc in rows:
            chunk_vec = np.array(chunk.embedding, dtype=np.float32)
            chunk_norm = float(np.linalg.norm(chunk_vec))
            sim = 0.0
            if chunk_norm > 0.0:
                sim = float(np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm))
            chunk_dense_scores.append((sim, chunk, doc))
            ct = _lexical_tokens(chunk.content)
            doc_tokens_list.append(ct)
            total_len += len(ct)

        avg_doc_len = total_len / max(len(rows), 1)
        query_tokens = _lexical_tokens(clean_query)

        # 2. Dense ranking
        dense_ranked = sorted(enumerate(chunk_dense_scores), key=lambda x: x[1][0], reverse=True)
        dense_ranks = {orig_idx: rank for rank, (orig_idx, _) in enumerate(dense_ranked)}

        # 3. Sparse lexical BM25 ranking
        sparse_scores = [
            _bm25_score(query_tokens, doc_tokens_list[i], avg_doc_len)
            for i in range(len(rows))
        ]
        sparse_ranked = sorted(enumerate(sparse_scores), key=lambda x: x[1], reverse=True)
        sparse_ranks = {orig_idx: rank for rank, (orig_idx, _) in enumerate(sparse_ranked)}

        # 4. Reciprocal Rank Fusion (RRF) & Calibration
        scored_results: list[SearchResult] = []
        rrf_k = 60
        for orig_idx, (dense_sim, chunk, doc) in enumerate(chunk_dense_scores):
            r_dense = dense_ranks[orig_idx]
            r_sparse = sparse_ranks[orig_idx]
            s_sparse = sparse_scores[orig_idx]

            # RRF combined score
            rrf_score = (0.6 / (rrf_k + r_dense)) + (0.4 / (rrf_k + r_sparse))

            # Calibrated blended similarity preserving cosine scale for downstream consumers
            blended_sim = 0.5 * max(dense_sim, 0.0) + 0.3 * min(s_sparse / 5.0, 1.0) + 0.2 * min(rrf_score * 50.0, 1.0)
            if dense_sim >= min_similarity or (s_sparse >= 1.5 and blended_sim >= min_similarity):
                scored_results.append(
                    SearchResult(
                        chunk_id=chunk.id,
                        document_id=doc.id,
                        filename=doc.filename,
                        content=chunk.content,
                        similarity=round(blended_sim, 4),
                        section_type=chunk.section_type,
                        page_number=chunk.page_number,
                        metadata=chunk.metadata_json,
                    )
                )

        scored_results.sort(key=lambda x: x.similarity, reverse=True)
        return scored_results[:top_k]

    def format_context_for_prompt(self, results: list[SearchResult]) -> str:
        """Formats retrieved chunks into a cited Markdown context block for model prompts."""
        if not results:
            return "No relevant documents found in knowledge base."

        blocks = []
        for idx, r in enumerate(results, start=1):
            blocks.append(f"{r.citation_header(idx)}\n{r.content}")

        return "\n\n---\n\n".join(blocks)

    async def list_documents(
        self,
        db: AsyncSession,
        collection_id: str | None = None,
    ) -> list[KnowledgeDocument]:
        stmt = select(KnowledgeDocument)
        if collection_id:
            stmt = stmt.where(KnowledgeDocument.collection_id == collection_id)
        stmt = stmt.order_by(KnowledgeDocument.created_at.desc())
        return list((await db.execute(stmt)).scalars().all())

    async def delete_document(self, db: AsyncSession, doc_id: uuid.UUID) -> bool:
        stmt = delete(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
        res = await db.execute(stmt)
        await db.commit()
        return (res.rowcount or 0) > 0


_knowledge_service_instance: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    global _knowledge_service_instance
    if _knowledge_service_instance is None:
        _knowledge_service_instance = KnowledgeService()
    return _knowledge_service_instance
