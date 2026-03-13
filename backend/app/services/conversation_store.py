from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Protocol, cast

from app.core.config import Settings, get_settings
from app.models.conversation import FolderConversationRecord
from app.models.session import utc_now_iso


class ConversationStoreProtocol(Protocol):
    def get_folder_conversation(
        self, owner_google_id: str, folder_id: str
    ) -> FolderConversationRecord | None: ...

    def upsert_folder_conversation(
        self, record: FolderConversationRecord
    ) -> FolderConversationRecord: ...

    def delete_folder_conversation(
        self, owner_google_id: str, folder_id: str
    ) -> None: ...

    def delete_user_conversations(self, owner_google_id: str) -> None: ...


class ConversationStore:
    def __init__(self, storage_dir: Path) -> None:
        self.base_dir = storage_dir / "_conversations"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_folder_conversation(
        self,
        owner_google_id: str,
        folder_id: str,
    ) -> FolderConversationRecord | None:
        path = self._conversation_path(owner_google_id, folder_id)
        if not path.exists():
            return None
        return cast(
            FolderConversationRecord,
            FolderConversationRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            ),
        )

    def upsert_folder_conversation(
        self,
        record: FolderConversationRecord,
    ) -> FolderConversationRecord:
        record.updated_at = utc_now_iso()
        path = self._conversation_path(record.owner_google_id, record.folder_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return record

    def delete_folder_conversation(self, owner_google_id: str, folder_id: str) -> None:
        path = self._conversation_path(owner_google_id, folder_id)
        if path.exists():
            path.unlink()

    def delete_user_conversations(self, owner_google_id: str) -> None:
        user_dir = self.base_dir / owner_google_id
        if not user_dir.exists():
            return
        for path in user_dir.glob("*.json"):
            path.unlink()
        user_dir.rmdir()

    def _conversation_path(self, owner_google_id: str, folder_id: str) -> Path:
        return self.base_dir / owner_google_id / f"{folder_id}.json"


class PgConversationStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _get_conn(self):
        import psycopg2

        return psycopg2.connect(self.database_url)

    def get_folder_conversation(
        self,
        owner_google_id: str,
        folder_id: str,
    ) -> FolderConversationRecord | None:
        import psycopg2.extras

        with closing(self._get_conn()) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT owner_google_id, folder_id, conversation_id,
                           last_response_id, created_at, updated_at
                    FROM conversations
                    WHERE owner_google_id = %s AND folder_id = %s
                    """,
                    (owner_google_id, folder_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return FolderConversationRecord(
            owner_google_id=row["owner_google_id"],
            folder_id=row["folder_id"],
            conversation_id=row["conversation_id"],
            last_response_id=row["last_response_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def upsert_folder_conversation(
        self,
        record: FolderConversationRecord,
    ) -> FolderConversationRecord:
        record.updated_at = utc_now_iso()
        with closing(self._get_conn()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO conversations
                        (owner_google_id, folder_id, conversation_id, last_response_id, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (owner_google_id, folder_id) DO UPDATE SET
                        conversation_id  = EXCLUDED.conversation_id,
                        last_response_id = EXCLUDED.last_response_id,
                        updated_at       = EXCLUDED.updated_at
                    """,
                    (
                        record.owner_google_id,
                        record.folder_id,
                        record.conversation_id,
                        record.last_response_id,
                        record.created_at,
                        record.updated_at,
                    ),
                )
            conn.commit()
        return record

    def delete_folder_conversation(self, owner_google_id: str, folder_id: str) -> None:
        with closing(self._get_conn()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM conversations WHERE owner_google_id = %s AND folder_id = %s",
                    (owner_google_id, folder_id),
                )
            conn.commit()

    def delete_user_conversations(self, owner_google_id: str) -> None:
        with closing(self._get_conn()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM conversations WHERE owner_google_id = %s",
                    (owner_google_id,),
                )
            conn.commit()


def get_conversation_store(
    settings: Settings | None = None,
) -> ConversationStore | PgConversationStore:
    resolved_settings = settings or get_settings()
    if resolved_settings.database_url:
        return PgConversationStore(database_url=resolved_settings.database_url)
    return ConversationStore(resolved_settings.storage_dir_path)
