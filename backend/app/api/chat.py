from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.rate_limit import check_chat_rate_limit
from app.core.session import get_session_user
from app.models.documents import DriveFileMetadata
from app.schemas.chat import (
    ChatRequest,
    ChatResetResponse,
    ChatResponse,
)
from app.services.chat_agent import ChatAgentService
from app.services.conversation_store import get_conversation_store
from app.services.ingestion import get_storage_backend
from app.services.retrieval_service import RetrievalService
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api", tags=["chat"])

FILE_SUGGESTIONS_LIMIT = 20


def _file_matches_query(file: DriveFileMetadata, q: str) -> bool:
    if not q:
        return True
    q_lower = q.casefold()
    name_lower = file.name.casefold()
    if q_lower in name_lower:
        return True
    path_lower = (file.folder_path or "").casefold()
    if path_lower and q_lower in path_lower:
        return True
    full_path = f"{path_lower}/{name_lower}".strip("/") if path_lower else name_lower
    return q_lower in full_path


def _build_chat_agent(settings: Settings) -> ChatAgentService:
    storage_backend = get_storage_backend(settings)
    return ChatAgentService(
        settings=settings,
        retrieval_service=RetrievalService(settings, storage_backend),
        conversation_store=get_conversation_store(settings),
    )


@router.get("/chat/files")
async def get_chat_file_suggestions(
    request: Request,
    q: str | None = Query(default=None, alias="q"),
    settings: Settings = Depends(get_settings),
) -> list[DriveFileMetadata]:
    """Return indexed files for @-mentions, optionally filtered by query."""
    user = get_session_user(request)
    storage_backend = get_storage_backend(settings)
    active_folder = storage_backend.get_active_folder(user["google_id"])
    if not active_folder:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ingest a Google Drive folder before selecting files.",
        )
    files = storage_backend.get_folder_files(user["google_id"], active_folder.folder_id)
    query = (q or "").strip()
    if query:
        files = [f for f in files if _file_matches_query(f, query)]
    # Sort by folder_path then name
    files.sort(key=lambda f: ((f.folder_path or ""), f.name))
    return files[:FILE_SUGGESTIONS_LIMIT]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    user = get_session_user(request)
    check_chat_rate_limit(user["google_id"])
    storage_backend = get_storage_backend(settings)
    active_folder = storage_backend.get_active_folder(user["google_id"])
    if not active_folder:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ingest a Google Drive folder before starting a chat.",
        )

    service = _build_chat_agent(settings)
    return service.answer_question(
        owner_google_id=user["google_id"],
        folder_id=active_folder.folder_id,
        folder_name=active_folder.folder_name,
        message=payload.message,
        selected_files=payload.selected_files,
    )


@router.post("/chat/stream")
async def stream_chat(
    payload: ChatRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    user = get_session_user(request)
    check_chat_rate_limit(user["google_id"])
    storage_backend = get_storage_backend(settings)
    active_folder = storage_backend.get_active_folder(user["google_id"])
    if not active_folder:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ingest a Google Drive folder before starting a chat.",
        )

    service = _build_chat_agent(settings)

    def event_generator():
        for event in service.stream_answer(
            owner_google_id=user["google_id"],
            folder_id=active_folder.folder_id,
            folder_name=active_folder.folder_name,
            message=payload.message,
            selected_files=payload.selected_files,
        ):
            serialized_event = event.model_dump_json()
            yield f"event: {event.type}\ndata: {serialized_event}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/chat/reset", response_model=ChatResetResponse)
async def reset_chat_context(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ChatResetResponse:
    user = get_session_user(request)
    storage_backend = get_storage_backend(settings)
    active_folder = storage_backend.get_active_folder(user["google_id"])
    if active_folder:
        _build_chat_agent(settings).reset_folder_conversation(
            user["google_id"],
            active_folder.folder_id,
        )
    storage_backend.clear_active_folder(user["google_id"])
    return ChatResetResponse(status="reset")
