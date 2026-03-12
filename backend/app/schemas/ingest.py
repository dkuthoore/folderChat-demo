from pydantic import BaseModel, HttpUrl

from app.models.documents import SyncSummary


class IngestRequest(BaseModel):
    folder_url: HttpUrl
    check_first: bool = True


class IngestAlreadySyncedResponse(BaseModel):
    already_synced: bool = True


class IngestAcceptedResponse(BaseModel):
    status: str
    job_id: str
    folder_id: str
    folder_name: str
    folder_url: HttpUrl


class IngestionJobEvent(BaseModel):
    job_id: str
    status: str
    progress_percentage: int
    current_step_message: str
    folder_id: str
    folder_name: str
    folder_url: HttpUrl
    sync_summary: SyncSummary | None = None
    error_message: str | None = None
