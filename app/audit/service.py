"""
app/audit/service.py — Sovereign Workbench Audit Service
=========================================================
Append-only audit event emission.

Usage:
    await emit_event(
        db,
        event_type=AuditEventType.LOGIN_SUCCESS,
        user_id=str(user.id),
        ip_address=request.client.host,
        summary="User logged in successfully",
    )

Rules:
- Call emit_event for every security-sensitive action.
- NEVER call db.delete() or execute UPDATE on audit_events in application code.
- The detail dict must NOT contain: passwords, raw tokens, or confidential document content.
"""

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent

logger = logging.getLogger("sovereign.audit")


async def emit_event(
    db: AsyncSession,
    event_type: str,
    *,
    user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    outcome: str = "success",
    ip_address: str | None = None,
    user_agent: str | None = None,
    detail: dict[str, Any] | None = None,
    summary: str | None = None,
) -> None:
    """
    Persist an audit event. Failures are logged but never raise — audit must not
    interrupt the primary request flow.
    """
    try:
        uid = uuid.UUID(user_id) if user_id else None
        event = AuditEvent(
            user_id=uid,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            ip_address=ip_address,
            user_agent=user_agent,
            detail=detail,
            summary=summary,
        )
        db.add(event)
        # Note: session.commit() is called by the request lifecycle in get_db()
        # For events that must be persisted immediately (e.g., before exception),
        # call db.flush() explicitly in the caller.
        logger.info(
            "AUDIT event_type=%s outcome=%s user_id=%s summary=%s",
            event_type,
            outcome,
            user_id,
            summary,
        )
    except Exception as exc:
        # Audit failure must never crash the request
        logger.error("Failed to emit audit event %s: %s", event_type, exc)
