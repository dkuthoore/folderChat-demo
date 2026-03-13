import { useCallback, useEffect, useRef, useState } from 'react'

import { FileChip } from './FileChip'
import { fetchChatFileSuggestions } from '../lib/api'
import type { DriveFileMetadata } from '../types/api'
import { iconBySourceType } from '../lib/icons'

const CHAT_TEXTAREA_MIN_HEIGHT = 44
const CHAT_TEXTAREA_MAX_HEIGHT = 200
const MENTION_DEBOUNCE_MS = 150

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
  onAddFile?: (file: DriveFileMetadata) => void
  onRemoveFile?: (file: DriveFileMetadata) => void
  onClearFiles?: () => void
  hasIndexedFiles?: boolean
}

export function ChatInput({
  onSubmit,
  value,
  onChange,
  disabled,
  isLoading,
  selectedFiles = [],
  onAddFile,
  onRemoveFile,
  onClearFiles,
  hasIndexedFiles = false,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const mentionDropdownRef = useRef<HTMLDivElement>(null)
  const [mentionQuery, setMentionQuery] = useState<string | null>(null)
  const [mentionStart, setMentionStart] = useState<number | null>(null)
  const [suggestions, setSuggestions] = useState<DriveFileMetadata[]>([])
  const [suggestionsLoading, setSuggestionsLoading] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const highlightedItemRef = useRef<HTMLButtonElement>(null)

  const closeMentionDropdown = useCallback(() => {
    setMentionQuery(null)
    setMentionStart(null)
    setSuggestions([])
    setHighlightedIndex(0)
  }, [])

  useEffect(() => {
    if (mentionQuery === null) return
    const handleClickOutside = (event: MouseEvent) => {
      if (mentionDropdownRef.current && !mentionDropdownRef.current.contains(event.target as Node)) {
        closeMentionDropdown()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [mentionQuery, closeMentionDropdown])

  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    const height = Math.min(Math.max(ta.scrollHeight, CHAT_TEXTAREA_MIN_HEIGHT), CHAT_TEXTAREA_MAX_HEIGHT)
    ta.style.height = `${height}px`
  }, [value])

  useEffect(() => {
    if (!hasIndexedFiles || !onAddFile || disabled || mentionQuery === null) return
    const query = mentionQuery
    const timer = setTimeout(() => {
      setSuggestionsLoading(true)
      fetchChatFileSuggestions(query || undefined)
        .then(setSuggestions)
        .catch(() => setSuggestions([]))
        .finally(() => setSuggestionsLoading(false))
    }, MENTION_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [mentionQuery, hasIndexedFiles, onAddFile, disabled])

  const handleTextChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = event.target.value
    const cursor = event.target.selectionStart ?? newValue.length
    onChange(newValue)

    const beforeCursor = newValue.slice(0, cursor)
    const lastAt = beforeCursor.lastIndexOf('@')
    if (lastAt === -1 || (lastAt > 0 && /\S/.test(newValue[lastAt - 1]))) {
      closeMentionDropdown()
      return
    }
    const query = newValue.slice(lastAt + 1, cursor)
    if (/\s/.test(query)) {
      closeMentionDropdown()
      return
    }
    setMentionStart(lastAt)
    setMentionQuery(query)
    setHighlightedIndex(0)
  }

  const handleSelectSuggestion = (file: DriveFileMetadata) => {
    if (!onAddFile || mentionStart === null) return
    const query = mentionQuery ?? ''
    const end = mentionStart + 1 + query.length
    const newValue = value.slice(0, mentionStart) + value.slice(end)
    onChange(newValue)
    onAddFile(file)
    closeMentionDropdown()
    textareaRef.current?.focus()
  }

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

  const showMentionDropdown = mentionQuery !== null && hasIndexedFiles && onAddFile && !disabled
  const selectableFiles = suggestions.filter(
    (f) => !selectedFiles.some((s) => s.file_id === f.file_id),
  )
  const canSelectFile = selectableFiles.length > 0 && !suggestionsLoading

  useEffect(() => {
    if (showMentionDropdown && canSelectFile) {
      highlightedItemRef.current?.scrollIntoView({ block: 'nearest' })
    }
  }, [highlightedIndex, showMentionDropdown, canSelectFile])

  const handleTextareaKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape') {
      closeMentionDropdown()
      return
    }

    if (showMentionDropdown) {
      if (event.key === 'ArrowDown' && canSelectFile) {
        event.preventDefault()
        setHighlightedIndex((i) => (i + 1) % selectableFiles.length)
        return
      }
      if (event.key === 'ArrowUp' && canSelectFile) {
        event.preventDefault()
        setHighlightedIndex(
          (i) => (i - 1 + selectableFiles.length) % selectableFiles.length,
        )
        return
      }
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault()
        if (canSelectFile) {
          const file = selectableFiles[highlightedIndex]
          if (file) {
            handleSelectSuggestion(file)
          }
        }
        return
      }
    }

    if (event.key !== 'Enter') return
    if (event.shiftKey) return
    event.preventDefault()
    void handleSubmit()
  }

  return (
    <div className="chat-input-row">
      <div className="chat-input-box" ref={mentionDropdownRef}>
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
          onChange={handleTextChange}
          onKeyDown={handleTextareaKeyDown}
        placeholder={
          selectedFiles.length > 0
            ? 'Type your question...'
            : 'Ask something about the ingested folder... (type @ to add a file)'
        }
        rows={1}
        disabled={disabled}
        />
        {showMentionDropdown ? (
          <div className="chat-mention-dropdown" role="listbox">
            {suggestionsLoading ? (
              <div className="chat-mention-item chat-mention-item--loading">Loading...</div>
            ) : selectableFiles.length === 0 ? (
              <div className="chat-mention-item chat-mention-item--empty">
                {selectedFiles.length >= 3 ? 'Maximum 3 files selected' : 'No files match'}
              </div>
            ) : (
              selectableFiles.map((file, index) => (
                <button
                  key={file.file_id}
                  ref={index === highlightedIndex ? highlightedItemRef : undefined}
                  type="button"
                  className={`chat-mention-item ${index === highlightedIndex ? 'chat-mention-item--highlighted' : ''}`}
                  role="option"
                  aria-selected={index === highlightedIndex}
                  onClick={() => handleSelectSuggestion(file)}
                >
                  <img
                    src={iconBySourceType[file.source_type]}
                    alt=""
                    className="chat-mention-item-icon"
                    aria-hidden
                  />
                  <span className="chat-mention-item-name">{file.name}</span>
                  {file.folder_path ? (
                    <span className="chat-mention-item-path">{file.folder_path}</span>
                  ) : null}
                </button>
              ))
            )}
          </div>
        ) : null}
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
