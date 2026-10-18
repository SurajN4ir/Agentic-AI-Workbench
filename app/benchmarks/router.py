"""
app/benchmarks/router.py
========================
FastAPI router for the Industrial AI Benchmark & Evaluation Dashboard.
Provides scenario introspection, latest evaluation reports, run histories,
and RBAC-protected execution triggers.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.benchmarks.schemas import (
    BenchmarkCaseOut,
    BenchmarkProgressOut,
    BenchmarkRunDetail,
    BenchmarkRunRequest,
    BenchmarkRunSummary,
)
from app.benchmarks.service import BenchmarkService, get_benchmark_service
from app.database import get_db
from app.identity.dependencies import get_current_user, require_role
from app.identity.models import User

router = APIRouter(prefix="/benchmarks", tags=["Benchmark & Evaluation"])


@router.get("/scenarios", response_model=list[BenchmarkCaseOut])
async def list_benchmark_scenarios(
    current_user: User = Depends(get_current_user),
    service: BenchmarkService = Depends(get_benchmark_service),
) -> list[BenchmarkCaseOut]:
    """Returns the comprehensive dataset of 15 industrial benchmark scenarios."""
    return service.get_scenarios()


@router.get("/latest", response_model=BenchmarkRunDetail)
async def get_latest_benchmark_run(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: BenchmarkService = Depends(get_benchmark_service),
) -> BenchmarkRunDetail:
    """Returns the most recent verified benchmark evaluation report."""
    run = await service.get_latest_run(db)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No benchmark evaluation records found.",
        )
    return run


@router.get("/history", response_model=list[BenchmarkRunSummary])
async def get_benchmark_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: BenchmarkService = Depends(get_benchmark_service),
) -> list[BenchmarkRunSummary]:
    """Returns chronological benchmark execution history for trend analysis."""
    return await service.get_run_history(db)


@router.get("/runs/{run_id}", response_model=BenchmarkRunDetail)
async def get_benchmark_run_detail(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: BenchmarkService = Depends(get_benchmark_service),
) -> BenchmarkRunDetail:
    """Returns full scenario drill-down results for a specific historical benchmark run."""
    run = await service.get_run_by_id(run_id, db)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark run '{run_id}' not found.",
        )
    return run


@router.post("/run", response_model=dict[str, str], status_code=status.HTTP_202_ACCEPTED)
async def trigger_benchmark_run(
    payload: BenchmarkRunRequest,
    current_user: User = Depends(require_role("admin")),
    service: BenchmarkService = Depends(get_benchmark_service),
) -> dict[str, str]:
    """
    Triggers a live benchmark evaluation run.
    Restricted to administrative users via Role-Based Access Control.
    """
    run_id = service.start_evaluation_run(request=payload, user=current_user)
    return {
        "run_id": run_id,
        "status": "running",
        "message": f"Benchmark evaluation started for model ({'mock' if payload.mock else 'local Ollama'}).",
    }


@router.get("/progress/{run_id}", response_model=BenchmarkProgressOut)
async def get_benchmark_progress(
    run_id: str,
    current_user: User = Depends(get_current_user),
    service: BenchmarkService = Depends(get_benchmark_service),
) -> BenchmarkProgressOut:
    """Returns live execution progress for an ongoing or recently completed evaluation."""
    return service.get_progress(run_id)
