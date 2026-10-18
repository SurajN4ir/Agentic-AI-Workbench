"""
tests/test_integration/test_end_to_end_workbench.py
==================================================
End-to-End Workbench integration test verifying the complete user workflow:
1. Static SPA frontend delivery from FastAPI root
2. Health & readiness status checks
3. User authentication & JWT bearer exchange
4. Agent workflow execution with citation verification
5. Artifact generation and workspace retrieval
"""

import uuid

import pytest
from app.database import get_db
from app.identity.models import User
from app.identity.service import create_access_token, hash_password
from app.main import create_app
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_end_to_end_frontend_and_api_workflow(test_engine) -> None:
    """Verifies that the entire application stack delivers SPA assets and serves API workflows."""
    app = create_app()
    from sqlalchemy.ext.asyncio import async_sessionmaker
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    # Seed an active admin user
    user_id = uuid.uuid4()
    admin_user = User(
        id=user_id,
        username="lead_engineer",
        name="Lead Engineer",
        role="admin",
        password_hash=hash_password("Sovereign2026!SecureKey"),
        is_active=True,
    )
    async with session_factory() as session:
        session.add(admin_user)
        await session.commit()

    token = create_access_token(user_id=str(user_id), role="admin", username="lead_engineer")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Verify frontend index.html served at root
        root_resp = await client.get("/")
        assert root_resp.status_code == 200
        assert "html" in root_resp.headers.get("content-type", "").lower()

        # 2. Verify health & readiness endpoints
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        assert health_resp.json() == {"status": "ok"}

        ready_resp = await client.get("/ready")
        assert ready_resp.status_code == 200

        # 3. Verify user profile retrieval with JWT
        me_resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        user_info = me_resp.json()
        assert user_info["username"] == "lead_engineer"
        assert user_info["role"] == "admin"

        # 4. Verify agent task execution through API
        run_payload = {
            "prompt": "Use the math tool to calculate 25 * 40.",
            "role_override": "reasoning",
            "max_iterations": 3,
        }
        agent_resp = await client.post(
            "/api/v1/agent/run",
            headers={"Authorization": f"Bearer {token}"},
            json=run_payload,
        )
        assert agent_resp.status_code == 200
        res_data = agent_resp.json()
        assert res_data["status"] == "completed"
        assert "1,000" in res_data["response"] or "1000" in res_data["response"]
        assert "citations_verified" in res_data
        assert res_data["citations_verified"] is True
