from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.models.documents import ChunkMetadata, ChunkRecord, DriveFileMetadata, ParsedDocument
from app.services.ingestion import IngestionService
from app.services.retrieval_service import RetrievalService
from app.services.storage.local_store import LocalStorageBackend


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        SESSION_SECRET="test-secret",
        GOOGLE_CLIENT_ID="test-google-client-id",
        GOOGLE_CLIENT_SECRET="test-google-client-secret",
        GOOGLE_REDIRECT_URI="http://localhost/auth/google/callback",
        OPENAI_API_KEY="test-openai-key",
        OPENAI_CHAT_MODEL="gpt-4o-mini",
        OPENAI_EMBEDDING_MODEL="text-embedding-3-small",
        FRONTEND_URL="http://localhost:5173",
        BACKEND_URL="http://localhost:8000",
        VECTOR_STORE_BACKEND="local",
        LOCAL_STORAGE_DIR=str(tmp_path / "storage"),
        LOCAL_UPLOADS_DIR=str(tmp_path / "uploads"),
    )


def build_file(
    file_id: str,
    modified_time: str,
    *,
    source_type: str = "document",
    mime_type: str = "application/vnd.google-apps.document",
) -> DriveFileMetadata:
    return DriveFileMetadata(
        file_id=file_id,
        name=f"{file_id}.txt",
        mime_type=mime_type,
        web_view_link=f"https://drive.google.com/file/d/{file_id}/view",
        source_type=source_type,
        modified_time=modified_time,
        folder_ids=["folder-123"],
    )


def build_document(file: DriveFileMetadata, text: str) -> ParsedDocument:
    return ParsedDocument(
        file_id=file.file_id,
        name=file.name,
        mime_type=file.mime_type,
        web_view_link=file.web_view_link,
        source_type=file.source_type,
        modified_time=file.modified_time,
        text=text,
        local_path=None,
    )


def build_service(tmp_path: Path) -> tuple[IngestionService, LocalStorageBackend]:
    settings = build_settings(tmp_path)
    storage = LocalStorageBackend(settings.storage_dir_path)
    service = IngestionService(settings, storage)
    service._embed_texts = lambda texts: [[1.0, 0.0, 0.0] for _ in texts]  # type: ignore[method-assign]
    return service, storage


def test_new_file_triggers_processing(tmp_path: Path) -> None:
    service, storage = build_service(tmp_path)
    file = build_file("file-new", "2026-03-11T10:00:00Z")
    processed: list[str] = []

    def download_document(input_file: DriveFileMetadata) -> ParsedDocument:
        processed.append(input_file.file_id)
        return build_document(input_file, "Freshly indexed content")

    result = service.ingest_folder("user-1", "folder-123", [file], download_document)

    assert processed == ["file-new"]
    assert result.sync_summary.new_files == 1
    assert result.sync_summary.skipped_files == 0
    assert result.sync_summary.updated_files == 0
    assert storage.get_file("user-1", "file-new") is not None


def test_unchanged_file_skips_processing_and_reuses_cache(tmp_path: Path) -> None:
    service, storage = build_service(tmp_path)
    file = build_file("file-same", "2026-03-11T10:00:00Z")

    service.ingest_folder(
        "user-1",
        "folder-123",
        [file],
        lambda input_file: build_document(input_file, "Original cached content"),
    )

    processed: list[str] = []
    result = service.ingest_folder(
        "user-1",
        "folder-123",
        [file],
        lambda input_file: processed.append(input_file.file_id) or build_document(input_file, "Should not run"),
    )

    queried_chunks = storage.query_chunks("user-1", "folder-123", [1.0, 0.0, 0.0], top_k=5)
    assert processed == []
    assert result.sync_summary.skipped_files == 1
    assert queried_chunks[0].metadata.text == "Original cached content"


