"""
app/routing/__init__.py
=======================
Task classification and 3-stage waterfall routing engine.
"""

from app.routing.schemas import FileMetadata, RouteDecision
from app.routing.service import TaskRouter, get_task_router

__all__ = [
    "FileMetadata",
    "RouteDecision",
    "TaskRouter",
    "get_task_router",
]
