"""
app/knowledge/models.py
=======================
SQLAlchemy models for Knowledge Base and pgvector Document Chunks.
Cross-dialect compatible: uses PostgreSQL vector(768) and jsonb in production,
falling back gracefully to standard JSON in SQLite test environments.
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

EMBEDDING_DIM = 768  # Standard dimension for nomic-embed-text


class KnowledgeDocument(Base):
    """Represents an ingested source document (PDF, Word, spreadsheet, text)."""

    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid().with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    collection_id: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        default="default",
        index=True,
    )
    filename: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    file_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    total_chunks: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid().with_variant(PG_UUID(as_uuid=True), "postgresql"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    # Relationships
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )


class DocumentChunk(Base):
    """Represents an individual chunk of a document with its vector embedding."""

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid().with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid().with_variant(PG_UUID(as_uuid=True), "postgresql"),
        sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    section_type: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="paragraph")
    page_number: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        sa.JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    embedding: Mapped[list[float]] = mapped_column(
        sa.JSON().with_variant(Vector(EMBEDDING_DIM), "postgresql"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    # Relationships
    document: Mapped["KnowledgeDocument"] = relationship(
        "KnowledgeDocument",
        back_populates="chunks",
    )
