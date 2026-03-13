from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.documents import (
    ActiveFolderRecord,
    ChunkRecord,
    DriveFileMetadata,
    IndexedFileRecord,
)


class StorageBackend(ABC):
    @abstractmethod
    def get_file(self, owner_google_id: str, file_id: str) -> IndexedFileRecord | None:
        raise NotImplementedError

    @abstractmethod
    def upsert_file(self, file_record: IndexedFileRecord) -> IndexedFileRecord:
        raise NotImplementedError

    @abstractmethod
    def replace_file_chunks(
        self,
        owner_google_id: str,
        file_id: str,
        chunks: list[ChunkRecord],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_file_chunks(self, owner_google_id: str, file_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def associate_file_with_folder(
        self, owner_google_id: str, file_id: str, folder_id: str
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def query_chunks(
        self,
        owner_google_id: str,
        folder_id: str,
        query_embedding: list[float],
        top_k: int = 5,
        file_name: str | None = None,
        min_similarity: float = 0.0,
    ) -> list[ChunkRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_folder_files(
        self, owner_google_id: str, folder_id: str
    ) -> list[DriveFileMetadata]:
        raise NotImplementedError

    @abstractmethod
    def get_file_chunks(self, owner_google_id: str, file_id: str) -> list[ChunkRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_active_folder(self, owner_google_id: str) -> ActiveFolderRecord | None:
        raise NotImplementedError

    @abstractmethod
    def set_active_folder(self, active_folder: ActiveFolderRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear_active_folder(self, owner_google_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear_user_data(self, owner_google_id: str) -> None:
        raise NotImplementedError
