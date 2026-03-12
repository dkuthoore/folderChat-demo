import { useEffect, useRef } from 'react'

import { FileChip } from './FileChip'
import type { DriveFileMetadata } from '../types/api'

const CHAT_TEXTAREA_MIN_HEIGHT = 44
const CHAT_TEXTAREA_MAX_HEIGHT = 200

function formatFileNamesForPrompt(files: DriveFileMetadata[]): string {
  if (files.length === 0) return ''
  if (files.length === 1) return `"${files[0].name}"`
  if (files.length === 2) return `"${files[0].name}" and "${files[1].name}"`
  const names = files.map((f) => `"${f.name}"`)
  return `${names.slice(0, -1).join(', ')}, and ${names[names.length - 1]}`
}

interface ChatInputProps {
  onSubmit: (message: string, selectedFiles: DriveFileMetadata[]) => Promise<void>
  value: string
  onChange: (value: string) => void
  disabled: boolean
  isLoading: boolean
  selectedFiles?: DriveFileMetadata[]
  onRemoveFile?: (file: DriveFileMetadata) => void
  onClearFiles?: () => void
}

export function ChatInput({
  onSubmit,
  value,
  onChange,
  disabled,
  isLoading,
  selectedFiles = [],
  onRemoveFile,
  onClearFiles,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    const height = Math.min(Math.max(ta.scrollHeight, CHAT_TEXTAREA_MIN_HEIGHT), CHAT_TEXTAREA_MAX_HEIGHT)
    ta.style.height = `${height}px`
  }, [value])

  const handleSubmit = async () => {
    const selectedFilesForMessage = [...selectedFiles]
    const filePrefix =
      selectedFilesForMessage.length > 0
        ? `Question about ${formatFileNamesForPrompt(selectedFilesForMessage)}: `
        : ''
    const message = filePrefix ? `${filePrefix}${value.trim()}` : value.trim()
    if (!message || disabled) {
      return
    }

    onChange('')
    onClearFiles?.()
    await onSubmit(message, selectedFilesForMessage)
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter') return
    if (event.shiftKey) return // Shift+Enter: new line
    event.preventDefault()
    void handleSubmit()
  }

  return (
    <div className="chat-input-row">
      <div className="chat-input-box">
        {selectedFiles.length > 0 ? (
          <div className="chat-input-file-chips">
            {selectedFiles.map((file) => (
              <div key={file.file_id} className="chat-input-file-chip">
                <FileChip file={file} onRemove={() => onRemoveFile?.(file)} />
              </div>
            ))}
          </div>
        ) : null}
        <textarea
          ref={textareaRef}
          className="chat-textarea"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={selectedFiles.length > 0 ? 'Type your question...' : 'Ask something about the ingested folder...'}
        rows={1}
        disabled={disabled}
        />
      </div>
      <button
        type="button"
        className="chat-send-button"
        onClick={() => void handleSubmit()}
        disabled={disabled}
        aria-label={isLoading ? 'Sending...' : 'Send message'}
        title={isLoading ? 'Sending...' : 'Send'}
      >
        {isLoading ? (
          <span className="chat-send-spinner" aria-hidden />
        ) : (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        )}
      </button>
    </div>
  )
}