def test_updated_file_invalidates_and_reingests(tmp_path: Path) -> None:
    service, storage = build_service(tmp_path)
    original_file = build_file("file-updated", "2026-03-11T10:00:00Z")
    updated_file = build_file("file-updated", "2026-03-12T10:00:00Z")

    service.ingest_folder(
        "user-1",
        "folder-123",
        [original_file],
        lambda input_file: build_document(input_file, "Old chunk text"),
    )

    result = service.ingest_folder(
        "user-1",
        "folder-123",
        [updated_file],
        lambda input_file: build_document(input_file, "New chunk text"),
    )

    queried_chunks = storage.query_chunks("user-1", "folder-123", [1.0, 0.0, 0.0], top_k=5)
    assert result.sync_summary.updated_files == 1
    assert len([chunk for chunk in queried_chunks if chunk.metadata.file_id == "file-updated"]) == 1
    assert queried_chunks[0].metadata.text == "New chunk text"


def test_query_chunks_filters_out_low_similarity_matches(tmp_path: Path) -> None:
    _, storage = build_service(tmp_path)
    strong_chunk = ChunkRecord(
        metadata=ChunkMetadata(
            chunk_id="strong-1",
            owner_google_id="user-1",
            file_id="file-strong",
            file_name="strong.txt",
            mime_type="application/vnd.google-apps.document",
            source_type="document",
            drive_url="https://drive.google.com/file/d/file-strong/view",
            folder_ids=["folder-123"],
            chunk_index=0,
            text="Strong match",
        ),
        embedding=[1.0, 0.0, 0.0],
    )
    weak_chunk = ChunkRecord(
        metadata=ChunkMetadata(
            chunk_id="weak-1",
            owner_google_id="user-1",
            file_id="file-weak",
            file_name="weak.txt",
            mime_type="application/vnd.google-apps.document",
            source_type="document",
            drive_url="https://drive.google.com/file/d/file-weak/view",
            folder_ids=["folder-123"],
            chunk_index=0,
            text="Weak match",
        ),
        embedding=[0.0, 1.0, 0.0],
    )
    storage.replace_file_chunks("user-1", "file-strong", [strong_chunk])
    storage.replace_file_chunks("user-1", "file-weak", [weak_chunk])

    queried_chunks = storage.query_chunks(
        "user-1",
        "folder-123",
        [1.0, 0.0, 0.0],
        top_k=5,
        min_similarity=0.5,
    )

    assert [chunk.metadata.file_id for chunk in queried_chunks] == ["file-strong"]


def test_query_chunks_returns_empty_when_threshold_filters_everything(
    tmp_path: Path,
) -> None:
    _, storage = build_service(tmp_path)
    best_chunk = ChunkRecord(
        metadata=ChunkMetadata(
            chunk_id="best-1",
            owner_google_id="user-1",
            file_id="file-best",
            file_name="best.txt",
            mime_type="application/vnd.google-apps.document",
            source_type="document",
            drive_url="https://drive.google.com/file/d/file-best/view",
            folder_ids=["folder-123"],
            chunk_index=0,
            text="Best available match",
        ),
        embedding=[1.0, 0.0, 0.0],
    )
    weaker_chunk = ChunkRecord(
        metadata=ChunkMetadata(
            chunk_id="weaker-1",
            owner_google_id="user-1",
            file_id="file-weaker",
            file_name="weaker.txt",
            mime_type="application/vnd.google-apps.document",
            source_type="document",
            drive_url="https://drive.google.com/file/d/file-weaker/view",
            folder_ids=["folder-123"],
            chunk_index=0,
            text="Weaker available match",
        ),
        embedding=[0.0, 1.0, 0.0],
    )
    storage.replace_file_chunks("user-1", "file-best", [best_chunk])
    storage.replace_file_chunks("user-1", "file-weaker", [weaker_chunk])

    queried_chunks = storage.query_chunks(
        "user-1",
        "folder-123",
        [1.0, 0.0, 0.0],
        top_k=5,
        min_similarity=1.1,
    )

    assert queried_chunks == []


