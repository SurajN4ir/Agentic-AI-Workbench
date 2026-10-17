"""
app/tools/interface.py
======================
Core tool interfaces, schemas, and workspace security boundary validator.
Guarantees path traversal prevention and audit metadata tracking.
"""

import logging
import re
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config import get_settings

logger = logging.getLogger("sovereign.tools")

SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")


class ToolStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


class ToolInput(BaseModel):
    """Base schema for all tool input parameters."""

    pass


class ToolResult(BaseModel):
    """Uniform output format for all tool executions."""

    status: ToolStatus
    data: Any | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def validate_workspace_path(
    path_str: str,
    session_id: str,
    create_parents: bool = True,
    base_override: Path | None = None,
) -> Path:
    """Validates and enforces strict workspace filesystem isolation.

    Ensures that every accessed file resolves strictly within:
    <workspace_dir>/<session_id>/

    Security rules enforced:
    1. Rejects empty, whitespace, or malformed session IDs.
    2. Enforces safe alphanumeric + hyphen + underscore characters for session IDs.
    3. Blocks directory traversal patterns (e.g. '..', '/../', '\\..\\').
    4. Blocks embedded null bytes.
    5. Resolves symlinks and ensures target is strictly relative to the session root.
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id is required for workspace boundary validation.")

    clean_session_id = session_id.strip()
    if not SESSION_ID_PATTERN.match(clean_session_id):
        raise ValueError(
            f"Invalid session_id '{clean_session_id}'. Must contain only alphanumeric, hyphen, or underscore characters."
        )

    if "\0" in path_str:
        raise ValueError("Null bytes are not allowed in file paths.")

    # Determine base workspace directory
    base_dir = base_override or Path(get_settings().workspace_dir)
    session_root = (base_dir / clean_session_id).resolve()

    # Pre-check for traversal tokens in path segments
    normalized_path = path_str.replace("\\", "/")
    segments = [s for s in normalized_path.split("/") if s]
    if ".." in segments:
        raise PermissionError(f"Security Alert: Path traversal '..' detected in path '{path_str}'")

    raw_path = Path(path_str)
    if raw_path.is_absolute():
        # Absolute path provided: must resolve inside session_root
        target_path = raw_path.resolve()
    else:
        # Relative path: resolve relative to session_root
        target_path = (session_root / raw_path).resolve()

    # Enforce strict boundary check
    try:
        target_path.relative_to(session_root)
    except ValueError:
        raise PermissionError(
            f"Security Violation: Access denied for path '{path_str}'. Path lies outside session workspace '{session_root}'."
        )

    if create_parents:
        target_path.parent.mkdir(parents=True, exist_ok=True)

    return target_path
