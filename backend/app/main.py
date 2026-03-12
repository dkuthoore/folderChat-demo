from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.ingest import router as ingest_router
from app.api.user_data import router as user_data_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)
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
    https_only=False,
)

app.include_router(auth_router)
app.include_router(ingest_router)
app.include_router(chat_router)
app.include_router(user_data_router)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
