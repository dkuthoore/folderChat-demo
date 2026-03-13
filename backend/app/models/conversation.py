from __future__ import annotations

from app.models.session import utc_now_iso
from pydantic import BaseModel, Field


class FolderConversationRecord(BaseModel):
    owner_google_id: str
    folder_id: str
    conversation_id: str
    last_response_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
