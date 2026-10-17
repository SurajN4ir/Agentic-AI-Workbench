"""
app/knowledge/router.py
=======================
FastAPI endpoints for knowledge base management and RAG retrieval.
Protected endpoints requiring authentication.
"""

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
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
}


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


class SearchResponse(BaseModel):
    query: str
    results_count: int
    results: list[SearchResultItem]
    formatted_context: str


class DocumentSummary(BaseModel):
    id: uuid.UUID
    filename: str
    file_type: str
    file_size_bytes: int
    file_hash: str
    total_chunks: int
    collection_id: str


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
    # Read and validate file content
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.max_upload_size_bytes} bytes.",
        )

    # Save to a temporary file for parser processing
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


@router.get("/documents", response_model=list[DocumentSummary])
async def list_documents(
    collection_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> list[DocumentSummary]:
    """Lists ingested knowledge documents."""
    docs = await service.list_documents(db=db, collection_id=collection_id)
    return [
        DocumentSummary(
            id=d.id,
            filename=d.filename,
            file_type=d.file_type,
            file_size_bytes=d.file_size_bytes,
            file_hash=d.file_hash,
            total_chunks=d.total_chunks,
            collection_id=d.collection_id,
        )
        for d in docs
    ]


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> None:
    """Deletes an ingested document and its vector chunks."""
    deleted = await service.delete_document(db=db, doc_id=doc_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{doc_id}' not found.",
        )
