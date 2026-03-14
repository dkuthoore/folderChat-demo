import { useCallback, useEffect, useState } from 'react'

import { ChatInterface } from '../components/ChatInterface'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { FolderInputBar } from '../components/FolderInputBar'
import { IngestionStatusBar } from '../components/IngestionStatusBar'
import { Sidebar } from '../components/Sidebar'
import { useAuth } from '../context/useAuth'
import { useIngestionJob } from '../hooks/useIngestionJob'
import { clearUserData, ingestFolder, resetChatContext, streamChatMessage } from '../lib/api'
import type { ChatStreamEvent, DriveFileMetadata, IngestionJobEvent, Message, SyncSummary } from '../types/api'

function normalizeAssistantText(value: string): string {
  return value.replace(/\[source_\d+\]/g, '').replace(/\s+/g, ' ').trim()
}

function userDisplayText(message: string, selectedFiles: DriveFileMetadata[]): string {
  if (selectedFiles.length === 0) return message
  return message.replace(/^Question about[\s\S]*?:\s*/, '')
}

export function DashboardPage() {
  const { user, files, signOut, refreshSession, currentFolderName, currentFolderUrl } = useAuth()
  const [folderUrl, setFolderUrl] = useState(currentFolderUrl ?? '')
  const [activeFolderUrl, setActiveFolderUrl] = useState<string | null>(currentFolderUrl ?? null)
  const [activeFolderName, setActiveFolderName] = useState<string | null>(currentFolderName ?? null)
  const [messages, setMessages] = useState<Message[]>([])
  const [draftMessage, setDraftMessage] = useState('')
  const [syncSummary, setSyncSummary] = useState<SyncSummary | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [isStartingIngestion, setIsStartingIngestion] = useState(false)
  const [isChatLoading, setIsChatLoading] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [showClearDataConfirm, setShowClearDataConfirm] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<DriveFileMetadata[]>([])
  const MAX_SELECTED_FILES = 3

  const hasIndexedFiles = files.length > 0

  const handleJobComplete = useCallback(
    async (event: IngestionJobEvent) => {
      const summary = event.sync_summary
      const alreadySynced =
        summary &&
        summary.new_files === 0 &&
        summary.updated_files === 0 &&
        summary.total_files > 0
      if (alreadySynced) {
        setToastMessage('✅ Files are already synced!')
      }
      setActiveFolderName(event.folder_name)
      setActiveFolderUrl(event.folder_url)
      setFolderUrl(event.folder_url)
      setSyncSummary(event.sync_summary ?? null)
      await refreshSession()
    },
    [refreshSession],
  )

  const {
    isProcessing: isIngesting,
    progress,
    statusMessage,
    error: jobError,
    syncSummary: liveSyncSummary,
  } = useIngestionJob(jobId, handleJobComplete)

  const showWorkspace = !!activeFolderUrl && !isIngesting

  useEffect(() => {
    if (currentFolderUrl) {
      setFolderUrl(currentFolderUrl)
      setActiveFolderUrl(currentFolderUrl)
    }
    setActiveFolderName(currentFolderName ?? null)
  }, [currentFolderName, currentFolderUrl])

  useEffect(() => {
    if (jobError) {
      setError(jobError)
    }
  }, [jobError])

  useEffect(() => {
    if (!toastMessage) return
    const t = setTimeout(() => setToastMessage(null), 3000)
    return () => clearTimeout(t)
  }, [toastMessage])

  useEffect(() => {
    if (!successMessage) return
    const t = setTimeout(() => setSuccessMessage(null), 3000)
    return () => clearTimeout(t)
  }, [successMessage])

  const handleIngest = async () => {
    const nextFolderUrl = folderUrl.trim()
    if (!nextFolderUrl) {
      return
    }

    setError(null)
    setSuccessMessage(null)
    setSyncSummary(null)
    setIsStartingIngestion(true)
    try {
      const result = await ingestFolder(nextFolderUrl)
      if (result.alreadySynced) {
        setToastMessage('✅ Files are already synced!')
        if (!activeFolderUrl) {
          await refreshSession()
        }
        return
      }
      setJobId(result.job.job_id)
      setActiveFolderName(result.job.folder_name)
      setActiveFolderUrl(result.job.folder_url)
      setFolderUrl(result.job.folder_url)
      setMessages([])
      setDraftMessage('')
      setSelectedFiles([])
    } catch (ingestError) {
      setError(ingestError instanceof Error ? ingestError.message : 'Folder ingestion failed.')
    } finally {
      setIsStartingIngestion(false)
    }
  }

  const handleSendMessage = async (message: string, selectedFilesForMessage: DriveFileMetadata[]) => {
    setError(null)
    setSuccessMessage(null)
    const assistantMessageId = `assistant-${crypto.randomUUID()}`
    const userMessage: Message = {
      id: `user-${crypto.randomUUID()}`,
      role: 'user',
      content: userDisplayText(message, selectedFilesForMessage),
      selectedFiles: selectedFilesForMessage,
    }
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      citations: [],
      status: 'Thinking...',
      hasStartedStreaming: false,
      toolSteps: [],
    }
    setMessages((current) => [...current, userMessage, assistantMessage])
    setIsChatLoading(true)

    try {
      await streamChatMessage(message, selectedFilesForMessage, (event: ChatStreamEvent) => {
        setMessages((current) =>
          current.map((currentMessage) => {
            if (currentMessage.id !== assistantMessageId) {
              return currentMessage
            }

            switch (event.type) {
              case 'assistant_delta':
                return {
                  ...currentMessage,
                  content: `${currentMessage.content}${event.delta}`,
                  hasStartedStreaming: true,
                  status: null,
                }
              case 'tool_call_started':
                return {
                  ...currentMessage,
                  status: currentMessage.hasStartedStreaming ? event.summary : currentMessage.status,
                  toolSteps: [
                    ...(currentMessage.toolSteps ?? []),
                    {
                      tool_name: event.tool_name,
                      summary: event.summary,
                      arguments: event.arguments,
                    },
                  ],
                }
              case 'tool_call_completed':
                return {
                  ...currentMessage,
                  status: currentMessage.hasStartedStreaming ? event.summary : currentMessage.status,
                }
              case 'citations_updated':
                return currentMessage
              case 'message_completed': {
                const streamedContent = currentMessage.content
                const keepStreamedContent =
                  streamedContent.trim().length > 0 &&
                  normalizeAssistantText(streamedContent) === normalizeAssistantText(event.answer)
                return {
                  ...currentMessage,
                  content: keepStreamedContent ? streamedContent : event.answer,
                  citations: event.citations,
                  hasStartedStreaming: true,
                  status: null,
                  toolSteps: currentMessage.toolSteps ?? [],
                }
              }
              case 'chat_failed':
                return {
                  ...currentMessage,
                  status: null,
                }
              default:
                return currentMessage
            }
          }),
        )

        if (event.type === 'chat_failed') {
          setError(event.error_message)
        }
      })
    } catch (chatError) {
      setMessages((current) => current.filter((currentMessage) => currentMessage.id !== assistantMessageId))
      setError(chatError instanceof Error ? chatError.message : 'Chat request failed.')
    } finally {
      setIsChatLoading(false)
    }
  }

  const handleFileSelect = (file: DriveFileMetadata) => {
    setSelectedFiles((prev) => {
      if (prev.some((f) => f.file_id === file.file_id)) return prev
      if (prev.length >= MAX_SELECTED_FILES) return prev
      return [...prev, file]
    })
  }

  const handleRemoveFile = (file: DriveFileMetadata) => {
    setSelectedFiles((prev) => prev.filter((f) => f.file_id !== file.file_id))
  }

  const handleNewFolder = async () => {
    setError(null)
    setSuccessMessage(null)
    try {
      await resetChatContext()
      setJobId(null)
      setActiveFolderUrl(null)
      setActiveFolderName(null)
      setFolderUrl('')
      setMessages([])
      setDraftMessage('')
      setSelectedFiles([])
      setSyncSummary(null)
      await refreshSession()
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : 'Failed to reset the active folder.')
    }
  }

  const handleClearDataClick = () => {
    setShowClearDataConfirm(true)
  }

  const handleClearDataConfirm = async () => {
    setShowClearDataConfirm(false)
    setError(null)
    setSuccessMessage(null)
    setIsDeleting(true)
    try {
      await clearUserData()
      setJobId(null)
      setMessages([])
      setDraftMessage('')
      setSelectedFiles([])
      setSyncSummary(null)
      setFolderUrl('')
      setActiveFolderUrl(null)
      setActiveFolderName(null)
      await refreshSession()
      setSuccessMessage('Your indexed data was cleared successfully.')
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Failed to clear your data.')
    } finally {
      setIsDeleting(false)
    }
  }

  const handleClearDataCancel = () => {
    setShowClearDataConfirm(false)
  }

  return (
    <main
      className={`dashboard-layout ${showWorkspace ? 'dashboard-layout--workspace' : 'dashboard-layout--welcome'} ${showWorkspace && !sidebarOpen ? 'sidebar-collapsed' : ''}`}
    >
      {!showWorkspace ? (
        <header className="topbar">
          <div className="topbar-left">
            <div className="topbar-identity">
              <span className="eyebrow">Signed in</span>
              <p className="topbar-user">
                {user?.name ?? 'Drive agent dashboard'}
                {user?.email ? ` · ${user.email}` : null}
              </p>
            </div>
          </div>
          <div className="topbar-folder-title--center" aria-hidden />
          <div className="topbar-actions">
            <button className="secondary-button topbar-folder-btn" onClick={signOut}>
              Sign out
            </button>
          </div>
        </header>
      ) : null}

      {error ? <div className="error-banner">{error}</div> : null}
      {successMessage ? <div className="success-banner">{successMessage}</div> : null}
      {toastMessage ? (
        <div className="toast" role="status" aria-live="polite">
          {toastMessage}
        </div>
      ) : null}

      <ConfirmDialog
        isOpen={showClearDataConfirm}
        title="Clear My Data"
        message="Clear all indexed files, chunks, and cached data associated with your account?"
        confirmLabel="Clear Data"
        cancelLabel="Cancel"
        variant="danger"
        onConfirm={() => void handleClearDataConfirm()}
        onCancel={handleClearDataCancel}
      />

      {showWorkspace ? (
        <>
          <Sidebar
            files={files}
            onSelectFile={handleFileSelect}
            isOpen={sidebarOpen}
            onToggle={() => setSidebarOpen((o) => !o)}
            user={user}
            onResync={() => void handleIngest()}
            onNewFolder={() => void handleNewFolder()}
            onClearData={handleClearDataClick}
            onSignOut={signOut}
            isIngesting={isIngesting}
            isResyncLoading={isStartingIngestion}
            isDeleting={isDeleting}
            showWorkspace={showWorkspace}
          />
          <section className="dashboard-grid">
            <div className="dashboard-main">
              <header className="chat-header">
                <h1 className="chat-header-title">
                  {activeFolderName ?? 'Google Drive folder'}
                </h1>
                {activeFolderUrl ? (
                  <a
                    href={activeFolderUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="chat-header-link"
                    aria-label="Open folder in Drive"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                      <polyline points="15 3 21 3 21 9" />
                      <line x1="10" y1="14" x2="21" y2="3" />
                    </svg>
                  </a>
                ) : null}
              </header>
              <div className="dashboard-main-wrap">
                <IngestionStatusBar
                  isProcessing={isIngesting}
                  progress={progress}
                  statusMessage={statusMessage}
                  syncSummary={liveSyncSummary ?? syncSummary}
                  folderName={activeFolderName}
                />
                <ChatInterface
                  messages={messages}
                  onSubmit={handleSendMessage}
                  draftMessage={draftMessage}
                  onDraftChange={setDraftMessage}
                  selectedFiles={selectedFiles}
                  onAddFile={handleFileSelect}
                  onRemoveFile={handleRemoveFile}
                  onClearFiles={() => setSelectedFiles([])}
                  isLoading={isChatLoading}
                  hasIndexedFiles={hasIndexedFiles}
                />
              </div>
            </div>
          </section>
        </>
      ) : (
        <section className="dashboard-welcome">
          <FolderInputBar
            value={folderUrl}
            onChange={setFolderUrl}
            onSubmit={() => void handleIngest()}
            isLoading={isStartingIngestion || isIngesting}
            activeFolderUrl={activeFolderUrl}
          />
          {(isStartingIngestion || isIngesting) ? (
            <IngestionStatusBar
              isProcessing={isStartingIngestion || isIngesting}
              progress={isStartingIngestion && !isIngesting ? 0 : progress}
              statusMessage={
                isStartingIngestion && !isIngesting
                  ? 'Connecting to Google Drive...'
                  : statusMessage
              }
              syncSummary={liveSyncSummary ?? syncSummary}
              folderName={isStartingIngestion && !isIngesting ? null : activeFolderName}
            />
          ) : null}
        </section>
      )}
    </main>
  )
}
