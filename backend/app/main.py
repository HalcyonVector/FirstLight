import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.v1 import analytics, dashboard, push, repositories, search, signals, trends
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: make sure newer tables exist even before the next pipeline run.
    # Best-effort -- a cold database must not stop the API from booting.
    from app.core.database import AsyncSessionLocal
    from app.core.schema_upgrade import ensure_schema
    try:
        async with AsyncSessionLocal() as session:
            await ensure_schema(session)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("Schema upgrade skipped: %s", exc)
    yield
    # Shutdown — close GitHub HTTP client
    from app.services.github_service import github_service
    await github_service.close()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Middleware
_allowed_origins = list(settings.CORS_ORIGINS)
if settings.FRONTEND_URL and settings.FRONTEND_URL not in _allowed_origins:
    _allowed_origins.append(settings.FRONTEND_URL.rstrip("/"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Routes
PREFIX = f"/api/{settings.API_VERSION}"
app.include_router(dashboard.router, prefix=PREFIX, tags=["Dashboard"])
app.include_router(repositories.router, prefix=f"{PREFIX}/repositories", tags=["Repositories"])
app.include_router(trends.router, prefix=f"{PREFIX}/trends", tags=["Trends"])
app.include_router(search.router, prefix=f"{PREFIX}/search", tags=["Search"])
app.include_router(push.router, prefix=f"{PREFIX}/push", tags=["Push"])
app.include_router(analytics.router, prefix=f"{PREFIX}/analytics", tags=["Analytics"])
app.include_router(signals.router, prefix=PREFIX, tags=["Signals"])


@app.get("/health")
@app.head("/health")
async def health():
    # HEAD support matters here: both cron-job.org and UptimeRobot default to
    # HEAD for their monitors, not GET. A GET-only route 405s a HEAD probe --
    # which, on a sleeping Render free instance, surfaces as a wake-proxy 503
    # instead of a clean 405 once awake. Either way, HEAD-only monitoring
    # never reliably keeps this endpoint warm without this.
    return {"status": "ok", "version": "1.0.0"}
