"""
0002_knowledge_rag — Knowledge documents and pgvector chunks schema.

Creates:
  - knowledge_documents (document metadata, file hash deduplication)
  - document_chunks    (chunk content, layout metadata, 768-dim vector embeddings)

Revision: 0002
Down Revision: 0001
"""

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── knowledge_documents ─────────────────────────────────────────────
    op.create_table(
        "knowledge_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("collection_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(32), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_knowledge_documents_collection_id", "knowledge_documents", ["collection_id"])
    op.create_index("ix_knowledge_documents_file_hash", "knowledge_documents", ["file_hash"])
    op.create_index("ix_knowledge_documents_user_id", "knowledge_documents", ["user_id"])

    # ── document_chunks ─────────────────────────────────────────────────
    op.create_table(
        "document_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("section_type", sa.String(32), nullable=False, server_default="paragraph"),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("metadata_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_chunk_index", "document_chunks", ["chunk_index"])


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("knowledge_documents")
