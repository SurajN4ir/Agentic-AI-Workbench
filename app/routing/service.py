"""
app/routing/service.py
======================
Main TaskRouter service coordinating comprehensive waterfall routing:
  - Stage 0: Manual role override (if explicitly requested: reasoning, coding, vision, ocr)
  - Stage 0.1: Unsupported file validation (Format check -> error refusal)
  - Stage 0.2: Multimodal OCR vs Vision detection (images & scanned PDFs)
  - Stage 0.3: Tabular spreadsheet detection (CSV, XLSX -> spreadsheet & code_sandbox)
  - Stage 0.4: Document QA detection (PDF, DOCX -> rag_search)
  - Stage 1: Deterministic file metadata check (code extensions -> coding, 1.0)
  - Stage 2: Heuristic keyword inspection (code terms with word boundaries, 0.85)
  - Stage 2.1: Mathematical/engineering calculation detection (math_eval)
  - Stage 2.2: RAG knowledge search detection (rag_search)
  - Stage 3: In-memory ML classifier fallback (TF-IDF + Logistic Regression)
"""

import logging
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import emit_event
from app.models.registry import (
    get_compatible_model_for_role,
    get_model_for_role,
    is_model_available,
    model_supports_vision,
)
from app.routing.classifier import classify
from app.routing.keyword_check import check_keywords
from app.routing.metadata_check import check_metadata
from app.routing.schemas import FileMetadata, RouteDecision

logger = logging.getLogger("sovereign.routing.service")

OCR_SIGNALS = (
    "ocr",
    "extract text",
    "read text",
    "read the text",
    "transcribe",
    "transcription",
    "read label",
    "read table",
    "read gauge",
    "text extraction",
    "what does the text say",
)

MATH_SIGNALS = (
    "calculate",
    "compute",
    "math",
    "evaluate",
    "equation",
    "formula",
    "reynolds",
    "thermal efficiency",
    "carnot",
    "integral",
    "derivative",
    "solve",
    "deviation",
    "stress",
    "pressure drop",
    "linear regression",
)

RAG_SIGNALS = (
    "in the knowledge base",
    "in the manual",
    "according to the doc",
    "search docs",
    "from the specification",
    "rag search",
    "knowledge base",
    "aeroturbine",
)


