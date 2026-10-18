"""
eval/runner.py
==============
Automated execution harness for running industrial benchmark evaluations.
Supports deterministic mock providers for CI and live Ollama models for on-prem benchmarking.
"""

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agent.service import AgentService
from app.agent.state import AgentRunRequest
from app.identity.models import User
from app.models.base import BaseModelProvider
from app.models.registry import get_default_provider
from sqlalchemy.ext.asyncio import AsyncSession

from eval.metrics import evaluate_case
from eval.schemas import BenchmarkCase, CaseEvaluationResult, EvaluationReport

logger = logging.getLogger("sovereign.eval.runner")

DEFAULT_DATASET_PATH = Path(__file__).parent / "dataset" / "industrial_benchmark_v1.json"


class EvaluationRunner:
    """Orchestrates evaluation runs across benchmark cases and aggregates metric reports."""

    def __init__(
        self,
        dataset_path: Path | None = None,
        provider: BaseModelProvider | None = None,
    ) -> None:
        self.dataset_path = dataset_path or DEFAULT_DATASET_PATH
        self.provider = provider or get_default_provider()
        self.cases = self._load_dataset()

    def _load_dataset(self) -> list[BenchmarkCase]:
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Benchmark dataset not found at {self.dataset_path}")

        with open(self.dataset_path, encoding="utf-8") as f:
            raw_cases = json.load(f)

        return [BenchmarkCase(**c) for c in raw_cases]

    async def run_evaluation(
        self,
        user: User,
        db: AsyncSession | None = None,
        category_filter: str | None = None,
        progress_callback: Any | None = None,
    ) -> EvaluationReport:
        """Executes all (or filtered) benchmark cases and computes overall performance metrics."""
        cases_to_run = self.cases
        if category_filter:
            cases_to_run = [c for c in self.cases if c.category == category_filter]

        service = AgentService(provider=self.provider)
        case_results: list[CaseEvaluationResult] = []
        durations: list[float] = []
        security_violations = 0
        total_cases_count = len(cases_to_run)

        for case in cases_to_run:
            logger.info("Evaluating benchmark case [%s]: %s", case.id, case.title)
            start_case = time.perf_counter()

            req = AgentRunRequest(
                prompt=case.prompt,
                max_iterations=case.max_allowed_iterations,
            )

            try:
                run_res = await service.run(request=req, user=user, db=db)
                case_duration = (time.perf_counter() - start_case) * 1000
                durations.append(case_duration)

                actual_tools = [tr.get("tool_name", "") for tr in run_res.tool_results]
                eval_res = evaluate_case(
                    case=case,
                    actual_role=run_res.route_decision.role,
                    actual_tools=actual_tools,
                    final_response=run_res.response,
                    tool_results=run_res.tool_results,
                    iterations_used=run_res.iterations,
                    duration_ms=case_duration,
                )

                if not eval_res.security_passed:
                    security_violations += 1

                case_results.append(eval_res)

                if progress_callback:
                    await progress_callback(eval_res, len(case_results), total_cases_count)

            except Exception as exc:
                case_duration = (time.perf_counter() - start_case) * 1000
                logger.error("Error executing case [%s]: %s", case.id, exc)
                err_res = CaseEvaluationResult(
                    case_id=case.id,
                    category=case.category,
                    title=case.title,
                    prompt=case.prompt,
                    expected_role=case.expected_role,
                    actual_role="error",
                    expected_tools=case.expected_tools,
                    actual_tools=[],
                    passed=False,
                    score=0.0,
                    routing_passed=False,
                    tools_passed=False,
                    citations_passed=False,
                    security_passed=True,
                    iterations_used=0,
                    duration_ms=round(case_duration, 2),
                    errors=[f"Execution exception: {exc}"],
                    failure_diagnosis=f"Execution exception during evaluation: {exc}",
                )
                case_results.append(err_res)
                if progress_callback:
                    await progress_callback(err_res, len(case_results), total_cases_count)

        total = len(case_results)
        passed = sum(1 for r in case_results if r.passed)
        overall_score = sum(r.score for r in case_results) / total if total > 0 else 0.0
        acc_pct = (passed / total * 100.0) if total > 0 else 0.0

        # Category scores
        cat_scores: dict[str, list[float]] = {}
        for r in case_results:
            cat_scores.setdefault(r.category, []).append(r.score)
        category_summary = {
            cat: round(sum(scores) / len(scores), 3)
            for cat, scores in cat_scores.items()
        }

        durations.sort()
        avg_dur = sum(durations) / len(durations) if durations else 0.0
        p95_idx = int(len(durations) * 0.95) if durations else 0
        p95_dur = durations[p95_idx] if durations else 0.0

        if "mock" in type(self.provider).__name__.lower():
            provider_type = "mock"
            model_name = "mock-benchmark-evaluator"
        else:
            provider_type = "ollama"
            model_name = "llama3.2:latest"

        return EvaluationReport(
            timestamp=datetime.now(UTC).isoformat(),
            benchmark_version="industrial_benchmark_v1",
            model_name=model_name,
            provider_type=provider_type,
            total_cases=total,
            passed_cases=passed,
            failed_cases=total - passed,
            overall_score=round(overall_score, 3),
            accuracy_percentage=round(acc_pct, 2),
            category_scores=category_summary,
            average_duration_ms=round(avg_dur, 2),
            p95_duration_ms=round(p95_dur, 2),
            results=case_results,
            security_violations=security_violations,
        )

    @staticmethod
    def format_markdown_report(report: EvaluationReport) -> str:
        """Formats an EvaluationReport into GitHub-flavored Markdown."""
        lines = [
            "# Sovereign AI Workbench — Evaluation & Benchmark Report",
            f"**Execution Timestamp:** `{report.timestamp}`  ",
            f"**Total Scenarios:** `{report.total_cases}` | **Passed:** `{report.passed_cases}` | **Failed:** `{report.failed_cases}`  ",
            f"**Overall Accuracy:** `{report.accuracy_percentage:.1f}%` | **Composite Score:** `{report.overall_score:.3f}`  ",
            f"**Security Violations:** `{report.security_violations}` (Target: 0)  ",
            f"**Latency:** Avg `{report.average_duration_ms:.1f}ms` | p95 `{report.p95_duration_ms:.1f}ms`  ",
            "",
            "## Category Performance Breakdown",
            "| Category | Score | Status |",
            "| :--- | :---: | :---: |",
        ]

        for cat, score in report.category_scores.items():
            status_icon = "PASS" if score >= 0.70 else "WARN"
            lines.append(f"| `{cat}` | `{score:.3f}` | {status_icon} |")

        lines.extend([
            "",
            "## Detailed Scenario Execution Results",
            "| Scenario ID | Category | Score | Routing | Tools | Security | Duration | Status |",
            "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ])

        for r in report.results:
            st = "PASS" if r.passed else "FAIL"
            r_flag = "OK" if r.routing_passed else "MISMATCH"
            t_flag = "OK" if r.tools_passed else "NO"
            s_flag = "SECURE" if r.security_passed else "VIOLATION"
            lines.append(
                f"| `{r.case_id}` | `{r.category}` | `{r.score:.2f}` | {r_flag} | {t_flag} | {s_flag} | {r.duration_ms:.0f}ms | **{st}** |"
            )

        return "\n".join(lines) + "\n"
