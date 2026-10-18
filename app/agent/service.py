"""
app/agent/service.py
====================
High-level Agent Service providing task orchestration, state persistence,
and real-time Server-Sent Events (SSE) streaming of agent thought traces and tool calls.
"""

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.citation_validator import CitationValidator
from app.agent.graph import AgentGraphBuilder
from app.agent.state import AgentRunRequest, AgentRunResponse, WorkbenchState
from app.audit.service import emit_event
from app.identity.models import User
from app.models.base import BaseModelProvider
from app.models.registry import get_default_provider
from app.routing.schemas import RouteDecision
from app.routing.service import TaskRouter
from app.tools.registry import ToolRegistry, get_tool_registry

logger = logging.getLogger("sovereign.agent.service")


class AgentService:
    """Orchestrates agent execution, state persistence, and event streaming."""

    def __init__(
        self,
        provider: BaseModelProvider | None = None,
        tool_registry: ToolRegistry | None = None,
        task_router: TaskRouter | None = None,
    ) -> None:
        self.provider = provider or get_default_provider()
        self.tool_registry = tool_registry or get_tool_registry()
        self.task_router = task_router or TaskRouter()

    async def run(
        self,
        request: AgentRunRequest,
        user: User,
        db: AsyncSession | None = None,
    ) -> AgentRunResponse:
        """Executes a complete agent task run and returns structured results."""
        start_time = time.perf_counter()
        session_id = request.session_id or str(uuid.uuid4())

        builder = AgentGraphBuilder(
            provider=self.provider,
            tool_registry=self.tool_registry,
            task_router=self.task_router,
            db=db,
        )
        graph = builder.build()

        file_meta_list = [fm.model_dump() for fm in request.file_metadata] if request.file_metadata else []
        route_decision = {"role": request.role_override} if request.role_override else None

        initial_state: WorkbenchState = {
            "session_id": session_id,
            "user_id": str(user.id),
            "user_role": user.role,
            "username": user.username,
            "prompt": request.prompt,
            "file_metadata": file_meta_list,
            "route_decision": route_decision,
            "max_iterations": request.max_iterations,
            "iteration_count": 0,
            "status": "initialized",
            "messages": [],
            "tool_calls": [],
            "tool_results": [],
            "thinking_trace": [],
            "artifacts": [],
        }

        try:
            final_state = await graph.ainvoke(initial_state)
        except Exception as exc:
            logger.exception("Agent graph execution failed: %s", exc)
            duration_ms = (time.perf_counter() - start_time) * 1000
            if db is not None:
                await emit_event(
                    db=db,
                    event_type="agent_task_failed",
                    user_id=str(user.id),
                    resource_type="agent_task",
                    resource_id=session_id,
                    outcome="error",
                    detail={"error": str(exc), "prompt": request.prompt},
                    summary=f"Agent task failed for session {session_id}",
                )
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000
        raw_decision = final_state.get("route_decision") or {
            "role": "reasoning",
            "confidence": 1.0,
            "method": "default",
            "reasoning": "Standard execution",
        }
        typed_decision = RouteDecision(**raw_decision) if isinstance(raw_decision, dict) else raw_decision

        tool_results = final_state.get("tool_results", [])
        artifacts = final_state.get("artifacts", [])
        raw_response = final_state.get("final_response") or ""

        # Validate citations against genuine retrieved tool evidence
        citation_validator = CitationValidator()
        val_result = citation_validator.validate(raw_response, tool_results)
        final_response_text = val_result.sanitized_response if not val_result.is_valid else raw_response

        # Emit audit trail event
        if db is not None:
            await emit_event(
                db=db,
                event_type="agent_task_completed",
                user_id=str(user.id),
                resource_type="agent_task",
                resource_id=session_id,
                outcome=final_state.get("status", "completed"),
                detail={
                    "iterations": final_state.get("iteration_count", 0),
                    "tool_calls_count": len(tool_results),
                    "duration_ms": round(duration_ms, 2),
                    "role": typed_decision.role,
                    "citations_verified": val_result.is_valid,
                    "verified_citations": val_result.verified_citations,
                    "ungrounded_citations": val_result.ungrounded_citations,
                },
                summary=f"Completed agent task ({final_state.get('iteration_count', 0)} iters, {len(tool_results)} tools)",
            )

        return AgentRunResponse(
            session_id=session_id,
            status=final_state.get("status", "completed"),
            route_decision=typed_decision,
            model_used=final_state.get("model_tag", "qwen2.5:3b"),
            response=final_response_text,
            thinking_trace=final_state.get("thinking_trace", []),
            iterations=final_state.get("iteration_count", 0),
            tool_calls_count=len(tool_results),
            tool_results=tool_results,
            artifacts=artifacts,
            duration_ms=round(duration_ms, 2),
            citations_verified=val_result.is_valid,
            verified_citations=val_result.verified_citations,
            ungrounded_citations=val_result.ungrounded_citations,
        )

    async def stream(
        self,
        request: AgentRunRequest,
        user: User,
        db: AsyncSession | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Asynchronously streams node transition events and outputs via Server-Sent Events (SSE).
        Yields typed event payloads:
          - {"event": "status", "data": ...}
          - {"event": "route", "data": ...}
          - {"event": "thinking", "data": ...}
          - {"event": "tool_call", "data": ...}
          - {"event": "tool_result", "data": ...}
          - {"event": "done", "data": ...}
        """
        start_time = time.perf_counter()
        session_id = request.session_id or str(uuid.uuid4())

        yield {
            "event": "status",
            "data": {"status": "starting", "session_id": session_id},
        }

        builder = AgentGraphBuilder(
            provider=self.provider,
            tool_registry=self.tool_registry,
            task_router=self.task_router,
            db=db,
        )
        graph = builder.build()

        file_meta_list = [fm.model_dump() for fm in request.file_metadata] if request.file_metadata else []
        route_decision = {"role": request.role_override} if request.role_override else None

        initial_state: WorkbenchState = {
            "session_id": session_id,
            "user_id": str(user.id),
            "user_role": user.role,
            "username": user.username,
            "prompt": request.prompt,
            "file_metadata": file_meta_list,
            "route_decision": route_decision,
            "max_iterations": request.max_iterations,
            "iteration_count": 0,
            "status": "initialized",
            "messages": [],
            "tool_calls": [],
            "tool_results": [],
            "thinking_trace": [],
            "artifacts": [],
        }

        last_thinking_count = 0
        last_tool_result_count = 0
        all_tool_results: list[dict[str, Any]] = []

        async for chunk in graph.astream(initial_state, stream_mode="updates"):
            for node_name, node_update in chunk.items():
                if node_name == "route_node":
                    yield {
                        "event": "route",
                        "data": node_update.get("route_decision"),
                    }

                elif node_name == "reason_node":
                    # Check for new thinking trace
                    traces = node_update.get("thinking_trace", [])
                    if len(traces) > last_thinking_count:
                        for tr in traces[last_thinking_count:]:
                            yield {
                                "event": "thinking",
                                "data": {"content": tr},
                            }
                        last_thinking_count = len(traces)

                    # Check for tool calls
                    calls = node_update.get("tool_calls", [])
                    if calls:
                        for c in calls:
                            func = c.get("function", {})
                            yield {
                                "event": "tool_call",
                                "data": {
                                    "id": c.get("id"),
                                    "name": func.get("name"),
                                    "arguments": func.get("arguments"),
                                    "requires_confirmation": False,
                                },
                            }

                elif node_name == "tool_node":
                    results = node_update.get("tool_results", [])
                    all_tool_results = results
                    if len(results) > last_tool_result_count:
                        for res in results[last_tool_result_count:]:
                            yield {
                                "event": "tool_result",
                                "data": res,
                            }
                        last_tool_result_count = len(results)

                elif node_name == "synthesize_node":
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    raw_res = node_update.get("final_response") or ""
                    val_res = CitationValidator().validate(raw_res, all_tool_results)
                    final_text = val_res.sanitized_response if not val_res.is_valid else raw_res
                    yield {
                        "event": "done",
                        "data": {
                            "response": final_text,
                            "status": node_update.get("status"),
                            "duration_ms": round(duration_ms, 2),
                            "citations_verified": val_res.is_valid,
                            "verified_citations": val_res.verified_citations,
                            "ungrounded_citations": val_res.ungrounded_citations,
                        },
                    }
