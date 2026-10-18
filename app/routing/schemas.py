"""
app/routing/schemas.py
======================
Pydantic schemas for router inputs, file metadata, and route decisions.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.registry import get_model_for_role

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
OCR_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}
SPREADSHEET_EXTENSIONS = {".csv", ".xlsx", ".xls"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".rtf"}
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
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | CODE_EXTENSIONS | SPREADSHEET_EXTENSIONS | DOCUMENT_EXTENSIONS


class FileMetadata(BaseModel):
    filename: str
    extension: str
    filepath: str | None = None
    mime_type: str | None = None
    likely_needs_ocr: bool = False
    is_image: bool = False
    is_code: bool = False
    is_spreadsheet: bool = False
    is_document: bool = False
    is_supported: bool = True

    def __init__(self, **data: object) -> None:
        if "path" in data and "filepath" not in data:
            data["filepath"] = data["path"]
        super().__init__(**data)
        ext = self.extension.strip().lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        self.likely_needs_ocr = ext in OCR_EXTENSIONS
        self.is_image = ext in IMAGE_EXTENSIONS
        self.is_code = ext in CODE_EXTENSIONS
        self.is_spreadsheet = ext in SPREADSHEET_EXTENSIONS
        self.is_document = ext in DOCUMENT_EXTENSIONS
        self.is_supported = ext in ALLOWED_EXTENSIONS


class RouteDecision(BaseModel):
    role: Literal["reasoning", "coding", "vision", "ocr"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    method: Literal[
        "multimodal_override",
        "metadata",
        "keyword",
        "classifier",
        "classifier_fallback",
        "manual_override",
        "ocr_detection",
        "vision_detection",
        "spreadsheet_detection",
        "error_refusal",
    ]
    reasoning: str | None = None
    selected_model: str | None = None
    target_tools: list[str] = Field(default_factory=list)
    is_multimodal: bool = False
    requires_ocr: bool = False
    requires_vision: bool = False
    fallback_role: str | None = None
    fallback_model: str | None = None
    is_supported: bool = True
    refusal_reason: str | None = None

    @property
    def model_tag(self) -> str:
        """Resolves the selected model tag from the global model registry."""
        if self.selected_model:
            return self.selected_model
        return get_model_for_role(self.role)

