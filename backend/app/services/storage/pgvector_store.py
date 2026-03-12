from __future__ import annotations

from app.models.documents import ActiveFolderRecord, ChunkRecord, DriveFileMetadata, IndexedFileRecord
from app.services.storage.base import StorageBackend


class PgVectorStorageBackend(StorageBackend):
    """Placeholder for the later Replit Postgres implementation."""

    def __init__(self, database_url: str, table_name: str) -> None:
        self.database_url = database_url
        self.table_name = table_name

    def get_file(self, owner_google_id: str, file_id: str) -> IndexedFileRecord | None:
        raise NotImplementedError(
            "PgVector storage is intentionally deferred until Replit Postgres is configured."
        )

    def upsert_file(self, file_record: IndexedFileRecord) -> IndexedFileRecord:
        raise NotImplementedError(
            "PgVector storage is intentionally deferred until Replit Postgres is configured."
        )

    def replace_file_chunks(
        self,
        owner_google_id: str,
        file_id: str,
        chunks: list[ChunkRecord],
    ) -> None:
        raise NotImplementedError(
            "PgVector storage is intentionally deferred until Replit Postgres is configured."
        )

    def delete_file_chunks(self, owner_google_id: str, file_id: str) -> None:
        raise NotImplementedError(
            "PgVector storage is intentionally deferred until Replit Postgres is configured."
        )

    def associate_file_with_folder(self, owner_google_id: str, file_id: str, folder_id: str) -> None:
        raise NotImplementedError(
            "PgVector storage is intentionally deferred until Replit Postgres is configured."
        )

    def query_chunks(
        self,
        owner_google_id: str,
        folder_id: str,
        query_embedding: list[float],
        top_k: int = 5,
        file_name: str | None = None,
        min_similarity: float = 0.0,
    ) -> list[ChunkRecord]:
        raise NotImplementedError(
            "PgVector storage is intentionally deferred until Replit Postgres is configured."
        )

    def get_folder_files(self, owner_google_id: str, folder_id: str) -> list[DriveFileMetadata]:
        raise NotImplementedError(
            "PgVector storage is intentionally deferred until Replit Postgres is configured."
        )

    def get_file_chunks(self, owner_google_id: str, file_id: str) -> list[ChunkRecord]:
        raise NotImplementedError(
            "PgVector storage is intentionally deferred until Replit Postgres is configured."
        )

    def clear_user_data(self, owner_google_id: str) -> None:
        raise NotImplementedError(
            "PgVector storage is intentionally deferred until Replit Postgres is configured."
        )

    def get_active_folder(self, owner_google_id: str) -> ActiveFolderRecord | None:
        raise NotImplementedError(
            "PgVector storage is intentionally deferred until Replit Postgres is configured."
        )

    def set_active_folder(self, active_folder: ActiveFolderRecord) -> None:
        raise NotImplementedError(
            "PgVector storage is intentionally deferred until Replit Postgres is configured."
        )

    def clear_active_folder(self, owner_google_id: str) -> None:
        raise NotImplementedError(
            "PgVector storage is intentionally deferred until Replit Postgres is configured."
        )
