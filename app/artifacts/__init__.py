"""
app/artifacts/__init__.py
========================
Deliverable artifact generation and secure export layer for Sovereign Workbench.
Provides Word (.docx), Excel (.xlsx), and Markdown deliverable generation.
"""

from app.artifacts.generator import ArtifactGenerator
from app.artifacts.models import ArtifactInfo, ReportSpec, SpreadsheetSpec, TableBlock, TextBlock
from app.artifacts.router import router

__all__ = [
    "ArtifactGenerator",
    "ArtifactInfo",
    "ReportSpec",
    "SpreadsheetSpec",
    "TableBlock",
    "TextBlock",
    "router",
]
