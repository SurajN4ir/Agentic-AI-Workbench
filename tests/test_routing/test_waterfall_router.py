"""
tests/test_routing/test_waterfall_router.py
===========================================
Comprehensive tests for the 3-Stage Waterfall Routing engine:
  - Stage 0: Manual role override
  - Stage 0.5: Multimodal image override
  - Stage 1: Deterministic file metadata inspection
  - Stage 2: Heuristic keyword inspection guard
  - Stage 3: In-memory ML classifier fallback
  - API endpoints: /api/v1/routing/route and /api/v1/routing/models
"""

import pytest
from app.identity.models import User
from app.routing.schemas import FileMetadata
from app.routing.service import TaskRouter, get_task_router
from httpx import AsyncClient

from tests.conftest import auth_headers


class TestWaterfallRouterStages:
    @pytest.fixture
    def router(self) -> TaskRouter:
        return get_task_router()

    def test_stage_0_manual_override(self, router: TaskRouter) -> None:
        """Explicit role override bypasses all automated stages."""
        dec = router.route("tell me a joke", role_override="coding")
        assert dec.role == "coding"
        assert dec.confidence == 1.0
        assert dec.method == "manual_override"

        dec2 = router.route("write a python script", role_override="reasoning")
        assert dec2.role == "reasoning"
        assert dec2.confidence == 1.0
        assert dec2.method == "manual_override"

    def test_stage_0_5_image_override(self, router: TaskRouter) -> None:
        """Attached image files trigger vision routing with multimodal capabilities."""
        files = [FileMetadata(filename="chart.png", extension=".png")]
        dec = router.route("What does this graph show?", file_metadata=files)
        assert dec.role == "vision"
        assert dec.confidence == 1.0
        assert dec.is_multimodal is True
        assert dec.method in ("vision_detection", "multimodal_override")

    def test_stage_1_metadata_check_code_files(self, router: TaskRouter) -> None:
        """Code file attachments route deterministically to coding role."""
        files = [FileMetadata(filename="main.py", extension=".py")]
        dec = router.route("Can you review this?", file_metadata=files)
        assert dec.role == "coding"
        assert dec.confidence == 1.0
        assert dec.method == "metadata"

        files_ts = [FileMetadata(filename="client.ts", extension=".ts")]
        dec_ts = router.route("Inspect this file", file_metadata=files_ts)
        assert dec_ts.role == "coding"
        assert dec_ts.confidence == 1.0
        assert dec_ts.method == "metadata"

    def test_stage_2_keyword_check_coding_signals(self, router: TaskRouter) -> None:
        """Prompts with code debugging/action keywords route to coding role."""
        dec = router.route("Please debug this null pointer exception")
        assert dec.role == "coding"
        assert dec.confidence == 0.85
        assert dec.method == "keyword"

        dec2 = router.route("Can you refactor this function to be faster?")
        assert dec2.role == "coding"
        assert dec2.confidence == 0.85
        assert dec2.method == "keyword"

        dec3 = router.route("write a script to parse log files")
        assert dec3.role == "coding"
        assert dec3.confidence == 0.85
        assert dec3.method == "keyword"

    def test_stage_2_specialized_tool_intents(self, router: TaskRouter) -> None:
        """Prompts with specialized industrial intents target appropriate tools deterministically."""
        # Document generation
        dec_doc = router.route("Generate a formal PDF inspection report summarizing bearing wear")
        assert dec_doc.role == "reasoning"
        assert dec_doc.target_tools is not None and "doc_gen" in dec_doc.target_tools
        assert dec_doc.method == "keyword"

        # Spreadsheet analysis (even when 'calculate' is present, spreadsheet priority holds)
        dec_sheet = router.route("Filter the telemetry spreadsheet and calculate the average flow rate")
        assert dec_sheet.role == "reasoning"
        assert dec_sheet.target_tools is not None and "spreadsheet" in dec_sheet.target_tools
        assert dec_sheet.method == "keyword"

        # Pure mathematical calculation
        dec_math = router.route("Calculate the Reynolds number given velocity 2.5 m/s and pipe diameter 0.1 m")
        assert dec_math.role == "reasoning"
        assert dec_math.target_tools is not None and "math_eval" in dec_math.target_tools
        assert dec_math.method == "keyword"

        # Technical domain knowledge inquiry (RAG)
        dec_rag1 = router.route("What is the over-speed trip limit for the high-pressure turbine?")
        assert dec_rag1.role == "reasoning"
        assert dec_rag1.target_tools is not None and "rag_search" in dec_rag1.target_tools
        assert dec_rag1.method == "keyword"

        dec_rag2 = router.route("Look up the seal flush requirements in the maintenance manual")
        assert dec_rag2.role == "reasoning"
        assert dec_rag2.target_tools is not None and "rag_search" in dec_rag2.target_tools
        assert dec_rag2.method == "keyword"

        dec_uploaded = router.route(
            "According to the uploaded specification 'Turbine_Operating_Spec_Verification.txt', "
            "what is the vibration alarm threshold?"
        )
        assert dec_uploaded.target_tools is not None and "rag_search" in dec_uploaded.target_tools
        assert dec_uploaded.method == "keyword"

        # A calculation inside code authoring is still a coding task.
        dec_code_math = router.route("Write a Python script using pandas to compute a rolling average")
        assert dec_code_math.role == "coding"
        assert dec_code_math.target_tools == ["code_sandbox"]

        # A negated formula request is conceptual, not deterministic math.
        dec_no_formula = router.route("Explain how neural networks learn without showing any code or formulas")
        assert "math_eval" not in (dec_no_formula.target_tools or [])

        # Incidental ranking words should only route to the spreadsheet tool with tabular context.
        dec_table = router.route("Sort the boiler sensor table by pressure and return the top 5 readings")
        assert "spreadsheet" in (dec_table.target_tools or [])

    def test_stage_2_conceptual_query_does_not_force_coding(self, router: TaskRouter) -> None:
        """Conceptual questions mentioning a language do not falsely trigger Stage 2 coding."""
        # "explain how python manages memory" -> conceptual, no action verb
        dec = router.route("explain how python manages memory conceptually")
        assert dec.method != "keyword"
        assert dec.role == "reasoning"

    def test_stage_3_classifier_fallback_ambiguous_prompts(self, router: TaskRouter) -> None:
        """Ambiguous prompts without direct keywords reach Stage 3 ML classifier."""
        # Coding intent without exact keywords ("can you clean this up and make it more efficient")
        dec_code = router.route("can you clean this up and make it more efficient")
        assert dec_code.method == "classifier"
        assert dec_code.role == "coding"
        assert dec_code.confidence >= 0.60

        # Reasoning intent without exact keywords
        dec_reason = router.route("summarize the key risks in this incident report")
        assert dec_reason.method == "classifier"
        assert dec_reason.role == "reasoning"
        assert dec_reason.confidence >= 0.60

    def test_empty_prompt_fallback(self, router: TaskRouter) -> None:
        """Whitespace or empty prompt safely returns reasoning fallback."""
        dec = router.route("   ")
        assert dec.role == "reasoning"
        assert dec.confidence == 0.50
        assert dec.method == "classifier_fallback"


