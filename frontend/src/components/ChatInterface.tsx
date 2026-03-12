import { ChatInput } from './ChatInput'
import { MessageList, type SuggestedPrompt } from './MessageList'
import type { DriveFileMetadata, Message } from '../types/api'

const SUGGESTED_PROMPTS: SuggestedPrompt[] = [
  { label: 'Give me an overview of this folder', text: 'Give me an overview of this folder' },
  { label: 'How many files are in this folder?', text: 'How many files are in this folder?' },
  { label: 'Summarize the files in this folder', text: 'Summarize the files in this folder' },
]

interface ChatInterfaceProps {
  messages: Message[]
  onSubmit: (message: string, selectedFiles: DriveFileMetadata[]) => Promise<void>
  draftMessage: string
  onDraftChange: (value: string) => void
  selectedFiles?: DriveFileMetadata[]
  onRemoveFile?: (file: DriveFileMetadata) => void
  onClearFiles?: () => void
  isLoading: boolean
  hasIndexedFiles: boolean
}

export function ChatInterface({
  messages,
  onSubmit,
  draftMessage,
  onDraftChange,
  selectedFiles = [],
  onRemoveFile,
  onClearFiles,
  isLoading,
  hasIndexedFiles,
}: ChatInterfaceProps) {
  const handlePromptClick = (text: string) => {
    void onSubmit(text, [])
  }

  return (
    <section className="panel chat-panel">
      <MessageList
        messages={messages}
        suggestedPrompts={hasIndexedFiles ? SUGGESTED_PROMPTS : []}
        onPromptClick={handlePromptClick}
        isLoading={isLoading}
      />
      <ChatInput
        onSubmit={onSubmit}
        value={draftMessage}
        onChange={onDraftChange}
        selectedFiles={selectedFiles}
        onRemoveFile={onRemoveFile}
        onClearFiles={onClearFiles}
        disabled={isLoading || !hasIndexedFiles}
        isLoading={isLoading}
      />
    </section>
  )
}
