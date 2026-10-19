"""
tests/test_integration/test_real_agent_workflow.py
==================================================
End-to-end integration tests running bounded agent orchestration against
the live local Ollama model with genuine tool execution.
"""

import uuid
from pathlib import Path

import pytest
from app.agent.service import AgentService
from app.agent.state import AgentRunRequest
from app.identity.models import User
from app.knowledge.service import KnowledgeService
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_integration.helpers import get_available_ollama_models, is_ollama_reachable

pytestmark = pytest.mark.skipif(
    not is_ollama_reachable(),
    reason="Local Ollama daemon is not running on 127.0.0.1:11434",
)


@pytest.fixture
def test_admin_user() -> User:
    return User(
        id=uuid.uuid4(),
        username="integration_admin",
        role="admin",
        is_active=True,
        password_hash="",
    )


@pytest.mark.asyncio
async def test_real_agent_math_tool_workflow(test_admin_user: User) -> None:
    available = get_available_ollama_models()
    if not any("llama3.2" in m for m in available):
        pytest.skip("llama3.2 model not available")

    service = AgentService()
    req = AgentRunRequest(
        prompt="Calculate the value of (120 - 45) * 4 using math_eval.",
        max_iterations=4,
    )

    res = await service.run(req, user=test_admin_user)
    assert res.status in {"completed", "synthesizing"}
    assert "300" in res.response
    tools_used = [t.get("tool_name") for t in res.tool_results]
    assert "math_eval" in tools_used


@pytest.mark.asyncio
async def test_real_agent_grounded_rag_workflow(
    test_admin_user: User,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    available = get_available_ollama_models()
    if not (any("llama3.2" in m for m in available) and any("all-minilm" in m for m in available)):
        pytest.skip("Required Ollama models not available")

    # Ingest a real technical standard into DB
    spec_file = tmp_path / "reactor_cooling_standard.txt"
    spec_file.write_text(
        "Standard RS-88: Maximum allowable cooling jacket temperature on reactor R-101 is 78.5 degrees Celsius. "
        "If cooling temperature exceeds 80C, emergency dump valve XV-202 must actuate automatically."
    )

    svc = KnowledgeService()
    await svc.ingest_file(
        db=db_session,
        file_path=spec_file,
        filename=spec_file.name,
        collection_id="default",
    )

    service = AgentService()
    req = AgentRunRequest(
        prompt="Search the knowledge base for the maximum allowable cooling jacket temperature on reactor R-101 and cite the source.",
        max_iterations=5,
    )

    res = await service.run(req, user=test_admin_user, db=db_session)
    tools_used = [t.get("tool_name") for t in res.tool_results]
    assert "rag_search" in tools_used
    assert any(num in res.response for num in ["78.5", "80"])
    assert any(term in res.response for term in ["Source", "RS-88", "reactor_cooling_standard"])


@pytest.mark.asyncio
async def test_real_agent_insufficient_evidence_refusal(
    test_admin_user: User,
    db_session: AsyncSession,
) -> None:
    available = get_available_ollama_models()
    if not (any("llama3.2" in m for m in available) and any("all-minilm" in m for m in available)):
        pytest.skip("Required Ollama models not available")

    service = AgentService()
    req = AgentRunRequest(
        prompt="Search the internal documents for the maintenance schedule of cryogenic tank T-9999. Cite the source document.",
        max_iterations=4,
    )

    res = await service.run(req, user=test_admin_user, db=db_session)
    # The agent must state insufficient evidence rather than fabricating a fake manual or schedule
    response_lower = res.response.lower()
    evidence_missing_indicators = [
        "insufficient",
        "no matching",
        "could not find",
        "couldn't find",
        "could not retrieve",
        "couldn't retrieve",
        "not found",
        "no information",
        "unable to find",
        "no internal",
        "not available",
        "no documents",
        "cannot find",
        "cannot retrieve",
        "no record",
        "does not mention",
        "did not find",
        "didn't find",
        "no results",
        "no data",
        "not contain",
        "no mention",
        "not locate",
        "no relevant",
        "no schedule",
        "does not exist",
    ]
    assert any(ind in response_lower for ind in evidence_missing_indicators)
    # Assert it does NOT hallucinate a made-up T-9999 manual citation
    assert "T-9999_manual.pdf" not in res.response
