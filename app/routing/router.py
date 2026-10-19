"""
app/routing/router.py
=====================
FastAPI router for task routing and model registry inspection.
Protected endpoints requiring valid authentication.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.models.registry import (
    get_default_provider,
    get_model_options,
    get_model_registry,
    load_models_config,
)
from app.models.schemas import ModelOption
from app.routing.schemas import FileMetadata, RouteDecision
from app.routing.service import TaskRouter, get_task_router

router = APIRouter(prefix="/routing", tags=["Routing & Models"])


class RouteRequest(BaseModel):
    prompt: str = Field(..., description="User prompt text to classify and route")
    file_metadata: list[FileMetadata] | None = Field(default=None, description="Metadata of attached files")
    role_override: str | None = Field(
        default=None, description="Optional manual override ('auto', 'coding', 'reasoning')"
    )


class RouteResponse(BaseModel):
    role: str
    confidence: float
    method: str
    selected_model: str
    reasoning: str | None = None


class ModelsResponse(BaseModel):
    models: dict[str, Any]
    registry: dict[str, str]
    options: list[ModelOption]
    inference_backend_healthy: bool


@router.post("/route", response_model=RouteResponse)
async def route_task(
    payload: RouteRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    task_router: TaskRouter = Depends(get_task_router),
) -> RouteResponse:
    """Classifies a user task prompt and attached files, resolving to the appropriate model."""
    decision: RouteDecision = await task_router.route_and_audit(
        prompt=payload.prompt,
        db=db,
        user_id=current_user.id,
        file_metadata=payload.file_metadata,
        role_override=payload.role_override,
    )
    return RouteResponse(
        role=decision.role,
        confidence=decision.confidence,
        method=decision.method,
        selected_model=decision.model_tag,
        reasoning=decision.reasoning,
    )


@router.get("/models", response_model=ModelsResponse)
async def get_models(
    current_user: User = Depends(get_current_user),
) -> ModelsResponse:
    """Returns configured model mappings, UI selection options, and inference backend health."""
    provider = get_default_provider()
    is_healthy = await provider.health_check()
    cfg = load_models_config()

    return ModelsResponse(
        models=cfg.get("models", {}),
        registry=get_model_registry(),
        options=get_model_options(),
        inference_backend_healthy=is_healthy,
    )
