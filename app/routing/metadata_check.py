"""
app/routing/metadata_check.py
=============================
Stage 1: Deterministic file metadata inspection guard.
Matches file extension against code extensions for 100% confidence routing.
"""

from app.routing.schemas import CODE_EXTENSIONS, FileMetadata, RouteDecision


def check_metadata(file_metadata: list[FileMetadata] | None = None) -> RouteDecision | None:
    """Stage 1 Waterfall check.

    If any input file extension is a programming code extension, route immediately to coding role.
    """
    if not file_metadata:
        return None

    for meta in file_metadata:
        ext = meta.extension.strip().lower()
        if not ext.startswith("."):
            ext = f".{ext}"

        if ext in CODE_EXTENSIONS:
            return RouteDecision(
                role="coding",
                confidence=1.0,
                method="metadata",
                reasoning=f"Attached file '{meta.filename}' has code extension '{ext}'.",
            )

    return None
