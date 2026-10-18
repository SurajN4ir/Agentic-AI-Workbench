"""
app/benchmarks/schemas.py
=========================
Pydantic schemas for the Benchmark & Evaluation API endpoints.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class BenchmarkCaseOut(BaseModel):
    """Scenario specification from the benchmark dataset."""

    id: str
    category: str
    title: str
    prompt: str
    expected_role: str
    expected_tools: list[str] = Field(default_factory=list)
    expected_citations: list[str] = Field(default_factory=list)
    max_allowed_iterations: int
    is_adversarial: bool


class CaseResultOut(BaseModel):
    """Detailed score and diagnostic results for an individual scenario."""

    case_id: str
    category: str
    title: str = ""
    prompt: str = ""
    expected_role: str = ""
    actual_role: str = ""
    expected_tools: list[str] = Field(default_factory=list)
    actual_tools: list[str] = Field(default_factory=list)
    passed: bool
    score: float
    routing_passed: bool
    tools_passed: bool
    citations_passed: bool
    security_passed: bool
    iterations_used: int
    duration_ms: float
    output_preview: str = ""
    errors: list[str] = Field(default_factory=list)
    failure_diagnosis: str = ""


class BenchmarkRunSummary(BaseModel):
    """Lightweight summary of an evaluation run for historical trend listings."""

    id: UUID
    timestamp: str
    benchmark_version: str
    model_name: str
    provider_type: str
    category_filter: str | None
    status: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    overall_score: float
    accuracy_percentage: float
    security_violations: int
    average_duration_ms: float
    triggered_by_username: str


class BenchmarkRunDetail(BaseModel):
    """Comprehensive evaluation run details including all scenario drill-down data."""

    id: UUID
    timestamp: str
    benchmark_version: str
    model_name: str
    provider_type: str
    category_filter: str | None
    status: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    overall_score: float
    accuracy_percentage: float
    security_violations: int
    average_duration_ms: float
    p95_duration_ms: float
    category_scores: dict[str, float]
    results: list[CaseResultOut]
    triggered_by_username: str
    error_message: str | None = None


class BenchmarkRunRequest(BaseModel):
    """Payload to trigger an industrial benchmark evaluation run."""

    category: str | None = Field(default=None, description="Optional category filter")
    mock: bool = Field(default=False, description="Use deterministic mock provider instead of local Ollama")


class BenchmarkProgressOut(BaseModel):
    """Real-time progress status of an active or recent benchmark evaluation."""

    run_id: str
    status: str  # "idle", "running", "completed", "failed"
    completed_cases: int
    total_cases: int
    current_case_id: str | None = None
    current_case_title: str | None = None
    elapsed_ms: float = 0.0
    error_message: str | None = None
    report: BenchmarkRunDetail | None = None