class TestRoutingEndpoints:
    @pytest.mark.asyncio
    async def test_route_endpoint_authenticated(self, client: AsyncClient, test_user: User) -> None:
        """POST /api/v1/routing/route succeeds for authenticated users."""
        payload = {
            "prompt": "write a python function to compute factorial",
            "file_metadata": None,
            "role_override": "auto",
        }
        r = await client.post("/api/v1/routing/route", json=payload, headers=auth_headers(test_user))
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "coding"
        assert data["confidence"] > 0.0
        assert "method" in data
        assert "selected_model" in data
        assert data["selected_model"] != ""

    @pytest.mark.asyncio
    async def test_route_endpoint_unauthenticated(self, client: AsyncClient) -> None:
        """POST /api/v1/routing/route rejects requests without Bearer token."""
        r = await client.post("/api/v1/routing/route", json={"prompt": "hello"})
        assert r.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_models_endpoint_authenticated(self, client: AsyncClient, test_user: User) -> None:
        """GET /api/v1/routing/models returns configured models and UI options."""
        r = await client.get("/api/v1/routing/models", headers=auth_headers(test_user))
        assert r.status_code == 200
        data = r.json()
        assert "models" in data
        assert "registry" in data
        assert "options" in data
        assert "inference_backend_healthy" in data
        assert len(data["options"]) >= 3
