"""
tests/test_benchmarks/test_router.py
====================================
Integration tests for the Benchmark & Evaluation API endpoints:
  - Scenario metadata listing
  - Latest benchmark run retrieval
  - Historical runs listing and single-run lookup
  - RBAC authorization check: non-admin users forbidden from triggering runs
  - Admin execution trigger and real-time progress retrieval
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from app.identity.models import User
from httpx import AsyncClient
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_list_benchmark_scenarios(client: AsyncClient, test_user: User):
    """Verifies that authenticated users can list all 15 industrial benchmark scenarios."""
    resp = await client.get("/api/v1/benchmarks/scenarios", headers=auth_headers(test_user))
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) == 15
    ids = [s["id"] for s in scenarios]
    assert "ENG-01" in ids
    assert "ENG-03" in ids
    assert "DATA-02" in ids
    assert "SEC-01" in ids


@pytest.mark.asyncio
async def test_get_latest_benchmark_run(client: AsyncClient, test_user: User):
    """Verifies that the latest verified benchmark run is returned with full scenario details."""
    resp = await client.get("/api/v1/benchmarks/latest", headers=auth_headers(test_user))
    assert resp.status_code == 200
    report = resp.json()
    assert report["benchmark_version"] == "industrial_benchmark_v1"
    assert report["total_cases"] == 15
    assert report["passed_cases"] == 15
    assert report["accuracy_percentage"] == 100.0
    assert report["security_violations"] == 0
    assert len(report["results"]) == 15

    # Check that ENG-03 and DATA-02 have rich diagnosis and metadata
    eng_03 = next(r for r in report["results"] if r["case_id"] == "ENG-03")
    assert eng_03["passed"] is True
    assert "math_eval" in eng_03["actual_tools"]
    assert "conversion" in eng_03["failure_diagnosis"].lower() or "passed" in eng_03["failure_diagnosis"].lower()

    data_02 = next(r for r in report["results"] if r["case_id"] == "DATA-02")
    assert data_02["passed"] is True
    assert "code_sandbox" in data_02["actual_tools"]


@pytest.mark.asyncio
async def test_get_benchmark_history(client: AsyncClient, test_user: User):
    """Verifies listing chronological benchmark execution runs."""
    resp = await client.get("/api/v1/benchmarks/history", headers=auth_headers(test_user))
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) >= 1
    assert history[0]["status"] == "completed"
    assert history[0]["total_cases"] == 15


@pytest.mark.asyncio
async def test_get_benchmark_run_by_id(client: AsyncClient, test_user: User):
    """Verifies fetching full detail of a run by UUID, and 404 for unknown run."""
    # First get latest run ID
    latest_resp = await client.get("/api/v1/benchmarks/latest", headers=auth_headers(test_user))
    assert latest_resp.status_code == 200
    run_id = latest_resp.json()["id"]

    # Fetch by ID
    run_resp = await client.get(f"/api/v1/benchmarks/runs/{run_id}", headers=auth_headers(test_user))
    assert run_resp.status_code == 200
    assert run_resp.json()["id"] == run_id

    # Unknown ID -> 404
    bad_id = uuid.uuid4()
    bad_resp = await client.get(f"/api/v1/benchmarks/runs/{bad_id}", headers=auth_headers(test_user))
    assert bad_resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_benchmark_run_rbac_enforcement(client: AsyncClient, test_user: User, admin_user: User):
    """
    CRITICAL RBAC SECURITY TEST:
    Verifies that non-admin users (role='user') are strictly forbidden (403) from triggering runs,
    while admin users can trigger evaluation.
    """
    payload = {"mock": True, "category": "engineering_reasoning"}

    # 1. Non-admin user attempts trigger -> 403 Forbidden
    forbidden_resp = await client.post(
        "/api/v1/benchmarks/run",
        json=payload,
        headers=auth_headers(test_user),
    )
    assert forbidden_resp.status_code == 403

    # 2. Admin user triggers run -> 202 Accepted
    with patch("app.benchmarks.service.BenchmarkService._execute_evaluation_task", new_callable=AsyncMock):
        accept_resp = await client.post(
            "/api/v1/benchmarks/run",
            json=payload,
            headers=auth_headers(admin_user),
        )
        assert accept_resp.status_code == 202
        data = accept_resp.json()
        assert "run_id" in data
        assert data["status"] == "running"

        run_id = data["run_id"]

        # 3. Check progress endpoint
        prog_resp = await client.get(f"/api/v1/benchmarks/progress/{run_id}", headers=auth_headers(test_user))
        assert prog_resp.status_code == 200
        prog_data = prog_resp.json()
        assert prog_data["run_id"] == run_id
        assert prog_data["status"] in ("running", "completed")


