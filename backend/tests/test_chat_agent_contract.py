from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.core.config import Settings
from app.services.chat_agent import ChatAgentService


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        SESSION_SECRET="test-secret",
        SESSION_TTL_SECONDS=604800,
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


def _build_service(tmp_path: Path) -> ChatAgentService:
    return ChatAgentService(
        settings=_build_settings(tmp_path),
        retrieval_service=SimpleNamespace(),  # type: ignore[arg-type]
        conversation_store=SimpleNamespace(),  # type: ignore[arg-type]
    )


def test_read_file_tool_schema_requires_file_id(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    tools = service._tool_definitions()
    read_file_tool = next(tool for tool in tools if tool["name"] == "read_file")

    assert "file_id" in read_file_tool["parameters"]["required"]


def test_execute_tool_rejects_read_file_without_file_id(tmp_path: Path) -> None:
    service = _build_service(tmp_path)

    try:
        service._execute_tool(
            owner_google_id="user-1",
            folder_id="folder-1",
            tool_name="read_file",
            arguments={},
            source_offset=0,
        )
    except ValueError as exc:
        assert "requires a non-empty file_id" in str(exc)
    else:
        raise AssertionError("Expected read_file calls without file_id to fail.")
