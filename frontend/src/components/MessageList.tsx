import { useEffect, useRef } from 'react'
import { MessageBubble } from './MessageBubble'
import type { Message } from '../types/api'

export interface SuggestedPrompt {
  label: string
  text: string
}

interface MessageListProps {
  messages: Message[]
  suggestedPrompts?: SuggestedPrompt[]
  onPromptClick?: (text: string) => void
  isLoading?: boolean
}

export function MessageList({
  messages,
  suggestedPrompts = [],
  onPromptClick,
  isLoading = false,
}: MessageListProps) {
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (messages.length > 0 && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [messages])

  if (messages.length === 0) {
    const showPrompts = suggestedPrompts.length > 0 && onPromptClick
    return (
      <div className="message-list empty-chat">
        {showPrompts && (
          <div className="empty-chat-prompts">
            <p className="empty-chat-prompts-title">Suggestions</p>
            <div className="empty-chat-prompts-list">
              {suggestedPrompts.map((prompt) => (
                <button
                  key={prompt.text}
                  type="button"
                  className="empty-chat-prompt-chip"
                  onClick={() => onPromptClick(prompt.text)}
                  disabled={isLoading}
                >
                  {prompt.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div ref={listRef} className="message-list">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`message-list-item message-list-item--${message.role}`}
        >
          <MessageBubble message={message} />
        </div>
      ))}
    </div>
  )
}