def test_search_folder_prefers_literal_mentions_within_semantic_candidates(
    tmp_path: Path,
) -> None:
    """Literal refinement keeps only chunks that contain the query text."""
    settings = build_settings(tmp_path)
    storage = LocalStorageBackend(settings.storage_dir_path)
    # Chunk similar to query embedding but does not contain the query term.
    storage.replace_file_chunks(
        "user-1",
        "file-a",
        [
            ChunkRecord(
                metadata=ChunkMetadata(
                    chunk_id="chunk-a",
                    owner_google_id="user-1",
                    file_id="file-a",
                    file_name="Overview",
                    mime_type="application/vnd.google-apps.document",
                    source_type="document",
                    drive_url="https://drive.google.com/file/d/file-a/view",
                    folder_ids=["folder-123"],
                    chunk_index=0,
                    text="The project uses a shared library for authentication and logging.",
                ),
                embedding=[1.0, 0.0, 0.0],
            )
        ],
    )
    # Chunk similar to query embedding and literally contains the query term.
    storage.replace_file_chunks(
        "user-1",
        "file-b",
        [
            ChunkRecord(
                metadata=ChunkMetadata(
                    chunk_id="chunk-b",
                    owner_google_id="user-1",
                    file_id="file-b",
                    file_name="Recommendations",
                    mime_type="application/vnd.google-apps.document",
                    source_type="document",
                    drive_url="https://drive.google.com/file/d/file-b/view",
                    folder_ids=["folder-123"],
                    chunk_index=0,
                    text="We recommend the widget for production deployments.",
                ),
                embedding=[0.9, 0.0, 0.0],
            )
        ],
    )
    retrieval = RetrievalService(settings, storage)
    retrieval._embed_texts = lambda texts: [[1.0, 0.0, 0.0] for _ in texts]  # type: ignore[method-assign]

    result = retrieval.search_folder(
        owner_google_id="user-1",
        folder_id="folder-123",
        query="widget",
        top_k=5,
    )

    assert [citation.file_id for citation in result.citations] == ["file-b"]
    assert result.used_literal_refinement is True
    assert "widget" in result.citations[0].chunk_excerpt


def test_read_file_returns_persisted_extracted_text_for_presentations(tmp_path: Path) -> None:
    service, storage = build_service(tmp_path)
    file = build_file(
        "file-slides",
        "2026-03-11T10:00:00Z",
        source_type="presentation",
        mime_type="application/vnd.google-apps.presentation",
    )
    service.ingest_folder(
        "user-1",
        "folder-123",
        [file],
        lambda input_file: build_document(
            input_file,
            "Slide 1 title\n\nQuarterly launch plan\n\nSlide 2\n\nRisks and mitigations",
        ),
    )
    retrieval = RetrievalService(build_settings(tmp_path), storage)

    result = retrieval.read_file(
        owner_google_id="user-1",
        folder_id="folder-123",
        file_id="file-slides",
        max_chars=12000,
    )

    assert result.citation.file_id == "file-slides"
    assert "Quarterly launch plan" in result.content
    assert result.truncated is False


def test_read_file_falls_back_to_file_name_when_model_passes_source_id(tmp_path: Path) -> None:
    service, storage = build_service(tmp_path)
    file = build_file(
        "file-applications",
        "2026-03-11T10:00:00Z",
        source_type="spreadsheet",
        mime_type="application/vnd.google-apps.spreadsheet",
    )
    file.name = "Applications "
    service.ingest_folder(
        "user-1",
        "folder-123",
        [file],
        lambda input_file: build_document(
            input_file,
            "Company,Status,Notes\nAlpha,No,not yet applying\n",
        ),
    )
    retrieval = RetrievalService(build_settings(tmp_path), storage)

    result = retrieval.read_file(
        owner_google_id="user-1",
        folder_id="folder-123",
        file_id="source_4",
        file_name="Applications ",
    )

    assert result.citation.file_id == "file-applications"
    assert "not yet applying" in result.content


def test_spreadsheet_chunking_keeps_rows_together(tmp_path: Path) -> None:
    service, _storage = build_service(tmp_path)
    spreadsheet = build_document(
        build_file(
            "file-sheet",
            "2026-03-11T10:00:00Z",
            source_type="spreadsheet",
            mime_type="application/vnd.google-apps.spreadsheet",
        ),
        "Company,Status,Notes\n"
        "Alpha,No,not yet applying because timing is off\n"
        "Beta,Yes,already applied\n",
    )

    chunk_texts = service._chunk_texts_for_document(spreadsheet)

    assert any("not yet applying because timing is off" in chunk for chunk in chunk_texts)
