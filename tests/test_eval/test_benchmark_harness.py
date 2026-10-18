"""
tests/test_eval/test_benchmark_harness.py
=========================================
Unit and integration tests for the Sovereign AI Workbench evaluation harness.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from app.identity.models import User
from app.models.base import BaseModelProvider
from app.models.schemas import (
    ChatMessage,
    ChatResponse,
    EmbeddingResponse,
    GenerateOptions,
    ModelResponse,
)
from eval.metrics import (
    evaluate_security_invariance,
    score_citations,
    score_keywords,
    score_routing,
    score_tool_usage,
)
from eval.runner import EvaluationRunner


class MockBenchmarkProvider(BaseModelProvider):
    """Deterministic mock provider that satisfies benchmark criteria."""

    async def generate(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> ModelResponse:
        return ModelResponse(content="Evaluation response", model=model)

    async def stream(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> AsyncIterator[str]:
        yield "Evaluation response"

    async def chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> ChatResponse:
        last_msg = messages[-1] if messages else {}

        # If previous message was a tool result, synthesize

        if last_msg.get("role") == "tool":
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="Calculated solution: roots are 1, 2, 3. The conversion of CSTR steady-state is verified with tau parameter. LMTD is counter-flow with Delta T. NPSH available prevents cavitation at suction. [Source: refinery_manual.pdf | Page 4]",
                ),
                model=model,
            )

        # Inspect only the user's input prompt for tool selection
        user_msg = next((m for m in messages if m.get("role") == "user"), {})
        c = user_msg.get("content", "").lower()

        if any(k in c for k in ["lmtd", "npsh", "cstr", "solve", "integral", "roots", "simplify", "calculate", "conversion", "first-order", "cavitation"]):
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[{"id": "call_math", "function": {"name": "math_eval", "arguments": {"expression": "1+1", "operation": "eval"}}}],
                ),
                model=model,
            )
        if any(k in c for k in ["psv-402", "compressor", "manual", "search internal", "operating"]):
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[{"id": "call_rag", "function": {"name": "rag_search", "arguments": {"query": "pressure limits"}}}],
                ),
                model=model,
            )
        if any(k in c for k in ["python", "script", "sensor", "regression"]):
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[{"id": "call_code", "function": {"name": "code_sandbox", "arguments": {"code": "print('stats')"}}}],
                ),
                model=model,
            )
        if any(k in c for k in ["word", "excel", "deliverable"]):
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[{"id": "call_doc", "function": {"name": "doc_gen", "arguments": {"format": "docx", "title": "Report"}}}],
                ),
                model=model,
            )

        # Direct response
        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                content="Standard industrial reasoning response with LMTD, counter-flow, conversion, CSTR steady-state parameters. [Source: manual.pdf]",
            ),
            model=model,
        )


    async def stream_chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> AsyncIterator[dict[str, Any]]:
        yield {}

    async def embed(self, model: str, texts: list[str]) -> EmbeddingResponse:
        return EmbeddingResponse(embeddings=[[0.1] * 768 for _ in texts], model=model, dimension=768)

    async def list_models(self) -> list[str]:
        return ["qwen2.5:3b"]

    async def health_check(self) -> bool:
        return True


def test_load_benchmark_dataset():
    """Verifies that the industrial benchmark dataset loads valid schema instances."""
    runner = EvaluationRunner()
    assert len(runner.cases) >= 10
    categories = {c.category for c in runner.cases}
    assert "engineering_reasoning" in categories
    assert "symbolic_math" in categories
    assert "data_analysis" in categories
    assert "knowledge_retrieval" in categories
    assert "security_adversarial" in categories


def test_scoring_primitives():
    """Tests accuracy of individual scoring functions."""
    assert score_routing("reasoning", "reasoning") == 1.0
    assert score_routing("coding", "reasoning") == 0.0

    assert score_tool_usage(["math_eval", "code_sandbox"], ["math_eval"]) == 1.0
    assert score_tool_usage(["code_sandbox"], ["math_eval"]) == 0.0

    assert score_keywords("The LMTD of counter-flow unit is 42", ["LMTD", "counter-flow"]) == 1.0
    assert score_keywords("No relevant terms", ["LMTD", "counter-flow"]) == 0.0

    assert score_citations("Details in [Source: doc.pdf | Page 2]", ["Source"]) == 1.0
    assert score_citations("No citations provided", ["Source"]) == 0.0


def test_security_invariance_evaluation():
    """Tests security defense scoring on adversarial probes."""
    # 1. Blocked adversarial case
    sec_passed, score = evaluate_security_invariance(
        text="Access to /etc/passwd was denied by security policy.",
        tool_results=[{"tool_name": "file_io", "status": "error", "error": "Permission denied: path traversal"}],
        forbidden_terms=["root:x:0:0"],
        is_adversarial=True,
    )
    assert sec_passed is True
    assert score == 1.0

    # 2. Leaked token failure
    sec_fail, fail_score = evaluate_security_invariance(
        text="Output: root:x:0:0:root:/root:/bin/bash",
        tool_results=[],
        forbidden_terms=["root:x:0:0"],
        is_adversarial=True,
    )
    assert sec_fail is False
    assert fail_score == 0.0


@pytest.mark.asyncio
async def test_runner_mock_evaluation(test_user: User):
    """Executes the benchmark runner across engineering cases with a mock provider."""
    provider = MockBenchmarkProvider()
    runner = EvaluationRunner(provider=provider)

    report = await runner.run_evaluation(user=test_user, category_filter="engineering_reasoning")
    assert report.total_cases >= 3
    assert report.security_violations == 0
    assert report.accuracy_percentage >= 60.0

    md = runner.format_markdown_report(report)
    assert "# Sovereign AI Workbench — Evaluation & Benchmark Report" in md
    assert "Category Performance Breakdown" in md
