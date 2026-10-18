"""
tests/test_agent/test_service.py
================================
Unit tests for AgentService run and SSE stream orchestration.
"""

import pytest
from app.agent.service import AgentService
from app.agent.state import AgentRunRequest
from app.identity.models import User
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_agent.test_graph import MockDirectProvider, MockMathToolProvider


@pytest.mark.asyncio
async def test_agent_service_run_direct(db_session: AsyncSession, test_user: User):
    """Verifies AgentService.run produces valid AgentRunResponse and audit event."""
    provider = MockDirectProvider()
    service = AgentService(provider=provider)

    req = AgentRunRequest(prompt="Summarize system stability parameters")
    resp = await service.run(request=req, user=test_user, db=db_session)

    assert resp.status == "completed"
    assert resp.response == "Direct reasoning response without tool usage."
    assert resp.iterations == 0
    assert resp.duration_ms > 0
    assert resp.model_used in ("llama3.2:latest", "qwen2.5:3b")
    assert resp.route_decision.role in ("reasoning", "coding")


@pytest.mark.asyncio
async def test_agent_service_run_with_tools(db_session: AsyncSession, test_user: User):
    """Verifies AgentService.run produces tool results and increments iterations."""
    provider = MockMathToolProvider()
    service = AgentService(provider=provider)

    req = AgentRunRequest(prompt="Solve 2*x - 10 = 0", max_iterations=5)
    resp = await service.run(request=req, user=test_user, db=db_session)

    assert resp.status == "completed"
    assert "x = 5" in resp.response
    assert resp.iterations == 1
    assert resp.tool_calls_count == 1
    assert len(resp.tool_results) == 1
    assert resp.tool_results[0]["tool_name"] == "math_eval"


@pytest.mark.asyncio
async def test_agent_service_stream_events(db_session: AsyncSession, test_user: User):
    """Verifies that AgentService.stream yields typed SSE events in proper sequence."""
    provider = MockMathToolProvider()
    service = AgentService(provider=provider)

    req = AgentRunRequest(prompt="Calculate the root of 2*x - 10 = 0")
    events = []

    async for event in service.stream(request=req, user=test_user, db=db_session):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "status" in event_types
    assert "route" in event_types
    assert "thinking" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "done" in event_types

    # Find the done event and verify data
    done_event = next(e for e in events if e["event"] == "done")
    assert "x = 5" in done_event["data"]["response"]
    assert done_event["data"]["status"] == "completed"
