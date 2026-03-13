from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.models.session import GoogleCredentialsPayload, SessionUser
from app.services.session_store import ServerSessionStore


def _build_store(tmp_path: Path, ttl_seconds: int) -> ServerSessionStore:
    return ServerSessionStore(tmp_path / "sessions", ttl_seconds)


def test_touch_session_returns_record_when_not_expired(tmp_path: Path) -> None:
    store = _build_store(tmp_path, ttl_seconds=3600)
    session = store.create_session(
        user=SessionUser(google_id="g-1", email="demo@example.com", name="Demo User"),
        credentials=GoogleCredentialsPayload(
            token="token",
            refresh_token="refresh",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="client-id",
            client_secret="client-secret",
            scopes=["openid"],
        ),
    )

    touched = store.touch_session(session.session_id)

    assert touched is not None
    assert touched.session_id == session.session_id


def test_get_session_expires_stale_records(tmp_path: Path) -> None:
    store = _build_store(tmp_path, ttl_seconds=10)
    session = store.create_session(
        user=SessionUser(google_id="g-1", email="demo@example.com", name="Demo User"),
        credentials=GoogleCredentialsPayload(
            token="token",
            refresh_token="refresh",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="client-id",
            client_secret="client-secret",
            scopes=["openid"],
        ),
    )

    stale_record = store.get_session(session.session_id)
    assert stale_record is not None
    stale_record.updated_at = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
    store._write_session(stale_record)

    assert store.get_session(session.session_id) is None
    assert not (tmp_path / "sessions" / f"{session.session_id}.json").exists()
