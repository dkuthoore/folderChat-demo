from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import cast

from app.models.documents import SyncSummary
from app.models.jobs import IngestionJobRecord, utc_now_iso


class LocalJobStore:
    def __init__(self, storage_dir: Path) -> None:
        self.jobs_dir = storage_dir / "_jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def create_job(
        self,
        owner_google_id: str,
        folder_url: str,
        folder_id: str,
        folder_name: str,
    ) -> IngestionJobRecord:
        job = IngestionJobRecord(
            id=str(uuid.uuid4()),
            owner_google_id=owner_google_id,
            folder_url=folder_url,
            folder_id=folder_id,
            folder_name=folder_name,
        )
        self._write_job(job)
        return job

    def get_job(self, owner_google_id: str, job_id: str) -> IngestionJobRecord | None:
        path = self._job_path(owner_google_id, job_id)
        if not path.exists():
            return None
        return cast(
            IngestionJobRecord,
            IngestionJobRecord.model_validate_json(path.read_text(encoding="utf-8")),
        )

    def update_job(
        self,
        owner_google_id: str,
        job_id: str,
        *,
        status: str | None = None,
        progress_percentage: int | None = None,
        current_step_message: str | None = None,
        error_message: str | None = None,
        sync_summary: SyncSummary | None = None,
    ) -> IngestionJobRecord:
        with self._lock:
            job = self.get_job(owner_google_id, job_id)
            if job is None:
                raise ValueError(f"Unknown job_id: {job_id}")

            if status is not None:
                job.status = status  # type: ignore[assignment]
            if progress_percentage is not None:
                job.progress_percentage = progress_percentage
            if current_step_message is not None:
                job.current_step_message = current_step_message
            if error_message is not None:
                job.error_message = error_message
            if sync_summary is not None:
                job.sync_summary = sync_summary

            job.updated_at = utc_now_iso()
            job.version += 1
            self._write_job(job)
            return job

    def _job_path(self, owner_google_id: str, job_id: str) -> Path:
        return self.jobs_dir / owner_google_id / f"{job_id}.json"

    def _write_job(self, job: IngestionJobRecord) -> None:
        path = self._job_path(job.owner_google_id, job.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(job.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        temp_path.replace(path)
