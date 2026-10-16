"""
app/routing/service.py
======================
Main TaskRouter service coordinating 3-stage waterfall routing:
  - Stage 0: Manual role override (if explicitly requested)
  - Stage 0.5: Multimodal image override (attached images routed to multimodal reasoning)
  - Stage 1: Deterministic file metadata check (code extensions -> coding, 1.0)
  - Stage 2: Heuristic keyword inspection (code terms with word boundaries, 0.85)
  - Stage 3: In-memory ML classifier fallback (TF-IDF + Logistic Regression)
"""

import logging
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import emit_event
from app.routing.classifier import classify
from app.routing.keyword_check import check_keywords
from app.routing.metadata_check import check_metadata
from app.routing.schemas import IMAGE_EXTENSIONS, FileMetadata, RouteDecision

logger = logging.getLogger("sovereign.routing.service")


class TaskRouter:
    """Orchestrates 3-Stage Waterfall Routing for incoming requests."""

    def route(
        self,
        prompt: str,
        file_metadata: list[FileMetadata] | None = None,
        role_override: str | None = None,
    ) -> RouteDecision:
        """Determines model role assignment using waterfall stages."""
        # Stage 0: Manual Role Override Check
        if role_override and role_override.lower() not in {"auto", ""}:
            target_role = role_override.lower()
            if target_role in {"coding", "reasoning"}:
                return RouteDecision(
                    role=target_role,  # type: ignore[arg-type]
                    confidence=1.0,
                    method="manual_override",
                    reasoning=f"User requested explicit role override: '{target_role}'.",
                )

        # Stage 0.5: Multimodal Image Override Check
        if file_metadata:
            for meta in file_metadata:
                ext = meta.extension.strip().lower()
                if not ext.startswith("."):
                    ext = f".{ext}"
                if ext in IMAGE_EXTENSIONS:
                    return RouteDecision(
                        role="reasoning",
                        confidence=1.0,
                        method="multimodal_override",
                        reasoning=f"Attached image '{meta.filename}' requires multimodal reasoning.",
                    )

        # Stage 1: Deterministic File Metadata Check
        meta_decision = check_metadata(file_metadata)
        if meta_decision:
            return meta_decision

        # Stage 2: Heuristic Keyword Inspection Check
        kw_decision = check_keywords(prompt)
        if kw_decision:
            return kw_decision

        # Stage 3: In-Memory ML Classifier Fallback
        return classify(prompt)

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
                outcome="success",
                detail={
                    "prompt_preview": prompt[:100] if prompt else "",
                    "role": decision.role,
                    "confidence": decision.confidence,
                    "method": decision.method,
                    "selected_model": decision.selected_model,
                },
            )
        return decision


@lru_cache(maxsize=1)
def get_task_router() -> TaskRouter:
    """Returns singleton TaskRouter instance."""
    return TaskRouter()
