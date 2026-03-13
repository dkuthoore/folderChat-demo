from __future__ import annotations

import asyncio
import logging
from typing import cast

from app.core.config import Settings, get_settings
from app.core.session import (
    get_google_credentials,
    get_server_session,
    get_session_user,
)
from app.models.documents import ActiveFolderRecord, SyncSummary
from app.models.jobs import IngestionJobRecord
from app.schemas.ingest import (
    IngestAcceptedResponse,
    IngestAlreadySyncedResponse,
    IngestionJobEvent,
    IngestRequest,
)
from app.services.google_drive import GoogleDriveService
from app.services.ingestion import IngestionService, get_storage_backend
from app.services.job_store import LocalJobStore
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError
from pydantic import HttpUrl

router = APIRouter(prefix="/api", tags=["ingest"])
logger = logging.getLogger(__name__)

FOLDER_NOT_FOUND_OR_ACCESS_DENIED = (
    "The Google Drive folder could not be found or you do not have access to it. "
    "Make sure the URL is correct and that you're signed in with the right Google account."
)
DRIVE_UNAVAILABLE = (
    "Google Drive returned an error while accessing this folder. Try again later."
)
INGESTION_UNEXPECTED_ERROR = (
    "An unexpected error occurred during folder ingestion. Try again later."
)


def _build_credentials(credentials_payload: dict) -> Credentials:
    return Credentials(
        token=credentials_payload["token"],
        refresh_token=credentials_payload.get("refresh_token"),
        token_uri=credentials_payload["token_uri"],
        client_id=credentials_payload["client_id"],
        client_secret=credentials_payload["client_secret"],
        scopes=credentials_payload.get("scopes"),
    )


def _job_store(settings: Settings) -> LocalJobStore:
    return LocalJobStore(settings.storage_dir_path)


def _drive_error_message(exc: HttpError) -> str:
    """Map Google Drive API HttpError to a user-friendly message."""
    status_code = getattr(exc, "status_code", None) or (
        getattr(exc.resp, "status", None) if hasattr(exc, "resp") else None
    )
    if status_code in (403, 404):
        return FOLDER_NOT_FOUND_OR_ACCESS_DENIED
    return DRIVE_UNAVAILABLE


def _serialize_job_event(job: IngestionJobRecord) -> str:
    return cast(
        str,
        IngestionJobEvent(
            job_id=job.id,
            status=job.status,
            progress_percentage=job.progress_percentage,
            current_step_message=job.current_step_message,
            folder_id=job.folder_id,
            folder_name=job.folder_name,
            folder_url=HttpUrl(job.folder_url),
            sync_summary=job.sync_summary,
            error_message=job.error_message,
        ).model_dump_json(),
    )


def _process_drive_folder_job(
    *,
    settings: Settings,
    owner_google_id: str,
    credentials_payload: dict,
    folder_id: str,
    folder_name: str,
    job_id: str,
) -> None:
    job_store = _job_store(settings)
    job_store.update_job(
        owner_google_id,
        job_id,
        status="in_progress",
        progress_percentage=5,
        current_step_message=f"Preparing ingestion for {folder_name}.",
    )

    try:
        drive_service = GoogleDriveService(
            _build_credentials(credentials_payload),
            settings.uploads_dir_path / owner_google_id,
        )
        files = drive_service.list_supported_files(folder_id)
        if not files:
            job_store.update_job(
                owner_google_id,
                job_id,
                status="completed",
                progress_percentage=100,
                current_step_message="No supported Google Docs, Sheets, Slides, or PDFs were found in this folder.",
                sync_summary=SyncSummary(
                    total_files=0,
                    new_files=0,
                    skipped_files=0,
                    updated_files=0,
                ),
            )
            return

        def _progress_cb(progress: int, message: str) -> None:
            job_store.update_job(
                owner_google_id,
                job_id,
                status="in_progress",
                progress_percentage=progress,
                current_step_message=message,
            )

        ingestion_service = IngestionService(settings, get_storage_backend(settings))
        result = ingestion_service.ingest_folder(
            owner_google_id=owner_google_id,
            folder_id=folder_id,
            files=files,
            download_document=lambda file: drive_service.download_and_parse(
                folder_id, file
            ),
            progress_callback=_progress_cb,
        )
        job_store.update_job(
            owner_google_id,
            job_id,
            status="completed",
            progress_percentage=100,
            current_step_message=f"Ingestion complete. Indexed {len(result.files)} file(s) from {folder_name}.",
            sync_summary=result.sync_summary,
        )
    except HttpError as exc:
        job_store.update_job(
            owner_google_id,
            job_id,
            status="failed",
            progress_percentage=100,
            current_step_message="Folder ingestion failed.",
            error_message=_drive_error_message(exc),
        )
    except Exception as exc:
        logger.exception(
            "ingest.failed owner=%s job_id=%s folder_id=%s",
            owner_google_id,
            job_id,
            folder_id,
        )
        job_store.update_job(
            owner_google_id,
            job_id,
            status="failed",
            progress_percentage=100,
            current_step_message="Folder ingestion failed.",
            error_message=INGESTION_UNEXPECTED_ERROR,
        )


