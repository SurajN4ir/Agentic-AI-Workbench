"""
app/database.py — Sovereign Workbench Database Layer
=====================================================
SQLAlchemy async engine and session factory.
Provides both async (API) and sync (Alembic/scripts) access.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()


# ─── SQLAlchemy Async Engine ──────────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,  # Only log SQL in debug mode
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Validate connections before use
    pool_recycle=3600,  # Recycle connections hourly
    connect_args={
        "connect_timeout": 10,
        "options": "-c statement_timeout=30000",  # 30 s query timeout
    },
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


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


# ─── Health check ─────────────────────────────────────────────────────────────
async def check_database_health() -> bool:
    """Returns True if the database is reachable and responsive."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
