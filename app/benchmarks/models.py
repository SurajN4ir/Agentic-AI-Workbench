"""
app/benchmarks/models.py
========================
SQLAlchemy ORM model for persistent storage of benchmark evaluation runs.
Maintains execution history, scenario-level scores, diagnostic errors, and performance latencies.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BenchmarkRun(Base):
    """Stores full execution metrics and scenario results for an industrial benchmark evaluation run."""

    __tablename__ = "benchmark_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid().with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    benchmark_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="industrial_benchmark_v1",
    )
    model_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="llama3.2:latest",
    )
    provider_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="ollama",
    )
    category_filter: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="completed",
        index=True,
    )
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    accuracy_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    security_violations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p95_duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    category_scores: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    results: Mapped[list[Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )

    triggered_by_username: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="system",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
