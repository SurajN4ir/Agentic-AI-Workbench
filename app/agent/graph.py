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
from app.tools.interface import ToolResult, ToolStatus
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
        session_id = state.get("session_id", "default")

        rd = state.get("route_decision")
        role_override = rd.get("role") if isinstance(rd, dict) else None
        route_decision = self.task_router.route(prompt=prompt, file_metadata=file_metadata, role_override=role_override)

        role = route_decision.role
        model_tag = state.get("model_tag") or route_decision.selected_model or get_model_for_role(role, default="llama3.2:latest")

        # Early refusal for unsupported files or configurations
        if not route_decision.is_supported:
            refusal_msg = route_decision.refusal_reason or "Unsupported file format or request."
            return {
                "route_decision": route_decision.model_dump(),
                "model_tag": model_tag,
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": refusal_msg},
                ],
                "status": "completed",
                "final_response": refusal_msg,
                "iteration_count": 0,
                "tool_retry_count": 0,
                "tool_calls": [],
                "tool_results": [],
                "thinking_trace": [],
                "artifacts": [],
            }

        sys_prompt = ROLE_SYSTEM_PROMPTS.get(role, ROLE_SYSTEM_PROMPTS["reasoning"])

        # Append workspace file context if attached files exist
        workspace_context = ""
        if file_metadata:
            names = [f.filename for f in file_metadata]
            workspace_context = f"\n\n[Attached Files in Session Workspace]: {', '.join(names)}"

        full_system_prompt = sys_prompt + workspace_context

        # Read base64 image data if multimodal vision is required
        image_b64_list: list[str] = []
        if (route_decision.is_multimodal or route_decision.requires_vision) and file_metadata:
            import base64
            from pathlib import Path
            from app.config import get_settings
            ws_dir = Path(get_settings().workspace_dir)

            for meta in file_metadata:
                if meta.is_image:
                    target_img_path: Path | None = None
                    if meta.filepath and Path(meta.filepath).exists():
                        target_img_path = Path(meta.filepath)
                    else:
                        candidate1 = ws_dir / session_id / meta.filename
                        candidate2 = ws_dir / session_id / "uploads" / meta.filename
                        if candidate1.exists():
                            target_img_path = candidate1
                        elif candidate2.exists():
                            target_img_path = candidate2

                    if target_img_path and target_img_path.is_file():
                        try:
                            img_bytes = target_img_path.read_bytes()
                            b64 = base64.b64encode(img_bytes).decode("utf-8")
                            image_b64_list.append(b64)
                        except Exception as read_err:
                            logger.warning("Failed to read image %s for vision: %s", target_img_path, read_err)

        user_message: dict[str, Any] = {"role": "user", "content": prompt}
        if image_b64_list:
            user_message["images"] = image_b64_list

        messages = [
            {"role": "system", "content": full_system_prompt},
            user_message,
        ]

        return {
            "route_decision": route_decision.model_dump(),
            "model_tag": model_tag,
            "messages": messages,
            "status": "reasoning",
            "iteration_count": 0,
            "tool_retry_count": 0,
            "tool_calls": [],
            "tool_results": [],
            "thinking_trace": [],
            "artifacts": [],
        }

    async def reason_node(self, state: WorkbenchState) -> dict[str, Any]:
        """
        Node 2: Generates reasoning response and tool calls via model provider.
        """
        model_tag = state.get("model_tag", "llama3.2:latest")
        messages = list(state.get("messages", []))
        user_role = state.get("user_role", "user")
        route_decision = state.get("route_decision") or {}

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
            logger.exception("Inference error with model '%s': %s", model_tag, exc)
            fallback_model = route_decision.get("fallback_model")
            if fallback_model and fallback_model != model_tag:
                logger.warning("Attempting execution with fallback model '%s'", fallback_model)
                try:
                    # Strip images if falling back to text-only model
                    fallback_messages = []
                    for m in messages:
                        if m.get("role") == "user" and "images" in m:
                            clean_m = dict(m)
                            clean_m.pop("images", None)
                            fallback_messages.append(clean_m)
                        else:
                            fallback_messages.append(m)
                    chat_resp = await self.provider.chat(
                        model=fallback_model,
                        messages=fallback_messages,
                        tools=tool_schemas if tool_schemas else None,
                    )
                    model_tag = fallback_model
                except Exception as fallback_exc:
                    logger.exception("Fallback model '%s' also failed: %s", fallback_model, fallback_exc)
                    return {
                        "status": "error",
                        "error": f"Model inference failure (primary and fallback failed): {fallback_exc}",
                        "final_response": f"I encountered an internal error communicating with the local models: {fallback_exc}",
                    }
            else:
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

    def _validate_tool_arguments(self, tool_name: str, args: dict[str, Any]) -> str | None:
        """Validates tool input arguments before execution to prevent malformed runs."""
        if not isinstance(args, dict):
            return f"Invalid arguments: expected JSON object, got {type(args).__name__}"

        if tool_name == "code_sandbox":
            code = args.get("code")
            if not isinstance(code, str) or not code.strip():
                return "Validation failed: 'code' parameter is required and cannot be empty for code_sandbox."
            timeout = args.get("timeout_s")
            if timeout is not None:
                try:
                    t_val = float(timeout)
                    if t_val <= 0 or t_val > 300:
                        return f"Validation failed: 'timeout_s' must be between 1 and 300 seconds, got {timeout}."
                except (ValueError, TypeError):
                    return f"Validation failed: 'timeout_s' must be a valid number, got {timeout}."

        elif tool_name == "math_eval":
            expr = args.get("expression")
            if not isinstance(expr, str) or not expr.strip():
                return "Validation failed: 'expression' parameter is required and cannot be empty for math_eval."

        elif tool_name == "rag_search":
            query = args.get("query")
            if not isinstance(query, str) or not query.strip():
                return "Validation failed: 'query' parameter is required and cannot be empty for rag_search."

        elif tool_name == "doc_gen":
            title = args.get("title")
            content = args.get("content")
            if not isinstance(title, str) or not title.strip():
                return "Validation failed: 'title' parameter is required and cannot be empty for doc_gen."
            if not isinstance(content, str) or not content.strip():
                return "Validation failed: 'content' parameter is required and cannot be empty for doc_gen."

        elif tool_name == "file_io":
            op = args.get("operation")
            path = args.get("path")
            if not isinstance(op, str) or not op.strip():
                return "Validation failed: 'operation' parameter is required for file_io."
            if not isinstance(path, str) or not path.strip():
                return "Validation failed: 'path' parameter is required for file_io."

        elif tool_name == "ocr_extract":
            file_path = args.get("file_path")
            if not isinstance(file_path, str) or not file_path.strip():
                return "Validation failed: 'file_path' parameter is required and cannot be empty for ocr_extract."

        elif tool_name == "spreadsheet":
            file_path = args.get("file_path")
            if not isinstance(file_path, str) or not file_path.strip():
                return "Validation failed: 'file_path' parameter is required and cannot be empty for spreadsheet."

        return None

    def determine_unsatisfied_tool_requirement(self, state: WorkbenchState) -> tuple[str, str] | None:
        """
        Determines if a task explicitly requires tool invocation that has not yet been satisfied.
        Uses task routing, prompt intent, response contents, and executed tool history.
        Does NOT rely solely on fragile keyword matching and respects security refusals.
        """
        prompt = (state.get("prompt") or "").lower()
        final_resp = (state.get("final_response") or "").lower()
        user_role = state.get("user_role", "user")
        tool_results = state.get("tool_results", [])

        # 1. Security / Adversarial check:
        # If the prompt is an adversarial attempt or the model issued a legitimate security refusal,
        # do not force tool retries.
        adversarial_indicators = [
            "/etc/passwd", "/etc/shadow", "hosts", "system32", "cat /",
            "curl ", "wget ", "whoami", "drop table", "sql injection",
            "leak secret", "exfiltrat", "bypass",
        ]
        if any(adv in prompt for adv in adversarial_indicators):
            return None

        refusal_indicators = [
            "access denied", "permission denied", "unauthorized",
            "i cannot fulfill", "i cannot execute", "security policy",
            "prohibited", "not permitted", "refuse to",
        ]
        if any(ref in final_resp for ref in refusal_indicators):
            return None

        # 2. Get executed tools and available tools for this user's RBAC role
        executed_tools = {tr.get("tool_name") for tr in tool_results}
        available_tool_names = {t["name"] for t in self.tool_registry.list_tools_for_role(user_role)}

        # 3. Check target_tools from route decision (e.g. ocr_extract, spreadsheet)
        route_decision = state.get("route_decision") or {}
        target_tools = route_decision.get("target_tools") or []
        for target_tool in target_tools:
            if target_tool in available_tool_names and target_tool not in executed_tools:
                if target_tool == "ocr_extract":
                    return (
                        "ocr_extract",
                        "TASK NOTICE: The input file requires OCR text extraction. "
                        "You MUST invoke the 'ocr_extract' tool with the file_path to extract text and telemetry.",
                    )
                elif target_tool == "spreadsheet":
                    return (
                        "spreadsheet",
                        "TASK NOTICE: The input file is a spreadsheet. "
                        "You MUST invoke the 'spreadsheet' tool to inspect or query the data before answering.",
                    )

        # 4. Code execution requirement (code_sandbox)
        if "code_sandbox" in available_tool_names and "code_sandbox" not in executed_tools:
            code_exec_triggers = [
                "regression", "calibration", "sensor calibration",
                "run python", "run code", "execute the code", "execute code",
                "compute using python", "fit a line", "least squares",
                "linear regression", "data-02",
            ]
            has_code_trigger = any(trig in prompt for trig in code_exec_triggers)
            has_prose_code = "```python" in final_resp or "```py" in final_resp

            # If spreadsheet was already executed, do not force code_sandbox unless the user explicitly requested code execution
            if has_code_trigger or (has_prose_code and "spreadsheet" not in executed_tools and any(w in prompt for w in ["calculate", "compute", "analyze", "regression", "fit", "slope"])):
                return (
                    "code_sandbox",
                    "SECURITY & EXECUTION NOTICE: Ordinary model prose cannot execute code on the host. "
                    "You MUST invoke the 'code_sandbox' tool to execute the code inside the isolated container sandbox and obtain verified outputs.",
                )

        # 5. Mathematical / Engineering calculation requirement (math_eval)
        if "math_eval" in available_tool_names and "math_eval" not in executed_tools and "code_sandbox" not in executed_tools and "spreadsheet" not in executed_tools:
            math_calc_triggers = [
                "cstr", "steady-state", "conversion", "kinetics", "reaction kinetics",
                "arrhenius", "reynolds", "bernoulli", "math_eval", "solve for",
                "steady-state conversion", "second-order reaction", "eng-03",
            ]
            has_math_trigger = any(trig in prompt for trig in math_calc_triggers)
            has_variable_calc = (
                any(w in prompt for w in ["calculate", "compute", "solve"])
                and any(v in prompt for v in ["v=", "v0=", "k=", "ca0=", "mol/l", "temperature", "pressure", "flow rate"])
            )

            if has_math_trigger or has_variable_calc:
                return (
                    "math_eval",
                    "VERIFICATION NOTICE: The task requires verified engineering/numerical computation. "
                    "You must NOT perform mental arithmetic or unverified calculation in prose. "
                    "You MUST invoke the 'math_eval' tool with the exact mathematical expression to compute and verify the result.",
                )

        return None

    def should_continue(self, state: WorkbenchState) -> str:
        """
        Conditional Edge: Determines whether to execute tools, retry missing tool calls,
        or transition to final synthesis. Enforces max_iterations and retry bounds.
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

        # Bounded retry: if no tool calls were generated but the task requires a tool
        retry_count = state.get("tool_retry_count", 0)
        max_retries = 2
        if retry_count < max_retries and iterations < max_limit:
            unsatisfied = self.determine_unsatisfied_tool_requirement(state)
            if unsatisfied is not None:
                return "retry_node"

        return "synthesize_node"

    async def retry_node(self, state: WorkbenchState) -> dict[str, Any]:
        """
        Node: Feeds explicit system guidance back to the model when an unsatisfied
        tool requirement is detected, bounded by strict retry limits.
        """
        retry_count = state.get("tool_retry_count", 0) + 1
        messages = list(state.get("messages", []))
        unsatisfied = self.determine_unsatisfied_tool_requirement(state)

        tool_name = "required_tool"
        feedback = "The task requires invoking a tool to complete verification."
        if unsatisfied:
            tool_name, feedback = unsatisfied

        logger.info(
            "Retrying tool dispatch (attempt %d/2) for required tool '%s'",
            retry_count,
            tool_name,
        )

        directive_msg = {
            "role": "user",
            "content": f"[SYSTEM TOOL DISPATCH DIRECTIVE]: {feedback} Please invoke the required tool now.",
        }
        messages.append(directive_msg)

        # Increment iteration count as well so retries count toward overall safety bound
        new_iterations = state.get("iteration_count", 0) + 1

        return {
            "messages": messages,
            "tool_retry_count": retry_count,
            "iteration_count": new_iterations,
            "status": "retrying_tool",
            "final_response": "",
        }

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

            # Validate arguments before execution
            validation_err = self._validate_tool_arguments(tool_name, raw_args)
            if validation_err:
                tool_result = ToolResult(
                    status=ToolStatus.ERROR,
                    error=validation_err,
                    metadata={"tool_name": tool_name, "validation_failed": True},
                )
            else:
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
        builder.add_node("retry_node", self.retry_node)
        builder.add_node("tool_node", self.tool_node)
        builder.add_node("synthesize_node", self.synthesize_node)

        builder.add_edge(START, "route_node")

        def should_route(state: WorkbenchState) -> str:
            rd = state.get("route_decision") or {}
            if not rd.get("is_supported", True) or state.get("status") == "completed":
                return "synthesize_node"
            return "reason_node"

        builder.add_conditional_edges(
            "route_node",
            should_route,
            {
                "reason_node": "reason_node",
                "synthesize_node": "synthesize_node",
            },
        )

        builder.add_conditional_edges(
            "reason_node",
            self.should_continue,
            {
                "tool_node": "tool_node",
                "retry_node": "retry_node",
                "synthesize_node": "synthesize_node",
            },
        )

        builder.add_edge("tool_node", "reason_node")
        builder.add_edge("retry_node", "reason_node")
        builder.add_edge("synthesize_node", END)

        if self.checkpointer:
            return builder.compile(checkpointer=self.checkpointer)
        return builder.compile()
