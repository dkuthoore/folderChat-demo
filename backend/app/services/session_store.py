from __future__ import annotations

import json
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings, get_settings
from app.models.session import (
    GoogleCredentialsPayload,
    ServerSessionRecord,
    SessionUser,
    utc_now_iso,
)


class ServerSessionStore:
    def __init__(self, sessions_dir: Path, session_ttl_seconds: int) -> None:
        self.sessions_dir = sessions_dir
        self.session_ttl_seconds = session_ttl_seconds
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def create_session(
        self,
        *,
        user: SessionUser,
        credentials: GoogleCredentialsPayload,
    ) -> ServerSessionRecord:
        record = ServerSessionRecord(
            session_id=str(uuid.uuid4()),
            user=user,
            credentials=credentials,
        )
        self._write_session(record)
        return record

    def get_session(self, session_id: str) -> ServerSessionRecord | None:
        path = self._session_path(session_id)
        if not path.exists():
            return None
        record = ServerSessionRecord.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if self._is_expired(record):
            self.delete_session(session_id)
            return None
        return record

    def delete_session(self, session_id: str) -> None:
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()

    def touch_session(self, session_id: str) -> ServerSessionRecord | None:
        record = self.get_session(session_id)
        if record is None:
            return None
        record.updated_at = utc_now_iso()
        self._write_session(record)
        return record

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _write_session(self, record: ServerSessionRecord) -> None:
        path = self._session_path(record.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        temp_path.replace(path)

    def _is_expired(self, record: ServerSessionRecord) -> bool:
        if self.session_ttl_seconds <= 0:
            return False
        updated_at = datetime.fromisoformat(record.updated_at)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        elapsed_seconds = (datetime.now(UTC) - updated_at).total_seconds()
        return elapsed_seconds > self.session_ttl_seconds


class PgSessionStore:
    def __init__(self, database_url: str, session_ttl_seconds: int) -> None:
        self.database_url = database_url
        self.session_ttl_seconds = session_ttl_seconds

    def _get_conn(self):
        import psycopg2
        import psycopg2.extras

        return psycopg2.connect(self.database_url)

    def create_session(
        self,
        *,
        user: SessionUser,
        credentials: GoogleCredentialsPayload,
    ) -> ServerSessionRecord:
        record = ServerSessionRecord(
            session_id=str(uuid.uuid4()),
            user=user,
            credentials=credentials,
        )
        self._write_session(record)
        return record

    def get_session(self, session_id: str) -> ServerSessionRecord | None:
        import psycopg2.extras

        with closing(self._get_conn()) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT session_id, user_json, credentials_json, created_at, updated_at "
                    "FROM sessions WHERE session_id = %s",
                    (session_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        record = ServerSessionRecord(
            session_id=row["session_id"],
            user=SessionUser.model_validate(row["user_json"]),
            credentials=GoogleCredentialsPayload.model_validate(
                row["credentials_json"]
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        if self._is_expired(record):
            self.delete_session(session_id)
            return None
        return record

    def delete_session(self, session_id: str) -> None:
        with closing(self._get_conn()) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM sessions WHERE session_id = %s", (session_id,))
            conn.commit()

    def touch_session(self, session_id: str) -> ServerSessionRecord | None:
        record = self.get_session(session_id)
        if record is None:
            return None
        record.updated_at = utc_now_iso()
        self._write_session(record)
        return record

    def _write_session(self, record: ServerSessionRecord) -> None:
        with closing(self._get_conn()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sessions (session_id, user_json, credentials_json, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE SET
                        user_json        = EXCLUDED.user_json,
                        credentials_json = EXCLUDED.credentials_json,
                        updated_at       = EXCLUDED.updated_at
                    """,
                    (
                        record.session_id,
                        json.dumps(record.user.model_dump(mode="json")),
                        json.dumps(record.credentials.model_dump(mode="json")),
                        record.created_at,
                        record.updated_at,
                    ),
                )
            conn.commit()

    def _is_expired(self, record: ServerSessionRecord) -> bool:
        if self.session_ttl_seconds <= 0:
            return False
        updated_at = datetime.fromisoformat(record.updated_at)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        elapsed_seconds = (datetime.now(UTC) - updated_at).total_seconds()
        return elapsed_seconds > self.session_ttl_seconds


def get_session_store(
    settings: Settings | None = None,
) -> ServerSessionStore | PgSessionStore:
    resolved_settings = settings or get_settings()
    if resolved_settings.database_url:
        return PgSessionStore(
            database_url=resolved_settings.database_url,
            session_ttl_seconds=resolved_settings.session_ttl_seconds,
        )
    return ServerSessionStore(
        resolved_settings.storage_dir_path / "_sessions",
        resolved_settings.session_ttl_seconds,
    )
