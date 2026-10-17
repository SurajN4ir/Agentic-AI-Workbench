"""
tests/test_tools/test_registry.py
=================================
Tests for Tool Registry, RBAC permission enforcement, and tool API endpoints.
"""

import pytest
from app.audit.models import AuditEvent
from app.identity.models import User
from app.tools.interface import ToolStatus
from app.tools.registry import ToolRegistry, get_tool_registry
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers


class TestToolRegistry:
    @pytest.fixture
    def registry(self) -> ToolRegistry:
        return get_tool_registry()

    def test_list_tools_for_roles(self, registry: ToolRegistry) -> None:
        """Regular users only see safe tools; technical roles see sandbox."""
        user_tools = [t["name"] for t in registry.list_tools_for_role("user")]
        assert "math_eval" in user_tools
        assert "code_sandbox" not in user_tools

        admin_tools = [t["name"] for t in registry.list_tools_for_role("admin")]
        assert "math_eval" in admin_tools
        assert "code_sandbox" in admin_tools

        analyst_tools = [t["name"] for t in registry.list_tools_for_role("analyst")]
        assert "code_sandbox" in analyst_tools

    @pytest.mark.asyncio
    async def test_rbac_denies_unauthorized_tool_execution(
        self,
        registry: ToolRegistry,
        test_user: User,
        db_session: AsyncSession,
    ) -> None:
        """A regular user (role='user') cannot execute code_sandbox."""
        res = await registry.execute_tool(
            name="code_sandbox",
            input_data={"code": "print('hello')"},
            user=test_user,
            session_id="session_123",
            db=db_session,
        )
        assert res.status == ToolStatus.ERROR
        assert "Permission denied" in str(res.error)

    @pytest.mark.asyncio
    async def test_safe_math_execution_allowed_for_regular_user(
        self,
        registry: ToolRegistry,
        test_user: User,
        db_session: AsyncSession,
    ) -> None:
        """A regular user can execute math_eval."""
        res = await registry.execute_tool(
            name="math_eval",
            input_data={"expression": "5 * 5", "mode": "evaluate"},
            user=test_user,
            session_id="session_123",
            db=db_session,
        )
        assert res.status == ToolStatus.SUCCESS
        assert res.data["result"] == "25.0000000000000"

        # Verify audit event was logged
        events = (
            (await db_session.execute(select(AuditEvent).where(AuditEvent.event_type == "tool_executed")))
            .scalars()
            .all()
        )
        assert len(events) >= 1
        assert events[-1].resource_id == "math_eval"


class TestToolEndpoints:
    @pytest.mark.asyncio
    async def test_list_tools_endpoint(self, client: AsyncClient, test_user: User) -> None:
        """GET /api/v1/tools returns tools allowed for the user's role."""
        r = await client.get("/api/v1/tools", headers=auth_headers(test_user))
        assert r.status_code == 200
        tools = r.json()
        names = [t["name"] for t in tools]
        assert "math_eval" in names
        assert "code_sandbox" not in names

    @pytest.mark.asyncio
    async def test_math_endpoint_authenticated(self, client: AsyncClient, test_user: User) -> None:
        """POST /api/v1/tools/math evaluates math expression."""
        payload = {"expression": "100 / 4", "mode": "evaluate"}
        r = await client.post("/api/v1/tools/math", json=payload, headers=auth_headers(test_user))
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "success"
        assert float(data["result_text"]) == 25.0

    @pytest.mark.asyncio
    async def test_sandbox_endpoint_forbidden_for_regular_user(
        self,
        client: AsyncClient,
        test_user: User,
    ) -> None:
        """POST /api/v1/tools/sandbox returns 403 Forbidden for role='user'."""
        payload = {"code": "print('exploit')", "session_id": "test_session"}
        r = await client.post("/api/v1/tools/sandbox", json=payload, headers=auth_headers(test_user))
        assert r.status_code == 403
        assert "Permission denied" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_sandbox_endpoint_allowed_for_admin_role(
        self,
        client: AsyncClient,
        admin_user: User,
    ) -> None:
        """POST /api/v1/tools/sandbox allows admin (fails-closed if docker daemon down, but authorized)."""
        payload = {"code": "print('allowed')", "session_id": "admin_session"}
        r = await client.post("/api/v1/tools/sandbox", json=payload, headers=auth_headers(admin_user))
        # Admin is permitted past the 403 gate; response is 200 with ToolResult
        assert r.status_code == 200
        data = r.json()
        # Even if docker daemon is down, status code is 200 with error reported in body (fail-closed)
        assert "status" in data
