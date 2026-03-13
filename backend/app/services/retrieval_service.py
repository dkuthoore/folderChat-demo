from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.models.documents import ChunkRecord, DriveFileMetadata
from app.schemas.chat import Citation
from app.services.storage.base import StorageBackend
from openai import OpenAI  # type: ignore[attr-defined]

WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass
class SearchFolderResult:
    citations: list[Citation]
    used_literal_refinement: bool = False

    def as_tool_payload(self) -> dict[str, object]:
        return {
            "guidance": (
                "Results are ranked by semantic relevance after applying a minimum similarity threshold. "
                "When any excerpts literally mention the query text, the result set is narrowed to those direct mentions. "
                "Only mention files that are clearly supported by the excerpts below. "
                "If none of the excerpts clearly answer the question, say you do not know based on the indexed files."
            ),
            "literal_refinement_applied": self.used_literal_refinement,
            "results": [
                {
                    "source_id": citation.source_id,
                    "file_name": citation.file_name,
                    "drive_url": citation.drive_url,
                    "excerpt": citation.chunk_excerpt,
                    "chunk_index": citation.chunk_index,
                }
                for citation in self.citations
            ],
        }


@dataclass
class ListFilesResult:
    citations: list[Citation]

    def as_tool_payload(self) -> dict[str, object]:
        return {
            "files": [
                {
                    "source_id": citation.source_id,
                    "file_id": citation.file_id,
                    "file_name": citation.file_name,
                    "drive_url": citation.drive_url,
                    "excerpt": citation.chunk_excerpt,
                    "folder_path": citation.folder_path or "",
                }
                for citation in self.citations
            ],
            "guidance": (
                "Each file has a folder_path: empty string means root level; a path like 'JDS' means the file is in that subfolder. "
                "When listing files for the user, group them by folder_path and present subfolder names as headers (e.g. 'In JDS: ...') so the structure matches the sidebar."
            ),
        }


@dataclass
class ReadFileResult:
    citation: Citation
    content: str
    truncated: bool
    source_type: str

    def as_tool_payload(self) -> dict[str, object]:
        return {
            "file": {
                "source_id": self.citation.source_id,
                "file_id": self.citation.file_id,
                "file_name": self.citation.file_name,
                "drive_url": self.citation.drive_url,
                "excerpt": self.citation.chunk_excerpt,
                "source_type": self.source_type,
            },
            "content": self.content,
            "truncated": self.truncated,
            "guidance": (
                "This is the extracted text content for one indexed file. "
                "Use it when the user asks about a specific file or when search results are insufficient."
            ),
        }


