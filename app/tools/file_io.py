"""
app/tools/file_io.py — Scoped Workspace File System Tool
=========================================================
Adapted from sovereign-agent reference architecture (SIH PS 26117).
Provides security-audited file I/O operations (read, write, list) strictly
constrained within /workspace/<session_id>/.
Deletion is explicitly prohibited for compliance and forensic audit integrity.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.tools.interface import ToolInput, ToolResult, ToolStatus, validate_workspace_path


class FileIOInput(ToolInput):
    """Input payload for workspace file I/O."""

    operation: Literal["read", "write", "list"] = Field(
        default="read",
        description="File operation: 'read' (read text file), 'write' (create/update file), 'list' (list directory).",
    )
    path: str = Field(
        default="",
        description="Relative file or directory path within the session workspace (e.g. 'script.py' or 'output/').",
    )
    content: str | None = Field(
        default=None,
        description="Text content to write when operation is 'write'.",
    )
    session_id: str = Field(default="default", description="Active workspace session identifier.")


class FileIOResult(ToolResult):
    """Structured output for workspace file I/O."""

    path: str | None = None
    content: str | None = None
    files: list[str] = Field(default_factory=list)
    summary: str | None = None


ALLOWED_OPERATIONS = {"read", "write", "list"}


def execute_file_io(
    operation: str = "read",
    path: str = "",
    content: str | None = None,
    session_id: str = "default",
) -> FileIOResult:
    """Read, write, or list files strictly within the session workspace boundary."""
    op = operation.lower().strip()
    if op not in ALLOWED_OPERATIONS:
        return FileIOResult(
            status=ToolStatus.ERROR,
            error=f"Unsupported file operation '{operation}'. Allowed: {sorted(ALLOWED_OPERATIONS)} (Deletion prohibited)",
        )

    # Validate workspace boundary strictly
    try:
        validated_path = validate_workspace_path(path, session_id, create_parents=(op == "write"))
    except Exception as err:
        return FileIOResult(status=ToolStatus.ERROR, error=f"Path validation failed: {err}")

    if op == "read":
        if not validated_path.exists() or not validated_path.is_file():
            return FileIOResult(
                status=ToolStatus.ERROR,
                error=f"File '{path}' does not exist in workspace for session '{session_id}'.",
            )
        try:
            text = validated_path.read_text(encoding="utf-8", errors="replace")
            # Truncate preview if exceptionally large
            preview = text[:20000]
            summary = f"Read {len(text)} characters from '{validated_path.name}'."
            return FileIOResult(
                status=ToolStatus.SUCCESS,
                path=str(path),
                content=preview,
                summary=summary,
            )
        except Exception as e:
            return FileIOResult(status=ToolStatus.ERROR, error=f"Failed reading '{path}': {e}")

    elif op == "write":
        if content is None:
            return FileIOResult(
                status=ToolStatus.ERROR,
                error="Field 'content' is required for 'write' operation.",
            )
        try:
            validated_path.parent.mkdir(parents=True, exist_ok=True)
            validated_path.write_text(content, encoding="utf-8")
            summary = f"Successfully wrote {len(content)} characters to '{validated_path.name}'."
            return FileIOResult(
                status=ToolStatus.SUCCESS,
                path=str(path),
                summary=summary,
            )
        except Exception as e:
            return FileIOResult(status=ToolStatus.ERROR, error=f"Failed writing '{path}': {e}")

    elif op == "list":
        target_dir = validated_path if validated_path.is_dir() else validated_path.parent
        if not target_dir.exists():
            return FileIOResult(status=ToolStatus.SUCCESS, files=[], summary="Workspace directory is empty.")

        try:
            entries = []
            for item in target_dir.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(target_dir)
                    entries.append(str(rel))
            entries.sort()
            summary = f"Found {len(entries)} files in session workspace."
            return FileIOResult(
                status=ToolStatus.SUCCESS,
                files=entries,
                summary=summary,
            )
        except Exception as e:
            return FileIOResult(status=ToolStatus.ERROR, error=f"Failed listing workspace directory: {e}")

    return FileIOResult(status=ToolStatus.ERROR, error="Unexpected file operation error")
