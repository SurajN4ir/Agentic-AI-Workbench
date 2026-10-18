"""
tests/test_agent/test_service.py
================================
Unit tests for AgentService run and SSE stream orchestration.
"""

from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_agent_service_citation_inspector_provenance(db_session: AsyncSession, test_user: User):
    """Verifies that RAG search results populate rich CitationDetail provenance in AgentRunResponse."""
    from app.models.base import BaseModelProvider
    from app.models.schemas import ChatMessage, ChatResponse, EmbeddingResponse, ModelResponse
    from app.tools.registry import ToolResult, ToolStatus

    class MockRagModelProvider(BaseModelProvider):
        def __init__(self):
            self.step = 0

        async def generate(self, model, prompt, system=None, options=None):
            return ModelResponse(content="Done", model=model)

        async def stream(self, model, prompt, system=None, options=None):
            yield "Done"

        async def chat(self, model, messages, tools=None, options=None):
            self.step += 1
            if self.step == 1:
                return ChatResponse(
                    message=ChatMessage(
                        role="assistant",
                        content="",
                        tool_calls=[
                            {
                                "id": "call_rag_1",
                                "function": {
                                    "name": "rag_search",
                                    "arguments": {"query": "turbine operating temperature"},
                                },
                            }
                        ],
                    ),
                    model=model,
                )
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="The turbine operating temperature limit is 1250 C [Source 1: turbine_specs.docx | Page 3 | SPECS].",
                ),
                model=model,
            )

        async def stream_chat(self, model, messages, tools=None, options=None):
            yield {}

        async def embed(self, model, texts):
            return EmbeddingResponse(embeddings=[[0.1] * 768 for _ in texts], model=model, dimension=768)

        async def list_models(self):
            return ["qwen2.5:3b"]

        async def health_check(self):
            return True

    provider = MockRagModelProvider()
    service = AgentService(provider=provider)

    mock_chunk_id = "11111111-2222-3333-4444-555555555555"
    mock_doc_id = "99999999-8888-7777-6666-555555555555"
    rag_tool_result = ToolResult(
        status=ToolStatus.SUCCESS,
        output="[Source 1: turbine_specs.docx | Page 3 | SPECS] (Similarity: 0.92)\nContinuous operating temperature limit is 1250 C.",
        data={
            "results": [
                {
                    "source": "turbine_specs.docx",
                    "page": 3,
                    "similarity": 0.92,
                    "section": "SPECS",
                    "content": "Continuous operating temperature limit is 1250 C.",
                    "citation": "[Source 1: turbine_specs.docx | Page 3 | SPECS] (Similarity: 0.92)",
                    "chunk_id": mock_chunk_id,
                    "document_id": mock_doc_id,
                    "dense_similarity": 0.91,
                    "dense_rank": 1,
                    "sparse_score": 14.5,
                    "sparse_rank": 1,
                    "rrf_score": 0.032,
                    "metadata": {"section_type": "specs"},
                }
            ],
            "count": 1,
        },
    )

    with patch.object(service.tool_registry, "execute_tool", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = rag_tool_result

        req = AgentRunRequest(prompt="What is the turbine operating temperature?", max_iterations=3)
        resp = await service.run(request=req, user=test_user, db=db_session)

        assert resp.status == "completed"
        assert resp.citations_verified is True
        assert "turbine_specs.docx" in resp.verified_citations
        assert len(resp.citation_details) == 1

        detail = resp.citation_details[0]
        assert detail.source_file == "turbine_specs.docx"
        assert detail.page_number == 3
        assert detail.status == "SUPPORTED"
        assert detail.chunk_id == mock_chunk_id
        assert detail.document_id == mock_doc_id
        assert detail.section == "SPECS"
        assert "1250" in detail.ground_truth_numbers
        assert "1250" in detail.extracted_numbers
        assert detail.dense_similarity == 0.91
        assert detail.sparse_score == 14.5
        assert detail.rrf_score == 0.032
        assert "1250 C" in (detail.chunk_content or "")

