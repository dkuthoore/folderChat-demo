from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from typing import Any

from openai import OpenAI

from app.core.config import Settings
from app.models.conversation import FolderConversationRecord
from app.schemas.chat import (
    AssistantDeltaEvent,
    ChatFailedEvent,
    ChatResponse,
    Citation,
    CitationsUpdatedEvent,
    MessageCompletedEvent,
    SelectedFile,
    ToolCallCompletedEvent,
    ToolCallStartedEvent,
)
from app.services.conversation_store import ConversationStore
from app.services.retrieval_service import RetrievalService

DRIVE_URL_PATTERN = re.compile(r"https?://[^\s)\]]+")
SOURCE_ID_PATTERN = re.compile(r"\[\s*(source_\d+)\s*\]|\b(source_\d+)\b")
SOURCE_TOKEN_PATTERN = re.compile(r"\[\s*source_\d+\s*\]|\bsource_\d+\b")
logger = logging.getLogger("uvicorn.error")


class ChatAgentService:
    def __init__(
        self,
        *,
        settings: Settings,
        retrieval_service: RetrievalService,
        conversation_store: ConversationStore,
    ) -> None:
        self.settings = settings
        self.retrieval_service = retrieval_service
        self.conversation_store = conversation_store
        self.openai = OpenAI(api_key=settings.openai_api_key)

    def answer_question(
        self,
        *,
        owner_google_id: str,
        folder_id: str,
        folder_name: str,
        message: str,
        selected_files: list[SelectedFile] | None = None,
    ) -> ChatResponse:
        final_response: ChatResponse | None = None
        for event in self.stream_answer(
            owner_google_id=owner_google_id,
            folder_id=folder_id,
            folder_name=folder_name,
            message=message,
            selected_files=selected_files,
        ):
            if isinstance(event, MessageCompletedEvent):
                final_response = ChatResponse(answer=event.answer, citations=event.citations)
            if isinstance(event, ChatFailedEvent):
                raise RuntimeError(event.error_message)

        if final_response is None:
            raise RuntimeError("Chat did not produce a final response.")
        return final_response

    def stream_answer(
        self,
        *,
        owner_google_id: str,
        folder_id: str,
        folder_name: str,
        message: str,
        selected_files: list[SelectedFile] | None = None,
    ) -> Iterator[
        AssistantDeltaEvent
        | ToolCallStartedEvent
        | ToolCallCompletedEvent
        | CitationsUpdatedEvent
        | MessageCompletedEvent
        | ChatFailedEvent
    ]:
        for conversation_attempt in range(2):
            conversation = self._get_or_create_conversation(owner_google_id, folder_id)
            source_registry: dict[str, Citation] = {}
            next_source_number = 1
            pending_input: str | list[dict[str, Any]] = self._compose_initial_user_input(
                message=message,
                selected_files=selected_files,
            )
            tool_parent_response_id: str | None = None

            try:
                while True:
                    response = None
                    stream_kwargs: dict[str, Any] = {
                        "model": self.settings.openai_chat_model,
                        "instructions": self._instructions(folder_name, selected_files),
                        "input": pending_input,
                        "tools": self._tool_definitions(),
                        "parallel_tool_calls": True,
                        "max_tool_calls": 20,
                        "store": True,
                    }
                    if tool_parent_response_id:
                        stream_kwargs["previous_response_id"] = tool_parent_response_id
                    elif conversation.last_response_id:
                        # Continue from last response so the API has full context (including
                        # tool outputs). Using conversation_id here would make the API see
                        # the conversation thread ending in an unresolved tool call and
                        # return "No tool output found".
                        stream_kwargs["previous_response_id"] = conversation.last_response_id
                    else:
                        stream_kwargs["conversation"] = conversation.conversation_id

                    logger.info(
                        "chat_agent.llm_request owner=%s folder=%s conversation=%s previous_response_id=%s input=%s",
                        owner_google_id,
                        folder_id,
                        stream_kwargs.get("conversation"),
                        stream_kwargs.get("previous_response_id"),
                        self._summarize_input_for_log(pending_input),
                    )

                    with self.openai.responses.stream(**stream_kwargs) as stream:
                        for event in stream:
                            if getattr(event, "type", None) == "response.output_text.delta":
                                delta = getattr(event, "delta", "")
                                if delta:
                                    yield AssistantDeltaEvent(delta=delta)
                        response = stream.get_final_response()

                    logger.info(
                        "chat_agent.llm_response owner=%s folder=%s response_id=%s output=%s output_text=%s",
                        owner_google_id,
                        folder_id,
                        getattr(response, "id", None),
                        self._summarize_response_for_log(response),
                        self._truncate(getattr(response, "output_text", "") or ""),
                    )

                    conversation.last_response_id = getattr(response, "id", None)
                    self.conversation_store.upsert_folder_conversation(conversation)

                    tool_calls = self._extract_tool_calls(response)
                    if not tool_calls:
                        raw_answer = getattr(response, "output_text", "") or ""
                        answer = self._extract_output_text(response)
                        citations = self._citations_for_answer(
                            answer=raw_answer,
                            owner_google_id=owner_google_id,
                            folder_id=folder_id,
                            source_registry=source_registry,
                        )
                        if citations:
                            yield CitationsUpdatedEvent(citations=citations)
                        logger.info(
                            "chat_agent.final_answer owner=%s folder=%s response_id=%s citations=%s answer=%s",
                            owner_google_id,
                            folder_id,
                            getattr(response, "id", None),
                            [citation.source_id for citation in citations],
                            self._truncate(answer),
                        )
                        yield MessageCompletedEvent(answer=answer, citations=citations)
                        return

                    tool_parent_response_id = getattr(response, "id", None)
                    tool_outputs: list[dict[str, Any]] = []
                    for tool_call in tool_calls:
                        tool_name = tool_call["name"]
                        tool_call_id = tool_call["call_id"]
                        arguments = tool_call["arguments"]
                        yield ToolCallStartedEvent(
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            summary=self._tool_summary(tool_name, arguments),
                            arguments=arguments,
                        )
                        logger.info(
                            "chat_agent.tool_call owner=%s folder=%s response_id=%s call_id=%s tool=%s args=%s",
                            owner_google_id,
                            folder_id,
                            tool_parent_response_id,
                            tool_call_id,
                            tool_name,
                            self._truncate(json.dumps(arguments, sort_keys=True)),
                        )
                        tool_result, new_citations = self._execute_tool(
                            owner_google_id=owner_google_id,
                            folder_id=folder_id,
                            tool_name=tool_name,
                            arguments=arguments,
                            source_offset=next_source_number - 1,
                        )
                        for citation in new_citations:
                            source_registry[citation.source_id] = citation
                        next_source_number += len(new_citations)
                        yield ToolCallCompletedEvent(
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            summary=self._tool_result_summary(tool_name, new_citations),
                        )
                        if new_citations:
                            yield CitationsUpdatedEvent(
                                citations=list(source_registry.values())
                            )
                        tool_outputs.append(
                            {
                                "type": "function_call_output",
                                "call_id": tool_call_id,
                                "output": json.dumps(tool_result),
                            }
                        )
                        logger.info(
                            "chat_agent.tool_output owner=%s folder=%s parent_response_id=%s call_id=%s payload=%s",
                            owner_google_id,
                            folder_id,
                            tool_parent_response_id,
                            tool_call_id,
                            self._truncate(json.dumps(tool_result, sort_keys=True)),
                        )
                    pending_input = tool_outputs

            except Exception as exc:
                if (
                    conversation_attempt == 0
                    and tool_parent_response_id is None
                    and self._is_missing_tool_output_error(exc)
                ):
                    logger.warning(
                        "chat_agent.reset_stale_conversation owner=%s folder=%s conversation=%s reason=%s",
                        owner_google_id,
                        folder_id,
                        conversation.conversation_id,
                        str(exc),
                    )
                    self.reset_folder_conversation(owner_google_id, folder_id)
                    continue

                logger.exception(
                    "chat_agent.failed owner=%s folder=%s conversation=%s previous_response_id=%s input=%s",
                    owner_google_id,
                    folder_id,
                    conversation.conversation_id,
                    tool_parent_response_id,
                    self._summarize_input_for_log(pending_input),
                )
                yield ChatFailedEvent(error_message=str(exc))
                return

    def reset_folder_conversation(self, owner_google_id: str, folder_id: str) -> None:
        self.conversation_store.delete_folder_conversation(owner_google_id, folder_id)

    def _get_or_create_conversation(
        self,
        owner_google_id: str,
        folder_id: str,
    ) -> FolderConversationRecord:
        record = self.conversation_store.get_folder_conversation(owner_google_id, folder_id)
        if record is not None:
            return record

        conversation = self.openai.conversations.create(
            metadata={
                "owner_google_id": owner_google_id,
                "folder_id": folder_id,
            }
        )
        record = FolderConversationRecord(
            owner_google_id=owner_google_id,
            folder_id=folder_id,
            conversation_id=conversation.id,
        )
        return self.conversation_store.upsert_folder_conversation(record)

    def _instructions(self, folder_name: str, selected_files: list[SelectedFile] | None = None) -> str:
        selected_files_instructions = self._selected_files_instructions(selected_files)
        return (
            "You are a grounded research assistant for a Google Drive folder. "
            f"The active folder is '{folder_name}'. "
            "Use the available tools before answering any question about the folder contents. "
            "list_files: use to see all files in the folder and subfolders (names and paths only; no file content). "
            "search_folder: use to semantically search for keywords or content within the folder's files and subfolders' files; returns ranked excerpts. "
            "read_file: use to actually read the full text of specific files; this tool requires file_id for exact matching. "
            "For broad or exploratory questions, use search_folder (and list_files if you need the file list). "
            "When the user names specific files or asks to read them, use read_file with file_id from selected files or prior tool outputs. "
            f"{selected_files_instructions}"
            "When listing files for the user, group them by folder_path (root vs subfolders) to match the sidebar. "
            "Always format every Drive URL as a markdown link: [link text](drive_url). Never output bare URLs or 'Drive link: https://...'. Use the exact drive_url from the tool payload. Example: [Job Description](https://docs.google.com/document/d/abc123/edit). "
            "Always cite the files that you are referencing in your response."
            "If the tools do not provide enough evidence, say that you do not know based on the indexed files."
        )

    def _tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "search_folder",
                "description": (
                    "Semantically search for keywords or content within the folder's files and subfolders' files. "
                    "Returns ranked excerpts; use for finding what files say about a topic. "
                    "Search the whole folder by default; use file_name only when limiting to one file."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "minimum": 1, "maximum": 8},
                        "file_name": {
                            "type": "string",
                            "description": "Optional file name filter. Leave unset for broad folder search.",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "list_files",
                "description": (
                    "See all files in the folder and subfolders (names and paths only; no file content). "
                    "Results include folder_path for each file (empty = root, non-empty = subfolder). "
                    "Group files by folder when presenting the list to the user."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "read_file",
                "description": (
                    "Actually read the full text content of a specific indexed file. "
                    "Use to answer questions about specific files. "
                    "This tool requires file_id from selected-file context or prior tool outputs."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_name": {
                            "type": "string",
                            "description": "Indexed file name to read.",
                        },
                        "file_id": {
                            "type": "string",
                            "description": "Required file ID for exact matching.",
                        },
                    },
                    "required": ["file_id"],
                    "additionalProperties": False,
                },
            },
        ]

    def _extract_tool_calls(self, response: Any) -> list[dict[str, Any]]:
        tool_calls: list[dict[str, Any]] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "function_call":
                continue
            try:
                arguments = json.loads(getattr(item, "arguments", "") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(
                {
                    "name": getattr(item, "name", ""),
                    "call_id": getattr(item, "call_id", ""),
                    "arguments": arguments,
                }
            )
        return tool_calls

    def _compose_initial_user_input(
        self,
        *,
        message: str,
        selected_files: list[SelectedFile] | None,
    ) -> str:
        if not selected_files:
            return message
        selected_lines = "\n".join(
            f"- {selected_file.file_name} (file_id: {selected_file.file_id})"
            for selected_file in selected_files
        )
        return (
            f"{message}\n\n"
            "Selected file context (authoritative):\n"
            f"{selected_lines}\n"
            "If you call read_file for one of these selected files, use the exact file_id shown above."
        )

    def _selected_files_instructions(self, selected_files: list[SelectedFile] | None) -> str:
        if not selected_files:
            return ""
        selected_lines = "; ".join(
            f"{selected_file.file_name} -> {selected_file.file_id}"
            for selected_file in selected_files
        )
        return (
            "When selected file context is provided, treat it as authoritative and prefer read_file with file_id "
            f"for those files. Selected files: {selected_lines}. "
        )

    def _extract_output_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", "") or ""
        cleaned_text = SOURCE_TOKEN_PATTERN.sub("", output_text)
        cleaned_text = re.sub(r"\s{2,}", " ", cleaned_text).strip()
        return cleaned_text or "I couldn't generate an answer."

    def _execute_tool(
        self,
        *,
        owner_google_id: str,
        folder_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        source_offset: int,
    ) -> tuple[dict[str, Any], list[Citation]]:
        if tool_name == "search_folder":
            result = self.retrieval_service.search_folder(
                owner_google_id=owner_google_id,
                folder_id=folder_id,
                query=str(arguments.get("query", "")).strip(),
                top_k=int(arguments.get("top_k", 5) or 5),
                file_name=str(arguments["file_name"]).strip() if arguments.get("file_name") else None,
                source_offset=source_offset,
            )
            return result.as_tool_payload(), result.citations

        if tool_name == "list_files":
            result = self.retrieval_service.list_files(
                owner_google_id=owner_google_id,
                folder_id=folder_id,
                source_offset=source_offset,
            )
            return result.as_tool_payload(), result.citations

        if tool_name == "read_file":
            file_id = str(arguments.get("file_id", "")).strip()
            if not file_id:
                raise ValueError("read_file requires a non-empty file_id.")
            result = self.retrieval_service.read_file(
                owner_google_id=owner_google_id,
                folder_id=folder_id,
                file_name=str(arguments["file_name"]).strip() if arguments.get("file_name") else None,
                file_id=file_id,
                source_offset=source_offset,
            )
            return result.as_tool_payload(), [result.citation]

        raise ValueError(f"Unsupported tool call: {tool_name}")

    def _tool_summary(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if tool_name == "search_folder":
            query = str(arguments.get("query", "")).strip() or "folder contents"
            file_name = str(arguments.get("file_name", "")).strip()
            if file_name:
                return f"Searching {file_name} for '{query}'."
            return f"Searching the folder for '{query}'."
        if tool_name == "read_file":
            file_name = str(arguments.get("file_name", "")).strip()
            if file_name:
                return f"Reading {file_name}."
            return "Reading a specific file."
        return "Listing indexed files."

    def _tool_result_summary(self, tool_name: str, citations: list[Citation]) -> str:
        if tool_name == "search_folder":
            if not citations:
                return "No relevant sources found in indexed files."
            return f"Found {len(citations)} relevant source(s)."
        if tool_name == "read_file":
            return f"Read {len(citations)} file."
        return f"Listed {len(citations)} indexed file(s)."

    def _citations_for_answer(
        self,
        *,
        answer: str,
        owner_google_id: str,
        folder_id: str,
        source_registry: dict[str, Citation],
    ) -> list[Citation]:
        seen_urls: set[str] = set()
        citations: list[Citation] = []

        by_url: dict[str, Citation] = {}
        for citation in source_registry.values():
            by_url[citation.drive_url] = citation

        seen_source_ids: set[str] = set()
        for bracketed_source_id, bare_source_id in SOURCE_ID_PATTERN.findall(answer):
            source_id = bracketed_source_id or bare_source_id
            if source_id in seen_source_ids:
                continue
            citation = source_registry.get(source_id)
            if citation is None:
                continue
            citations.append(citation)
            seen_source_ids.add(source_id)
            seen_urls.add(citation.drive_url)

        for indexed_file in self.retrieval_service.storage_backend.get_folder_files(
            owner_google_id, folder_id
        ):
            by_url.setdefault(
                indexed_file.web_view_link,
                Citation(
                    source_id=indexed_file.file_id,
                    file_id=indexed_file.file_id,
                    file_name=indexed_file.name,
                    drive_url=indexed_file.web_view_link,
                    chunk_excerpt="Referenced in assistant answer.",
                    chunk_index=None,
                    folder_path=indexed_file.folder_path or "",
                ),
            )

        for drive_url in DRIVE_URL_PATTERN.findall(answer):
            if drive_url in seen_urls:
                continue
            citation = by_url.get(drive_url)
            if citation is None:
                continue
            citations.append(citation)
            seen_urls.add(drive_url)
        return citations

    def _summarize_input_for_log(self, input_payload: str | list[dict[str, Any]]) -> str:
        if isinstance(input_payload, str):
            return self._truncate(input_payload)

        summarized_items: list[dict[str, str | None]] = []
        for item in input_payload:
            summarized_items.append(
                {
                    "type": str(item.get("type")),
                    "call_id": str(item.get("call_id")) if item.get("call_id") else None,
                    "output": self._truncate(str(item.get("output", ""))),
                }
            )
        return self._truncate(json.dumps(summarized_items, sort_keys=True))

    def _summarize_response_for_log(self, response: Any) -> str:
        summarized_items: list[dict[str, str | None]] = []
        for item in getattr(response, "output", []) or []:
            summarized_items.append(
                {
                    "type": getattr(item, "type", None),
                    "name": getattr(item, "name", None),
                    "call_id": getattr(item, "call_id", None),
                    "arguments": self._truncate(getattr(item, "arguments", "") or ""),
                }
            )
        return self._truncate(json.dumps(summarized_items, sort_keys=True))

    def _truncate(self, value: str, limit: int = 600) -> str:
        if len(value) <= limit:
            return value
        return f"{value[:limit]}...<truncated>"

    def _is_missing_tool_output_error(self, exc: Exception) -> bool:
        return "No tool output found for function call" in str(exc)
