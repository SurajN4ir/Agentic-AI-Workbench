"""
app/knowledge/router.py
=======================
FastAPI endpoints for knowledge base management, chunk inspection,
collection lifecycle, re-indexing, and RAG retrieval.
Protected endpoints requiring authentication.
"""

import asyncio
import logging
import math
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal, get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.knowledge.service import KnowledgeService, SearchResult, get_knowledge_service

logger = logging.getLogger("sovereign.knowledge.router")

router = APIRouter(prefix="/knowledge", tags=["Knowledge & RAG"])

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".csv",
    ".xlsx",
    ".txt",
    ".md",
    ".json",
    ".py",
    ".sql",
    ".yaml",
    ".yml",
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".bmp",
    ".webp",
}


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────


class DocumentUploadResponse(BaseModel):
    id: uuid.UUID
    filename: str
    file_type: str
    file_size_bytes: int
    file_hash: str
    total_chunks: int
    collection_id: str


class SearchRequest(BaseModel):
    query: str = Field(..., description="Semantic search query")
    collection_id: str | None = Field(default=None, description="Optional collection to search within")
    top_k: int = Field(default=5, ge=1, le=20, description="Maximum number of chunks to return")
    min_similarity: float = Field(default=0.35, ge=0.0, le=1.0, description="Minimum cosine similarity threshold")


class SearchResultItem(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    content: str
    similarity: float
    section_type: str
    page_number: int | None
    citation: str
    metadata: dict[str, Any]
    dense_similarity: float
    dense_rank: int
    sparse_score: float
    sparse_rank: int
    rrf_score: float


class SearchResponse(BaseModel):
    query: str
    results_count: int
    results: list[SearchResultItem]
    formatted_context: str


class DocumentDetail(BaseModel):
    id: uuid.UUID
    filename: str
    file_type: str
    file_size_bytes: int
    file_hash: str
    total_chunks: int
    collection_id: str
    status: str
    error_message: str | None
    source_path: str | None
    user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DocumentSummary(BaseModel):
    id: uuid.UUID
    filename: str
    file_type: str
    file_size_bytes: int
    file_hash: str
    total_chunks: int
    collection_id: str


class DocumentReassignRequest(BaseModel):
    collection_id: str = Field(..., min_length=1, max_length=64)


class CollectionSummary(BaseModel):
    id: uuid.UUID | None
    name: str
    description: str
    document_count: int
    chunk_count: int
    total_bytes: int
    user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CollectionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="Alphanumeric slug")
    description: str = Field(default="", max_length=255)


class CollectionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)


class ChunkSummary(BaseModel):
    id: uuid.UUID
    chunk_index: int
    section_type: str
    page_number: int | None
    char_count: int
    content_preview: str
    metadata: dict[str, Any]
    embedding_dim: int
    created_at: datetime


class ChunkListResponse(BaseModel):
    document_id: uuid.UUID
    page: int
    page_size: int
    total_chunks: int
    total_pages: int
    items: list[ChunkSummary]


