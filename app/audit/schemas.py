"""
app/audit/schemas.py — Pydantic response schemas for audit log queries.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditEventOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    event_type: str
    resource_type: str | None
    resource_id: str | None
    outcome: str
    ip_address: str | None
    summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogPage(BaseModel):
    items: list[AuditEventOut]
    total: int
    page: int
    page_size: int
