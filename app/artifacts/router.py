"""
app/artifacts/router.py
======================
FastAPI endpoints for deliverable generation and secure authenticated artifact downloads.
Strictly checks authorization and blocks directory traversal attempts.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.artifacts.generator import ArtifactGenerator
from app.artifacts.models import ArtifactInfo, GenerateArtifactRequest
from app.artifacts.service import ArtifactService
from app.identity.dependencies import get_current_user
from app.identity.models import User

router = APIRouter(prefix="/artifacts", tags=["Deliverables & Artifacts"])


@router.get(
    "/{session_id}",
    response_model=list[ArtifactInfo],
    summary="List generated deliverable files for a session",
)
async def list_session_artifacts(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> list[ArtifactInfo]:
    """Lists all deliverables created during agent task runs inside the session workspace."""
    try:
        return ArtifactService.list_artifacts(session_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error inspecting artifacts: {exc}",
        ) from exc


@router.get(
    "/{session_id}/{filename:path}",
    summary="Download a generated deliverable file",
    description="Secure file download endpoint enforcing directory traversal prevention.",
)
async def download_artifact(
    session_id: str,
    filename: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Streams the requested file with appropriate content-type and disposition headers."""
    try:
        safe_path, mime_type = ArtifactService.get_artifact_file(session_id, filename)
    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(fnf),
        ) from fnf
    except (ValueError, PermissionError) as sec_err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {sec_err}",
        ) from sec_err

    return FileResponse(
        path=str(safe_path),
        media_type=mime_type,
        filename=safe_path.name,
        headers={"Content-Disposition": f'attachment; filename="{safe_path.name}"'},
    )


@router.post(
    "/generate",
    response_model=ArtifactInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Explicitly generate a Word, Excel, or Markdown report",
)
async def generate_artifact(
    request: GenerateArtifactRequest,
    current_user: User = Depends(get_current_user),
) -> ArtifactInfo:
    """Generates a deliverable file from a structured specification."""
    session_id = request.session_id or str(uuid.uuid4())
    fmt = request.format.lower()

    try:
        if fmt == "docx":
            if not request.report_spec:
                raise HTTPException(status_code=400, detail="report_spec required for format 'docx'")
            target = ArtifactGenerator.generate_docx(request.report_spec, session_id)

        elif fmt == "xlsx":
            if not request.spreadsheet_spec:
                raise HTTPException(status_code=400, detail="spreadsheet_spec required for format 'xlsx'")
            target = ArtifactGenerator.generate_xlsx(request.spreadsheet_spec, session_id)

        elif fmt == "markdown":
            if not request.report_spec:
                raise HTTPException(status_code=400, detail="report_spec required for format 'markdown'")
            target = ArtifactGenerator.generate_markdown(request.report_spec, session_id)

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported deliverable format: '{fmt}'")

        mime = ArtifactService.get_mime_type(target)
        return ArtifactInfo(
            filename=target.name,
            size_bytes=target.stat().st_size,
            mime_type=mime,
            session_id=session_id,
            download_url=f"/api/v1/artifacts/{session_id}/{target.name}",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Deliverable generation error: {exc}",
        ) from exc
