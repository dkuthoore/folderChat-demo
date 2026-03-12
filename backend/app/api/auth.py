from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.core.config import Settings, get_settings
from app.core.session import SESSION_COOKIE_KEY
from app.models.session import GoogleCredentialsPayload, SessionUser
from app.schemas.auth import AuthenticatedUser, SessionResponse
from app.services.ingestion import get_storage_backend
from app.services.session_store import get_session_store

router = APIRouter(tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_SCOPE = "openid email profile https://www.googleapis.com/auth/drive.readonly"


@router.get("/auth/google")
async def google_login(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state

    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_SCOPE,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
    )
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{query}")


@router.get("/auth/google/callback")
async def google_callback(
    request: Request,
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    expected_state = request.session.get("oauth_state")
    if not expected_state or state != expected_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state validation failed.",
        )

    async with httpx.AsyncClient(timeout=30) as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_response.raise_for_status()
        token_payload = token_response.json()

        userinfo_response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token_payload['access_token']}"},
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

    session_store = get_session_store(settings)
    existing_session_id = request.session.get(SESSION_COOKIE_KEY)
    if existing_session_id:
        session_store.delete_session(existing_session_id)

    session_record = session_store.create_session(
        user=SessionUser(
            google_id=userinfo["sub"],
            email=userinfo["email"],
            name=userinfo.get("name", userinfo["email"]),
            picture=userinfo.get("picture"),
        ),
        credentials=GoogleCredentialsPayload(
            token=token_payload["access_token"],
            refresh_token=token_payload.get("refresh_token"),
            token_uri=GOOGLE_TOKEN_URL,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=token_payload.get("scope", GOOGLE_SCOPE).split(),
        ),
    )
    request.session[SESSION_COOKIE_KEY] = session_record.session_id
    request.session.pop("oauth_state", None)

    return RedirectResponse(f"{settings.frontend_url}/dashboard")


@router.get("/auth/logout")
async def logout(request: Request, settings: Settings = Depends(get_settings)) -> RedirectResponse:
    session_id = request.session.get(SESSION_COOKIE_KEY)
    if session_id:
        get_session_store(settings).delete_session(session_id)
    request.session.clear()
    return RedirectResponse(settings.frontend_url)


@router.get("/api/session", response_model=SessionResponse)
async def get_session(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    session_id = request.session.get(SESSION_COOKIE_KEY)
    if not session_id:
        return SessionResponse(is_authenticated=False)

    session_record = get_session_store(settings).touch_session(session_id)
    if session_record is None:
        request.session.clear()
        return SessionResponse(is_authenticated=False)

    user = session_record.user.model_dump(mode="json")

    storage_backend = get_storage_backend(settings)
    active_folder = storage_backend.get_active_folder(user["google_id"])
    current_folder_id = active_folder.folder_id if active_folder else None
    files = []
    if current_folder_id:
        files = storage_backend.get_folder_files(user["google_id"], current_folder_id)

    return SessionResponse(
        is_authenticated=True,
        user=AuthenticatedUser.model_validate(user),
        current_folder_id=current_folder_id,
        current_folder_name=active_folder.folder_name if active_folder else None,
        current_folder_url=active_folder.folder_url if active_folder else None,
        files=files,
    )
