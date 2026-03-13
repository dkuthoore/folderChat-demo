from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient


def _set_test_env(tmp_path) -> None:
    os.environ["SESSION_SECRET"] = "test-session-secret"
    os.environ["GOOGLE_CLIENT_ID"] = "test-google-client-id"
    os.environ["GOOGLE_CLIENT_SECRET"] = "test-google-client-secret"
    os.environ["GOOGLE_REDIRECT_URI"] = "http://testserver/auth/google/callback"
    os.environ["OPENAI_API_KEY"] = "test-openai-key"
    os.environ["OPENAI_CHAT_MODEL"] = "gpt-4o-mini"
    os.environ["OPENAI_EMBEDDING_MODEL"] = "text-embedding-3-small"
    os.environ["FRONTEND_URL"] = "http://localhost:5173"
    os.environ["BACKEND_URL"] = "http://testserver"
    os.environ["SESSION_TTL_SECONDS"] = "604800"
    os.environ["VECTOR_STORE_BACKEND"] = "local"
    os.environ["LOCAL_STORAGE_DIR"] = str(tmp_path / "storage")
    os.environ["LOCAL_UPLOADS_DIR"] = str(tmp_path / "uploads")
    os.environ["DISABLE_RATE_LIMIT"] = "1"


@pytest.fixture
def app_client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    _set_test_env(tmp_path)

    from app.core.config import get_settings

    get_settings.cache_clear()
    import app.main as main_module

    main_module = importlib.reload(main_module)
    return TestClient(main_module.app)


@dataclass
class FakeResponse:
    payload: dict
    status_code: int = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")

    def json(self) -> dict:
        return self.payload


class FakeAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        return FakeResponse(
            {
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
                "scope": "openid email profile https://www.googleapis.com/auth/drive.readonly",
            }
        )

    async def get(self, *args, **kwargs):
        return FakeResponse(
            {
                "sub": "google-user-123",
                "email": "demo@example.com",
                "name": "Demo User",
                "picture": "https://example.com/avatar.png",
            }
        )


@pytest.fixture
def authenticated_client(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    import app.api.auth as auth_module

    monkeypatch.setattr(
        auth_module.httpx, "AsyncClient", lambda timeout=30: FakeAsyncClient()
    )

    login_response = app_client.get("/auth/google", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]
    callback_response = app_client.get(
        f"/auth/google/callback?code=test-code&state={state}",
        follow_redirects=False,
    )
    assert callback_response.status_code in {302, 307}
    return app_client
