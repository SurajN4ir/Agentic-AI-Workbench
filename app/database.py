"""
app/database.py — Sovereign Workbench Database Layer
=====================================================
SQLAlchemy async engine and session factory.
Supports both production PostgreSQL (+ pgvector) and local persistent SQLite fallback.
Provides both async (API) and sync (Alembic/scripts) access.
"""

import logging
import socket
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

if sys.platform == "win32":
    import asyncio
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:  # noqa: S110
        pass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

logger = logging.getLogger("sovereign.database")
settings = get_settings()

SQLITE_FALLBACK_URL = "sqlite+aiosqlite:///workspace/sovereign_workbench.db"


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


def is_postgres_available(host: str, port: int, timeout: float = 0.5) -> bool:
    """Fast probe checking if PostgreSQL port is accepting TCP connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _create_engine_for_url(db_url: str) -> AsyncEngine:
    if db_url.startswith("sqlite"):
        return create_async_engine(
            db_url,
            echo=settings.debug,
        )
    return create_async_engine(
        db_url,
        echo=settings.debug,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=30000",
        },
    )


# Determine initial active URL based on availability
_active_db_url = settings.database_url
if not _active_db_url.startswith("sqlite"):
    if not is_postgres_available(settings.postgres_host, settings.postgres_port):
        logger.info(
            "PostgreSQL port (%s:%d) is not reachable. Using persistent local SQLite database (%s).",
            settings.postgres_host,
            settings.postgres_port,
            SQLITE_FALLBACK_URL,
        )
        Path("workspace").mkdir(parents=True, exist_ok=True)
        _active_db_url = SQLITE_FALLBACK_URL

# ─── SQLAlchemy Async Engine ──────────────────────────────────────────────────
engine: AsyncEngine = _create_engine_for_url(_active_db_url)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ─── Dependency: async DB session ────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency providing a database session per request.
    Rolls back on exception, always closes the session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─── Schema initialization ───────────────────────────────────────────────────
async def init_db() -> None:
    """Ensures database schema tables exist in the active database engine."""
    # Ensure models are imported so Base.metadata is fully populated
    import app.artifacts.models  # noqa: F401
    import app.audit.models  # noqa: F401
    import app.identity.models  # noqa: F401
    import app.knowledge.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema initialized on %s", engine.url.render_as_string(hide_password=True))


# ─── Health check ─────────────────────────────────────────────────────────────
async def check_database_health() -> bool:
    """Returns True if the database is reachable and responsive."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database health check failed on %s: %s", engine.url.render_as_string(hide_password=True), exc)
        return False
