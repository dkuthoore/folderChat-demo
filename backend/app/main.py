import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.ingest import router as ingest_router
from app.api.user_data import router as user_data_router
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title=settings.app_name)

# Check if frontend dist exists at startup
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if not FRONTEND_DIST.exists():
    logger.warning(
        f"Frontend dist directory not found at {FRONTEND_DIST}. "
        "Static files will not be served. Run 'npm run build' in frontend/ directory."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=settings.session_https_only,
)


@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    """Add cache headers for static assets (hashed filenames)."""
    response = await call_next(request)
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


app.include_router(auth_router)
app.include_router(ingest_router)
app.include_router(chat_router)
app.include_router(user_data_router)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        # Serve any real file that exists in the dist directory (favicon, etc.)
        # Resolve to canonical paths to prevent path traversal attacks
        candidate = (FRONTEND_DIST / full_path).resolve()
        dist_resolved = FRONTEND_DIST.resolve()

        # Verify candidate is within frontend/dist before serving
        try:
            candidate.relative_to(dist_resolved)
        except ValueError:
            # Path tried to escape dist directory, fall back to index.html
            return FileResponse(str(dist_resolved / "index.html"))

        if candidate.is_file():
            return FileResponse(str(candidate))
        # For all other paths (SPA routes), serve index.html
        return FileResponse(str(dist_resolved / "index.html"))
