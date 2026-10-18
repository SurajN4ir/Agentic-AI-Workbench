"""
eval/schemas.py
===============
Data structures for the Sovereign Industrial AI Benchmark and Evaluation Harness.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class BenchmarkCase(BaseModel):
    """An individual industrial test scenario with ground-truth expectations."""

    id: str = Field(..., description="Unique scenario ID, e.g. 'ENG-01', 'SEC-04'")
    category: Literal[
        "engineering_reasoning",
        "symbolic_math",
        "data_analysis",
        "knowledge_retrieval",
        "deliverable_generation",
        "security_adversarial",
    ]
    title: str = Field(..., description="Short descriptive title")
    prompt: str = Field(..., description="Input prompt for the workbench")
    file_metadata: list[dict[str, Any]] = Field(default_factory=list, description="Attached files metadata")
    expected_role: str = Field(default="reasoning", description="Expected waterfall routing role")
    expected_tools: list[str] = Field(default_factory=list, description="Tools that should be invoked")
    expected_keywords: list[str] = Field(default_factory=list, description="Keywords expected in final response")
    expected_citations: list[str] = Field(default_factory=list, description="Source documents that must be cited")
    forbidden_terms: list[str] = Field(default_factory=list, description="Forbidden terms (e.g. external domains)")
    max_allowed_iterations: int = Field(default=8, description="Maximum iterations permitted")
    is_adversarial: bool = Field(default=False, description="Whether case tests security defenses")


class CaseEvaluationResult(BaseModel):
    """Detailed scoring result for a single benchmark case."""

    case_id: str
    category: str
    title: str = ""
    prompt: str = ""
    expected_role: str = ""
    actual_role: str = ""
    expected_tools: list[str] = Field(default_factory=list)
    actual_tools: list[str] = Field(default_factory=list)
    passed: bool
    score: float = Field(ge=0.0, le=1.0, description="Normalized score 0.0 to 1.0")
    routing_passed: bool
    tools_passed: bool
    citations_passed: bool
    security_passed: bool
    iterations_used: int
    duration_ms: float
    output_preview: str = ""
    errors: list[str] = Field(default_factory=list)
    failure_diagnosis: str = ""


class EvaluationReport(BaseModel):
    """Comprehensive summary of an entire benchmark evaluation run."""

    timestamp: str
    benchmark_version: str = "industrial_benchmark_v1"
    model_name: str = "llama3.2:latest"
    provider_type: str = "ollama"
    total_cases: int
    passed_cases: int
    failed_cases: int
    overall_score: float
    accuracy_percentage: float
    category_scores: dict[str, float]
    average_duration_ms: float
    p95_duration_ms: float
    results: list[CaseEvaluationResult]
    security_violations: int = 0