class RetrievalService:
    def __init__(self, settings: Settings, storage_backend: StorageBackend) -> None:
        self.settings = settings
        self.storage_backend = storage_backend
        self.openai = OpenAI(api_key=settings.openai_api_key)

    def search_folder(
        self,
        *,
        owner_google_id: str,
        folder_id: str,
        query: str,
        top_k: int = 5,
        file_name: str | None = None,
        source_offset: int = 0,
    ) -> SearchFolderResult:
        query_embedding = self._embed_texts([query])[0]
        retrieved_chunks = self.storage_backend.query_chunks(
            owner_google_id,
            folder_id,
            query_embedding,
            top_k=top_k,
            file_name=file_name,
            min_similarity=self.settings.semantic_search_min_similarity,
        )
        refined_chunks = self._prefer_literal_query_mentions(retrieved_chunks, query)
        used_literal_refinement = bool(refined_chunks) and len(refined_chunks) != len(
            retrieved_chunks
        )
        citations = [
            Citation(
                source_id=f"source_{source_offset + index}",
                file_id=chunk.metadata.file_id,
                file_name=chunk.metadata.file_name,
                drive_url=chunk.metadata.drive_url,
                chunk_excerpt=self._build_excerpt(
                    chunk.metadata.text,
                    query=query,
                    prefer_query_window=used_literal_refinement,
                ),
                chunk_index=chunk.metadata.chunk_index,
            )
            for index, chunk in enumerate(refined_chunks, start=1)
        ]
        return SearchFolderResult(
            citations=citations,
            used_literal_refinement=used_literal_refinement,
        )

    def list_files(
        self,
        *,
        owner_google_id: str,
        folder_id: str,
        source_offset: int = 0,
    ) -> ListFilesResult:
        files = self.storage_backend.get_folder_files(owner_google_id, folder_id)
        citations = [
            Citation(
                source_id=f"source_{source_offset + index}",
                file_id=file.file_id,
                file_name=file.name,
                drive_url=file.web_view_link,
                chunk_excerpt="Indexed file available in the current folder.",
                chunk_index=None,
                folder_path=file.folder_path or "",
            )
            for index, file in enumerate(files, start=1)
        ]
        return ListFilesResult(citations=citations)

    def read_file(
        self,
        *,
        owner_google_id: str,
        folder_id: str,
        file_name: str | None = None,
        file_id: str | None = None,
        source_offset: int = 0,
        max_chars: int | None = None,
    ) -> ReadFileResult:
        file = self._resolve_file(
            owner_google_id=owner_google_id,
            folder_id=folder_id,
            file_name=file_name,
            file_id=file_id,
        )
        full_text = self._load_full_text(owner_google_id, file.file_id)
        if not full_text.strip():
            raise ValueError(f"No readable text is available for '{file.name}'.")

        limit = max_chars or self.settings.read_file_max_chars
        truncated = len(full_text) > limit
        visible_text = full_text[:limit] if truncated else full_text
        citation = Citation(
            source_id=f"source_{source_offset + 1}",
            file_id=file.file_id,
            file_name=file.name,
            drive_url=file.web_view_link,
            chunk_excerpt=self._build_excerpt(
                visible_text, query="", prefer_query_window=False
            ),
            chunk_index=None,
        )
        return ReadFileResult(
            citation=citation,
            content=visible_text,
            truncated=truncated,
            source_type=file.source_type,
        )

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self.openai.embeddings.create(
            model=self.settings.openai_embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def _prefer_literal_query_mentions(self, chunks, query: str):
        normalized_query = self._normalize_for_match(query)
        if not normalized_query:
            return chunks

        literal_matches = [
            chunk
            for chunk in chunks
            if normalized_query in self._normalize_for_match(chunk.metadata.text)
        ]
        return literal_matches or chunks

    def _normalize_for_match(self, value: str) -> str:
        return WHITESPACE_PATTERN.sub(" ", value.casefold()).strip().strip("\"'")

    def _resolve_file(
        self,
        *,
        owner_google_id: str,
        folder_id: str,
        file_name: str | None,
        file_id: str | None,
    ) -> DriveFileMetadata:
        files = self.storage_backend.get_folder_files(owner_google_id, folder_id)
        if file_id:
            for file in files:
                if file.file_id == file_id:
                    return file
            if not file_name or file_id.startswith("source_") is False:
                raise ValueError(
                    f"Could not find indexed file '{file_id}' in the active folder."
                )

        normalized_name = self._normalize_for_match(file_name or "")
        if not normalized_name:
            raise ValueError("read_file requires either file_id or file_name.")

        exact_matches = [
            file
            for file in files
            if self._normalize_for_match(file.name) == normalized_name
        ]
        if exact_matches:
            return exact_matches[0]

        partial_matches = [
            file
            for file in files
            if normalized_name in self._normalize_for_match(file.name)
        ]
        if len(partial_matches) == 1:
            return partial_matches[0]
        if len(partial_matches) > 1:
            raise ValueError(
                "Multiple indexed files matched that file_name. Use a more specific file name."
            )
        raise ValueError(
            f"Could not find indexed file '{file_name}' in the active folder."
        )

    def _load_full_text(self, owner_google_id: str, file_id: str) -> str:
        persisted_path = self._document_text_path(owner_google_id, file_id)
        if persisted_path.exists():
            return persisted_path.read_text(encoding="utf-8")
        return self._reconstruct_text_from_chunks(
            self.storage_backend.get_file_chunks(owner_google_id, file_id)
        )

    def _document_text_path(self, owner_google_id: str, file_id: str) -> Path:
        return (
            self.settings.storage_dir_path
            / owner_google_id
            / "texts"
            / f"{file_id}.txt"
        )

    def _reconstruct_text_from_chunks(self, chunks: list[ChunkRecord]) -> str:
        if not chunks:
            return ""
        merged = chunks[0].metadata.text
        for chunk in chunks[1:]:
            next_text = chunk.metadata.text
            overlap = self._suffix_prefix_overlap(merged, next_text)
            merged += next_text[overlap:]
        return merged

    def _suffix_prefix_overlap(
        self, left: str, right: str, min_overlap: int = 40
    ) -> int:
        max_overlap = min(len(left), len(right))
        for size in range(max_overlap, min_overlap - 1, -1):
            if left.endswith(right[:size]):
                return size
        return 0

    def _build_excerpt(
        self,
        text: str,
        *,
        query: str,
        prefer_query_window: bool,
        max_length: int = 400,
    ) -> str:
        if not prefer_query_window:
            return text[:max_length]

        normalized_query = self._normalize_for_match(query)
        if not normalized_query:
            return text[:max_length]

        match = re.search(re.escape(normalized_query), self._normalize_for_match(text))
        if match is None:
            return text[:max_length]

        raw_match = re.search(
            re.escape(query.strip().strip("\"'")), text, flags=re.IGNORECASE
        )
        if raw_match is None:
            return text[:max_length]

        half_window = max_length // 2
        start = max(raw_match.start() - half_window, 0)
        end = min(raw_match.end() + half_window, len(text))
        excerpt = text[start:end].strip()

        if start > 0:
            excerpt = f"...{excerpt}"
        if end < len(text):
            excerpt = f"{excerpt}..."
        return excerpt
