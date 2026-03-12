from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.models.documents import SyncSummary

JobStatus = Literal["pending", "in_progress", "completed", "failed"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IngestionJobRecord(BaseModel):
    id: str
    owner_google_id: str
    folder_url: str
    folder_id: str
    folder_name: str
    status: JobStatus = "pending"
    progress_percentage: int = 0
    current_step_message: str = "Waiting to start ingestion."
    error_message: str | None = None
    sync_summary: SyncSummary | None = None
    updated_at: str = Field(default_factory=utc_now_iso)
    version: int = 0

