"""
app/tools/registry.py
=====================
Central tool registry for Sovereign Workbench.
Enforces Role-Based Access Control (RBAC) on all tool invocations
and logs every execution to the append-only audit trail.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import emit_event
from app.identity.models import User
from app.sandbox.docker_sandbox import DockerSandbox
from app.tools.interface import ToolResult, ToolStatus
from app.tools.math_eval import MathEvalInput, evaluate_math

logger = logging.getLogger("sovereign.tools.registry")


@dataclass
class ToolDefinition:
    name: str
    description: str
    required_roles: set[str] = field(default_factory=lambda: {"admin", "developer", "analyst", "user"})
    handler: Callable[..., ToolResult] = field(default=lambda *args, **kwargs: ToolResult(status=ToolStatus.ERROR))


class ToolRegistry:
    """Registry managing available tools, access permissions, and audited execution."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        # 1. Safe symbolic mathematics (available to all users)
        self.register(
            ToolDefinition(
                name="math_eval",
                description="Exact symbolic formula evaluation, calculus, and equation solving using SymPy.",
                required_roles={"admin", "developer", "analyst", "user"},
                handler=self._execute_math,
            )
        )

        # 2. Isolated Docker Code Sandbox (restricted to admin, developer, analyst)
        self.register(
            ToolDefinition(
                name="code_sandbox",
                description="Isolated Docker container sandbox for untrusted Python data analysis and computations.",
                required_roles={"admin", "developer", "analyst"},
                handler=self._execute_code_sandbox,
            )
        )

    def register(self, tool_def: ToolDefinition) -> None:
        self._tools[tool_def.name] = tool_def
        logger.info("Registered tool '%s' with required roles %s", tool_def.name, tool_def.required_roles)

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_tools_for_role(self, role: str) -> list[dict[str, Any]]:
        """Returns metadata for tools the given role is authorized to use."""
        result: list[dict[str, Any]] = []
        for name, tool in self._tools.items():
            if role in tool.required_roles:
                result.append(
                    {
                        "name": name,
                        "description": tool.description,
                        "required_roles": sorted(tool.required_roles),
                    }
                )
        return result

    def _execute_math(self, input_data: dict[str, Any], session_id: str) -> ToolResult:
        typed_input = MathEvalInput(**input_data)
        return evaluate_math(typed_input)

    def _execute_code_sandbox(self, input_data: dict[str, Any], session_id: str) -> ToolResult:
        code = str(input_data.get("code", ""))
        timeout_s = input_data.get("timeout_s")
        timeout_int = int(timeout_s) if timeout_s else None

        sandbox = DockerSandbox()
        res = sandbox.execute(code=code, session_id=session_id, timeout_s=timeout_int)

        status = ToolStatus.SUCCESS if res.success else ToolStatus.ERROR
        return ToolResult(
            status=status,
            data={
                "stdout": res.stdout,
                "exit_code": res.exit_code,
                "generated_files": res.generated_files,
                "execution_time_ms": res.execution_time_ms,
                "steps": res.steps,
            },
            error=res.stderr if not res.success else None,
            metadata={"isolated": res.isolated, "execution_time_ms": res.execution_time_ms},
        )

    async def execute_tool(
        self,
        name: str,
        input_data: dict[str, Any],
        user: User,
        session_id: str,
        db: AsyncSession | None = None,
    ) -> ToolResult:
        """Executes a tool with strict RBAC permission check and audit event emission."""
        start_time = time.perf_counter()
        tool = self.get_tool(name)

        if tool is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                error=f"Tool '{name}' not found in registry.",
            )

        # RBAC Permission Check
        if user.role not in tool.required_roles:
            logger.warning(
                "Access denied: User '%s' (role='%s') attempted to execute tool '%s' (required: %s)",
                user.username,
                user.role,
                name,
                tool.required_roles,
            )
            return ToolResult(
                status=ToolStatus.ERROR,
                error=f"Permission denied: Tool '{name}' requires one of the following roles: {sorted(tool.required_roles)}. Your role is '{user.role}'.",
            )

        # Execute handler
        try:
            result = tool.handler(input_data, session_id)
        except Exception as exc:
            logger.exception("Error executing tool '%s': %s", name, exc)
            result = ToolResult(
                status=ToolStatus.ERROR,
                error=f"Internal tool execution error: {exc}",
            )

        duration_ms = (time.perf_counter() - start_time) * 1000
        result.metadata["duration_ms"] = round(duration_ms, 2)
        result.metadata["tool_name"] = name
        result.metadata["session_id"] = session_id

        # Record audit event
        if db is not None:
            await emit_event(
                db=db,
                event_type="tool_executed",
                user_id=str(user.id),
                resource_type="tool",
                resource_id=name,
                outcome=result.status.value,
                detail={
                    "tool": name,
                    "session_id": session_id,
                    "duration_ms": round(duration_ms, 2),
                    "status": result.status.value,
                },
                summary=f"Executed tool '{name}' -> {result.status.value}",
            )

        return result


_registry_instance: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Returns singleton ToolRegistry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ToolRegistry()
    return _registry_instance
