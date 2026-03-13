from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
from typing import cast

from app.models.documents import (
    ActiveFolderRecord,
    ChunkRecord,
    DriveFileMetadata,
    FolderIndexSummary,
    IndexedFileRecord,
)
from app.services.storage.base import StorageBackend


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class LocalStorageBackend(StorageBackend):
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def get_file(self, owner_google_id: str, file_id: str) -> IndexedFileRecord | None:
        files = self._read_files(owner_google_id)
        payload = files.get(file_id)
        if not payload:
            return None
        return cast(IndexedFileRecord, IndexedFileRecord.model_validate(payload))

    def upsert_file(self, file_record: IndexedFileRecord) -> IndexedFileRecord:
        files = self._read_files(file_record.owner_google_id)
        files[file_record.file_id] = file_record.model_dump(mode="json")
        self._write_files(file_record.owner_google_id, files)
        self._write_folder_indexes(file_record.owner_google_id, files)
        return file_record

    def replace_file_chunks(
        self,
        owner_google_id: str,
        file_id: str,
        chunks: list[ChunkRecord],
    ) -> None:
        all_chunks = self._read_chunks(owner_google_id)
        filtered_chunks = [
            chunk for chunk in all_chunks if chunk.metadata.file_id != file_id
        ]
        filtered_chunks.extend(chunks)
        self._write_chunks(owner_google_id, filtered_chunks)

    def delete_file_chunks(self, owner_google_id: str, file_id: str) -> None:
        chunks = self._read_chunks(owner_google_id)
        remaining_chunks = [
            chunk for chunk in chunks if chunk.metadata.file_id != file_id
        ]
        self._write_chunks(owner_google_id, remaining_chunks)

    def associate_file_with_folder(
        self, owner_google_id: str, file_id: str, folder_id: str
    ) -> None:
        files = self._read_files(owner_google_id)
        if file_id not in files:
            return

        file_record = IndexedFileRecord.model_validate(files[file_id])
        if folder_id in file_record.folder_ids:
            return

        file_record.folder_ids = sorted({*file_record.folder_ids, folder_id})
        files[file_id] = file_record.model_dump(mode="json")
        self._write_files(owner_google_id, files)
        self._write_folder_indexes(owner_google_id, files)

        chunks = self._read_chunks(owner_google_id)
        for chunk in chunks:
            if chunk.metadata.file_id == file_id:
                chunk.metadata.folder_ids = sorted(
                    {*chunk.metadata.folder_ids, folder_id}
                )
        self._write_chunks(owner_google_id, chunks)

    def query_chunks(
        self,
        owner_google_id: str,
        folder_id: str,
        query_embedding: list[float],
        top_k: int = 5,
        file_name: str | None = None,
        min_similarity: float = 0.0,
    ) -> list[ChunkRecord]:
        chunks = [
            chunk
            for chunk in self._read_chunks(owner_google_id)
            if folder_id in chunk.metadata.folder_ids
        ]
        if file_name:
            normalized_file_name = file_name.strip().lower()
            chunks = [
                chunk
                for chunk in chunks
                if normalized_file_name in chunk.metadata.file_name.lower()
            ]
        scored_chunks = [
            (chunk, _cosine_similarity(chunk.embedding, query_embedding))
            for chunk in chunks
        ]
        ranked = sorted(scored_chunks, key=lambda item: item[1], reverse=True)
        filtered = [
            chunk for chunk, similarity in ranked if similarity >= min_similarity
        ]
        return filtered[:top_k]

    def get_folder_files(
        self, owner_google_id: str, folder_id: str
    ) -> list[DriveFileMetadata]:
        folder_index_path = (
            self._user_dir(owner_google_id) / "folders" / f"{folder_id}.json"
        )
        if not folder_index_path.exists():
            return []
        summary = FolderIndexSummary.model_validate_json(
            folder_index_path.read_text(encoding="utf-8")
        )

        files = self._read_files(owner_google_id)
        folder_files: list[DriveFileMetadata] = []
        for file_id in summary.file_ids:
            payload = files.get(file_id)
            if payload:
                folder_files.append(
                    IndexedFileRecord.model_validate(payload).to_drive_metadata()
                )
        return folder_files

    def get_file_chunks(self, owner_google_id: str, file_id: str) -> list[ChunkRecord]:
        chunks = [
            chunk
            for chunk in self._read_chunks(owner_google_id)
            if chunk.metadata.file_id == file_id
        ]
        return sorted(chunks, key=lambda chunk: chunk.metadata.chunk_index)

    def get_active_folder(self, owner_google_id: str) -> ActiveFolderRecord | None:
        active_folder_path = self._user_dir(owner_google_id) / "active_folder.json"
        if not active_folder_path.exists():
            return None
        return cast(
            ActiveFolderRecord,
            ActiveFolderRecord.model_validate_json(
                active_folder_path.read_text(encoding="utf-8")
            ),
        )

    def set_active_folder(self, active_folder: ActiveFolderRecord) -> None:
        user_dir = self._user_dir(active_folder.owner_google_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "active_folder.json").write_text(
            active_folder.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def clear_active_folder(self, owner_google_id: str) -> None:
        active_folder_path = self._user_dir(owner_google_id) / "active_folder.json"
        if active_folder_path.exists():
            active_folder_path.unlink()

    def clear_user_data(self, owner_google_id: str) -> None:
        user_dir = self._user_dir(owner_google_id)
        if user_dir.exists():
            shutil.rmtree(user_dir)

    def _user_dir(self, owner_google_id: str) -> Path:
        return self.storage_dir / owner_google_id

    def _read_files(self, owner_google_id: str) -> dict[str, dict]:
        files_path = self._user_dir(owner_google_id) / "files.json"
        if not files_path.exists():
            return {}
        return cast(dict[str, dict], json.loads(files_path.read_text(encoding="utf-8")))

    def _write_files(self, owner_google_id: str, payload: dict[str, dict]) -> None:
        user_dir = self._user_dir(owner_google_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "files.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def _read_chunks(self, owner_google_id: str) -> list[ChunkRecord]:
        chunks_path = self._user_dir(owner_google_id) / "chunks.json"
        if not chunks_path.exists():
            return []
        payload = json.loads(chunks_path.read_text(encoding="utf-8"))
        return [ChunkRecord.model_validate(item) for item in payload]

    def _write_chunks(self, owner_google_id: str, chunks: list[ChunkRecord]) -> None:
        user_dir = self._user_dir(owner_google_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "chunks.json").write_text(
            json.dumps([chunk.model_dump(mode="json") for chunk in chunks], indent=2),
            encoding="utf-8",
        )

    def _write_folder_indexes(
        self, owner_google_id: str, files: dict[str, dict]
    ) -> None:
        folders_dir = self._user_dir(owner_google_id) / "folders"
        folders_dir.mkdir(parents=True, exist_ok=True)

        for path in folders_dir.glob("*.json"):
            path.unlink()

        folder_map: dict[str, list[str]] = {}
        for file_id, payload in files.items():
            file_record = IndexedFileRecord.model_validate(payload)
            for folder_id in file_record.folder_ids:
                folder_map.setdefault(folder_id, []).append(file_id)

        for folder_id, file_ids in folder_map.items():
            summary = FolderIndexSummary(
                owner_google_id=owner_google_id,
                folder_id=folder_id,
                file_ids=sorted(file_ids),
            )
            (folders_dir / f"{folder_id}.json").write_text(
                summary.model_dump_json(indent=2),
                encoding="utf-8",
            )
