from __future__ import annotations

import io
import re
from pathlib import Path
from typing import cast

from app.models.documents import DriveFileMetadata, ParsedDocument, SupportedDriveType
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pypdf import PdfReader

FOLDER_ID_PATTERN = re.compile(r"/folders/([a-zA-Z0-9_-]+)")

GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDE_MIME = "application/vnd.google-apps.presentation"
GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"
PDF_MIME = "application/pdf"


class GoogleDriveService:
    def __init__(self, credentials: Credentials, uploads_dir: Path) -> None:
        self.credentials = credentials
        self.uploads_dir = uploads_dir
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.drive = build(
            "drive", "v3", credentials=credentials, cache_discovery=False
        )

    @staticmethod
    def parse_folder_id(folder_url: str) -> str:
        match = FOLDER_ID_PATTERN.search(folder_url)
        if not match:
            raise ValueError(
                "Could not extract a Google Drive folder ID from the provided URL."
            )
        return match.group(1)

    def list_supported_files(self, folder_id: str) -> list[DriveFileMetadata]:
        """List supported files recursively, including files in subfolders."""
        return self._list_supported_files_recursive(
            root_folder_id=folder_id,
            current_folder_id=folder_id,
            path_components=[],
        )

    def _list_supported_files_recursive(
        self,
        *,
        root_folder_id: str,
        current_folder_id: str,
        path_components: list[str],
    ) -> list[DriveFileMetadata]:
        supported_files: list[DriveFileMetadata] = []
        page_token: str | None = None

        while True:
            query = f"'{current_folder_id}' in parents and trashed = false"
            list_kwargs: dict = {
                "q": query,
                "fields": "nextPageToken,files(id,name,mimeType,webViewLink,modifiedTime)",
                "includeItemsFromAllDrives": True,
                "supportsAllDrives": True,
                "pageSize": 1000,
            }
            if page_token:
                list_kwargs["pageToken"] = page_token
            request = self.drive.files().list(**list_kwargs)
            response = request.execute()

            for item in response.get("files", []):
                mime_type = item.get("mimeType", "")
                if mime_type == GOOGLE_FOLDER_MIME:
                    subfolder_name = self.get_folder_name(item["id"])
                    subfolder_path = path_components + [subfolder_name]
                    subfolder_files = self._list_supported_files_recursive(
                        root_folder_id=root_folder_id,
                        current_folder_id=item["id"],
                        path_components=subfolder_path,
                    )
                    supported_files.extend(subfolder_files)
                    continue

                source_type = self._map_source_type(mime_type)
                if not source_type:
                    continue
                folder_path = "/".join(path_components) if path_components else ""
                supported_files.append(
                    DriveFileMetadata(
                        file_id=item["id"],
                        name=item["name"],
                        mime_type=mime_type,
                        web_view_link=item.get("webViewLink", ""),
                        source_type=source_type,
                        modified_time=item.get("modifiedTime", ""),
                        folder_ids=[root_folder_id],
                        folder_path=folder_path,
                    )
                )

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return supported_files

    def get_folder_name(self, folder_id: str) -> str:
        response = (
            self.drive.files()
            .get(
                fileId=folder_id,
                fields="id,name",
                supportsAllDrives=True,
            )
            .execute()
        )
        return cast(str, response.get("name", folder_id))

    def download_and_parse(
        self, folder_id: str, file: DriveFileMetadata
    ) -> ParsedDocument:
        folder_dir = self.uploads_dir / folder_id
        folder_dir.mkdir(parents=True, exist_ok=True)

        if file.source_type == "document":
            local_path = folder_dir / f"{file.file_id}.txt"
            content = self._export_text(file.file_id, "text/plain", local_path)
            return self._parsed_document(file, content, local_path)

        if file.source_type == "spreadsheet":
            local_path = folder_dir / f"{file.file_id}.csv"
            content = self._export_text(file.file_id, "text/csv", local_path)
            return self._parsed_document(file, content, local_path)

        if file.source_type == "presentation":
            local_path = folder_dir / f"{file.file_id}.pdf"
            self._export_binary(file.file_id, "application/pdf", local_path)
            content = self._read_pdf_text(local_path)
            return self._parsed_document(file, content, local_path)

        if file.source_type == "pdf":
            local_path = folder_dir / f"{file.file_id}.pdf"
            self._download_binary(file.file_id, local_path)
            content = self._read_pdf_text(local_path)
            return self._parsed_document(file, content, local_path)

        raise ValueError(f"Unsupported file type: {file.mime_type}")

    def _parsed_document(
        self,
        file: DriveFileMetadata,
        text: str,
        local_path: Path,
    ) -> ParsedDocument:
        return ParsedDocument(
            file_id=file.file_id,
            name=file.name,
            mime_type=file.mime_type,
            web_view_link=file.web_view_link,
            source_type=file.source_type,
            modified_time=file.modified_time,
            text=text,
            local_path=str(local_path),
            folder_path=file.folder_path or "",
        )

    def _export_text(self, file_id: str, mime_type: str, output_path: Path) -> str:
        request = self.drive.files().export_media(fileId=file_id, mimeType=mime_type)
        text = self._download_request_bytes(request).decode("utf-8", errors="ignore")
        output_path.write_text(text, encoding="utf-8")
        return text

    def _export_binary(self, file_id: str, mime_type: str, output_path: Path) -> None:
        request = self.drive.files().export_media(fileId=file_id, mimeType=mime_type)
        output_path.write_bytes(self._download_request_bytes(request))

    def _download_binary(self, file_id: str, output_path: Path) -> None:
        request = self.drive.files().get_media(fileId=file_id)
        output_path.write_bytes(self._download_request_bytes(request))

    def _download_request_bytes(self, request) -> bytes:
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()

    def _read_pdf_text(self, path: Path) -> str:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages).strip()

    def _map_source_type(self, mime_type: str) -> SupportedDriveType | None:
        mapping: dict[str, SupportedDriveType] = {
            GOOGLE_DOC_MIME: "document",
            GOOGLE_SHEET_MIME: "spreadsheet",
            GOOGLE_SLIDE_MIME: "presentation",
            PDF_MIME: "pdf",
        }
        return cast(SupportedDriveType | None, mapping.get(mime_type))
