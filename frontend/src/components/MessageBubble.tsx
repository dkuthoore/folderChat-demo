import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Message, ToolStep } from '../types/api'
import { FileChip } from './FileChip'

function formatToolStepLabel(step: ToolStep): string {
  const args = step.arguments
  if (step.tool_name === 'search_folder' && args) {
    const query = typeof args.query === 'string' ? args.query.trim() : ''
    const fileName = typeof args.file_name === 'string' ? args.file_name.trim() : ''
    if (query) {
      return fileName ? `${step.tool_name} in "${fileName}" for "${query}"` : `${step.tool_name} for "${query}"`
    }
  }
  if (step.tool_name === 'list_files') {
    return step.tool_name
  }
  if (step.tool_name === 'read_file' && args) {
    const fileName = typeof args.file_name === 'string' ? args.file_name.trim() : ''
    if (fileName) {
      return `${step.tool_name} — "${fileName}"`
    }
  }
  return step.summary ? `${step.tool_name} — ${step.summary}` : step.tool_name
}

export function MessageBubble({ message }: { message: Message }) {
  const toolSteps = message.toolSteps ?? []
  const hasToolSteps = toolSteps.length > 0
  const [toolStepsExpanded, setToolStepsExpanded] = useState(false)
  const content = message.content
  const selectedFiles = message.selectedFiles ?? []
  const showThinking =
    message.role === 'assistant' &&
    message.status === 'Thinking...' &&
    !message.hasStartedStreaming &&
    content.trim().length === 0

  return (
    <article className={`message-bubble ${message.role === 'user' ? 'message-user' : 'message-ai'}`}>
      {showThinking ? (
        <p className="message-status message-status--thinking" role="status" aria-live="polite">
          <span>Thinking</span>
          <span className="message-status-dots" aria-hidden />
        </p>
      ) : message.status ? (
        <p className="message-status">{message.status}</p>
      ) : null}
      {message.role === 'user' && selectedFiles.length > 0 ? (
        <div className="message-selected-files">
          {selectedFiles.map((file) => (
            <div key={`${message.id}-${file.file_id}`} className="message-selected-file-chip">
              <FileChip file={file} />
            </div>
          ))}
        </div>
      ) : null}
      {hasToolSteps && message.role === 'assistant' ? (
        <div className="tool-steps">
          <button
            type="button"
            className="tool-steps-toggle"
            onClick={() => setToolStepsExpanded((prev) => !prev)}
            aria-expanded={toolStepsExpanded}
            aria-label={toolStepsExpanded ? 'Collapse tool calls' : `Expand to see ${toolSteps.length} tool call${toolSteps.length === 1 ? '' : 's'}`}
          >
            <span className="tool-steps-toggle-chevron" aria-hidden>
              {toolStepsExpanded ? '▼' : '▶'}
            </span>
            <span className="tool-steps-toggle-label">
              Agent Called {toolSteps.length} Tool{toolSteps.length === 1 ? '' : 's'}
            </span>
          </button>
          {toolStepsExpanded ? (
            <ol className="tool-steps-list">
              {toolSteps.map((step, i) => (
                <li key={`${message.id}-step-${i}`}>{formatToolStepLabel(step)}</li>
              ))}
            </ol>
          ) : null}
        </div>
      ) : null}
      {content.trim().length > 0 ? (
        <div className="message-content">
          <ReactMarkdown
            components={{
              a: ({ href, children, ...props }) => (
                <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                  {children}
                </a>
              ),
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      ) : null}
    </article>
  )
}