@router.post("/ingest")
async def ingest_folder(
    payload: IngestRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
):
    user = get_session_user(request)
    credentials = get_google_credentials(request)
    credentials_payload = get_server_session(request).credentials.model_dump(
        mode="json"
    )

    try:
        folder_id = GoogleDriveService.parse_folder_id(str(payload.folder_url))
        drive_service = GoogleDriveService(
            credentials,
            settings.uploads_dir_path / user["google_id"],
        )
        folder_name = drive_service.get_folder_name(folder_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except HttpError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_drive_error_message(exc),
        ) from exc

    storage_backend = get_storage_backend(settings)
    storage_backend.set_active_folder(
        ActiveFolderRecord(
            owner_google_id=user["google_id"],
            folder_id=folder_id,
            folder_name=folder_name,
            folder_url=str(payload.folder_url),
        )
    )

    if payload.check_first:
        try:
            files = drive_service.list_supported_files(folder_id)
        except HttpError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_drive_error_message(exc),
            ) from exc
        if files:
            ingestion_service = IngestionService(settings, storage_backend)
            new_count, skipped_count, updated_count = ingestion_service.sync_check(
                owner_google_id=user["google_id"],
                folder_id=folder_id,
                files=files,
            )
            if new_count == 0 and updated_count == 0 and len(files) > 0:
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=IngestAlreadySyncedResponse().model_dump(mode="json"),
                )

    job = _job_store(settings).create_job(
        owner_google_id=user["google_id"],
        folder_url=str(payload.folder_url),
        folder_id=folder_id,
        folder_name=folder_name,
    )
    background_tasks.add_task(
        _process_drive_folder_job,
        settings=settings,
        owner_google_id=user["google_id"],
        credentials_payload=credentials_payload,
        folder_id=folder_id,
        folder_name=folder_name,
        job_id=job.id,
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=IngestAcceptedResponse(
            status="accepted",
            job_id=job.id,
            folder_id=folder_id,
            folder_name=folder_name,
            folder_url=payload.folder_url,
        ).model_dump(mode="json"),
    )


@router.get("/jobs/{job_id}/stream")
async def stream_ingestion_job(
    job_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    user = get_session_user(request)
    job_store = _job_store(settings)
    job = job_store.get_job(user["google_id"], job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found."
        )

    async def event_generator():
        last_seen_version = -1
        while True:
            current_job = job_store.get_job(user["google_id"], job_id)
            if current_job is None:
                yield 'event: failed\ndata: {"detail":"Ingestion job was not found."}\n\n'
                break

            if current_job.version != last_seen_version:
                event_name = "progress"
                if current_job.status == "completed":
                    event_name = "complete"
                elif current_job.status == "failed":
                    event_name = "failed"

                yield f"event: {event_name}\ndata: {_serialize_job_event(current_job)}\n\n"
                last_seen_version = current_job.version

                if current_job.status in {"completed", "failed"}:
                    break

            await asyncio.sleep(0.35)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
