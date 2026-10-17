"""
app/agent/router.py
===================
FastAPI endpoints for sovereign agent task execution and real-time SSE streaming.
Strictly requires authenticated session (Authorization: Bearer <token>) and enforces RBAC.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agent.service import AgentService
from app.agent.state import AgentRunRequest, AgentRunResponse
from app.database import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.models.registry import load_models_config

router = APIRouter(prefix="/agent", tags=["Agent Orchestration"])


_agent_service: AgentService | None = None


def get_agent_service() -> AgentService:
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService()
    return _agent_service



@router.post(
    "/run",
    response_model=AgentRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute bounded agent task workflow",
    description="Synchronously executes the ReAct LangGraph loop with tool dispatch and RBAC bounds.",
)
async def run_agent_task(
    request: AgentRunRequest,
    current_user: User = Depends(get_current_user),

    db: AsyncSession = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> AgentRunResponse:
    """Executes a bounded multi-step agent task."""
    try:
        return await service.run(request=request, user=current_user, db=db)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent execution error: {exc}",
        ) from exc


@router.post(
    "/stream",
    summary="Stream agent reasoning and tool executions via SSE",
    description="Streams Server-Sent Events (SSE) representing agent thoughts, tool dispatches, and final response.",
)
async def stream_agent_task(
    request: AgentRunRequest,
    current_user: User = Depends(get_current_user),

    db: AsyncSession = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> EventSourceResponse:
    """Streams live thought traces, tool invocations, and synthesized responses."""
    async def event_generator() -> AsyncIterator[dict[str, Any]]:
        try:
            async for item in service.stream(request=request, user=current_user, db=db):
                yield {
                    "event": item["event"],
                    "data": json.dumps(item["data"]),
                }
        except Exception as exc:
            yield {
                "event": "error",
                "data": json.dumps({"error": str(exc)}),
            }

    return EventSourceResponse(event_generator())


@router.get(
    "/models",
    response_model=dict[str, Any],
    summary="List configured local agent models and capabilities",
)
async def list_agent_models(
    current_user: User = Depends(get_current_user),

) -> dict[str, Any]:
    """Returns local model assignments for reasoning, coding, vision, and embeddings."""
    return load_models_config()

