"""
app/tools/registry.py
=====================
Central tool registry for Sovereign Workbench.
Enforces Role-Based Access Control (RBAC) on all tool invocations
and logs every execution to the append-only audit trail.
"""

import inspect
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
    schema: dict[str, Any] = field(default_factory=dict)
    required_roles: set[str] = field(default_factory=lambda: {"admin", "developer", "analyst", "user"})
    handler: Callable[..., Any] = field(default=lambda *args, **kwargs: ToolResult(status=ToolStatus.ERROR))


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
                schema={
                    "type": "function",
                    "function": {
                        "name": "math_eval",
                        "description": "Exact symbolic formula evaluation, calculus, and equation solving using SymPy.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "expression": {
                                    "type": "string",
                                    "description": "Mathematical expression (e.g. '2*x + 5 = 15', 'diff(sin(x)*exp(x), x)', 'integrate(x**2, x)', 'sqrt(144) + 12')",
                                },
                                "operation": {
                                    "type": "string",
                                    "enum": ["eval", "simplify", "diff", "integrate", "solve"],
                                    "description": "The mathematical operation to execute. Default is 'eval'.",
                                },
                                "variable": {
                                    "type": "string",
                                    "description": "Variable with respect to which to differentiate, integrate, or solve (default 'x').",
                                },
                            },
                            "required": ["expression"],
                        },
                    },
                },
                required_roles={"admin", "developer", "analyst", "user"},
                handler=self._execute_math,
            )
        )

        # 2. Isolated Docker Code Sandbox (restricted to admin, developer, analyst)
        self.register(
            ToolDefinition(
                name="code_sandbox",
                description="Isolated Docker container sandbox for untrusted Python data analysis and computations.",
                schema={
                    "type": "function",
                    "function": {
                        "name": "code_sandbox",
                        "description": "Execute untrusted Python code inside an isolated, air-gapped Docker container with numpy, pandas, scipy, sympy, openpyxl, matplotlib.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "code": {
                                    "type": "string",
                                    "description": "Complete Python script to execute. Write to stdout for tabular or text results, or save output files directly into the workspace.",
                                },
                                "timeout_s": {
                                    "type": "integer",
                                    "description": "Execution timeout in seconds (default: 30, maximum: 60).",
                                },
                            },
                            "required": ["code"],
                        },
                    },
                },
                required_roles={"admin", "developer", "analyst"},
                handler=self._execute_code_sandbox,
            )
        )

        # 3. Private Sovereign RAG Knowledge Base Search
        self.register(
            ToolDefinition(
                name="rag_search",
                description="Query the private sovereign document knowledge base using pgvector semantic vector search.",
                schema={
                    "type": "function",
                    "function": {
                        "name": "rag_search",
                        "description": "Query the private sovereign document knowledge base using pgvector semantic vector search to retrieve authoritative facts, specifications, and procedures.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Natural language search query to retrieve relevant facts from ingested documents.",
                                },
                                "top_k": {
                                    "type": "integer",
                                    "description": "Number of most relevant text chunks to retrieve (default: 4).",
                                },
                                "collection_id": {
                                    "type": "string",
                                    "description": "Knowledge collection identifier (default: 'default').",
                                },
                            },
                            "required": ["query"],
                        },
                    },
                },
                required_roles={"admin", "developer", "analyst", "user"},
                handler=self._execute_rag_search,
            )
        )

        # 4. Deliverable Document Generator (Word .docx, Excel .xlsx, Markdown)
        self.register(
            ToolDefinition(
                name="doc_gen",
                description="Generate downloadable reports and workbooks (.docx, .xlsx, .md) inside the session workspace.",
                schema={
                    "type": "function",
                    "function": {
                        "name": "doc_gen",
                        "description": "Generate a downloadable Word report (.docx), Excel spreadsheet (.xlsx), or Markdown document.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "format": {
                                    "type": "string",
                                    "enum": ["docx", "xlsx", "markdown"],
                                    "description": "The output file format.",
                                },
                                "title": {
                                    "type": "string",
                                    "description": "Title of the document or report.",
                                },
                                "filename": {
                                    "type": "string",
                                    "description": "Desired filename (e.g. 'summary_report.docx', 'financial_model.xlsx').",
                                },
                                "sections": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "heading": {"type": "string"},
                                            "body": {"type": "string"},
                                        },
                                        "required": ["body"],
                                    },
                                    "description": "Text sections for docx or markdown reports.",
                                },
                                "table": {
                                    "type": "object",
                                    "properties": {
                                        "headers": {"type": "array", "items": {"type": "string"}},
                                        "rows": {"type": "array", "items": {"type": "array"}},
                                    },
                                    "description": "Optional tabular data to include in the document or spreadsheet.",
                                },
                            },
                            "required": ["format", "title"],
                        },
                    },
                },
                required_roles={"admin", "developer", "analyst", "user"},
                handler=self._execute_doc_gen,
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

    def get_tool_schemas_for_role(self, role: str) -> list[dict[str, Any]]:
        """Returns Ollama/OpenAI-compatible tool schemas permitted for user's role."""
        schemas: list[dict[str, Any]] = []
        for tool in self._tools.values():
            if role in tool.required_roles and tool.schema:
                schemas.append(tool.schema)
        return schemas

    async def _execute_rag_search(
        self,
        input_data: dict[str, Any],
        session_id: str,
        db: AsyncSession | None = None,
    ) -> ToolResult:
        query = str(input_data.get("query", "")).strip()
        if not query:
            return ToolResult(status=ToolStatus.ERROR, error="Search query cannot be empty.")
        top_k = int(input_data.get("top_k", 4))
        collection_id = str(input_data.get("collection_id", "default"))

        if db is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                error="Database session unavailable for knowledge search.",
            )

        from app.knowledge.service import KnowledgeService

        service = KnowledgeService()
        results = await service.search(db=db, query=query, top_k=top_k, collection_id=collection_id)


        if not results:
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={"results": [], "summary": "No matching knowledge base documents found."},
                output="No matching knowledge base documents found for query.",
            )

        formatted_chunks = []
        for i, r in enumerate(results, start=1):
            formatted_chunks.append(
                {
                    "source": r.filename,
                    "page": r.page_number,
                    "similarity": round(r.similarity, 4),
                    "section": r.section_type,
                    "content": r.content,
                    "citation": r.citation_header(i),
                }
            )

        output_text = "\n\n".join([f"{c['citation']}\n{c['content']}" for c in formatted_chunks])
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={"results": formatted_chunks, "count": len(formatted_chunks)},
            output=output_text,
        )

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

    def _execute_doc_gen(self, input_data: dict[str, Any], session_id: str) -> ToolResult:
        from app.artifacts.generator import ArtifactGenerator
        from app.artifacts.models import ReportSpec, SheetSpec, SpreadsheetSpec, TableBlock, TextBlock

        fmt = str(input_data.get("format", "docx")).lower().strip()
        title = str(input_data.get("title", "Report")).strip()
        filename = str(input_data.get("filename") or f"{title.lower().replace(' ', '_')}.{fmt}")

        sections_raw = input_data.get("sections", [])
        table_raw = input_data.get("table")

        blocks: list[TextBlock | TableBlock] = []
        for s in sections_raw:
            if isinstance(s, dict) and "body" in s:
                blocks.append(TextBlock(heading=s.get("heading"), body=s["body"]))

        if isinstance(table_raw, dict) and "headers" in table_raw and "rows" in table_raw:
            blocks.append(TableBlock(headers=table_raw["headers"], rows=table_raw["rows"], caption=table_raw.get("caption")))

        try:
            if fmt == "docx":
                spec = ReportSpec(title=title, sections=blocks, filename=filename)
                out_path = ArtifactGenerator.generate_docx(spec, session_id)
            elif fmt == "xlsx":
                headers = table_raw.get("headers", []) if isinstance(table_raw, dict) else []
                rows = table_raw.get("rows", []) if isinstance(table_raw, dict) else []
                sheet = SheetSpec(name=title[:31], headers=headers, rows=rows)
                sheet_spec = SpreadsheetSpec(sheets=[sheet], filename=filename)
                out_path = ArtifactGenerator.generate_xlsx(sheet_spec, session_id)
            elif fmt == "markdown":
                spec = ReportSpec(title=title, sections=blocks, filename=filename)
                out_path = ArtifactGenerator.generate_markdown(spec, session_id)
            else:
                return ToolResult(status=ToolStatus.ERROR, error=f"Unsupported deliverable format: '{fmt}'")

            return ToolResult(
                status=ToolStatus.SUCCESS,
                output=f"Successfully generated deliverable '{out_path.name}' ({out_path.stat().st_size} bytes).",
                data={
                    "generated_files": [str(out_path)],
                    "filename": out_path.name,
                    "size_bytes": out_path.stat().st_size,
                    "session_id": session_id,
                },
            )
        except Exception as exc:
            logger.exception("Deliverable generation failed: %s", exc)
            return ToolResult(status=ToolStatus.ERROR, error=f"Document generation failed: {exc}")


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

        result: ToolResult
        try:
            if inspect.iscoroutinefunction(tool.handler):
                raw_res = await tool.handler(input_data, session_id, db=db)
            else:
                raw_res = tool.handler(input_data, session_id)
            result = raw_res if isinstance(raw_res, ToolResult) else ToolResult(status=ToolStatus.SUCCESS, data=raw_res)
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
