from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionUser(BaseModel):
    google_id: str
    email: str
    name: str
    picture: str | None = None


class GoogleCredentialsPayload(BaseModel):
    token: str
    refresh_token: str | None = None
    token_uri: str
    client_id: str
    client_secret: str
    scopes: list[str] = Field(default_factory=list)


class ServerSessionRecord(BaseModel):
    session_id: str
    user: SessionUser
    credentials: GoogleCredentialsPayload
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
