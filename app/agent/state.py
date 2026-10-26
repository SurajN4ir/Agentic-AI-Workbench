"""
app/agent/state.py
==================
State schema and API request/response models for LangGraph agent orchestration.
Enforces iteration limits, RBAC context, and structured audit metadata.
"""

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

from app.routing.schemas import FileMetadata, RouteDecision


class WorkbenchState(TypedDict, total=False):
    """
    Internal State schema passed between nodes in the LangGraph StateGraph.
    All state transitions are deterministic and bound by max_iterations.
    """
    session_id: str
    user_id: str
    user_role: str
    username: str
    prompt: str
    file_metadata: list[dict[str, Any]]
    route_decision: dict[str, Any] | None
    model_tag: str
    messages: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    iteration_count: int
    tool_retry_count: int
    max_iterations: int
    thinking_trace: list[str]
    artifacts: list[dict[str, Any]]
    final_response: str | None
    status: Literal["initialized", "routing", "reasoning", "executing_tools", "synthesizing", "completed", "max_iterations_reached", "error"]
    error: str | None
    duration_ms: float | None


class AgentRunRequest(BaseModel):
    """Request payload for running an agent task."""
    prompt: str = Field(..., min_length=1, description="User instruction or task prompt")
    session_id: str | None = Field(default=None, description="Optional persistent session identifier (UUID)")
    role_override: str | None = Field(default=None, description="Optional manual role override: reasoning, coding, auto")
    max_iterations: int = Field(default=8, ge=1, le=15, description="Safety bound: maximum tool execution loops")
    file_metadata: list[FileMetadata] | None = Field(default=None, description="Optional metadata for attached files")


class CitationDetail(BaseModel):
    """Detailed audit provenance for an individual citation and claimed fact."""
    citation_text: str
    source_file: str
    page_number: int | None = None
    associated_sentence: str = ""
    status: str
    reason: str = ""
    extracted_numbers: list[str] = Field(default_factory=list)
    ground_truth_numbers: list[str] = Field(default_factory=list)
    chunk_id: str | None = None
    document_id: str | None = None
    section: str | None = None
    chunk_content: str | None = None
    similarity: float = 0.0
    dense_similarity: float = 0.0
    dense_rank: int = 1
    sparse_score: float = 0.0
    sparse_rank: int = 1
    rrf_score: float = 0.0


class AgentRunResponse(BaseModel):
    """Structured response returned by completed agent execution."""
    session_id: str
    status: str
    route_decision: RouteDecision
    model_used: str
    response: str
    thinking_trace: list[str] = Field(default_factory=list)
    iterations: int
    tool_calls_count: int
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: float
    citations_verified: bool = True
    verified_citations: list[str] = Field(default_factory=list)
    ungrounded_citations: list[str] = Field(default_factory=list)
    citation_details: list[CitationDetail] = Field(default_factory=list)
    evidence_fallback_used: bool = False

