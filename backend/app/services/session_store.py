from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid
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
        record = ServerSessionRecord.model_validate_json(path.read_text(encoding="utf-8"))
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
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        elapsed_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
        return elapsed_seconds > self.session_ttl_seconds


def get_session_store(settings: Settings | None = None) -> ServerSessionStore:
    resolved_settings = settings or get_settings()
    return ServerSessionStore(
        resolved_settings.storage_dir_path / "_sessions",
        resolved_settings.session_ttl_seconds,
    )
