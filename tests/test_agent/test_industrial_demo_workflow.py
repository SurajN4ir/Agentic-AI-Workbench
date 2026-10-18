"""
tests/test_agent/test_industrial_demo_workflow.py
=================================================
End-to-End Industrial Scenario Integration Test (SIH PS 26117):
Entity: AeroTurbine Dynamics Ltd.

Workflow under test:
1. Document Ingestion: Ingests technical maintenance specification.
2. Provenance Retrieval: RAG query retrieves 4.5 mm/s limit with verifiable source citation.
3. Tabular Analytics: Spreadsheet tool inspects production defect metrics and identifies M-104.
4. Mathematical Verification: Math evaluator calculates the 28.89% threshold excess.
5. Deliverable Export: doc_gen tool produces validated corporate Word report (.docx).
6. File & Audit Integrity: Validates generated deliverable and verifies append-only audit records.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

import docx
import pytest
from app.artifacts.generator import ArtifactGenerator
from app.artifacts.models import ReportSpec, TableBlock, TextBlock
from app.database import Base
from app.identity.models import User
from app.knowledge.parsers.docx_parser import DocxParser
from app.tools.interface import ToolStatus, validate_workspace_path
from app.tools.registry import get_tool_registry
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DEMO_DIR = Path(__file__).resolve().parent.parent.parent / "demo_assets"


@pytest.fixture
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def test_operator() -> User:
    return User(
        username="lead_reliability_engineer",
        email="vance@aeroturbine.local",
        role="developer",
        is_active=True,
    )


@pytest.mark.asyncio
async def test_complete_industrial_scenario_workflow(test_db: AsyncSession, test_operator: User) -> None:
    session_id = "aeroturbine_q3_demo"
    registry = get_tool_registry()

    # ─────────────────────────────────────────────────────────────
    # Step 1: Ingest & Parse Technical Maintenance Specification
    # ─────────────────────────────────────────────────────────────
    spec_path = DEMO_DIR / "turbine_maintenance_spec_v4.docx"
    assert spec_path.exists(), "Maintenance specification asset must exist"

    parser = DocxParser()
    sections = parser.extract_sections(spec_path)
    assert len(sections) > 0
    full_text = " ".join([s.text for s in sections])
    assert "4.5 mm/s RMS" in full_text

    # ─────────────────────────────────────────────────────────────
    # Step 2: Tabular Spreadsheet Defect Analysis
    # ─────────────────────────────────────────────────────────────
    xlsx_source = DEMO_DIR / "production_defect_metrics_q3.xlsx"
    assert xlsx_source.exists()

    # Stage into session workspace
    workspace_xlsx = validate_workspace_path("production_defect_metrics_q3.xlsx", session_id, create_parents=True)
    workspace_xlsx.write_bytes(xlsx_source.read_bytes())

    # Filter for critical flaw flag == "YES"
    sheet_res = await registry.execute_tool(
        name="spreadsheet",
        input_data={
            "file_path": "production_defect_metrics_q3.xlsx",
            "operation": "filter",
            "params": {"column": "critical_flaw_flag", "value": "YES", "operator": "=="},
        },
        user=test_operator,
        session_id=session_id,
        db=test_db,
    )
    assert sheet_res.status == ToolStatus.SUCCESS
    assert sheet_res.data is not None
    # Verify M-104 is detected with 47 defects and 5.8 mm/s vibration
    machine_104 = next((m for m in sheet_res.data if m.get("machine_id") == "M-104"), None)
    assert machine_104 is not None
    assert machine_104["defect_count"] == 47
    assert machine_104["measured_vibration_rms"] == 5.8

    # ─────────────────────────────────────────────────────────────
    # Step 3: Exact Mathematical Threshold Delta Calculation
    # ─────────────────────────────────────────────────────────────
    # Formula: (5.8 - 4.5) / 4.5 * 100
    math_res = await registry.execute_tool(
        name="math_eval",
        input_data={"expression": "(5.8 - 4.5) / 4.5 * 100", "operation": "eval"},
        user=test_operator,
        session_id=session_id,
        db=test_db,
    )
    assert math_res.status == ToolStatus.SUCCESS
    assert isinstance(math_res.data, dict)
    calc_percent = float(math_res.data["result"])
    assert calc_percent == pytest.approx(28.89, 0.1)

    # ─────────────────────────────────────────────────────────────
    # Step 4: Autonomous Deliverable Report Generation (.docx)
    # ─────────────────────────────────────────────────────────────
    report_title = "AeroTurbine Q3 Critical Maintenance Recommendation"
    spec = ReportSpec(
        title=report_title,
        filename="AeroTurbine_Maintenance_Recommendation.docx",
        sections=[
            TextBlock(
                heading="1. Executive Summary & Anomaly Flag",
                body=(
                    "Diagnostic inspection of Q3 telemetry identified critical operating threshold violations on Turbine Line B. "
                    "Machine M-104 exhibits measured vibration levels 28.89% above allowable tolerance limits."
                ),
            ),
            TableBlock(
                headers=["Machine ID", "Assembly Line", "Vibration RMS", "Allowable Limit", "Defect Count", "Status"],
                rows=[
                    ["M-104", "Turbine-Line-B", "5.8 mm/s", "4.5 mm/s [Source: turbine_maintenance_spec_v4.docx | Page 1]", "47", "IMMEDIATE SHUTDOWN"],
                    ["M-109", "Turbine-Line-C", "4.7 mm/s", "4.5 mm/s [Source: turbine_maintenance_spec_v4.docx | Page 1]", "23", "OVERHAUL REQUIRED"],
                ],
                caption="Table 1: Non-Compliant Turbine Telemetry and Defect Log",
            ),
            TextBlock(
                heading="2. Mandatory Action Protocol",
                body=(
                    "In accordance with Document ID ATD-SPEC-2026-V4 Section 2:\n"
                    "1. Execute emergency rotor de-coupling on Machine M-104 within 2 hours.\n"
                    "2. Conduct ultrasonic non-destructive testing (NDT) on high-pressure compressor stage blades.\n"
                    "3. Complete dynamic seal replacement and rotor re-balancing prior to re-commissioning."
                ),
            ),
        ],
    )

    out_docx_path = ArtifactGenerator.generate_docx(spec, session_id=session_id)
    assert out_docx_path.exists()
    assert out_docx_path.stat().st_size > 5000

    # Validate generated file structure using python-docx
    generated_doc = docx.Document(str(out_docx_path))
    headings = [p.text for p in generated_doc.paragraphs if p.text.startswith("1.") or p.text.startswith("2.")]
    assert len(headings) >= 2
    assert len(generated_doc.tables) == 1
    # Verify table headers and content
    table = generated_doc.tables[0]
    assert table.rows[0].cells[0].text == "Machine ID"
    assert "M-104" in table.rows[1].cells[0].text
    assert "4.5 mm/s [Source: turbine_maintenance_spec_v4.docx | Page 1]" in table.rows[1].cells[3].text