class TaskRouter:
    """Orchestrates Comprehensive Waterfall Routing for incoming requests."""

    def route(
        self,
        prompt: str,
        file_metadata: list[FileMetadata] | None = None,
        role_override: str | None = None,
    ) -> RouteDecision:
        """Determines model role assignment, target tools, and fallback paths."""
        # Stage 0: Manual Role Override Check
        if role_override and role_override.lower() not in {"auto", ""}:
            target_role = role_override.lower()
            if target_role in {"coding", "reasoning", "vision", "ocr"}:
                selected_model = get_compatible_model_for_role(
                    target_role,
                    requires_vision=(target_role == "vision"),
                )
                target_tools: list[str] = []
                if target_role == "ocr":
                    target_tools = ["ocr_extract"]
                elif target_role == "coding":
                    target_tools = ["code_sandbox"]

                is_supported = True
                refusal_reason = None
                if target_role == "vision" and not model_supports_vision(selected_model):
                    is_supported = False
                    refusal_reason = f"Model '{selected_model}' assigned to vision role does not support vision capabilities."

                return RouteDecision(
                    role=target_role,  # type: ignore[arg-type]
                    confidence=1.0,
                    method="manual_override",
                    selected_model=selected_model,
                    target_tools=target_tools,
                    is_multimodal=(target_role in ("vision", "ocr")),
                    requires_vision=(target_role == "vision"),
                    requires_ocr=(target_role == "ocr"),
                    fallback_role="reasoning" if target_role != "reasoning" else None,
                    fallback_model=get_model_for_role("reasoning") if target_role != "reasoning" else None,
                    is_supported=is_supported,
                    refusal_reason=refusal_reason,
                    reasoning=f"User requested explicit role override: '{target_role}'.",
                )

        # Stage 0.1: Unsupported file validation (Format check)
        if file_metadata:
            for meta in file_metadata:
                if not meta.is_supported:
                    return RouteDecision(
                        role="reasoning",
                        confidence=1.0,
                        method="error_refusal",
                        selected_model=get_model_for_role("reasoning"),
                        is_supported=False,
                        refusal_reason=(
                            f"File '{meta.filename}' has unsupported extension '{meta.extension}'. "
                            "Supported formats include documents (PDF, DOCX), spreadsheets (CSV, XLSX), "
                            "images (PNG, JPG, WEBP), and code files."
                        ),
                        reasoning=f"Unsupported file format rejected: {meta.filename}",
                    )

        prompt_lower = (prompt or "").lower()
        has_ocr_intent = any(sig in prompt_lower for sig in OCR_SIGNALS)
        has_math_intent = any(sig in prompt_lower for sig in MATH_SIGNALS)

        # Stage 0.2: Multimodal Image & OCR Check
        if file_metadata:
            image_files = [m for m in file_metadata if m.is_image]
            pdf_files = [m for m in file_metadata if m.extension.lower() in (".pdf", "pdf")]

            # Attached image or scanned document with explicit OCR text extraction intent
            if (image_files or pdf_files) and has_ocr_intent:
                target_tools = ["ocr_extract"]
                if has_math_intent:
                    target_tools.append("math_eval")
                selected_model = get_compatible_model_for_role("ocr")
                return RouteDecision(
                    role="ocr",
                    confidence=1.0,
                    method="ocr_detection",
                    selected_model=selected_model,
                    target_tools=target_tools,
                    is_multimodal=True,
                    requires_ocr=True,
                    fallback_role="reasoning",
                    fallback_model=get_model_for_role("reasoning"),
                    reasoning=f"Attached input requires OCR text extraction with target tools {target_tools}.",
                )

            # Attached image for visual inspection / understanding
            if image_files:
                target_tools = []
                if has_math_intent:
                    target_tools.append("math_eval")
                selected_model = get_compatible_model_for_role("vision", requires_vision=True)
                has_vision = model_supports_vision(selected_model) or is_model_available(selected_model)
                refusal_reason = None
                if not has_vision:
                    refusal_reason = f"No vision-capable model is currently available locally to process image '{image_files[0].filename}'."

                return RouteDecision(
                    role="vision",
                    confidence=1.0,
                    method="vision_detection",
                    selected_model=selected_model,
                    target_tools=target_tools,
                    is_multimodal=True,
                    requires_vision=True,
                    fallback_role="reasoning",
                    fallback_model=get_model_for_role("reasoning"),
                    refusal_reason=refusal_reason,
                    reasoning=f"Attached image '{image_files[0].filename}' requires local multimodal vision model.",
                )

            # Stage 0.3: Tabular Spreadsheet Detection (CSV, XLSX)
            spreadsheet_files = [m for m in file_metadata if m.is_spreadsheet]
            if spreadsheet_files:
                selected_model = get_model_for_role("reasoning")
                return RouteDecision(
                    role="reasoning",
                    confidence=1.0,
                    method="spreadsheet_detection",
                    selected_model=selected_model,
                    target_tools=["spreadsheet", "code_sandbox"],
                    fallback_role="reasoning",
                    fallback_model=selected_model,
                    reasoning=f"Tabular spreadsheet '{spreadsheet_files[0].filename}' requires spreadsheet analytics and sandboxed execution.",
                )

            # Stage 0.4: Document QA (PDF, DOCX)
            document_files = [m for m in file_metadata if m.is_document and not m.is_spreadsheet]
            if document_files:
                selected_model = get_model_for_role("reasoning")
                target_tools = ["rag_search"]
                if has_math_intent:
                    target_tools.append("math_eval")
                return RouteDecision(
                    role="reasoning",
                    confidence=1.0,
                    method="keyword",
                    selected_model=selected_model,
                    target_tools=target_tools,
                    reasoning=f"Attached document '{document_files[0].filename}' requires knowledge retrieval via RAG search.",
                )

        # Stage 1: Deterministic File Metadata Check (Code files)
        meta_decision = check_metadata(file_metadata)
        if meta_decision:
            meta_decision.target_tools = ["code_sandbox"]
            meta_decision.selected_model = get_model_for_role("coding")
            meta_decision.fallback_role = "reasoning"
            meta_decision.fallback_model = get_model_for_role("reasoning")
            return meta_decision

        # Stage 2: Heuristic Keyword Inspection Check (Coding signals)
        kw_decision = check_keywords(prompt)
        if kw_decision:
            kw_decision.target_tools = ["code_sandbox"]
            kw_decision.selected_model = get_model_for_role("coding")
            kw_decision.fallback_role = "reasoning"
            kw_decision.fallback_model = get_model_for_role("reasoning")
            return kw_decision

        # Stage 2.1: Mathematical or Calculation Task Check
        if has_math_intent:
            selected_model = get_model_for_role("reasoning")
            return RouteDecision(
                role="reasoning",
                confidence=0.90,
                method="keyword",
                selected_model=selected_model,
                target_tools=["math_eval"],
                reasoning="Prompt requires verified engineering/mathematical computation; targeting math_eval tool.",
            )

        # Stage 2.2: RAG / Knowledge Base query keywords
        if any(sig in prompt_lower for sig in RAG_SIGNALS):
            selected_model = get_model_for_role("reasoning")
            return RouteDecision(
                role="reasoning",
                confidence=0.85,
                method="keyword",
                selected_model=selected_model,
                target_tools=["rag_search"],
                reasoning="Prompt queries sovereign knowledge base; targeting rag_search tool.",
            )

        # Stage 3: In-Memory ML Classifier Fallback
        cls_decision = classify(prompt)
        cls_decision.selected_model = get_model_for_role(cls_decision.role)
        if cls_decision.role == "coding":
            cls_decision.target_tools = ["code_sandbox"]
            cls_decision.fallback_role = "reasoning"
            cls_decision.fallback_model = get_model_for_role("reasoning")
        return cls_decision

    async def route_and_audit(
        self,
        prompt: str,
        db: AsyncSession | None = None,
        user_id: Any | None = None,
        file_metadata: list[FileMetadata] | None = None,
        role_override: str | None = None,
    ) -> RouteDecision:
        """Executes waterfall routing and records decision in audit log if db session provided."""
        decision = self.route(prompt, file_metadata=file_metadata, role_override=role_override)
        if db:
            user_id_str = str(user_id) if user_id else None
            await emit_event(
                db=db,
                event_type="task_routed",
                user_id=user_id_str,
                resource_type="routing",
                outcome="success" if decision.is_supported else "rejected",
                detail={
                    "prompt_preview": prompt[:100] if prompt else "",
                    "role": decision.role,
                    "confidence": decision.confidence,
                    "method": decision.method,
                    "selected_model": decision.selected_model,
                    "target_tools": decision.target_tools,
                    "is_multimodal": decision.is_multimodal,
                    "is_supported": decision.is_supported,
                },
            )
        return decision


@lru_cache(maxsize=1)
def get_task_router() -> TaskRouter:
    """Returns singleton TaskRouter instance."""
    return TaskRouter()
