"""
app/benchmarks/service.py
=========================
Core service orchestrating benchmark scenario introspection, evaluation runs,
live progress tracking, and database persistence.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from eval.mock_provider import MockBenchmarkProvider
from eval.runner import DEFAULT_DATASET_PATH, EvaluationRunner
from eval.schemas import CaseEvaluationResult, EvaluationReport
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.benchmarks.models import BenchmarkRun
from app.benchmarks.schemas import (
    BenchmarkCaseOut,
    BenchmarkProgressOut,
    BenchmarkRunDetail,
    BenchmarkRunRequest,
    BenchmarkRunSummary,
    CaseResultOut,
)
from app.database import AsyncSessionLocal
from app.identity.models import User

logger = logging.getLogger("sovereign.benchmarks.service")

BASELINE_FILE = Path(__file__).resolve().parent.parent.parent / "eval" / "dataset" / "verified_baseline_report.json"


class BenchmarkService:
    """Manages benchmark evaluations, progress tracking, and database persistence."""

    _active_runs: dict[str, dict[str, Any]] = {}

    def __init__(self) -> None:
        self.dataset_path = DEFAULT_DATASET_PATH

    def get_scenarios(self) -> list[BenchmarkCaseOut]:
        """Returns all configured industrial benchmark scenarios."""
        if not self.dataset_path.exists():
            return []

        with open(self.dataset_path, encoding="utf-8") as f:
            raw_cases = json.load(f)

        return [
            BenchmarkCaseOut(
                id=c["id"],
                category=c["category"],
                title=c["title"],
                prompt=c["prompt"],
                expected_role=c.get("expected_role", "reasoning"),
                expected_tools=c.get("expected_tools", []),
                expected_citations=c.get("expected_citations", []),
                max_allowed_iterations=c.get("max_allowed_iterations", 8),
                is_adversarial=c.get("is_adversarial", False),
            )
            for c in raw_cases
        ]

    async def _seed_baseline_if_needed(self, db: AsyncSession) -> BenchmarkRun | None:
        """Seeds initial verified benchmark baseline into database if no runs exist."""
        if not BASELINE_FILE.exists():
            return None

        try:
            with open(BASELINE_FILE, encoding="utf-8") as f:
                data = json.load(f)

            baseline_run = BenchmarkRun(
                id=uuid.uuid4(),
                timestamp=datetime.fromisoformat(data["timestamp"]),
                benchmark_version=data.get("benchmark_version", "industrial_benchmark_v1"),
                model_name=data.get("model_name", "llama3.2:latest"),
                provider_type=data.get("provider_type", "ollama"),
                category_filter=None,
                status="completed",
                total_cases=data["total_cases"],
                passed_cases=data["passed_cases"],
                failed_cases=data["failed_cases"],
                overall_score=data["overall_score"],
                accuracy_percentage=data["accuracy_percentage"],
                security_violations=data["security_violations"],
                average_duration_ms=data["average_duration_ms"],
                p95_duration_ms=data["p95_duration_ms"],
                category_scores=data["category_scores"],
                results=data["results"],
                triggered_by_username="system_verified_baseline",
            )
            db.add(baseline_run)
            await db.commit()
            await db.refresh(baseline_run)
            logger.info("Successfully seeded verified benchmark baseline into database.")
            return baseline_run
        except Exception as exc:
            logger.error("Failed to seed benchmark baseline: %s", exc)
            await db.rollback()
            return None

    async def get_latest_run(self, db: AsyncSession) -> BenchmarkRunDetail | None:
        """Returns the most recent completed evaluation run."""
        stmt = (
            select(BenchmarkRun)
            .where(BenchmarkRun.status == "completed")
            .order_by(desc(BenchmarkRun.timestamp))
            .limit(1)
        )
        res = await db.execute(stmt)
        run = res.scalar_one_or_none()

        if not run:
            run = await self._seed_baseline_if_needed(db)

        if not run:
            return None

        return self._to_detail(run)

    async def get_run_history(self, db: AsyncSession, limit: int = 30) -> list[BenchmarkRunSummary]:
        """Returns chronological history of benchmark runs."""
        stmt = (
            select(BenchmarkRun)
            .order_by(desc(BenchmarkRun.timestamp))
            .limit(limit)
        )
        res = await db.execute(stmt)
        runs = res.scalars().all()

        if not runs:
            baseline = await self._seed_baseline_if_needed(db)
            runs = [baseline] if baseline else []

        return [
            BenchmarkRunSummary(
                id=r.id,
                timestamp=r.timestamp.isoformat(),
                benchmark_version=r.benchmark_version,
                model_name=r.model_name,
                provider_type=r.provider_type,
                category_filter=r.category_filter,
                status=r.status,
                total_cases=r.total_cases,
                passed_cases=r.passed_cases,
                failed_cases=r.failed_cases,
                overall_score=r.overall_score,
                accuracy_percentage=r.accuracy_percentage,
                security_violations=r.security_violations,
                average_duration_ms=r.average_duration_ms,
                triggered_by_username=r.triggered_by_username,
            )
            for r in runs
        ]

    async def get_run_by_id(self, run_id: UUID, db: AsyncSession) -> BenchmarkRunDetail | None:
        """Returns detailed report for a specific run ID."""
        stmt = select(BenchmarkRun).where(BenchmarkRun.id == run_id)
        res = await db.execute(stmt)
        run = res.scalar_one_or_none()
        if not run:
            return None
        return self._to_detail(run)

    def get_progress(self, run_id: str) -> BenchmarkProgressOut:
        """Returns live execution progress for an active or completed evaluation."""
        if run_id in self._active_runs:
            data = self._active_runs[run_id]
            return BenchmarkProgressOut(
                run_id=run_id,
                status=data.get("status", "running"),
                completed_cases=data.get("completed_cases", 0),
                total_cases=data.get("total_cases", 0),
                current_case_id=data.get("current_case_id"),
                current_case_title=data.get("current_case_title"),
                elapsed_ms=round((time.perf_counter() - data["start_time"]) * 1000, 1),
                error_message=data.get("error_message"),
                report=data.get("report"),
            )

        return BenchmarkProgressOut(
            run_id=run_id,
            status="idle",
            completed_cases=0,
            total_cases=0,
            error_message="Run not found or inactive",
        )

    def start_evaluation_run(self, request: BenchmarkRunRequest, user: User) -> str:
        """Launches an asynchronous evaluation job with real-time progress callbacks."""
        run_id = str(uuid.uuid4())
        scenarios = self.get_scenarios()
        total_cases = len(scenarios) if not request.category else len([s for s in scenarios if s.category == request.category])

        self._active_runs[run_id] = {
            "status": "running",
            "completed_cases": 0,
            "total_cases": total_cases,
            "current_case_id": None,
            "current_case_title": None,
            "start_time": time.perf_counter(),
            "error_message": None,
            "report": None,
        }

        # Launch background execution task
        asyncio.create_task(
            self._execute_evaluation_task(
                run_id=run_id,
                request=request,
                user=user,
            )
        )

        return run_id

    async def _execute_evaluation_task(
        self,
        run_id: str,
        request: BenchmarkRunRequest,
        user: User,
    ) -> None:
        """Worker task executing benchmark runner and saving results into database."""
        logger.info("Starting background benchmark execution [%s] (mock=%s)", run_id, request.mock)
        provider = MockBenchmarkProvider() if request.mock else None
        runner = EvaluationRunner(provider=provider)

        async def on_progress(res: CaseEvaluationResult, completed: int, total: int) -> None:
            if run_id in self._active_runs:
                self._active_runs[run_id]["completed_cases"] = completed
                self._active_runs[run_id]["total_cases"] = total
                self._active_runs[run_id]["current_case_id"] = res.case_id
                self._active_runs[run_id]["current_case_title"] = res.title

        try:
            async with AsyncSessionLocal() as session:
                report: EvaluationReport = await runner.run_evaluation(
                    user=user,
                    db=session,
                    category_filter=request.category,
                    progress_callback=on_progress,
                )

                # Persist to database
                db_run = BenchmarkRun(
                    id=uuid.UUID(run_id),
                    timestamp=datetime.now(UTC),
                    benchmark_version=report.benchmark_version,
                    model_name=report.model_name,
                    provider_type=report.provider_type,
                    category_filter=request.category,
                    status="completed",
                    total_cases=report.total_cases,
                    passed_cases=report.passed_cases,
                    failed_cases=report.failed_cases,
                    overall_score=report.overall_score,
                    accuracy_percentage=report.accuracy_percentage,
                    security_violations=report.security_violations,
                    average_duration_ms=report.average_duration_ms,
                    p95_duration_ms=report.p95_duration_ms,
                    category_scores=report.category_scores,
                    results=[r.model_dump() for r in report.results],
                    triggered_by_username=user.username,
                )
                session.add(db_run)
                await session.commit()
                await session.refresh(db_run)

                detail = self._to_detail(db_run)
                if run_id in self._active_runs:
                    self._active_runs[run_id]["status"] = "completed"
                    self._active_runs[run_id]["report"] = detail

                logger.info(
                    "Background benchmark run [%s] completed successfully (%d/%d passed, score=%.3f)",
                    run_id,
                    report.passed_cases,
                    report.total_cases,
                    report.overall_score,
                )

        except Exception as exc:
            logger.exception("Benchmark run [%s] failed: %s", run_id, exc)
            if run_id in self._active_runs:
                self._active_runs[run_id]["status"] = "failed"
                self._active_runs[run_id]["error_message"] = str(exc)

    def _to_detail(self, run: BenchmarkRun) -> BenchmarkRunDetail:
        """Converts ORM BenchmarkRun into Pydantic BenchmarkRunDetail."""
        results = [
            CaseResultOut(
                case_id=r.get("case_id", ""),
                category=r.get("category", ""),
                title=r.get("title", ""),
                prompt=r.get("prompt", ""),
                expected_role=r.get("expected_role", ""),
                actual_role=r.get("actual_role", ""),
                expected_tools=r.get("expected_tools", []),
                actual_tools=r.get("actual_tools", []),
                passed=r.get("passed", False),
                score=r.get("score", 0.0),
                routing_passed=r.get("routing_passed", False),
                tools_passed=r.get("tools_passed", False),
                citations_passed=r.get("citations_passed", False),
                security_passed=r.get("security_passed", False),
                iterations_used=r.get("iterations_used", 0),
                duration_ms=r.get("duration_ms", 0.0),
                output_preview=r.get("output_preview", ""),
                errors=r.get("errors", []),
                failure_diagnosis=r.get("failure_diagnosis", ""),
            )
            for r in (run.results if isinstance(run.results, list) else [])
        ]

        return BenchmarkRunDetail(
            id=run.id,
            timestamp=run.timestamp.isoformat(),
            benchmark_version=run.benchmark_version,
            model_name=run.model_name,
            provider_type=run.provider_type,
            category_filter=run.category_filter,
            status=run.status,
            total_cases=run.total_cases,
            passed_cases=run.passed_cases,
            failed_cases=run.failed_cases,
            overall_score=run.overall_score,
            accuracy_percentage=run.accuracy_percentage,
            security_violations=run.security_violations,
            average_duration_ms=run.average_duration_ms,
            p95_duration_ms=run.p95_duration_ms,
            category_scores=run.category_scores if isinstance(run.category_scores, dict) else {},
            results=results,
            triggered_by_username=run.triggered_by_username,
            error_message=run.error_message,
        )


_service_instance: BenchmarkService | None = None


def get_benchmark_service() -> BenchmarkService:
    global _service_instance
    if _service_instance is None:
        _service_instance = BenchmarkService()
    return _service_instance
