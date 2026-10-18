"""
tests/test_eval/test_benchmark_harness.py
=========================================
Unit and integration tests for the Sovereign AI Workbench evaluation harness.
"""


import pytest
from app.identity.models import User
from eval.metrics import (
    evaluate_security_invariance,
    score_citations,
    score_keywords,
    score_routing,
    score_tool_usage,
)
from eval.mock_provider import MockBenchmarkProvider
from eval.runner import EvaluationRunner


def test_load_benchmark_dataset() -> None:
    """Verifies that the industrial benchmark dataset loads valid schema instances."""
    runner = EvaluationRunner()
    assert len(runner.cases) >= 10
    categories = {c.category for c in runner.cases}
    assert "engineering_reasoning" in categories
    assert "symbolic_math" in categories
    assert "data_analysis" in categories
    assert "knowledge_retrieval" in categories
    assert "security_adversarial" in categories


def test_scoring_primitives() -> None:
    """Tests accuracy of individual scoring functions."""
    assert score_routing("reasoning", "reasoning") == 1.0
    assert score_routing("coding", "reasoning") == 0.0

    assert score_tool_usage(["math_eval", "code_sandbox"], ["math_eval"]) == 1.0
    assert score_tool_usage(["code_sandbox"], ["math_eval"]) == 0.0

    assert score_keywords("The LMTD of counter-flow unit is 42", ["LMTD", "counter-flow"]) == 1.0
    assert score_keywords("No relevant terms", ["LMTD", "counter-flow"]) == 0.0

    assert score_citations("Details in [Source: doc.pdf | Page 2]", ["Source"]) == 1.0
    assert score_citations("No citations provided", ["Source"]) == 0.0


def test_security_invariance_evaluation() -> None:
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
async def test_runner_mock_evaluation(test_user: User) -> None:
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
