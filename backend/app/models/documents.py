from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


SupportedDriveType = Literal["document", "spreadsheet", "presentation", "pdf"]
SyncStatus = Literal["new", "skipped", "updated"]


class DriveFileMetadata(BaseModel):
    file_id: str
    name: str
    mime_type: str
    web_view_link: str
    source_type: SupportedDriveType
    modified_time: str
    folder_ids: list[str] = Field(default_factory=list)
    folder_path: str = ""


class ParsedDocument(BaseModel):
    file_id: str
    name: str
    mime_type: str
    web_view_link: str
    source_type: SupportedDriveType
    modified_time: str
    text: str
    local_path: str | None = None
    folder_path: str = ""


class ChunkMetadata(BaseModel):
    chunk_id: str
    owner_google_id: str
    file_id: str
    file_name: str
    mime_type: str
    source_type: SupportedDriveType
    drive_url: str
    folder_ids: list[str] = Field(default_factory=list)
    chunk_index: int
    text: str = Field(repr=False)


class ChunkRecord(BaseModel):
    metadata: ChunkMetadata
    embedding: list[float]


class IndexedFileRecord(BaseModel):
    owner_google_id: str
    file_id: str
    name: str
    mime_type: str
    web_view_link: str
    source_type: SupportedDriveType
    modified_time: str
    folder_ids: list[str] = Field(default_factory=list)
    folder_path: str = ""
    last_synced_at: str

    @classmethod
    def from_drive_file(
        cls,
        owner_google_id: str,
        file: DriveFileMetadata,
        folder_ids: list[str],
    ) -> "IndexedFileRecord":
        return cls(
            owner_google_id=owner_google_id,
            file_id=file.file_id,
            name=file.name,
            mime_type=file.mime_type,
            web_view_link=file.web_view_link,
            source_type=file.source_type,
            modified_time=file.modified_time,
            folder_ids=sorted(set(folder_ids)),
            folder_path=file.folder_path or "",
            last_synced_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_drive_metadata(self) -> DriveFileMetadata:
        return DriveFileMetadata(
            file_id=self.file_id,
            name=self.name,
            mime_type=self.mime_type,
            web_view_link=self.web_view_link,
            source_type=self.source_type,
            modified_time=self.modified_time,
            folder_ids=self.folder_ids,
            folder_path=self.folder_path or "",
        )


class FolderIndexSummary(BaseModel):
    owner_google_id: str
    folder_id: str
    file_ids: list[str] = Field(default_factory=list)


class ActiveFolderRecord(BaseModel):
    owner_google_id: str
    folder_id: str
    folder_name: str
    folder_url: str


class SyncDecision(BaseModel):
    file: DriveFileMetadata
    status: SyncStatus


class SyncSummary(BaseModel):
    total_files: int
    new_files: int
    skipped_files: int
    updated_files: int
