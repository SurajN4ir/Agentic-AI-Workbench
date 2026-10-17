"""
app/artifacts/service.py
========================
Artifact service managing session workspace discovery and secure file downloads.
"""

import logging
from pathlib import Path

from app.artifacts.models import ArtifactInfo
from app.config import get_settings
from app.tools.interface import validate_workspace_path

logger = logging.getLogger("sovereign.artifacts.service")

MIME_MAP = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class ArtifactService:
    """Manages discoverability and access to session-generated deliverable files."""

    @staticmethod
    def get_mime_type(file_path: Path) -> str:
        """Determines standard MIME type based on file extension."""
        ext = file_path.suffix.lower()
        return MIME_MAP.get(ext, "application/octet-stream")

    @classmethod
    def list_artifacts(cls, session_id: str) -> list[ArtifactInfo]:
        """Lists all files generated in the given session workspace directory."""
        settings = get_settings()
        workspace_base = Path(settings.workspace_dir).resolve()
        session_dir = (workspace_base / session_id).resolve()

        if not session_dir.exists() or not session_dir.is_dir():
            return []

        artifacts: list[ArtifactInfo] = []
        for item in sorted(session_dir.rglob("*")):
            if item.is_file() and not item.name.startswith("."):
                rel_path = item.relative_to(session_dir).as_posix()
                mime = cls.get_mime_type(item)
                artifacts.append(
                    ArtifactInfo(
                        filename=rel_path,
                        size_bytes=item.stat().st_size,
                        mime_type=mime,
                        session_id=session_id,
                        download_url=f"/api/v1/artifacts/{session_id}/{rel_path}",
                    )
                )

        return artifacts

    @staticmethod
    def get_artifact_file(session_id: str, filename: str) -> tuple[Path, str]:
        """
        Validates path traversal bounds and returns safe Path and mime type.
        Raises ValueError on malformed IDs or path traversal attempts.
        Raises FileNotFoundError if file does not exist.
        """
        safe_path = validate_workspace_path(filename, session_id, create_parents=False)
        if not safe_path.exists() or not safe_path.is_file():
            raise FileNotFoundError(f"Artifact '{filename}' not found in session '{session_id}'.")

        mime = ArtifactService.get_mime_type(safe_path)
        return safe_path, mime
