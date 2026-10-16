"""
tests/conftest.py — Pytest fixtures for Sovereign Workbench.

Provides:
  - A temporary in-memory SQLite or test-Postgres DB
  - A FastAPI test client (async)
  - Helper fixtures for creating test users and tokens
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from app.database import Base, get_db
from app.identity.models import User
from app.identity.service import create_access_token, hash_password
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ─── Use SQLite in-memory for unit tests (no Postgres required) ───────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    """Async test client wired to a fresh in-memory DB."""
    from app.main import create_app

    app: FastAPI = create_app()
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """A regular user (role=user) with a known password."""
    user = User(
        id=uuid.uuid4(),
        username="testuser",
        name="Test User",
        role="user",
        password_hash=hash_password("TestPass123!"),
        avatar_color="bg-slate-500",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """An admin user with a known password."""
    user = User(
        id=uuid.uuid4(),
        username="testadmin",
        name="Test Admin",
        role="admin",
        password_hash=hash_password("AdminPass123!"),
        avatar_color="bg-blue-600",
    )
    db_session.add(user)
    await db_session.commit()
    return user


def make_access_token(user: User) -> str:
    return create_access_token(str(user.id), user.role, user.username)


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_access_token(user)}"}
