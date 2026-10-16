"""
app/audit/models.py — Sovereign Workbench Audit Log Model
==========================================================
Append-only audit event log.

Design constraints:
- The audit_events table has no UPDATE or DELETE privileges in application code.
- Rows are inserted once and never modified.
- The database role used by the application should have INSERT + SELECT only on this table.
- All security-sensitive actions must emit an audit event.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# Canonical event type constants — use these, never raw strings
class AuditEventType:
    # Authentication
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGIN_2FA_SUCCESS = "auth.login.2fa.success"
    LOGIN_2FA_FAILURE = "auth.login.2fa.failure"
    LOGOUT = "auth.logout"
    TOKEN_REFRESH = "auth.token.refresh"
    TOKEN_REVOKED = "auth.token.revoked"
    ACCOUNT_LOCKED = "auth.account.locked"
    PASSWORD_CHANGED = "auth.password.changed"

    # 2FA
    TOTP_ENROLLED = "auth.totp.enrolled"
    TOTP_DISABLED = "auth.totp.disabled"
    TOTP_BACKUP_USED = "auth.totp.backup_code.used"

    # Admin actions
    USER_CREATED = "admin.user.created"
    USER_DELETED = "admin.user.deleted"
    USER_ROLE_CHANGED = "admin.user.role_changed"

    # Agent / task
    TASK_STARTED = "agent.task.started"
    TASK_COMPLETED = "agent.task.completed"
    TASK_FAILED = "agent.task.failed"
    TASK_CANCELLED = "agent.task.cancelled"
    TOOL_CALLED = "agent.tool.called"
    TOOL_DENIED = "agent.tool.denied"

    # Documents / RAG
    DOCUMENT_UPLOADED = "doc.uploaded"
    DOCUMENT_DELETED = "doc.deleted"
    RAG_QUERY = "rag.query"

    # Artifacts
    ARTIFACT_CREATED = "artifact.created"
    ARTIFACT_DOWNLOADED = "artifact.downloaded"

    # Security events
    PROMPT_INJECTION_DETECTED = "security.prompt_injection"
    UNAUTHORIZED_ACCESS = "security.unauthorized"
    OFFLINE_VIOLATION = "security.offline_mode_violation"


class AuditEvent(Base):
    """
    Immutable audit event record.

    Application code must NEVER DELETE or UPDATE rows in this table.
    The DB role for the application user should enforce this at the database level.
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid().with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )

    # The user performing the action (nullable — some events occur before auth)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid().with_variant(PG_UUID(as_uuid=True), "postgresql"),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # What kind of resource this event affects
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # The ID of the affected resource (task_id, document_id, user_id, etc.)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Outcome: "success", "failure", "denied"
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="success")

    # Client information
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Structured detail — stored as JSONB for queryability
    # Must NOT contain: passwords, raw tokens, confidential document content, PII beyond username
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    # Safe human-readable summary
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    def __repr__(self) -> str:
        return f"<AuditEvent id={self.id} type={self.event_type!r} outcome={self.outcome!r}>"
