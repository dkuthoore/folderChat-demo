from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.documents import DriveFileMetadata, ParsedDocument
from app.models.conversation import FolderConversationRecord
from tests.helpers import FakeOpenAI


def fake_drive_file(file_id: str, modified_time: str = "2026-03-11T10:00:00Z") -> DriveFileMetadata:
    return DriveFileMetadata(
        file_id=file_id,
        name=f"{file_id}.txt",
        mime_type="application/vnd.google-apps.document",
        web_view_link=f"https://drive.google.com/file/d/{file_id}/view",
        source_type="document",
        modified_time=modified_time,
        folder_ids=["folder-abc"],
    )


def fake_document(file: DriveFileMetadata, text: str) -> ParsedDocument:
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


def patch_openai(monkeypatch) -> None:
    import app.services.chat_agent as chat_agent_module
    import app.services.ingestion as ingestion_module
    import app.services.retrieval_service as retrieval_module

    FakeOpenAI.reset()
    monkeypatch.setattr(ingestion_module, "OpenAI", lambda api_key: FakeOpenAI(api_key))
    monkeypatch.setattr(retrieval_module, "OpenAI", lambda api_key: FakeOpenAI(api_key))
    monkeypatch.setattr(chat_agent_module, "OpenAI", lambda api_key: FakeOpenAI(api_key))


def test_ingest_endpoint_returns_sync_summary(
    authenticated_client: TestClient,
    monkeypatch,
) -> None:
    import app.api.ingest as ingest_module

    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "get_folder_name",
        lambda self, folder_id: "Demo Folder",
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "list_supported_files",
        lambda self, folder_id: [fake_drive_file("file-1")],
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "download_and_parse",
        lambda self, folder_id, file: fake_document(file, "Indexed doc text"),
    )
    patch_openai(monkeypatch)

    response = authenticated_client.post(
        "/api/ingest",
        json={"folder_url": "https://drive.google.com/drive/folders/folder-abc"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["folder_name"] == "Demo Folder"
    assert payload["folder_id"] == "folder-abc"


def test_session_returns_folder_files_from_storage_after_ingest(
    authenticated_client: TestClient,
    monkeypatch,
) -> None:
    import app.api.ingest as ingest_module

    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "get_folder_name",
        lambda self, folder_id: "Session Folder",
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "list_supported_files",
        lambda self, folder_id: [fake_drive_file("file-session")],
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "download_and_parse",
        lambda self, folder_id, file: fake_document(file, "Session-backed doc text"),
    )
    patch_openai(monkeypatch)

    ingest_response = authenticated_client.post(
        "/api/ingest",
        json={"folder_url": "https://drive.google.com/drive/folders/folder-abc"},
    )
    assert ingest_response.status_code == 202

    session_response = authenticated_client.get("/api/session")
    assert session_response.status_code == 200

    payload = session_response.json()
    assert payload["current_folder_id"] == "folder-abc"
    assert payload["current_folder_name"] == "Session Folder"
    assert payload["current_folder_url"] == "https://drive.google.com/drive/folders/folder-abc"
    assert payload["files"][0]["file_id"] == "file-session"


def test_job_stream_emits_completion_event(
    authenticated_client: TestClient,
    monkeypatch,
) -> None:
    import app.api.ingest as ingest_module

    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "get_folder_name",
        lambda self, folder_id: "Streaming Folder",
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "list_supported_files",
        lambda self, folder_id: [fake_drive_file("file-stream")],
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "download_and_parse",
        lambda self, folder_id, file: fake_document(file, "Stream me"),
    )
    patch_openai(monkeypatch)

    ingest_response = authenticated_client.post(
        "/api/ingest",
        json={"folder_url": "https://drive.google.com/drive/folders/folder-abc"},
    )
    assert ingest_response.status_code == 202
    job_id = ingest_response.json()["job_id"]

    stream_response = authenticated_client.get(f"/api/jobs/{job_id}/stream")
    assert stream_response.status_code == 200
    assert "event: complete" in stream_response.text
    assert "\"folder_name\":\"Streaming Folder\"" in stream_response.text


def test_chat_endpoint_returns_answer_and_citations(
    authenticated_client: TestClient,
    monkeypatch,
) -> None:
    import app.api.ingest as ingest_module

    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "get_folder_name",
        lambda self, folder_id: "Chat Folder",
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "list_supported_files",
        lambda self, folder_id: [fake_drive_file("file-chat")],
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "download_and_parse",
        lambda self, folder_id, file: fake_document(file, "Quarterly revenue was $2M."),
    )
    patch_openai(monkeypatch)

    ingest_response = authenticated_client.post(
        "/api/ingest",
        json={"folder_url": "https://drive.google.com/drive/folders/folder-abc"},
    )
    assert ingest_response.status_code == 202

    chat_response = authenticated_client.post(
        "/api/chat",
        json={"message": "What was the quarterly revenue?"},
    )

    assert chat_response.status_code == 200
    payload = chat_response.json()
    assert payload["answer"] == "Grounded answer from cached folder content."
    assert payload["citations"][0]["file_name"] == "file-chat.txt"
    assert payload["citations"][0]["source_id"] == "source_1"


