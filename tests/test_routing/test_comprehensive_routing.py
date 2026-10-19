"""
tests/test_routing/test_comprehensive_routing.py
=================================================
Comprehensive 14-scenario test suite for Sovereign Automatic Multimodal Routing & End-to-End Verification:
  Scenario 1: Normal text question -> reasoning role (local LLaMA/text model)
  Scenario 2: Image object/scene understanding -> vision role (qwen3.5:4b) with multimodal capabilities
  Scenario 3: Image text extraction -> ocr role with ocr_extract tool target
  Scenario 4: Scanned PDF document -> ocr role with ocr_extract tool target
  Scenario 5: Text PDF / DOCX document QA -> reasoning role with rag_search tool target
  Scenario 6: CSV / XLSX tabular data -> reasoning role with spreadsheet & code_sandbox tool targets
  Scenario 7: Programming & software engineering -> coding role with code_sandbox tool target
  Scenario 8: Mathematical & verified engineering calculation -> reasoning role with math_eval tool target
  Scenario 9: Image analysis requiring verified calculation -> mixed vision/ocr + math_eval multi-tool targets
  Scenario 10: Missing or unsupported vision model -> graceful refusal or fallback
  Scenario 11: Missing OCR engine -> graceful diagnostic error handling in ocr_extract tool
  Scenario 12: Corrupt or unsupported file format -> graceful error refusal (is_supported=False)
  Scenario 13: Multi-tool task dispatch -> target_tools tracking and retry guidance
  Scenario 14: Failed primary model inference -> graceful fallback execution
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.agent.graph import AgentGraphBuilder
from app.agent.state import WorkbenchState
from app.identity.models import User
from app.knowledge.ocr.base import OCRResult
from app.models.registry import (
    get_model_for_role,
    model_supports_vision,
)
from app.models.schemas import ChatMessage, ChatResponse
from app.routing.schemas import FileMetadata
from app.routing.service import TaskRouter
from app.tools.interface import ToolStatus
from app.tools.registry import ToolRegistry
from PIL import Image


@pytest.fixture
def router() -> TaskRouter:
    return TaskRouter()


@pytest.fixture
def test_user() -> User:
    return User(
        id="usr-test-123",
        username="lead_engineer",
        role="developer",
    )


# -----------------------------------------------------------------------------
# Scenario 1: Normal text question -> reasoning role
# -----------------------------------------------------------------------------
def test_scenario_01_normal_text_question(router: TaskRouter) -> None:
    prompt = "Explain the operating principles of high-pressure multi-stage centrifugal compressors."
    decision = router.route(prompt=prompt)
    assert decision.role == "reasoning"
    assert decision.is_multimodal is False
    assert decision.is_supported is True
    assert decision.selected_model == get_model_for_role("reasoning")


# -----------------------------------------------------------------------------
# Scenario 2: Image object/scene understanding -> vision role (qwen3.5:4b)
# -----------------------------------------------------------------------------
def test_scenario_02_image_scene_understanding(router: TaskRouter) -> None:
    files = [FileMetadata(filename="turbine_blade_crack.png", extension=".png")]
    prompt = "Inspect this image of the turbine blade and identify any surface cracking or thermal fatigue."
    decision = router.route(prompt=prompt, file_metadata=files)
    assert decision.role == "vision"
    assert decision.is_multimodal is True
    assert decision.requires_vision is True
    assert decision.method == "vision_detection"
    assert model_supports_vision(decision.model_tag) is True
    assert decision.fallback_role == "reasoning"


# -----------------------------------------------------------------------------
# Scenario 3: Image text extraction -> ocr role (ocr_extract)
# -----------------------------------------------------------------------------
def test_scenario_03_image_text_extraction(router: TaskRouter) -> None:
    files = [FileMetadata(filename="gauge_plate.jpg", extension=".jpg")]
    prompt = "Extract text from this image and transcribe the pressure gauge label and serial number."
    decision = router.route(prompt=prompt, file_metadata=files)
    assert decision.role == "ocr"
    assert decision.requires_ocr is True
    assert "ocr_extract" in decision.target_tools
    assert decision.method == "ocr_detection"


# -----------------------------------------------------------------------------
# Scenario 4: Scanned PDF document -> ocr role (ocr_extract)
# -----------------------------------------------------------------------------
def test_scenario_04_scanned_pdf_ocr(router: TaskRouter) -> None:
    files = [FileMetadata(filename="scanned_maintenance_sheet.pdf", extension=".pdf")]
    prompt = "OCR this scanned PDF document and extract the handwritten inspection notes."
    decision = router.route(prompt=prompt, file_metadata=files)
    assert decision.role == "ocr"
    assert decision.requires_ocr is True
    assert "ocr_extract" in decision.target_tools
    assert decision.method == "ocr_detection"


# -----------------------------------------------------------------------------
# Scenario 5: Text PDF / DOCX document QA -> reasoning role (rag_search)
# -----------------------------------------------------------------------------
def test_scenario_05_document_qa_rag(router: TaskRouter) -> None:
    files = [FileMetadata(filename="aeroturbine_manual.docx", extension=".docx")]
    prompt = "What are the recommended bearing lubrication intervals in this manual?"
    decision = router.route(prompt=prompt, file_metadata=files)
    assert decision.role == "reasoning"
    assert "rag_search" in decision.target_tools
    assert decision.is_supported is True


# -----------------------------------------------------------------------------
# Scenario 6: CSV / XLSX tabular data -> reasoning role (spreadsheet, code_sandbox)
# -----------------------------------------------------------------------------
def test_scenario_06_spreadsheet_analysis(router: TaskRouter) -> None:
    files = [FileMetadata(filename="vibration_telemetry.csv", extension=".csv")]
    prompt = "Analyze the vibration peaks and filter for rows where RMS vibration exceeds 4.5 mm/s."
    decision = router.route(prompt=prompt, file_metadata=files)
    assert decision.role == "reasoning"
    assert decision.method == "spreadsheet_detection"
    assert "spreadsheet" in decision.target_tools
    assert "code_sandbox" in decision.target_tools


# -----------------------------------------------------------------------------
# Scenario 7: Coding task -> coding role (code_sandbox)
# -----------------------------------------------------------------------------
def test_scenario_07_coding_task(router: TaskRouter) -> None:
    files = [FileMetadata(filename="pipeline.py", extension=".py")]
    prompt = "Refactor this pipeline script to handle asynchronous batch processing."
    decision = router.route(prompt=prompt, file_metadata=files)
    assert decision.role == "coding"
    assert decision.confidence == 1.0
    assert "code_sandbox" in decision.target_tools
    assert decision.method == "metadata"


# -----------------------------------------------------------------------------
# Scenario 8: Mathematical & verified calculation -> math_eval
# -----------------------------------------------------------------------------
def test_scenario_08_mathematical_calculation(router: TaskRouter) -> None:
    prompt = "Calculate the thermal efficiency of a Carnot cycle operating between 950 K and 300 K."
    decision = router.route(prompt=prompt)
    assert decision.role == "reasoning"
    assert "math_eval" in decision.target_tools
    assert decision.method == "keyword"


# -----------------------------------------------------------------------------
# Scenario 9: Image analysis requiring calculation -> mixed vision/ocr + math_eval
# -----------------------------------------------------------------------------
def test_scenario_09_mixed_ocr_math_calculation(router: TaskRouter) -> None:
    files = [FileMetadata(filename="pressure_chart.png", extension=".png")]
    prompt = "Extract text from this chart to find P1 and P2, then calculate the pressure drop delta."
    decision = router.route(prompt=prompt, file_metadata=files)
    assert decision.role == "ocr"
    assert "ocr_extract" in decision.target_tools
    assert "math_eval" in decision.target_tools


# -----------------------------------------------------------------------------
# Scenario 10: Missing or unsupported vision model -> graceful refusal / fallback
# -----------------------------------------------------------------------------
def test_scenario_10_missing_vision_model_handling(router: TaskRouter) -> None:
    with patch("app.routing.service.is_model_available", return_value=False), \
         patch("app.routing.service.model_supports_vision", return_value=False):
        files = [FileMetadata(filename="inspection.png", extension=".png")]
        decision = router.route(prompt="Inspect this image", file_metadata=files)
        assert decision.role == "vision"
        assert decision.refusal_reason is not None
        assert "vision-capable model" in decision.refusal_reason
        assert decision.fallback_role == "reasoning"


# -----------------------------------------------------------------------------
# Scenario 11: Missing OCR engine -> graceful diagnostic handling in ocr_extract tool
# -----------------------------------------------------------------------------
def test_scenario_11_missing_ocr_engine_diagnostic(tmp_path: Path, test_user: User) -> None:
    # Create test image in workspace
    session_id = "test_ocr_sess"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    img_path = session_dir / "sample.png"

    img = Image.new("RGB", (60, 30), color=(255, 255, 255))
    img.save(img_path)

    registry = ToolRegistry()

    # Mock OCR pipeline reporting both engines unavailable
    mock_pipeline = MagicMock()
    mock_pipeline.process_image.return_value = OCRResult(
        text="",
        confidence=0.0,
        engine="ocr_unavailable",
    )

    with patch("app.tools.interface.get_settings") as mock_settings, \
         patch("app.knowledge.ocr.pipeline.get_ocr_pipeline", return_value=mock_pipeline):
        mock_settings.return_value.workspace_dir = str(tmp_path)

        res = registry._execute_ocr(
            input_data={"file_path": "sample.png"},
            session_id=session_id,
        )

        assert res.status == ToolStatus.ERROR
        assert "No OCR engine is available" in (res.error or "")


# -----------------------------------------------------------------------------
# Scenario 12: Corrupt or unsupported file format -> graceful error refusal
# -----------------------------------------------------------------------------
def test_scenario_12_unsupported_file_refusal(router: TaskRouter) -> None:
    files = [FileMetadata(filename="payload.exe", extension=".exe")]
    prompt = "Please execute or inspect this file."
    decision = router.route(prompt=prompt, file_metadata=files)
    assert decision.is_supported is False
    assert decision.method == "error_refusal"
    assert "unsupported extension '.exe'" in (decision.refusal_reason or "")


# -----------------------------------------------------------------------------
# Scenario 13: Multi-tool task dispatch -> target_tools tracking & retry guidance
# -----------------------------------------------------------------------------
def test_scenario_13_multitool_task_dispatch(router: TaskRouter) -> None:
    graph = AgentGraphBuilder()
    state: WorkbenchState = {
        "prompt": "Extract the pressure values from this document and calculate the deviation.",
        "user_role": "analyst",
        "route_decision": {
            "role": "ocr",
            "target_tools": ["ocr_extract", "math_eval"],
            "selected_model": "qwen3.5:4b",
        },
        "tool_results": [],  # neither executed yet
        "final_response": "The pressure values are 100 psi and 120 psi.",
    }

    req = graph.determine_unsatisfied_tool_requirement(state)
    assert req is not None
    tool_name, guidance = req
    assert tool_name == "ocr_extract"
    assert "ocr_extract" in guidance

    # Simulate ocr_extract executed, now math_eval should be required
    state["tool_results"] = [{"tool_name": "ocr_extract", "status": "success"}]
    req2 = graph.determine_unsatisfied_tool_requirement(state)
    assert req2 is not None
    tool_name2, guidance2 = req2
    assert tool_name2 == "math_eval"


# -----------------------------------------------------------------------------
# Scenario 14: Failed primary model inference -> graceful fallback execution
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_14_failed_model_fallback_execution() -> None:
    graph = AgentGraphBuilder()
    mock_provider = MagicMock()

    # First call with primary model fails, second call with fallback succeeds
    async def chat_side_effect(model: str, messages: list, tools=None, options=None):
        if model == "primary-failing-model":
            raise RuntimeError("CUDA Out of Memory on primary vision model")
        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                content="Fallback text model recovered successfully and answered.",
            ),
            model="llama3.2:latest",
        )

    mock_provider.chat = AsyncMock(side_effect=chat_side_effect)
    graph.provider = mock_provider

    state: WorkbenchState = {
        "model_tag": "primary-failing-model",
        "route_decision": {
            "role": "vision",
            "fallback_model": "llama3.2:latest",
        },
        "messages": [
            {"role": "user", "content": "Analyze this data", "images": ["fake_b64"]},
        ],
        "user_role": "developer",
    }

    result = await graph.reason_node(state)
    assert result.get("status") != "error"
    assert "Fallback text model recovered" in (result.get("final_response") or "")
