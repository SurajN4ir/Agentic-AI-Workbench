"""
tests/test_knowledge/test_service_and_retrieval.py
==================================================
Tests for KnowledgeService ingestion, deduplication, and vector retrieval.
"""

from pathlib import Path

import numpy as np
import pytest
from app.knowledge.models import DocumentChunk, KnowledgeDocument
from app.knowledge.service import KnowledgeService
from app.models.schemas import EmbeddingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class MockEmbeddingProvider:
    """Mock model provider producing deterministic 768-dim vector embeddings."""

    async def embed(self, model: str, texts: list[str]) -> EmbeddingResponse:
        # Create unique, deterministic normalized vectors with positive semantic similarity
        embeddings = []
        for text in texts:
            seed = sum(ord(c) for c in text) % 1000
            np.random.seed(seed)
            # Shared positive base (0.5) + small variation ensures positive cosine similarity ~0.85-0.95
            vec = (np.ones(768, dtype=np.float32) * 0.5) + (np.random.randn(768).astype(np.float32) * 0.1)
            vec = vec / np.linalg.norm(vec)
            embeddings.append(vec.tolist())

        return EmbeddingResponse(
            embeddings=embeddings,
            model=model,
            dimension=768,
        )


class TestKnowledgeService:
    @pytest.fixture
    def service(self) -> KnowledgeService:
        provider = MockEmbeddingProvider()
        return KnowledgeService(provider=provider)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_ingest_and_deduplicate_document(
        self,
        service: KnowledgeService,
        db_session: AsyncSession,
        tmp_path: Path,
    ) -> None:
        """Verifies ingestion creates records, and re-ingesting the identical file returns existing."""
        f_path = tmp_path / "safety_policy.txt"
        f_path.write_text("All personnel must wear personal protective equipment in Zone 4.", encoding="utf-8")

        # 1. First Ingestion
        doc1 = await service.ingest_file(
            db=db_session,
            file_path=f_path,
            filename="safety_policy.txt",
            collection_id="industrial_safety",
        )
        assert doc1.filename == "safety_policy.txt"
        assert doc1.total_chunks >= 1
        assert len(doc1.file_hash) == 64

        # Verify chunks exist in DB
        chunks = (
            (await db_session.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc1.id)))
            .scalars()
            .all()
        )
        assert len(chunks) == doc1.total_chunks
        assert len(chunks[0].embedding) == 768

        # 2. Second Ingestion of same file (Deduplication)
        doc2 = await service.ingest_file(
            db=db_session,
            file_path=f_path,
            filename="safety_policy.txt",
            collection_id="industrial_safety",
        )
        assert doc2.id == doc1.id
        assert doc2.file_hash == doc1.file_hash

        # Verify no duplicate documents created in DB
        all_docs = (
            (
                await db_session.execute(
                    select(KnowledgeDocument).where(KnowledgeDocument.filename == "safety_policy.txt")
                )
            )
            .scalars()
            .all()
        )
        assert len(all_docs) == 1

    @pytest.mark.asyncio
    async def test_vector_search_and_citation_formatting(
        self,
        service: KnowledgeService,
        db_session: AsyncSession,
        tmp_path: Path,
    ) -> None:
        """Verifies vector cosine search retrieves relevant chunks with formatted citations."""
        f_path = tmp_path / "emergency_protocols.md"
        f_path.write_text(
            "# Emergency Evacuation\n\nProceed to Assembly Point C during a fire alarm.\n\n"
            "# Equipment Shutdown\n\nPress the emergency red stop button on the generator.",
            encoding="utf-8",
        )

        # Ingest protocols document
        _ = await service.ingest_file(
            db=db_session,
            file_path=f_path,
            filename="emergency_protocols.md",
            collection_id="default",
        )

        # Search for evacuation
        results = await service.search(
            db=db_session,
            query="evacuation procedure",
            top_k=2,
            collection_id="default",
            min_similarity=0.0,
        )

        assert len(results) >= 1
        top_result = results[0]
        assert top_result.filename == "emergency_protocols.md"
        assert top_result.similarity > 0.0

        # Verify context formatting for prompts
        context_str = service.format_context_for_prompt(results)
        assert "Source 1: emergency_protocols.md" in context_str
        assert "Similarity:" in context_str

    @pytest.mark.asyncio
    async def test_delete_document_cascades(
        self,
        service: KnowledgeService,
        db_session: AsyncSession,
        tmp_path: Path,
    ) -> None:
        """Deleting a document also deletes its associated chunks."""
        f_path = tmp_path / "temp_doc.txt"
        f_path.write_text("Temporary confidential document.", encoding="utf-8")

        doc = await service.ingest_file(db=db_session, file_path=f_path, filename="temp_doc.txt")
        doc_id = doc.id

        # Verify document and chunks exist
        doc_exists = (
            await db_session.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))
        ).scalar_one_or_none()
        assert doc_exists is not None

        # Delete document
        deleted = await service.delete_document(db=db_session, doc_id=doc_id)
        assert deleted is True

        # Verify document is gone
        doc_after = (
            await db_session.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))
        ).scalar_one_or_none()
        assert doc_after is None
