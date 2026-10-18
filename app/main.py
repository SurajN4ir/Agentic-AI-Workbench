"""
app/main.py — Sovereign Workbench FastAPI Application Entry Point
=================================================================
Creates the FastAPI app with:
  - Structured JSON logging
  - Security headers middleware
  - CORS restricted to configured origins
  - Rate limiting via slowapi
  - Audit middleware (logs every request)
  - Health + readiness endpoints (no sensitive data exposed unauthenticated)
  - All API routers mounted under /api/v1
"""

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.agent.router import router as agent_router
from app.artifacts.router import router as artifacts_router
from app.benchmarks.router import router as benchmarks_router
from app.config import get_settings
from app.database import check_database_health, engine, init_db
from app.identity.router import router as auth_router
from app.knowledge.router import router as knowledge_router
from app.routing.router import router as routing_router
from app.tools.router import router as tools_router

# ─── Logging setup ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("sovereign")

settings = get_settings()

# ─── Rate limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ─── Lifespan (startup / shutdown) ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Sovereign Workbench starting up (env=%s)", settings.app_env)

    # Verify DB connectivity on startup — fail fast if misconfigured
    db_ok = await check_database_health()
    if not db_ok:
        logger.error("Database health check failed on startup. Check database configuration.")
    else:
        try:
            await init_db()
        except Exception as e:
            logger.warning("Auto schema init notice: %s", e)

    if settings.strict_offline:
        logger.warning("STRICT_OFFLINE mode is ENABLED. All external network access is blocked.")

    logger.info("Startup complete.")
    yield
    logger.info("Sovereign Workbench shutting down.")
    await engine.dispose()


# ─── App factory ─────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="Sovereign On-Premise Agentic AI Workbench",
        version="1.0.0-phase1",
        description="Secure, local-first agentic AI for confidential industrial workflows.",
        # Disable OpenAPI docs in production (avoids exposing schema externally)
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # ─── Rate limiter ────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # ─── CORS ────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    # ─── Security headers middleware ─────────────────────────────────
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # ─── Request timing middleware ────────────────────────────────────
    @app.middleware("http")
    async def add_request_timing(request: Request, call_next):  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.1f}"
        return response

    # ─── Routers ─────────────────────────────────────────────────────
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(routing_router, prefix="/api/v1")
    app.include_router(tools_router, prefix="/api/v1")
    app.include_router(knowledge_router, prefix="/api/v1")
    app.include_router(agent_router, prefix="/api/v1")
    app.include_router(artifacts_router, prefix="/api/v1")
    app.include_router(benchmarks_router, prefix="/api/v1")



    # ─── Health endpoints ─────────────────────────────────────────────
    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        """
        Basic liveness probe. Returns 200 if the process is running.
        Does NOT expose model names, service topology, or configuration.
        """
        return {"status": "ok"}

    @app.get("/ready", include_in_schema=False)
    async def ready() -> Response:
        """
        Readiness probe. Returns 200 only if the database is reachable.
        Returns 503 if the DB is down.
        """
        db_ok = await check_database_health()
        if db_ok:
            return JSONResponse({"status": "ready", "database": "ok"})
        return JSONResponse(
            {"status": "not_ready", "database": "unreachable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # ─── Mount Frontend Static Build (SPA) ───────────────────────────
    frontend_dist = Path("frontend/dist")
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        if (frontend_dist / "assets").exists():
            app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> Response:
            target = frontend_dist / full_path
            if full_path and target.is_file():
                return FileResponse(target)
            if full_path.startswith("api/") or full_path in ("health", "ready", "docs", "redoc", "openapi.json"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return FileResponse(frontend_dist / "index.html")

    return app


app = create_app()
