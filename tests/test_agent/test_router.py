"""
tests/test_agent/test_router.py
===============================
Integration tests for Agent API endpoints:
  - POST /api/v1/agent/run
  - POST /api/v1/agent/stream
  - GET /api/v1/agent/models
  - Authentication & RBAC protection
"""

from collections.abc import Generator

import pytest
from app.agent.router import get_agent_service
from app.identity.models import User
from httpx import AsyncClient

from tests.conftest import auth_headers
from tests.test_agent.test_graph import MockMathToolProvider


@pytest.fixture(autouse=True)
def inject_mock_service() -> Generator[None, None, None]:
    service = get_agent_service()
    orig_provider = service.provider
    service.provider = MockMathToolProvider()
    yield
    service.provider = orig_provider


@pytest.mark.asyncio
async def test_agent_run_unauthenticated(client: AsyncClient):
    """Rejects unauthenticated requests without Bearer token."""
    resp = await client.post(
        "/api/v1/agent/run",
        json={"prompt": "Solve 2*x = 10"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_agent_run_authenticated(
    client: AsyncClient,
    test_user: User,
):
    """Executes agent run endpoint with valid Bearer token."""
    resp = await client.post(
        "/api/v1/agent/run",
        json={"prompt": "Solve 2*x - 10 = 0", "max_iterations": 5},
        headers=auth_headers(test_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "x = 5" in data["response"]
    assert data["iterations"] == 1
    assert data["tool_calls_count"] == 1
    assert len(data["tool_results"]) == 1


@pytest.mark.asyncio
async def test_agent_stream_authenticated(
    client: AsyncClient,
    test_user: User,
):
    """Executes SSE streaming endpoint and verifies event-stream content."""
    resp = await client.post(
        "/api/v1/agent/stream",
        json={"prompt": "Solve 2*x - 10 = 0"},
        headers=auth_headers(test_user),
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    assert "event: route" in body or "event: status" in body
    assert "event: done" in body


@pytest.mark.asyncio
async def test_agent_models_list(client: AsyncClient, test_user: User):
    """Verifies GET /api/v1/agent/models returns registered models and options."""
    resp = await client.get(
        "/api/v1/agent/models",
        headers=auth_headers(test_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "reasoning" in data["models"]
    assert "coding" in data["models"]
    assert "options" in data
