"""
app/knowledge/service.py
========================
RAG Knowledge Base & pgvector vector retrieval service.
Coordinates layout-aware parsing, cryptographic deduplication,
batch embedding generation, Reciprocal Rank Fusion (RRF),
collection lifecycle, chunk inspection, and document re-indexing.
"""

import logging
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import sqlalchemy as sa
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.chunking import chunk_sections
from app.knowledge.models import DocumentChunk, KnowledgeCollection, KnowledgeDocument
from app.knowledge.parsers.unified import get_unified_parser
from app.models.base import BaseModelProvider
from app.models.registry import get_default_provider, get_model_for_role

logger = logging.getLogger("sovereign.knowledge.service")

# Global in-memory tracking for background re-indexing tasks
_active_indexing_jobs: set[uuid.UUID] = set()
_indexing_progress: dict[uuid.UUID, dict[str, Any]] = {}


def _lexical_tokens(text: str) -> list[str]:
    """Tokenizes text into words, alphanumeric equipment codes, and numbers."""
    return re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?", text.lower())


def _bm25_score(
    query_tokens: list[str],
    chunk_tokens: list[str],
    avg_doc_len: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
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
    dense_similarity: float = 0.0
    dense_rank: int = 1
    sparse_score: float = 0.0
    sparse_rank: int = 1
    rrf_score: float = 0.0

    def citation_header(self, index: int = 1) -> str:
        page_str = f" | Page {self.page_number}" if self.page_number else ""
        return f"[Source {index}: {self.filename}{page_str} | {self.section_type.upper()}] (Similarity: {self.similarity:.2f})"


class KnowledgeService:
    """Manages document ingestion, deduplication, embedding, vector search, and collection lifecycle."""

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

        # 5. Persist Document Record and preserve source file
        doc_id = uuid.uuid4()
        saved_source_path: str | None = None
        try:
            store_dir = Path("uploads/knowledge_store")
            store_dir.mkdir(parents=True, exist_ok=True)
            dest_path = store_dir / f"{doc_id}_{filename}"
            if file_path.exists():
                shutil.copy2(file_path, dest_path)
                saved_source_path = str(dest_path)
        except Exception as copy_err:
            logger.warning("Could not persist source file: %s", copy_err)

        doc = KnowledgeDocument(
            id=doc_id,
            collection_id=collection_id,
            filename=filename,
            file_type=ext,
            file_size_bytes=file_size,
            file_hash=file_hash,
            total_chunks=len(draft_chunks),
            status="indexed",
            error_message=None,
            source_path=saved_source_path,
            user_id=user_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
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
                created_at=datetime.now(UTC),
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
                        dense_similarity=round(max(dense_sim, 0.0), 4),
                        dense_rank=r_dense + 1,
                        sparse_score=round(s_sparse, 4),
                        sparse_rank=r_sparse + 1,
                        rrf_score=round(rrf_score, 6),
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
        """Lists ingested knowledge documents, optionally filtered by collection."""
        stmt = select(KnowledgeDocument)
        if collection_id:
            stmt = stmt.where(KnowledgeDocument.collection_id == collection_id)
        stmt = stmt.order_by(KnowledgeDocument.created_at.desc())
        return list((await db.execute(stmt)).scalars().all())

    async def get_document(self, db: AsyncSession, doc_id: uuid.UUID) -> KnowledgeDocument | None:
        """Retrieves a single document by its UUID."""
        stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
        return (await db.execute(stmt)).scalars().first()

    async def delete_document(self, db: AsyncSession, doc_id: uuid.UUID) -> bool:
        """Deletes an ingested document, its vector chunks, and its cached source file."""
        doc = await self.get_document(db, doc_id)
        if not doc:
            return False

        # Attempt to clean up stored source file
        if doc.source_path:
            try:
                p = Path(doc.source_path)
                if p.exists():
                    p.unlink()
            except Exception as e:
                logger.debug("Could not remove stored file %s: %s", doc.source_path, e)

        stmt = delete(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
        res = await db.execute(stmt)
        await db.commit()
        return (res.rowcount or 0) > 0

    # ─── Collection Management ──────────────────────────────────────────────

    async def list_collections(self, db: AsyncSession) -> list[dict[str, Any]]:
        """Lists all collections with aggregated statistics (doc count, chunks, bytes)."""
        stmt_colls = select(KnowledgeCollection).order_by(KnowledgeCollection.name.asc())
        explicit_colls = {c.name: c for c in (await db.execute(stmt_colls)).scalars().all()}

        stmt_stats = select(
            KnowledgeDocument.collection_id,
            func.count(KnowledgeDocument.id).label("doc_count"),
            func.sum(KnowledgeDocument.total_chunks).label("chunk_count"),
            func.sum(KnowledgeDocument.file_size_bytes).label("total_bytes"),
            func.min(KnowledgeDocument.created_at).label("first_created"),
            func.max(KnowledgeDocument.updated_at).label("last_updated"),
        ).group_by(KnowledgeDocument.collection_id)
        stats_rows = (await db.execute(stmt_stats)).all()

        stats_map: dict[str, dict[str, Any]] = {}
        for r in stats_rows:
            stats_map[r.collection_id] = {
                "document_count": int(r.doc_count or 0),
                "chunk_count": int(r.chunk_count or 0),
                "total_bytes": int(r.total_bytes or 0),
                "created_at": r.first_created or datetime.now(UTC),
                "updated_at": r.last_updated or datetime.now(UTC),
            }

        all_names = set(explicit_colls.keys()) | set(stats_map.keys()) | {"default"}

        result = []
        for name in sorted(all_names):
            coll_obj = explicit_colls.get(name)
            stat = stats_map.get(
                name,
                {
                    "document_count": 0,
                    "chunk_count": 0,
                    "total_bytes": 0,
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                },
            )
            result.append(
                {
                    "id": coll_obj.id if coll_obj else None,
                    "name": name,
                    "description": coll_obj.description
                    if coll_obj
                    else ("Default industrial knowledge collection" if name == "default" else ""),
                    "document_count": stat["document_count"],
                    "chunk_count": stat["chunk_count"],
                    "total_bytes": stat["total_bytes"],
                    "user_id": coll_obj.user_id if coll_obj else None,
                    "created_at": coll_obj.created_at if coll_obj else stat["created_at"],
                    "updated_at": coll_obj.updated_at if coll_obj else stat["updated_at"],
                }
            )
        return result

    async def create_collection(
        self,
        db: AsyncSession,
        name: str,
        description: str = "",
        user_id: uuid.UUID | None = None,
    ) -> KnowledgeCollection:
        """Creates a new unique knowledge collection slug."""
        name_clean = name.strip()
        if not re.match(r"^[a-zA-Z0-9_\-]+$", name_clean):
            raise ValueError("Collection name must contain only letters, numbers, hyphens, and underscores.")
        if len(name_clean) < 1 or len(name_clean) > 64:
            raise ValueError("Collection name must be between 1 and 64 characters.")

        stmt = select(KnowledgeCollection).where(func.lower(KnowledgeCollection.name) == name_clean.lower())
        existing = (await db.execute(stmt)).scalars().first()
        if existing or name_clean.lower() == "default":
            raise ValueError(f"Collection '{name_clean}' already exists.")

        coll = KnowledgeCollection(
            id=uuid.uuid4(),
            name=name_clean,
            description=description.strip(),
            user_id=user_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(coll)
        await db.commit()
        await db.refresh(coll)
        return coll

    async def update_collection(
        self,
        db: AsyncSession,
        name: str,
        new_name: str | None = None,
        description: str | None = None,
    ) -> KnowledgeCollection:
        """Updates collection metadata or renames collection, updating document associations."""
        name_clean = name.strip()
        if name_clean == "default" and new_name and new_name.strip() != "default":
            raise ValueError("The default collection cannot be renamed.")

        stmt = select(KnowledgeCollection).where(KnowledgeCollection.name == name_clean)
        coll = (await db.execute(stmt)).scalars().first()
        if not coll:
            coll = KnowledgeCollection(
                id=uuid.uuid4(),
                name=name_clean,
                description="",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(coll)
            await db.flush()

        if new_name and new_name.strip() != name_clean:
            target_name = new_name.strip()
            if not re.match(r"^[a-zA-Z0-9_\-]+$", target_name):
                raise ValueError("Collection name must contain only letters, numbers, hyphens, and underscores.")
            chk_stmt = select(KnowledgeCollection).where(KnowledgeCollection.name == target_name)
            if (await db.execute(chk_stmt)).scalars().first():
                raise ValueError(f"Collection '{target_name}' already exists.")

            stmt_update = (
                sa.update(KnowledgeDocument)
                .where(KnowledgeDocument.collection_id == name_clean)
                .values(collection_id=target_name, updated_at=datetime.now(UTC))
            )
            await db.execute(stmt_update)
            coll.name = target_name

        if description is not None:
            coll.description = description.strip()

        coll.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(coll)
        return coll

    async def delete_collection(
        self,
        db: AsyncSession,
        name: str,
        reassign_to: str | None = None,
        delete_documents: bool = False,
    ) -> None:
        """Safely deletes a collection with either document reassignment or explicit cascading delete."""
        name_clean = name.strip()
        if name_clean == "default":
            raise ValueError("The default collection cannot be deleted.")

        stmt_docs = select(KnowledgeDocument).where(KnowledgeDocument.collection_id == name_clean)
        docs = list((await db.execute(stmt_docs)).scalars().all())

        if docs:
            if reassign_to:
                target = reassign_to.strip()
                if target == name_clean:
                    raise ValueError("Cannot reassign documents to the collection being deleted.")
                stmt_update = (
                    sa.update(KnowledgeDocument)
                    .where(KnowledgeDocument.collection_id == name_clean)
                    .values(collection_id=target, updated_at=datetime.now(UTC))
                )
                await db.execute(stmt_update)
            elif delete_documents:
                for d in docs:
                    await self.delete_document(db, d.id)
            else:
                raise ValueError(
                    f"Collection '{name_clean}' contains {len(docs)} documents. "
                    "Specify reassign_to or set delete_documents=true."
                )

        stmt_del = delete(KnowledgeCollection).where(KnowledgeCollection.name == name_clean)
        await db.execute(stmt_del)
        await db.commit()

    async def reassign_document(
        self,
        db: AsyncSession,
        doc_id: uuid.UUID,
        target_collection_id: str,
    ) -> KnowledgeDocument:
        """Reassigns a document to a different collection."""
        stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
        doc = (await db.execute(stmt)).scalars().first()
        if not doc:
            raise ValueError(f"Document with ID '{doc_id}' not found.")

        target = target_collection_id.strip()
        if not re.match(r"^[a-zA-Z0-9_\-]+$", target):
            raise ValueError("Target collection name must contain only letters, numbers, hyphens, and underscores.")

        doc.collection_id = target
        doc.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(doc)
        return doc

    # ─── Chunk Inspection ───────────────────────────────────────────────────

    async def list_document_chunks(
        self,
        db: AsyncSession,
        doc_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        section_type: str | None = None,
        search: str | None = None,
    ) -> tuple[list[DocumentChunk], int]:
        """Returns paginated chunks for a given document with optional filtering."""
        stmt = select(DocumentChunk).where(DocumentChunk.document_id == doc_id)

        if section_type:
            stmt = stmt.where(DocumentChunk.section_type == section_type.lower().strip())
        if search:
            search_clean = search.strip()
            stmt = stmt.where(DocumentChunk.content.ilike(f"%{search_clean}%"))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(DocumentChunk.chunk_index.asc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        chunks = list((await db.execute(stmt)).scalars().all())

        return chunks, total_count

    async def get_chunk_detail(
        self,
        db: AsyncSession,
        chunk_id: uuid.UUID,
    ) -> tuple[DocumentChunk, KnowledgeDocument] | None:
        """Retrieves a single chunk along with its parent document."""
        stmt = (
            select(DocumentChunk, KnowledgeDocument)
            .join(KnowledgeDocument, DocumentChunk.document_id == KnowledgeDocument.id)
            .where(DocumentChunk.id == chunk_id)
        )
        row = (await db.execute(stmt)).first()
        if not row:
            return None
        return row[0], row[1]

    # ─── Re-indexing Workflow ───────────────────────────────────────────────

    def get_reindex_status(self, doc_id: uuid.UUID) -> dict[str, Any]:
        """Queries the live status of an ongoing or completed re-index job."""
        if doc_id in _active_indexing_jobs:
            return _indexing_progress.get(
                doc_id,
                {
                    "status": "in_progress",
                    "progress_pct": 50,
                    "message": "Re-indexing in progress",
                },
            )
        return _indexing_progress.get(
            doc_id,
            {
                "status": "idle",
                "progress_pct": 100,
                "message": "No active re-index job",
            },
        )

    async def trigger_reindex(
        self,
        db: AsyncSession,
        doc_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Registers a document re-indexing job. Raises ValueError if already active."""
        doc = await self.get_document(db, doc_id)
        if not doc:
            raise ValueError(f"Document with ID '{doc_id}' not found.")

        if doc_id in _active_indexing_jobs:
            raise ValueError(f"Re-indexing already in progress for document '{doc.filename}'.")

        _active_indexing_jobs.add(doc_id)
        _indexing_progress[doc_id] = {
            "status": "in_progress",
            "progress_pct": 10,
            "message": f"Parsing and chunking '{doc.filename}'...",
        }
        return {"status": "started", "document_id": str(doc_id), "filename": doc.filename}

    async def execute_reindex(
        self,
        db: AsyncSession,
        doc_id: uuid.UUID,
    ) -> None:
        """Executes layout-aware chunking, batch embeddings, and chunk persistence."""
        try:
            doc = await self.get_document(db, doc_id)
            if not doc:
                return

            doc.status = "indexing"
            await db.commit()

            _indexing_progress[doc_id] = {
                "status": "in_progress",
                "progress_pct": 30,
                "message": "Re-extracting content...",
            }

            has_source = doc.source_path and Path(doc.source_path).exists()
            if has_source and doc.source_path:
                source_p = Path(doc.source_path)
                parser = get_unified_parser()
                file_hash, sections = parser.parse(source_p)
                draft_chunks = chunk_sections(sections)
                if not draft_chunks:
                    draft_chunks = chunk_sections(
                        [parser.text_parser.extract_sections(source_p)[0]]
                        if source_p.stat().st_size > 0
                        else []
                    )
                texts_to_embed = [c.content for c in draft_chunks]
                _indexing_progress[doc_id] = {
                    "status": "in_progress",
                    "progress_pct": 60,
                    "message": f"Generating embeddings for {len(draft_chunks)} chunks...",
                }
                embed_res = await self.provider.embed(self.embedding_model, texts_to_embed)
                embeddings = embed_res.embeddings

                # Remove old chunks
                await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))

                # Insert new chunks
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
                        created_at=datetime.now(UTC),
                    )
                    db.add(chunk)

                doc.total_chunks = len(draft_chunks)
                doc.file_hash = file_hash
            else:
                # Re-embed existing chunks
                stmt_chk = (
                    select(DocumentChunk)
                    .where(DocumentChunk.document_id == doc_id)
                    .order_by(DocumentChunk.chunk_index.asc())
                )
                existing_chunks = list((await db.execute(stmt_chk)).scalars().all())
                if existing_chunks:
                    texts = [c.content for c in existing_chunks]
                    _indexing_progress[doc_id] = {
                        "status": "in_progress",
                        "progress_pct": 60,
                        "message": f"Re-embedding {len(existing_chunks)} chunks...",
                    }
                    embed_res = await self.provider.embed(self.embedding_model, texts)
                    embeddings = embed_res.embeddings
                    for idx, c in enumerate(existing_chunks):
                        if idx < len(embeddings):
                            c.embedding = embeddings[idx]

            doc.status = "indexed"
            doc.error_message = None
            doc.updated_at = datetime.now(UTC)
            await db.commit()
            _indexing_progress[doc_id] = {
                "status": "completed",
                "progress_pct": 100,
                "message": f"Successfully re-indexed '{doc.filename}'.",
            }
        except Exception as e:
            logger.exception("Failed to re-index document %s: %s", doc_id, e)
            try:
                doc = await self.get_document(db, doc_id)
                if doc:
                    doc.status = "failed"
                    doc.error_message = str(e)
                    await db.commit()
            except Exception as status_err:
                logger.debug("Failed to update document failure status: %s", status_err)
            _indexing_progress[doc_id] = {
                "status": "failed",
                "progress_pct": 0,
                "error": str(e),
                "message": f"Re-indexing failed: {e}",
            }
        finally:
            _active_indexing_jobs.discard(doc_id)


_knowledge_service_instance: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    global _knowledge_service_instance
    if _knowledge_service_instance is None:
        _knowledge_service_instance = KnowledgeService()
    return _knowledge_service_instance
