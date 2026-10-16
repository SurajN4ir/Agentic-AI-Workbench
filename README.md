"""
Sovereign Workbench — README (Phase 1)
"""
# Sovereign On-Premise Agentic AI Workbench

> **Status: Phase 1 — Foundation & Security Core (In Progress)**  
> Target: MRPL / PSUs / Defence / Air-Gapped Infrastructures  
> SIH 2026 PS 26117

---

## Quick Start (Development)

### Prerequisites
- Python 3.11+, uv, Docker, Node.js 20+, Git

### 1. Clone and setup
```powershell
git clone <repo> "D:\AGENTIC AI MAJOR PROJECT"
cd "D:\AGENTIC AI MAJOR PROJECT"
uv venv --python 3.11 .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Configure environment
```powershell
Copy-Item .env.example .env
# Edit .env — set JWT_SECRET_KEY and POSTGRES_PASSWORD
# Generate a strong secret: python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Start infrastructure
```powershell
docker compose up postgres ollama -d
```

### 4. Run migrations and create admin
```powershell
alembic upgrade head
python scripts/setup_admin.py
```

### 5. Start backend
```powershell
uvicorn app.main:app --reload --port 8000
```

### 6. Run tests
```powershell
pytest tests/ -v --cov=app
```

---

## Security Notes

- `JWT_SECRET_KEY` and `POSTGRES_PASSWORD` are **required** — the app refuses to start without them.
- No default credentials are created. Use `scripts/setup_admin.py` for the first admin account.
- Admin accounts cannot disable 2FA.
- JWT is only accepted in the `Authorization: Bearer` header — never as a query parameter.
- All security-sensitive actions are written to the append-only `audit_events` table.
- Set `STRICT_OFFLINE=true` to block external HTTP calls at the application level.

---

## Project Structure

```
app/
  config.py          Settings (required secrets, no insecure defaults)
  database.py        SQLAlchemy async engine
  main.py            FastAPI app factory, middleware, health endpoints
  identity/          JWT auth, RBAC, sessions, TOTP
  audit/             Append-only audit log
  network/           Strict offline mode guard

alembic/             Database migrations
scripts/             setup_admin.py, train_router_classifier.py
tests/               pytest unit tests (SQLite in-memory, no Postgres needed)
```

---

## Known Limitations (Phase 1)

- RAG, document ingestion, and agent orchestration not yet implemented (Phase 4/3).
- Frontend TypeScript migration not yet done (Phase 6).
- PaddleOCR on AMD hardware not yet validated.
- Strict-offline mode blocks Python urllib only — OS-level firewall rules needed for full isolation.
- LangGraph PostgreSQL checkpointer not yet evaluated (Phase 3).

See `Architecture_And_Dependencies.md` for the full plan.
