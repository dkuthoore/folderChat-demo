export type SourceType = 'document' | 'spreadsheet' | 'presentation' | 'pdf'

export interface DriveFileMetadata {
  file_id: string
  name: string
  mime_type: string
  web_view_link: string
  source_type: SourceType
  modified_time: string
  folder_ids: string[]
  folder_path?: string
}

export interface IngestStage {
  label: string
  detail: string
}

export interface SyncDecision {
  file: DriveFileMetadata
  status: 'new' | 'skipped' | 'updated'
}

export interface SyncSummary {
  total_files: number
  new_files: number
  skipped_files: number
  updated_files: number
}

export interface IngestAcceptedResponse {
  status: string
  job_id: string
  folder_id: string
  folder_name: string
  folder_url: string
}

export interface IngestAlreadySyncedResponse {
  already_synced: true
}

export interface IngestionJobEvent {
  job_id: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  progress_percentage: number
  current_step_message: string
  folder_id: string
  folder_name: string
  folder_url: string
  sync_summary?: SyncSummary | null
  error_message?: string | null
}

export interface Citation {
  source_id: string
  file_id: string
  file_name: string
  drive_url: string
  chunk_excerpt: string
  chunk_index?: number | null
}

export interface ChatResponse {
  answer: string
  citations: Citation[]
}

export interface ChatResetResponse {
  status: 'reset'
}

export interface AssistantDeltaEvent {
  type: 'assistant_delta'
  delta: string
}

export interface ToolCallStartedEvent {
  type: 'tool_call_started'
  tool_call_id: string
  tool_name: string
  summary: string
  arguments?: Record<string, unknown>
}

export interface ToolCallCompletedEvent {
  type: 'tool_call_completed'
  tool_call_id: string
  tool_name: string
  summary: string
}

export interface CitationsUpdatedEvent {
  type: 'citations_updated'
  citations: Citation[]
}

export interface MessageCompletedEvent {
  type: 'message_completed'
  answer: string
  citations: Citation[]
}

export interface ChatFailedEvent {
  type: 'chat_failed'
  error_message: string
}

export type ChatStreamEvent =
  | AssistantDeltaEvent
  | ToolCallStartedEvent
  | ToolCallCompletedEvent
  | CitationsUpdatedEvent
  | MessageCompletedEvent
  | ChatFailedEvent

export interface UserProfile {
  google_id: string
  email: string
  name: string
  picture?: string | null
}

export interface SessionResponse {
  is_authenticated: boolean
  user: UserProfile | null
  current_folder_id: string | null
  current_folder_name?: string | null
  current_folder_url?: string | null
  files: DriveFileMetadata[]
}

export interface ToolStep {
  tool_name: string
  summary: string
  arguments?: Record<string, unknown>
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  status?: string | null
  toolSteps?: ToolStep[]
  selectedFiles?: DriveFileMetadata[]
}
