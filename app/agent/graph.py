"""
app/agent/graph.py
==================
ReAct LangGraph Orchestrator for Sovereign Agentic AI Workbench.
Topology:
  START -> route_node -> reason_node -> (should_continue) -> tool_node -> reason_node -> ...
                                      \\-> synthesize_node -> END

Enforces:
  1. Strict iteration safety bound (max_iterations, default 8, hard ceiling 15).
  2. RBAC permission checks on every tool dispatch.
  3. In-memory and persistent PostgreSQL checkpointing compatibility.
  4. Fallback JSON tool call extraction for open-weight local models.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.parser import parse_json_tool_calls
from app.agent.prompts import ROLE_SYSTEM_PROMPTS
from app.agent.state import WorkbenchState
from app.identity.models import User
from app.models.base import BaseModelProvider
from app.models.registry import get_default_provider, get_model_for_role
from app.routing.schemas import FileMetadata
from app.routing.service import TaskRouter
from app.tools.interface import ToolStatus
from app.tools.registry import ToolRegistry, get_tool_registry

logger = logging.getLogger("sovereign.agent.graph")


class AgentGraphBuilder:
    """Builds and compiles the bounded ReAct StateGraph with injected dependencies."""

    def __init__(
        self,
        provider: BaseModelProvider | None = None,
        tool_registry: ToolRegistry | None = None,
        task_router: TaskRouter | None = None,
        db: AsyncSession | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        self.provider = provider or get_default_provider()
        self.tool_registry = tool_registry or get_tool_registry()
        self.task_router = task_router or TaskRouter()
        self.db = db
        self.checkpointer = checkpointer

    async def route_node(self, state: WorkbenchState) -> dict[str, Any]:
        """
        Node 1: Evaluates 3-stage waterfall router and initializes workspace system prompt.
        """
        prompt = state.get("prompt", "")
        file_meta_raw = state.get("file_metadata", [])
        file_metadata = [FileMetadata(**fm) if isinstance(fm, dict) else fm for fm in file_meta_raw]

        rd = state.get("route_decision")
        role_override = rd.get("role") if isinstance(rd, dict) else None
        route_decision = self.task_router.route(prompt=prompt, file_metadata=file_metadata, role_override=role_override)


        role = route_decision.role
        model_tag = state.get("model_tag") or get_model_for_role(role, default="llama3.2:latest")

        sys_prompt = ROLE_SYSTEM_PROMPTS.get(role, ROLE_SYSTEM_PROMPTS["reasoning"])

        # Append workspace file context if attached files exist
        workspace_context = ""
        if file_metadata:
            names = [f.filename for f in file_metadata]
            workspace_context = f"\n\n[Attached Files in Session Workspace]: {', '.join(names)}"

        full_system_prompt = sys_prompt + workspace_context
        messages = [
            {"role": "system", "content": full_system_prompt},
            {"role": "user", "content": prompt},
        ]

        return {
            "route_decision": route_decision.model_dump(),
            "model_tag": model_tag,
            "messages": messages,
            "status": "reasoning",
            "iteration_count": 0,
            "tool_calls": [],
            "tool_results": [],
            "thinking_trace": [],
            "artifacts": [],
        }

    async def reason_node(self, state: WorkbenchState) -> dict[str, Any]:
        """
        Node 2: Generates reasoning response and tool calls via model provider.
        """
        model_tag = state.get("model_tag", "qwen2.5:3b")
        messages = list(state.get("messages", []))
        user_role = state.get("user_role", "user")

        # Get permitted tool schemas for the caller's RBAC role
        tool_schemas = self.tool_registry.get_tool_schemas_for_role(user_role)
        available_tool_names = {t["name"] for t in self.tool_registry.list_tools_for_role(user_role)}

        try:
            chat_resp = await self.provider.chat(
                model=model_tag,
                messages=messages,
                tools=tool_schemas if tool_schemas else None,
            )
        except Exception as exc:
            logger.exception("Inference error in reason_node: %s", exc)
            return {
                "status": "error",
                "error": f"Model inference failure: {exc}",
                "final_response": f"I encountered an internal error communicating with the local model: {exc}",
            }

        msg = chat_resp.message
        content = msg.content or ""
        tool_calls = msg.tool_calls or []

        thinking_trace = list(state.get("thinking_trace", []))
        if chat_resp.thinking_content:
            thinking_trace.append(chat_resp.thinking_content)

        # Fallback parser: scan text content for JSON tool calls if model didn't use native tool_calls
        if not tool_calls and content and available_tool_names:
            extracted_calls = parse_json_tool_calls(content, available_tool_names)
            if extracted_calls:
                tool_calls = extracted_calls
                # Clean content if it was purely a tool call payload
                content = ""

        # Update messages history
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        updated_messages = list(messages) + [assistant_msg]

        update: dict[str, Any] = {
            "messages": updated_messages,
            "tool_calls": tool_calls,
            "thinking_trace": thinking_trace,
        }

        if tool_calls:
            update["status"] = "executing_tools"
        else:
            update["status"] = "synthesizing"
            update["final_response"] = content

        return update

    def should_continue(self, state: WorkbenchState) -> str:
        """
        Conditional Edge: Determines whether to execute tools or transition to final synthesis.
        Enforces max_iterations safety bounds to eliminate infinite loop risks.
        """
        has_tool_calls = bool(state.get("tool_calls"))
        iterations = state.get("iteration_count", 0)
        max_limit = min(state.get("max_iterations", 8), 15)

        if has_tool_calls:
            if iterations >= max_limit:
                logger.warning(
                    "Agent reached safety iteration limit (%d >= %d). Halting loop.",
                    iterations,
                    max_limit,
                )
                return "synthesize_node"
            return "tool_node"
        return "synthesize_node"

    async def tool_node(self, state: WorkbenchState) -> dict[str, Any]:
        """
        Node 3: Executes pending tool calls with RBAC verification and session isolation.
        """
        tool_calls = state.get("tool_calls", [])
        user_id_str = state.get("user_id") or str(uuid.uuid4())
        user_role = state.get("user_role", "user")
        username = state.get("username", "system_user")
        session_id = state.get("session_id", "default_session")

        # Construct synthetic User instance for RBAC and audit logging
        synthetic_user = User(
            id=uuid.UUID(user_id_str) if isinstance(user_id_str, str) and len(user_id_str) == 36 else uuid.uuid4(),
            username=username,
            role=user_role,
            is_active=True,
            password_hash="",  # noqa: S106

        )

        updated_messages = list(state.get("messages", []))
        tool_results = list(state.get("tool_results", []))
        artifacts = list(state.get("artifacts", []))

        for call in tool_calls:
            call_id = call.get("id") or f"call_{uuid.uuid4().hex[:8]}"
            func_data = call.get("function", {})
            tool_name = func_data.get("name", "")
            raw_args = func_data.get("arguments", {})

            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except Exception:
                    raw_args = {}

            # Execute tool through secure RBAC-enforcing ToolRegistry
            tool_result = await self.tool_registry.execute_tool(
                name=tool_name,
                input_data=raw_args,
                user=synthetic_user,
                session_id=session_id,
                db=self.db,
            )

            # Record serialized tool result in state
            res_dict = {
                "tool_name": tool_name,
                "tool_call_id": call_id,
                "status": tool_result.status.value,
                "output": tool_result.output,
                "data": tool_result.data,
                "error": tool_result.error,
                "metadata": tool_result.metadata,
            }
            tool_results.append(res_dict)

            # Check for generated artifact files
            if tool_result.status == ToolStatus.SUCCESS and isinstance(tool_result.data, dict):
                gen_files = tool_result.data.get("generated_files", [])
                for gf in gen_files:
                    artifacts.append({
                        "filename": Path(gf).name,
                        "path": str(gf),
                        "tool": tool_name,
                        "session_id": session_id,
                    })

            # Format tool response message for LLM context
            output_content = tool_result.output or tool_result.error or json.dumps(tool_result.data or {})
            tool_msg = {
                "role": "tool",
                "content": str(output_content),
                "tool_call_id": call_id,
            }
            updated_messages.append(tool_msg)

        new_iteration_count = state.get("iteration_count", 0) + 1

        return {
            "messages": updated_messages,
            "tool_results": tool_results,
            "artifacts": artifacts,
            "tool_calls": [],
            "iteration_count": new_iteration_count,
            "status": "reasoning",
        }

    async def synthesize_node(self, state: WorkbenchState) -> dict[str, Any]:
        """
        Node 4: Synthesizes final response, handles iteration cutoff notices, and closes task.
        """
        final_resp = state.get("final_response")
        iteration_count = state.get("iteration_count", 0)
        max_iterations = min(state.get("max_iterations", 8), 15)
        tool_results = state.get("tool_results", [])

        # If loop was cut off by max_iterations safety bound without final text
        if iteration_count >= max_iterations and (not final_resp or not final_resp.strip()):
            summary_lines = [
                f"**Task Notice**: Reached maximum tool execution limit ({iteration_count} iterations).",
                "",
                "### Intermediate Tool Results:",
            ]
            for tr in tool_results:
                status_icon = "PASS" if tr["status"] == "success" else "FAIL"
                summary_lines.append(f"- **{tr['tool_name']}** [{status_icon}]: {tr.get('output') or tr.get('error') or 'Completed'}")

            final_resp = "\n".join(summary_lines)
            return {
                "final_response": final_resp,
                "status": "max_iterations_reached",
            }

        # If no tool calls and response was already generated
        if not final_resp:
            final_resp = "Task processed successfully."

        return {
            "final_response": final_resp,
            "status": "completed",
        }

    def build(self) -> Any:
        """Assembles and compiles the StateGraph workflow."""

        builder = StateGraph(WorkbenchState)

        builder.add_node("route_node", self.route_node)
        builder.add_node("reason_node", self.reason_node)
        builder.add_node("tool_node", self.tool_node)
        builder.add_node("synthesize_node", self.synthesize_node)

        builder.add_edge(START, "route_node")
        builder.add_edge("route_node", "reason_node")

        builder.add_conditional_edges(
            "reason_node",
            self.should_continue,
            {
                "tool_node": "tool_node",
                "synthesize_node": "synthesize_node",
            },
        )

        builder.add_edge("tool_node", "reason_node")
        builder.add_edge("synthesize_node", END)

        if self.checkpointer:
            return builder.compile(checkpointer=self.checkpointer)
        return builder.compile()
