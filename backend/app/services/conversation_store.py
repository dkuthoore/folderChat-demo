from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, get_settings
from app.models.conversation import FolderConversationRecord
from app.models.session import utc_now_iso


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
        return FolderConversationRecord.model_validate_json(path.read_text(encoding="utf-8"))

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


def get_conversation_store(settings: Settings | None = None) -> ConversationStore:
    resolved_settings = settings or get_settings()
    return ConversationStore(resolved_settings.storage_dir_path)
