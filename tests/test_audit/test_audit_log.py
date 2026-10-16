"""
tests/test_audit/test_audit_log.py
====================================
Tests for the append-only audit log.

Verifies:
  - Audit events are persisted to the DB
  - emit_event does not raise even if DB commit fails (logged, not propagated)
  - AuditEvent model has no UPDATE or DELETE in application service code
  - Event types are correctly recorded
"""

import uuid

import pytest
from app.audit.models import AuditEvent, AuditEventType
from app.audit.service import emit_event
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TestAuditEventEmission:
    @pytest.mark.asyncio
    async def test_event_written_to_db(self, db_session: AsyncSession) -> None:
        uid = str(uuid.uuid4())
        await emit_event(
            db_session,
            event_type=AuditEventType.LOGIN_SUCCESS,
            user_id=uid,
            outcome="success",
            ip_address="127.0.0.1",
            summary="Test login event",
        )
        await db_session.flush()

        result = await db_session.execute(
            select(AuditEvent).where(AuditEvent.event_type == AuditEventType.LOGIN_SUCCESS)
        )
        events = result.scalars().all()
        assert len(events) >= 1
        e = events[0]
        assert e.outcome == "success"
        assert e.ip_address == "127.0.0.1"
        assert e.summary == "Test login event"

    @pytest.mark.asyncio
    async def test_event_without_user_id(self, db_session: AsyncSession) -> None:
        """Audit events before auth (e.g., login failure for unknown user) must not require user_id."""
        await emit_event(
            db_session,
            event_type=AuditEventType.LOGIN_FAILURE,
            outcome="failure",
            summary="Unknown user login attempt",
        )
        await db_session.flush()
        result = await db_session.execute(
            select(AuditEvent).where(AuditEvent.event_type == AuditEventType.LOGIN_FAILURE)
        )
        events = result.scalars().all()
        assert len(events) >= 1
        assert events[0].user_id is None

    @pytest.mark.asyncio
    async def test_emit_does_not_raise_on_error(self, db_session: AsyncSession) -> None:
        """emit_event must not propagate exceptions — audit must not crash the request."""
        from unittest.mock import patch

        # Even if db.add raises, emit_event catches and logs it
        with patch.object(db_session, "add", side_effect=RuntimeError("DB error")):
            # Should not raise
            await emit_event(
                db_session,
                event_type=AuditEventType.LOGIN_SUCCESS,
                summary="This should not raise",
            )

    @pytest.mark.asyncio
    async def test_audit_service_has_no_delete_method(self) -> None:
        """Verify audit service module exposes no delete operations on audit events."""
        import ast
        import inspect

        import app.audit.service as svc

        # Check exposed callable attributes
        for name in dir(svc):
            assert not name.startswith("delete_"), f"Audit service should not expose delete methods: {name}"

        # Parse AST and ensure no delete statements or calls to delete()
        tree = ast.parse(inspect.getsource(svc))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "delete":
                raise AssertionError("audit service contains call to .delete()")
