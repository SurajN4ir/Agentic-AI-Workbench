"""
tests/test_agent/test_state.py
==============================
Unit tests for WorkbenchState schemas, AgentRunRequest, and AgentRunResponse.
"""

import pytest
from app.agent.state import AgentRunRequest, AgentRunResponse, WorkbenchState
from app.routing.schemas import RouteDecision
from pydantic import ValidationError


def test_workbench_state_dict_structure():
    """Verifies WorkbenchState TypedDict initialization and key assignments."""
    state: WorkbenchState = {
        "session_id": "test_session_123",
        "user_id": "user-456",
        "user_role": "analyst",
        "username": "alice",
        "prompt": "Evaluate reactor pressure dynamics",
        "file_metadata": [],
        "route_decision": {"role": "reasoning", "confidence": 0.95},
        "model_tag": "qwen2.5:3b",
        "messages": [{"role": "user", "content": "hello"}],
        "tool_calls": [],
        "tool_results": [],
        "iteration_count": 1,
        "max_iterations": 8,
        "thinking_trace": ["Step 1: Check formula"],
        "artifacts": [],
        "final_response": "Result is stable.",
        "status": "completed",
        "error": None,
        "duration_ms": 125.4,
    }

    assert state["session_id"] == "test_session_123"
    assert state["iteration_count"] == 1
    assert state["status"] == "completed"
    assert len(state["thinking_trace"]) == 1


def test_agent_run_request_validation():
    """Tests AgentRunRequest constraints and boundary clamps."""
    # Valid request with defaults
    req = AgentRunRequest(prompt="Calculate the integral of x^3")
    assert req.prompt == "Calculate the integral of x^3"
    assert req.max_iterations == 8
    assert req.session_id is None
    assert req.role_override is None

    # Empty prompt rejection
    with pytest.raises(ValidationError):
        AgentRunRequest(prompt="")

    # max_iterations boundaries (ge=1, le=15)
    with pytest.raises(ValidationError):
        AgentRunRequest(prompt="test", max_iterations=0)

    with pytest.raises(ValidationError):
        AgentRunRequest(prompt="test", max_iterations=16)

    valid_custom = AgentRunRequest(prompt="test", max_iterations=15, role_override="coding")
    assert valid_custom.max_iterations == 15
    assert valid_custom.role_override == "coding"


def test_agent_run_response_serialization():
    """Verifies AgentRunResponse serialization and field structure."""
    decision = RouteDecision(
        role="reasoning",
        confidence=0.92,
        method="keyword",

        reasoning="Prompt contains formula analysis keywords",
    )
    resp = AgentRunResponse(
        session_id="session-789",
        status="completed",
        route_decision=decision,
        model_used="qwen2.5:3b",
        response="The integral is x^4/4 + C",
        thinking_trace=["Calculated power rule"],
        iterations=1,
        tool_calls_count=1,
        tool_results=[{"tool_name": "math_eval", "status": "success"}],
        artifacts=[],
        duration_ms=45.2,
    )

    data = resp.model_dump()
    assert data["session_id"] == "session-789"
    assert data["route_decision"]["role"] == "reasoning"
    assert data["iterations"] == 1
    assert data["tool_calls_count"] == 1
    assert data["duration_ms"] == 45.2
