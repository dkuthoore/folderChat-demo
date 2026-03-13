from __future__ import annotations

from typing import TypedDict, cast

from app.models.session import ServerSessionRecord
from app.services.session_store import get_session_store
from fastapi import HTTPException, Request, status
from google.oauth2.credentials import Credentials


class SessionUserPayload(TypedDict):
    google_id: str
    email: str
    name: str
    picture: str | None


SESSION_COOKIE_KEY = "server_session_id"


def get_server_session(request: Request) -> ServerSessionRecord:
    session_id = request.session.get(SESSION_COOKIE_KEY)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You must sign in with Google first.",
        )

    session_store = get_session_store()
    record = session_store.touch_session(session_id)
    if record is None:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please sign in again.",
        )
    return record


def get_session_user(request: Request) -> SessionUserPayload:
    return cast(
        SessionUserPayload,
        get_server_session(request).user.model_dump(mode="json"),
    )


def get_google_credentials(request: Request) -> Credentials:
    credentials_payload = get_server_session(request).credentials.model_dump(
        mode="json"
    )

    return Credentials(
        token=credentials_payload["token"],
        refresh_token=credentials_payload.get("refresh_token"),
        token_uri=credentials_payload["token_uri"],
        client_id=credentials_payload["client_id"],
        client_secret=credentials_payload["client_secret"],
        scopes=credentials_payload.get("scopes"),
    )
