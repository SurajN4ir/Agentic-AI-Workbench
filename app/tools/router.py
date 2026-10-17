"""
app/tools/router.py
===================
FastAPI router for tool discovery and execution.
All endpoints require authentication and enforce Role-Based Access Control.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.tools.interface import ToolResult
from app.tools.math_eval import MathEvalInput, MathEvalResult, evaluate_math
from app.tools.registry import ToolRegistry, get_tool_registry

router = APIRouter(prefix="/tools", tags=["Tools & Execution"])


class ToolExecuteRequest(BaseModel):
    name: str = Field(..., description="Tool name, e.g. 'math_eval' or 'code_sandbox'")
    input: dict[str, Any] = Field(..., description="Tool input parameters")
    session_id: str = Field(default="default_session", description="Unique session ID for workspace scoping")


class CodeSandboxRequest(BaseModel):
    code: str = Field(..., description="Python script to execute in container sandbox")
    session_id: str = Field(default="default_session", description="Session ID for workspace")
    timeout_s: int = Field(default=15, ge=1, le=60, description="Execution timeout limit in seconds")


@router.get("", response_model=list[dict[str, Any]])
async def list_available_tools(
    current_user: User = Depends(get_current_user),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> list[dict[str, Any]]:
    """Returns tools available to the authenticated user based on their active role."""
    return registry.list_tools_for_role(current_user.role)


@router.post("/execute", response_model=ToolResult)
async def execute_tool_endpoint(
    payload: ToolExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> ToolResult:
    """Executes a tool with RBAC permission enforcement and audit logging."""
    tool = registry.get_tool(payload.name)
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{payload.name}' not found.",
        )

    if current_user.role not in tool.required_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Tool '{payload.name}' requires role in {sorted(tool.required_roles)}. Your role is '{current_user.role}'.",
        )

    return await registry.execute_tool(
        name=payload.name,
        input_data=payload.input,
        user=current_user,
        session_id=payload.session_id,
        db=db,
    )


@router.post("/math", response_model=MathEvalResult)
async def execute_math_endpoint(
    payload: MathEvalInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> MathEvalResult:
    """Safely computes algebraic and calculus mathematics using SymPy."""
    result = evaluate_math(payload)
    return result


@router.post("/sandbox", response_model=ToolResult)
async def execute_sandbox_endpoint(
    payload: CodeSandboxRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> ToolResult:
    """Executes untrusted code within an isolated, air-gapped Docker sandbox (requires developer/analyst/admin role)."""
    tool = registry.get_tool("code_sandbox")
    if tool is None or current_user.role not in tool.required_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: 'code_sandbox' requires developer, analyst, or admin privileges. Your role is '{current_user.role}'.",
        )

    return await registry.execute_tool(
        name="code_sandbox",
        input_data={"code": payload.code, "timeout_s": payload.timeout_s},
        user=current_user,
        session_id=payload.session_id,
        db=db,
    )