def test_chat_endpoint_maps_direct_answer_urls_back_to_citations(
    authenticated_client: TestClient,
    monkeypatch,
) -> None:
    import app.api.ingest as ingest_module

    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "get_folder_name",
        lambda self, folder_id: "URL Citation Folder",
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "list_supported_files",
        lambda self, folder_id: [fake_drive_file("file-url")],
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "download_and_parse",
        lambda self, folder_id, file: fake_document(file, "The roadmap mentions stablecoins."),
    )
    patch_openai(monkeypatch)
    FakeOpenAI.tool_output_answer_text = (
        "The answer is in "
        "[file-url.txt](https://drive.google.com/file/d/file-url/view)."
    )

    ingest_response = authenticated_client.post(
        "/api/ingest",
        json={"folder_url": "https://drive.google.com/drive/folders/folder-abc"},
    )
    assert ingest_response.status_code == 202

    chat_response = authenticated_client.post(
        "/api/chat",
        json={"message": "Where is the roadmap mentioned?"},
    )

    assert chat_response.status_code == 200
    payload = chat_response.json()
    assert payload["answer"] == "The answer is in [file-url.txt](https://drive.google.com/file/d/file-url/view)."
    assert payload["citations"][0]["file_id"] == "file-url"
    assert payload["citations"][0]["source_id"] == "source_1"


def test_chat_stream_emits_tool_activity_and_completion(
    authenticated_client: TestClient,
    monkeypatch,
) -> None:
    import app.api.ingest as ingest_module

    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "get_folder_name",
        lambda self, folder_id: "Chat Stream Folder",
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "list_supported_files",
        lambda self, folder_id: [fake_drive_file("file-chat-stream")],
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "download_and_parse",
        lambda self, folder_id, file: fake_document(file, "Quarterly revenue was $2M."),
    )
    patch_openai(monkeypatch)

    ingest_response = authenticated_client.post(
        "/api/ingest",
        json={"folder_url": "https://drive.google.com/drive/folders/folder-abc"},
    )
    assert ingest_response.status_code == 202

    chat_response = authenticated_client.post(
        "/api/chat/stream",
        json={"message": "What was the quarterly revenue?"},
    )

    assert chat_response.status_code == 200
    assert "event: tool_call_started" in chat_response.text
    assert "event: citations_updated" in chat_response.text
    assert "event: message_completed" in chat_response.text
    assert "event: chat_failed" not in chat_response.text


def test_chat_second_turn_reuses_conversation_without_mutually_exclusive_state(
    authenticated_client: TestClient,
    monkeypatch,
) -> None:
    import app.api.ingest as ingest_module

    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "get_folder_name",
        lambda self, folder_id: "Followup Folder",
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "list_supported_files",
        lambda self, folder_id: [fake_drive_file("file-followup")],
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "download_and_parse",
        lambda self, folder_id, file: fake_document(file, "Quarterly revenue was $2M."),
    )
    patch_openai(monkeypatch)

    ingest_response = authenticated_client.post(
        "/api/ingest",
        json={"folder_url": "https://drive.google.com/drive/folders/folder-abc"},
    )
    assert ingest_response.status_code == 202

    first_response = authenticated_client.post(
        "/api/chat",
        json={"message": "What was the quarterly revenue?"},
    )
    assert first_response.status_code == 200

    second_response = authenticated_client.post(
        "/api/chat",
        json={"message": "What files are in the folder?"},
    )
    assert second_response.status_code == 200
    assert second_response.json()["answer"] == "Grounded answer from cached folder content."


def test_chat_recovers_from_stale_openai_conversation(
    authenticated_client: TestClient,
    monkeypatch,
) -> None:
    import app.api.ingest as ingest_module
    from app.core.config import get_settings
    from app.services.conversation_store import get_conversation_store

    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "get_folder_name",
        lambda self, folder_id: "Recovery Folder",
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "list_supported_files",
        lambda self, folder_id: [fake_drive_file("file-recovery")],
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "download_and_parse",
        lambda self, folder_id, file: fake_document(file, "Quarterly revenue was $2M."),
    )
    patch_openai(monkeypatch)

    ingest_response = authenticated_client.post(
        "/api/ingest",
        json={"folder_url": "https://drive.google.com/drive/folders/folder-abc"},
    )
    assert ingest_response.status_code == 202

    conversation_store = get_conversation_store(get_settings())
    conversation_store.upsert_folder_conversation(
        FolderConversationRecord(
            owner_google_id="google-user-123",
            folder_id="folder-abc",
            conversation_id="conv-stale",
            last_response_id="resp-stale",
        )
    )
    # Next request uses previous_response_id (follow-up), so poison that to simulate stale state.
    FakeOpenAI.poison_previous_response_ids = {"resp-stale"}

    chat_response = authenticated_client.post(
        "/api/chat",
        json={"message": "What was the quarterly revenue?"},
    )

    assert chat_response.status_code == 200
    assert chat_response.json()["answer"] == "Grounded answer from cached folder content."
    stored_conversation = conversation_store.get_folder_conversation("google-user-123", "folder-abc")
    assert stored_conversation is not None
    assert stored_conversation.conversation_id != "conv-stale"


def test_delete_user_data_clears_indexed_files(
    authenticated_client: TestClient,
    monkeypatch,
) -> None:
    import app.api.ingest as ingest_module

    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "get_folder_name",
        lambda self, folder_id: "Delete Folder",
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "list_supported_files",
        lambda self, folder_id: [fake_drive_file("file-delete")],
    )
    monkeypatch.setattr(
        ingest_module.GoogleDriveService,
        "download_and_parse",
        lambda self, folder_id, file: fake_document(file, "Delete me"),
    )
    patch_openai(monkeypatch)

    ingest_response = authenticated_client.post(
        "/api/ingest",
        json={"folder_url": "https://drive.google.com/drive/folders/folder-abc"},
    )
    assert ingest_response.status_code == 202

    delete_response = authenticated_client.delete("/api/user/data")
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"

    session_response = authenticated_client.get("/api/session")
    assert session_response.status_code == 200
    assert session_response.json()["files"] == []
