"""
app/routing/schemas.py
======================
Pydantic schemas for router inputs, file metadata, and route decisions.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.registry import get_model_for_role

OCR_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".go",
    ".rs",
    ".ipynb",
    ".sh",
    ".bash",
    ".pyw",
    ".sql",
    ".html",
    ".css",
}


class FileMetadata(BaseModel):
    filename: str
    extension: str
    filepath: str | None = None
    likely_needs_ocr: bool = False

    def __init__(self, **data: object) -> None:
        if "path" in data and "filepath" not in data:
            data["filepath"] = data["path"]
        super().__init__(**data)
        ext = self.extension.strip().lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        self.likely_needs_ocr = ext in OCR_EXTENSIONS


class RouteDecision(BaseModel):
    role: Literal["reasoning", "coding"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    method: Literal[
        "multimodal_override",
        "metadata",
        "keyword",
        "classifier",
        "classifier_fallback",
        "manual_override",
    ]
    reasoning: str | None = None

    @property
    def selected_model(self) -> str:
        """Resolves the selected model tag from the global model registry."""
        return get_model_for_role(self.role)
