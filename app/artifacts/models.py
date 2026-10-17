"""
app/artifacts/models.py
=======================
Schemas and primitives for structured report generation and artifact downloads.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    """Section text with optional heading."""
    heading: str | None = Field(default=None, description="Optional section heading")
    body: str = Field(..., description="Paragraph body text (supports markdown bullet lines)")


class TableBlock(BaseModel):
    """Tabular grid data."""
    headers: list[str] = Field(..., description="Column header labels")
    rows: list[list[str]] = Field(..., description="2D matrix of cell values")
    caption: str | None = Field(default=None, description="Optional table caption")


class ReportSpec(BaseModel):
    """Specification for structured Word (.docx) or Markdown report generation."""
    title: str = Field(..., min_length=1, description="Document title")
    subtitle: str | None = Field(default=None, description="Optional document subtitle")
    author: str | None = Field(default="Sovereign AI Workbench", description="Author or generating system name")
    sections: list[TextBlock | TableBlock] = Field(default_factory=list, description="Ordered content blocks")
    filename: str = Field(default="report.docx", description="Target filename")


class SheetSpec(BaseModel):
    """Specification for an individual Excel worksheet."""
    name: str = Field(default="Sheet1", max_length=31, description="Worksheet tab name")
    headers: list[str] = Field(default_factory=list, description="Column headers")
    rows: list[list[Any]] = Field(default_factory=list, description="Data rows")


class SpreadsheetSpec(BaseModel):
    """Specification for multi-sheet Excel (.xlsx) workbook generation."""
    sheets: list[SheetSpec] = Field(..., min_length=1, description="Worksheets to create")
    filename: str = Field(default="export.xlsx", description="Target filename")


class ArtifactInfo(BaseModel):
    """Metadata describing a downloadable file deliverable."""
    filename: str
    size_bytes: int
    mime_type: str
    session_id: str
    download_url: str


class GenerateArtifactRequest(BaseModel):
    """Request payload to generate a downloadable deliverable."""
    format: Literal["docx", "xlsx", "markdown"] = Field(..., description="Deliverable format")
    session_id: str | None = Field(default=None, description="Workspace session UUID")
    filename: str | None = Field(default=None, description="Desired output filename")
    report_spec: ReportSpec | None = Field(default=None, description="Content spec if format is docx or markdown")
    spreadsheet_spec: SpreadsheetSpec | None = Field(default=None, description="Content spec if format is xlsx")
