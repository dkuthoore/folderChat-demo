from __future__ import annotations

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.models.documents import (
    ChunkMetadata,
    ChunkRecord,
    DriveFileMetadata,
    IndexedFileRecord,
    ParsedDocument,
    SyncDecision,
    SyncSummary,
)
from app.services.storage.base import StorageBackend
from app.services.storage.local_store import LocalStorageBackend
from app.services.storage.pgvector_store import PgVectorStorageBackend
from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from openai import OpenAI  # type: ignore[attr-defined]


@dataclass
class IngestionResult:
    folder_id: str
    files: list[DriveFileMetadata]
    sync_decisions: list[SyncDecision]
    sync_summary: SyncSummary
    stages: list[dict[str, str]]


def get_storage_backend(settings: Settings | None = None) -> StorageBackend:
    settings = settings or get_settings()
    if settings.vector_store_backend == "pgvector":
        if not settings.database_url:
            raise ValueError(
                "DATABASE_URL must be configured when VECTOR_STORE_BACKEND=pgvector"
            )
        return PgVectorStorageBackend(
            database_url=settings.database_url,
            table_name=settings.pgvector_table_name,
        )
    return LocalStorageBackend(settings.storage_dir_path)


class IngestionService:
    def __init__(self, settings: Settings, storage_backend: StorageBackend) -> None:
        self.settings = settings
        self.storage_backend = storage_backend
        self.openai = OpenAI(api_key=settings.openai_api_key)
        self.splitter = SentenceSplitter(chunk_size=800, chunk_overlap=120)

    def sync_check(
        self,
        owner_google_id: str,
        folder_id: str,
        files: list[DriveFileMetadata],
    ) -> tuple[int, int, int]:
        """Compare Drive files with storage. Returns (new_count, skipped_count, updated_count)."""
        new_count = 0
        skipped_count = 0
        updated_count = 0
        for file in files:
            existing_file = self.storage_backend.get_file(owner_google_id, file.file_id)
            if not existing_file:
                new_count += 1
                continue
            if existing_file.modified_time == file.modified_time:
                self.storage_backend.associate_file_with_folder(
                    owner_google_id, file.file_id, folder_id
                )
                skipped_count += 1
                continue
            updated_count += 1
        return new_count, skipped_count, updated_count

    def ingest_folder(
        self,
        owner_google_id: str,
        folder_id: str,
        files: list[DriveFileMetadata],
        download_document: Callable[[DriveFileMetadata], ParsedDocument],
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> IngestionResult:
        self._emit_progress(
            progress_callback,
            10,
            f"Fetching files from Drive and planning Smart Sync for {len(files)} file(s).",
        )
        stages = [
            {
                "label": "Fetching files",
                "detail": f"Loaded {len(files)} supported files from Drive.",
            },
        ]

        sync_decisions: list[SyncDecision] = []
        processed_files: list[DriveFileMetadata] = []
        new_count = 0
        skipped_count = 0
        updated_count = 0

        for file in files:
            existing_file = self.storage_backend.get_file(owner_google_id, file.file_id)
            if not existing_file:
                sync_decisions.append(SyncDecision(file=file, status="new"))
                processed_files.append(file)
                new_count += 1
                continue

            if existing_file.modified_time == file.modified_time:
                self.storage_backend.associate_file_with_folder(
                    owner_google_id, file.file_id, folder_id
                )
                sync_decisions.append(
                    SyncDecision(
                        file=existing_file.to_drive_metadata(),
                        status="skipped",
                    )
                )
                skipped_count += 1
                continue

            sync_decisions.append(SyncDecision(file=file, status="updated"))
            processed_files.append(file)
            updated_count += 1

        stages.append(
            {
                "label": "Smart Sync",
                "detail": (
                    f"{new_count} new, {skipped_count} cached, {updated_count} updated files "
                    "require processing or reuse."
                ),
            }
        )
        self._emit_progress(
            progress_callback,
            25,
            (
                f"Smart Sync planned: {new_count} new, {skipped_count} cached, "
                f"{updated_count} updated."
            ),
        )

        processed_documents: list[ParsedDocument] = []
        failed_documents: list[str] = []
        total_processed_files = len(processed_files)
        for index, file in enumerate(processed_files, start=1):
            self._emit_progress(
                progress_callback,
                25 + int((index / max(total_processed_files, 1)) * 20),
                f"Parsing text from {file.name} ({index}/{total_processed_files}).",
            )
            try:
                processed_documents.append(download_document(file))
            except Exception:
                failed_documents.append(file.name)

        if processed_documents:
            stages.append(
                {
                    "label": "Parsing text",
                    "detail": (
                        f"Exported and normalized {len(processed_documents)} file(s) "
                        "that required ingestion."
                        + (
                            f" Skipped {len(failed_documents)} file(s) that could not be parsed."
                            if failed_documents
                            else ""
                        )
                    ),
                }
            )
        else:
            stages.append(
                {
                    "label": "Parsing text",
                    "detail": (
                        "No files required parsing because every file was reused from cache."
                        if not failed_documents
                        else f"Skipped {len(failed_documents)} file(s) because they could not be parsed."
                    ),
                }
            )

        stored_chunk_count = 0
        failed_chunking: list[str] = []
        total_documents = len(processed_documents)
        for index, document in enumerate(processed_documents, start=1):
            self._emit_progress(
                progress_callback,
                50 + int(((index - 1) / max(total_documents, 1)) * 20),
                f"Chunking content for {document.name} ({index}/{total_documents}).",
            )
            try:
                existing_file = self.storage_backend.get_file(
                    owner_google_id, document.file_id
                )
                folder_ids = sorted(
                    {
                        folder_id,
                        *(existing_file.folder_ids if existing_file else []),
                    }
                )
                indexed_file = IndexedFileRecord.from_drive_file(
                    owner_google_id=owner_google_id,
                    file=document_to_drive_metadata(document, folder_ids),
                    folder_ids=folder_ids,
                )

                if existing_file:
                    self.storage_backend.delete_file_chunks(
                        owner_google_id, document.file_id
                    )

                chunks = self._build_chunks(owner_google_id, indexed_file, document)
                self._emit_progress(
                    progress_callback,
                    75 + int((index / max(total_documents, 1)) * 15),
                    f"Generating embeddings for {document.name} ({index}/{total_documents}).",
                )
                self._store_document_text(owner_google_id, document)
                self.storage_backend.upsert_file(indexed_file)
                self.storage_backend.replace_file_chunks(
                    owner_google_id, document.file_id, chunks
                )
                stored_chunk_count += len(chunks)
            except Exception:
                failed_chunking.append(document.name)

        if stored_chunk_count:
            stages.append(
                {
                    "label": "Chunking content",
                    "detail": f"Prepared {stored_chunk_count} chunks for retrieval.",
                }
            )
            stages.append(
                {
                    "label": "Generating embeddings",
                    "detail": (
                        f"Stored {stored_chunk_count} embedded chunks in the active vector backend."
                        + (
                            f" Skipped {len(failed_chunking)} file(s) that failed during chunking."
                            if failed_chunking
                            else ""
                        )
                    ),
                }
            )
        else:
            stages.append(
                {
                    "label": "Chunking content",
                    "detail": (
                        "No new chunks were created during this sync."
                        if not failed_chunking
                        else f"No new chunks were created. {len(failed_chunking)} file(s) failed during chunking."
                    ),
                }
            )
            stages.append(
                {
                    "label": "Generating embeddings",
                    "detail": "Skipped embedding generation because all files were reused from cache.",
                }
            )

        folder_files = self.storage_backend.get_folder_files(owner_google_id, folder_id)
        return IngestionResult(
            folder_id=folder_id,
            files=folder_files,
            sync_decisions=sync_decisions,
            sync_summary=SyncSummary(
                total_files=len(files),
                new_files=new_count,
                skipped_files=skipped_count,
                updated_files=updated_count,
            ),
            stages=stages,
        )

    def _emit_progress(
        self,
        progress_callback: Callable[[int, str], None] | None,
        progress: int,
        message: str,
    ) -> None:
        if progress_callback:
            progress_callback(progress, message)

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self.openai.embeddings.create(
            model=self.settings.openai_embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def _build_chunks(
        self,
        owner_google_id: str,
        indexed_file: IndexedFileRecord,
        document: ParsedDocument,
    ) -> list[ChunkRecord]:
        if not document.text.strip():
            return []

        chunk_texts = self._chunk_texts_for_document(document)
        if not chunk_texts:
            return []

        embeddings = self._embed_texts(chunk_texts)
        chunk_records: list[ChunkRecord] = []
        for index, (chunk_text, embedding) in enumerate(
            zip(chunk_texts, embeddings, strict=False)
        ):
            metadata = ChunkMetadata(
                chunk_id=f"{document.file_id}-chunk-{index}",
                owner_google_id=owner_google_id,
                file_id=document.file_id,
                file_name=document.name,
                mime_type=document.mime_type,
                source_type=document.source_type,
                drive_url=document.web_view_link,
                folder_ids=indexed_file.folder_ids,
                chunk_index=index,
                text=chunk_text,
            )
            chunk_records.append(ChunkRecord(metadata=metadata, embedding=embedding))
        return chunk_records

    def _chunk_texts_for_document(self, document: ParsedDocument) -> list[str]:
        if document.source_type == "spreadsheet":
            return self._build_spreadsheet_chunk_texts(document.text)

        llama_documents = [Document(text=document.text)]
        nodes = self.splitter.get_nodes_from_documents(llama_documents)
        return [getattr(node, "text", "") for node in nodes]

    def _build_spreadsheet_chunk_texts(self, text: str) -> list[str]:
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            return []

        serialized_rows = [self._serialize_csv_row(row) for row in rows]
        if len(serialized_rows) == 1:
            return serialized_rows

        header = serialized_rows[0]
        data_rows = serialized_rows[1:]
        chunks: list[str] = []
        current_rows = [header]
        current_length = len(header)

        for row_text in data_rows:
            row_length = len(row_text) + 1
            if (
                current_rows
                and len(current_rows) > 1
                and current_length + row_length > 800
            ):
                chunks.append("\n".join(current_rows))
                current_rows = [header, row_text]
                current_length = len(header) + row_length
                continue

            if len(current_rows) == 1 and current_length + row_length > 800:
                chunks.extend(self._split_long_text(f"{header}\n{row_text}"))
                current_rows = [header]
                current_length = len(header)
                continue

            current_rows.append(row_text)
            current_length += row_length

        if len(current_rows) > 1:
            chunks.append("\n".join(current_rows))

        return chunks or self._split_long_text(text)

    def _serialize_csv_row(self, row: list[str]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(row)
        return buffer.getvalue().strip("\r\n")

    def _split_long_text(self, text: str) -> list[str]:
        nodes = self.splitter.get_nodes_from_documents([Document(text=text)])
        return [getattr(node, "text", "") for node in nodes]

    def _store_document_text(
        self, owner_google_id: str, document: ParsedDocument
    ) -> None:
        text_dir = self.settings.storage_dir_path / owner_google_id / "texts"
        text_dir.mkdir(parents=True, exist_ok=True)
        (text_dir / f"{document.file_id}.txt").write_text(
            document.text, encoding="utf-8"
        )


def document_to_drive_metadata(
    document: ParsedDocument, folder_ids: list[str]
) -> DriveFileMetadata:
    return DriveFileMetadata(
        file_id=document.file_id,
        name=document.name,
        mime_type=document.mime_type,
        web_view_link=document.web_view_link,
        source_type=document.source_type,
        modified_time=document.modified_time,
        folder_ids=folder_ids,
        folder_path=document.folder_path or "",
    )
