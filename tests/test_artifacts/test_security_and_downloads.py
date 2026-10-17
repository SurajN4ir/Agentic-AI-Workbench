"""
tests/test_artifacts/test_security_and_downloads.py
===================================================
Security and download verification tests:
  - Directory traversal blocking
  - Proper MIME types and download headers
  - Session workspace listing
  - REST generate endpoint
"""

import uuid

import pytest
from app.artifacts.generator import ArtifactGenerator
from app.artifacts.models import ReportSpec, TextBlock
from app.identity.models import User
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.fixture
def session_id() -> str:
    return f"sec_art_{uuid.uuid4().hex[:12]}"


@pytest.mark.asyncio
async def test_artifact_listing_and_download(
    client: AsyncClient,
    test_user: User,
    session_id: str,
):
    """Verifies artifact creation, directory discovery, and authenticated file download."""
    # 1. Generate an artifact
    spec = ReportSpec(
        title="Inspection Summary",
        sections=[TextBlock(body="No structural anomalies detected.")],
        filename="summary.docx",
    )
    ArtifactGenerator.generate_docx(spec, session_id)

    headers = auth_headers(test_user)

    # 2. List artifacts
    list_resp = await client.get(f"/api/v1/artifacts/{session_id}", headers=headers)
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) >= 1
    target_item = next(i for i in items if i["filename"] == "summary.docx")
    assert target_item["mime_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert target_item["size_bytes"] > 0

    # 3. Download artifact
    dl_resp = await client.get(f"/api/v1/artifacts/{session_id}/summary.docx", headers=headers)
    assert dl_resp.status_code == 200
    assert "attachment; filename=\"summary.docx\"" in dl_resp.headers.get("content-disposition", "")
    assert dl_resp.headers.get("content-type") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert len(dl_resp.content) > 0


@pytest.mark.asyncio
async def test_path_traversal_prevention(
    client: AsyncClient,
    test_user: User,
    session_id: str,
):
    """
    CRITICAL SECURITY TEST (CWE-22):
    Verifies that directory traversal patterns via URL parameters, dots, or slashes
    are strictly rejected and never leak host files.
    """
    headers = auth_headers(test_user)

    traversal_payloads = [
        "../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "....//....//config.py",
        "/etc/shadow",
        "C:\\Windows\\System32\\cmd.exe",
        "..\\..\\app\\config.py",
    ]

    for payload in traversal_payloads:
        resp = await client.get(f"/api/v1/artifacts/{session_id}/{payload}", headers=headers)
        # Must return 400, 403, or 404 — never 200
        assert resp.status_code in (400, 403, 404), f"Failed for payload '{payload}': got {resp.status_code}"


@pytest.mark.asyncio
async def test_artifact_unauthenticated_access(client: AsyncClient, session_id: str):
    """Verifies that unauthenticated requests to artifacts are rejected."""
    resp = await client.get(f"/api/v1/artifacts/{session_id}")
    assert resp.status_code in (401, 403)

    resp_dl = await client.get(f"/api/v1/artifacts/{session_id}/test.docx")
    assert resp_dl.status_code in (401, 403)


@pytest.mark.asyncio
async def test_generate_artifact_endpoint(
    client: AsyncClient,
    test_user: User,
    session_id: str,
):
    """Verifies the POST /api/v1/artifacts/generate endpoint for docx and xlsx."""
    headers = auth_headers(test_user)

    # 1. Generate docx via API
    docx_req = {
        "format": "docx",
        "session_id": session_id,
        "report_spec": {
            "title": "API Generated Report",
            "sections": [{"heading": "Introduction", "body": "Report generated via REST API."}],
            "filename": "api_report.docx",
        },
    }
    r1 = await client.post("/api/v1/artifacts/generate", json=docx_req, headers=headers)
    assert r1.status_code == 201
    d1 = r1.json()
    assert d1["filename"] == "api_report.docx"
    assert d1["mime_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    # 2. Generate xlsx via API
    xlsx_req = {
        "format": "xlsx",
        "session_id": session_id,
        "spreadsheet_spec": {
            "filename": "api_data.xlsx",
            "sheets": [
                {
                    "name": "Metrics",
                    "headers": ["Metric", "Value"],
                    "rows": [["Pressure", 10.5], ["Temperature", 88.2]],
                }
            ],
        },
    }
    r2 = await client.post("/api/v1/artifacts/generate", json=xlsx_req, headers=headers)
    assert r2.status_code == 201
    d2 = r2.json()
    assert d2["filename"] == "api_data.xlsx"
    assert d2["mime_type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
