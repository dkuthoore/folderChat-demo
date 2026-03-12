from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SelectedFile(BaseModel):
    file_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    selected_files: list[SelectedFile] = Field(default_factory=list)


class Citation(BaseModel):
    source_id: str
    file_id: str
    file_name: str
    drive_url: str
    chunk_excerpt: str
    chunk_index: int | None = None
    folder_path: str = ""


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)


class ChatResetResponse(BaseModel):
    status: Literal["reset"]


class AssistantDeltaEvent(BaseModel):
    type: Literal["assistant_delta"] = "assistant_delta"
    delta: str


class ToolCallStartedEvent(BaseModel):
    type: Literal["tool_call_started"] = "tool_call_started"
    tool_call_id: str
    tool_name: str
    summary: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallCompletedEvent(BaseModel):
    type: Literal["tool_call_completed"] = "tool_call_completed"
    tool_call_id: str
    tool_name: str
    summary: str


class CitationsUpdatedEvent(BaseModel):
    type: Literal["citations_updated"] = "citations_updated"
    citations: list[Citation] = Field(default_factory=list)


class MessageCompletedEvent(BaseModel):
    type: Literal["message_completed"] = "message_completed"
    answer: str
    citations: list[Citation] = Field(default_factory=list)


class ChatFailedEvent(BaseModel):
    type: Literal["chat_failed"] = "chat_failed"
    error_message: str
