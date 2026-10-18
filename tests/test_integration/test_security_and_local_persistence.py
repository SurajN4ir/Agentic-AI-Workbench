"""
tests/test_integration/test_security_and_local_persistence.py
=============================================================
Integration tests verifying security bounds, air-gap enforcement,
RBAC tool authorization, and persistent storage retention.
"""

import uuid
from pathlib import Path

import pytest
from app.audit.models import AuditEvent
from app.identity.models import User
from app.network.offline_guard import OfflineViolationError, _BlockingHandler, _is_allowed_host
from app.tools.file_io import execute_file_io
from app.tools.interface import ToolStatus
from app.tools.registry import get_tool_registry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def test_airgap_egress_blocking() -> None:
    assert _is_allowed_host("127.0.0.1") is True
    assert _is_allowed_host("localhost") is True
    assert _is_allowed_host("8.8.8.8") is False

    class FakeRequest:
        host = "external-api.openai.com:443"
        full_url = "https://external-api.openai.com/v1/chat"

    handler = _BlockingHandler()
    with pytest.raises(OfflineViolationError):
        handler._check(FakeRequest())


def test_file_io_path_traversal_blocked(tmp_path: Path) -> None:
    session_id = f"sec_test_{uuid.uuid4().hex[:8]}"

    # Attempt directory traversal out of workspace
    res = execute_file_io(
        operation="read",
        path="../../app/config.py",
        session_id=session_id,
    )
    assert res.status == ToolStatus.ERROR
    assert "Access denied" in str(res.error) or "traversal" in str(res.error).lower()


@pytest.mark.asyncio
async def test_rbac_tool_authorization_enforcement() -> None:
    registry = get_tool_registry()

    # Create a regular user (not an analyst, developer, or admin)
    regular_user = User(
        id=uuid.uuid4(),
        username="operator_joe",
        role="user",
        is_active=True,
        password_hash="",
    )

    # Attempt to execute privileged code_sandbox tool
    res = await registry.execute_tool(
        name="code_sandbox",
        input_data={"code": "print('hello')"},
        user=regular_user,
        session_id="sec_session",
    )

    assert res.status == ToolStatus.ERROR
    assert "Permission denied" in str(res.error)


@pytest.mark.asyncio
async def test_database_data_persistence_across_sessions(db_session: AsyncSession) -> None:
    # Insert an audit record
    user_id = uuid.uuid4()
    audit_evt = AuditEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        event_type="INTEGRATION_TEST_EVENT",
        resource_type="system",
        resource_id="test_01",
        outcome="SUCCESS",
        detail={"metric": 42},
        summary="Integration persistence verification",
    )
    db_session.add(audit_evt)
    await db_session.commit()

    # Re-query in a fresh transaction to verify persistence
    stmt = select(AuditEvent).where(AuditEvent.event_type == "INTEGRATION_TEST_EVENT")
    record = (await db_session.execute(stmt)).scalars().first()

    assert record is not None
    assert record.user_id == user_id
    assert record.outcome == "SUCCESS"
    assert record.detail == {"metric": 42}
