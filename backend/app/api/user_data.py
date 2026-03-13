from __future__ import annotations

import shutil

from app.core.config import Settings, get_settings
from app.core.session import get_session_user
from app.services.conversation_store import get_conversation_store
from app.services.ingestion import get_storage_backend
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/api", tags=["user-data"])


@router.delete("/user/data")
async def clear_user_data(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    user = get_session_user(request)
    storage_backend = get_storage_backend(settings)
    storage_backend.clear_active_folder(user["google_id"])
    storage_backend.clear_user_data(user["google_id"])
    get_conversation_store(settings).delete_user_conversations(user["google_id"])

    uploads_dir = settings.uploads_dir_path / user["google_id"]
    if uploads_dir.exists():
        shutil.rmtree(uploads_dir)

    return {"status": "deleted"}