class ChunkDetail(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    section_type: str
    page_number: int | None
    content: str
    metadata: dict[str, Any]
    embedding_dim: int
    created_at: datetime


class ReindexStatusResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    progress_pct: int
    message: str


# ─── Collection Routes ────────────────────────────────────────────────────────


@router.get("/collections", response_model=list[CollectionSummary])
async def list_collections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> list[CollectionSummary]:
    """Lists all knowledge collections with aggregated statistics."""
    colls = await service.list_collections(db)
    return [CollectionSummary(**c) for c in colls]


@router.post("/collections", response_model=CollectionSummary, status_code=status.HTTP_201_CREATED)
async def create_collection(
    payload: CollectionCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> CollectionSummary:
    """Creates a new knowledge collection."""
    try:
        coll = await service.create_collection(
            db=db,
            name=payload.name,
            description=payload.description,
            user_id=current_user.id,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    return CollectionSummary(
        id=coll.id,
        name=coll.name,
        description=coll.description,
        document_count=0,
        chunk_count=0,
        total_bytes=0,
        user_id=coll.user_id,
        created_at=coll.created_at,
        updated_at=coll.updated_at,
    )


@router.patch("/collections/{name}", response_model=CollectionSummary)
async def update_collection(
    name: str,
    payload: CollectionUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> CollectionSummary:
    """Updates collection name or description, re-pointing documents if renamed."""
    try:
        coll = await service.update_collection(
            db=db,
            name=name,
            new_name=payload.name,
            description=payload.description,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    # Fetch stats
    colls = await service.list_collections(db)
    target_stat = next((c for c in colls if c["name"] == coll.name), None)
    if not target_stat:
        return CollectionSummary(
            id=coll.id,
            name=coll.name,
            description=coll.description,
            document_count=0,
            chunk_count=0,
            total_bytes=0,
            user_id=coll.user_id,
            created_at=coll.created_at,
            updated_at=coll.updated_at,
        )
    return CollectionSummary(**target_stat)


@router.delete("/collections/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    name: str,
    reassign_to: str | None = Query(default=None),
    delete_documents: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> None:
    """Deletes a collection after safely reassigning or deleting its documents."""
    try:
        await service.delete_collection(
            db=db,
            name=name,
            reassign_to=reassign_to,
            delete_documents=delete_documents,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


# ─── Document Routes ──────────────────────────────────────────────────────────


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    collection_id: str = Form("default"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> DocumentUploadResponse:
    """Uploads and ingests a document into the sovereign knowledge base."""
    filename = file.filename or "uploaded_document"
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed extensions: {sorted(ALLOWED_EXTENSIONS)}",
        )

    settings = get_settings()
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.max_upload_size_bytes} bytes.",
        )

    temp_dir = Path(tempfile.gettempdir()) / "sovereign_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{uuid.uuid4()}_{filename}"

    try:
        temp_path.write_bytes(content)

        doc = await service.ingest_file(
            db=db,
            file_path=temp_path,
            filename=filename,
            user_id=current_user.id,
            collection_id=collection_id,
        )

        return DocumentUploadResponse(
            id=doc.id,
            filename=doc.filename,
            file_type=doc.file_type,
            file_size_bytes=doc.file_size_bytes,
            file_hash=doc.file_hash,
            total_chunks=doc.total_chunks,
            collection_id=doc.collection_id,
        )
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception as unlink_err:
                logger.debug("Temporary upload cleanup notice: %s", unlink_err)


@router.get("/documents", response_model=list[DocumentDetail])
async def list_documents(
    collection_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> list[DocumentDetail]:
    """Lists ingested knowledge documents with full metadata."""
    docs = await service.list_documents(db=db, collection_id=collection_id)
    return [
        DocumentDetail(
            id=d.id,
            filename=d.filename,
            file_type=d.file_type,
            file_size_bytes=d.file_size_bytes,
            file_hash=d.file_hash,
            total_chunks=d.total_chunks,
            collection_id=d.collection_id,
            status=d.status,
            error_message=d.error_message,
            source_path=d.source_path,
            user_id=d.user_id,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in docs
    ]


@router.get("/documents/{doc_id}", response_model=DocumentDetail)
async def get_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> DocumentDetail:
    """Retrieves metadata for a specific document."""
    doc = await service.get_document(db, doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{doc_id}' not found.",
        )
    return DocumentDetail(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size_bytes=doc.file_size_bytes,
        file_hash=doc.file_hash,
        total_chunks=doc.total_chunks,
        collection_id=doc.collection_id,
        status=doc.status,
        error_message=doc.error_message,
        source_path=doc.source_path,
        user_id=doc.user_id,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.patch("/documents/{doc_id}", response_model=DocumentDetail)
async def reassign_document_collection(
    doc_id: uuid.UUID,
    payload: DocumentReassignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> DocumentDetail:
    """Reassigns a document to a different collection."""
    doc = await service.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if current_user.role != "admin" and doc.user_id and doc.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    try:
        updated_doc = await service.reassign_document(db, doc_id, payload.collection_id)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    return DocumentDetail(
        id=updated_doc.id,
        filename=updated_doc.filename,
        file_type=updated_doc.file_type,
        file_size_bytes=updated_doc.file_size_bytes,
        file_hash=updated_doc.file_hash,
        total_chunks=updated_doc.total_chunks,
        collection_id=updated_doc.collection_id,
        status=updated_doc.status,
        error_message=updated_doc.error_message,
        source_path=updated_doc.source_path,
        user_id=updated_doc.user_id,
        created_at=updated_doc.created_at,
        updated_at=updated_doc.updated_at,
    )


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> None:
    """Deletes an ingested document and its vector chunks."""
    doc = await service.get_document(db, doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{doc_id}' not found.",
        )
    if current_user.role != "admin" and doc.user_id and doc.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    deleted = await service.delete_document(db=db, doc_id=doc_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{doc_id}' not found.",
        )


# ─── Chunk Inspection Routes ──────────────────────────────────────────────────


@router.get("/documents/{doc_id}/chunks", response_model=ChunkListResponse)
async def list_document_chunks(
    doc_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    section_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> ChunkListResponse:
    """Inspects layout-aware chunks of a document with pagination and filters."""
    doc = await service.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunks, total = await service.list_document_chunks(
        db=db,
        doc_id=doc_id,
        page=page,
        page_size=page_size,
        section_type=section_type,
        search=search,
    )

    items = [
        ChunkSummary(
            id=c.id,
            chunk_index=c.chunk_index,
            section_type=c.section_type,
            page_number=c.page_number,
            char_count=len(c.content),
            content_preview=c.content[:200] + ("..." if len(c.content) > 200 else ""),
            metadata=c.metadata_json or {},
            embedding_dim=len(c.embedding) if c.embedding else 0,
            created_at=c.created_at,
        )
        for c in chunks
    ]

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return ChunkListResponse(
        document_id=doc_id,
        page=page,
        page_size=page_size,
        total_chunks=total,
        total_pages=total_pages,
        items=items,
    )


@router.get("/chunks/{chunk_id}", response_model=ChunkDetail)
async def get_chunk_detail(
    chunk_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> ChunkDetail:
    """Retrieves full content and provenance metadata for a single chunk."""
    res = await service.get_chunk_detail(db, chunk_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")

    chunk, doc = res
    return ChunkDetail(
        id=chunk.id,
        document_id=doc.id,
        filename=doc.filename,
        chunk_index=chunk.chunk_index,
        section_type=chunk.section_type,
        page_number=chunk.page_number,
        content=chunk.content,
        metadata=chunk.metadata_json or {},
        embedding_dim=len(chunk.embedding) if chunk.embedding else 0,
        created_at=chunk.created_at,
    )


# ─── Re-indexing Routes ───────────────────────────────────────────────────────


@router.post("/documents/{doc_id}/reindex", response_model=ReindexStatusResponse)
async def reindex_document(
    doc_id: uuid.UUID,
    sync: bool = Query(default=False, description="Execute synchronously for testing"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> ReindexStatusResponse:
    """Re-parses and re-embeds document chunks with duplicate run prevention."""
    doc = await service.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if current_user.role != "admin" and doc.user_id and doc.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    try:
        await service.trigger_reindex(db, doc_id)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))

    if sync:
        await service.execute_reindex(db, doc_id)
        stat = service.get_reindex_status(doc_id)
        return ReindexStatusResponse(
            document_id=doc_id,
            status=stat.get("status", "completed"),
            progress_pct=stat.get("progress_pct", 100),
            message=stat.get("message", "Re-indexing complete"),
        )

    async def _run_in_background() -> None:
        async with AsyncSessionLocal() as session:
            await service.execute_reindex(session, doc_id)

    asyncio.create_task(_run_in_background())

    return ReindexStatusResponse(
        document_id=doc_id,
        status="in_progress",
        progress_pct=10,
        message=f"Re-indexing initiated for '{doc.filename}'.",
    )


@router.get("/documents/{doc_id}/reindex-status", response_model=ReindexStatusResponse)
async def get_reindex_status(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> ReindexStatusResponse:
    """Queries live re-indexing progress for a document."""
    doc = await service.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    stat = service.get_reindex_status(doc_id)
    return ReindexStatusResponse(
        document_id=doc_id,
        status=stat.get("status", doc.status),
        progress_pct=stat.get("progress_pct", 100 if doc.status == "indexed" else 0),
        message=stat.get("message", f"Document status: {doc.status}"),
    )


# ─── Search Route ─────────────────────────────────────────────────────────────


@router.post("/search", response_model=SearchResponse)
async def search_knowledge(
    payload: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> SearchResponse:
    """Searches the knowledge base using semantic vector retrieval with source citations."""
    results: list[SearchResult] = await service.search(
        db=db,
        query=payload.query,
        top_k=payload.top_k,
        collection_id=payload.collection_id,
        min_similarity=payload.min_similarity,
    )

    items = [
        SearchResultItem(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            filename=r.filename,
            content=r.content,
            similarity=r.similarity,
            section_type=r.section_type,
            page_number=r.page_number,
            citation=r.citation_header(idx),
            metadata=r.metadata,
            dense_similarity=r.dense_similarity,
            dense_rank=r.dense_rank,
            sparse_score=r.sparse_score,
            sparse_rank=r.sparse_rank,
            rrf_score=r.rrf_score,
        )
        for idx, r in enumerate(results, start=1)
    ]

    context = service.format_context_for_prompt(results)

    return SearchResponse(
        query=payload.query,
        results_count=len(items),
        results=items,
        formatted_context=context,
    )
