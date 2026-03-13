import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DashboardPage } from './DashboardPage'
import { useAuth } from '../context/useAuth'
import { useIngestionJob } from '../hooks/useIngestionJob'
import { clearUserData, ingestFolder, resetChatContext, streamChatMessage } from '../lib/api'
import type { IngestAcceptedResponse, SessionResponse } from '../types/api'

vi.mock('../context/useAuth')
vi.mock('../hooks/useIngestionJob')
vi.mock('../lib/api')

const mockedUseAuth = vi.mocked(useAuth)
const mockedUseIngestionJob = vi.mocked(useIngestionJob)
const mockedIngestFolder = vi.mocked(ingestFolder)
const mockedClearUserData = vi.mocked(clearUserData)
const mockedResetChatContext = vi.mocked(resetChatContext)
const mockedStreamChatMessage = vi.mocked(streamChatMessage)

function buildSession(): SessionResponse {
  return {
    is_authenticated: true,
    user: {
      google_id: 'google-user-123',
      email: 'demo@example.com',
      name: 'Demo User',
      picture: null,
    },
    current_folder_id: null,
    current_folder_name: null,
    current_folder_url: null,
    files: [],
  }
}

function buildIndexedSession(): SessionResponse {
  return {
    ...buildSession(),
    current_folder_id: 'folder-abc',
    current_folder_name: 'Tenex Folder',
    current_folder_url: 'https://drive.google.com/drive/folders/folder-abc',
    files: [
      {
        file_id: 'file-1',
        name: 'Tenex',
        mime_type: 'application/vnd.google-apps.document',
        web_view_link: 'https://docs.google.com/document/d/file-1/edit',
        source_type: 'document',
        modified_time: '2026-03-11T18:21:48.410Z',
        folder_ids: ['folder-abc'],
      },
      {
        file_id: 'file-2',
        name: 'Budget',
        mime_type: 'application/vnd.google-apps.spreadsheet',
        web_view_link: 'https://docs.google.com/spreadsheets/d/file-2/edit',
        source_type: 'spreadsheet',
        modified_time: '2026-03-11T18:21:48.410Z',
        folder_ids: ['folder-abc'],
      },
    ],
  }
}

function buildIngestResponse(): IngestAcceptedResponse {
  return {
    status: 'accepted',
    job_id: 'job-123',
    folder_id: 'folder-abc',
    folder_name: 'Tenex Folder',
    folder_url: 'https://drive.google.com/drive/folders/folder-abc',
  }
}

describe('DashboardPage', () => {
  beforeEach(() => {
    mockedUseAuth.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      user: buildSession().user,
      files: [],
      currentFolderId: null,
      currentFolderName: null,
      currentFolderUrl: null,
      refreshSession: vi.fn().mockResolvedValue(buildSession()),
      signIn: vi.fn(),
      signOut: vi.fn(),
    })
    mockedUseIngestionJob.mockReturnValue({
      isProcessing: false,
      progress: 0,
      statusMessage: 'Waiting to start ingestion.',
      error: null,
      syncSummary: null,
    })
    mockedResetChatContext.mockResolvedValue({ status: 'reset' })
    mockedStreamChatMessage.mockImplementation(async (_message, _selectedFiles, onEvent) => {
      onEvent({ type: 'message_completed', answer: 'ok', citations: [] })
    })
    vi.clearAllMocks()
  })

  it('shows toast and keeps workspace when files are already synced on resync', async () => {
    mockedIngestFolder.mockResolvedValue({ alreadySynced: true })
    mockedUseAuth.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      user: buildSession().user,
      files: buildIndexedSession().files,
      currentFolderId: 'folder-abc',
      currentFolderName: 'Tenex Folder',
      currentFolderUrl: 'https://drive.google.com/drive/folders/folder-abc',
      refreshSession: vi.fn().mockResolvedValue(buildIndexedSession()),
      signIn: vi.fn(),
      signOut: vi.fn(),
    })
    mockedUseIngestionJob.mockReturnValue({
      isProcessing: false,
      progress: 100,
      statusMessage: 'Ingestion complete.',
      error: null,
      syncSummary: null,
    })

    render(<DashboardPage />)

    await userEvent.click(screen.getByTitle('Re-sync folder'))

    await waitFor(() => {
      expect(screen.getByText('✅ Files are already synced!')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Ask something about the ingested folder... (type @ to add a file)')).toBeInTheDocument()
    })
  })

  it('shows live ingestion progress and active folder context after starting a job', async () => {
    mockedIngestFolder.mockResolvedValue({ alreadySynced: false, job: buildIngestResponse() })
    mockedUseIngestionJob.mockImplementation((jobId) =>
      jobId
        ? {
            isProcessing: true,
            progress: 45,
            statusMessage: 'Parsing text from Tenex (1/3).',
            error: null,
            syncSummary: {
              total_files: 3,
              new_files: 1,
              skipped_files: 1,
              updated_files: 1,
            },
          }
        : {
            isProcessing: false,
            progress: 0,
            statusMessage: 'Waiting to start ingestion.',
            error: null,
            syncSummary: null,
          },
    )

    render(<DashboardPage />)

    await userEvent.type(
      screen.getByPlaceholderText('https://drive.google.com/drive/folders/...'),
      'https://drive.google.com/drive/folders/folder-abc',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Ingest' }))

    await waitFor(() => {
      expect(screen.getByText('45%')).toBeInTheDocument()
      expect(screen.getByText('Parsing text from Tenex (1/3).')).toBeInTheDocument()
      expect(screen.getByText('Tenex Folder')).toBeInTheDocument()
    })
  })

  it('clears user data and shows a success banner', async () => {
    mockedClearUserData.mockResolvedValue({ status: 'deleted' })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockedUseAuth.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      user: buildSession().user,
      files: buildIndexedSession().files,
      currentFolderId: 'folder-abc',
      currentFolderName: 'Tenex Folder',
      currentFolderUrl: 'https://drive.google.com/drive/folders/folder-abc',
      refreshSession: vi.fn().mockResolvedValue(buildSession()),
      signIn: vi.fn(),
      signOut: vi.fn(),
    })

    render(<DashboardPage />)

    await userEvent.click(screen.getByRole('button', { name: 'Clear My Data' }))

    await waitFor(() => {
      expect(mockedClearUserData).toHaveBeenCalledTimes(1)
      expect(screen.getByText('Your indexed data was cleared successfully.')).toBeInTheDocument()
    })
  })

  it('clicking a sidebar file seeds the chat box with a file-specific prompt', async () => {
    mockedUseAuth.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      user: buildSession().user,
      files: buildIndexedSession().files,
      currentFolderId: 'folder-abc',
      currentFolderName: 'Tenex Folder',
      currentFolderUrl: 'https://drive.google.com/drive/folders/folder-abc',
      refreshSession: vi.fn().mockResolvedValue(buildIndexedSession()),
      signIn: vi.fn(),
      signOut: vi.fn(),
    })
    mockedUseIngestionJob.mockReturnValue({
      isProcessing: false,
      progress: 100,
      statusMessage: 'Ingestion complete.',
      error: null,
      syncSummary: null,
    })

    render(<DashboardPage />)

    await userEvent.click(screen.getByRole('button', { name: /Tenex/i }))

    expect(screen.getByPlaceholderText('Type your question...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove Tenex' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Budget/i }))

    expect(screen.getByRole('button', { name: 'Remove Tenex' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove Budget' })).toBeInTheDocument()
  })

  it('persists tool steps after message completes', async () => {
    mockedUseAuth.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      user: buildSession().user,
      files: buildIndexedSession().files,
      currentFolderId: 'folder-abc',
      currentFolderName: 'Tenex Folder',
      currentFolderUrl: 'https://drive.google.com/drive/folders/folder-abc',
      refreshSession: vi.fn().mockResolvedValue(buildIndexedSession()),
      signIn: vi.fn(),
      signOut: vi.fn(),
    })
    mockedStreamChatMessage.mockImplementation(async (_message, _selectedFiles, onEvent) => {
      onEvent({
        type: 'tool_call_started',
        tool_call_id: 'call-1',
        tool_name: 'search_folder',
        summary: 'Searching the folder for "X".',
        arguments: { query: 'X', top_k: 5, file_name: '' },
      })
      onEvent({
        type: 'tool_call_completed',
        tool_call_id: 'call-1',
        tool_name: 'search_folder',
        summary: 'Found 2 relevant source(s).',
      })
      onEvent({ type: 'message_completed', answer: 'Here is the answer.', citations: [] })
    })

    render(<DashboardPage />)

    const input = screen.getByPlaceholderText('Ask something about the ingested folder... (type @ to add a file)')
    await userEvent.type(input, 'What files mention X?')
    await userEvent.click(screen.getByRole('button', { name: 'Send message' }))
    await userEvent.click(screen.getByRole('button', { name: /expand to see 1 tool call/i }))

    await waitFor(() => {
      expect(screen.getByText(/search_folder for "X"/)).toBeInTheDocument()
    })
  })

  it('preserves streamed formatting when the completed answer only differs by whitespace', async () => {
    mockedUseAuth.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      user: buildSession().user,
      files: buildIndexedSession().files,
      currentFolderId: 'folder-abc',
      currentFolderName: 'Tenex Folder',
      currentFolderUrl: 'https://drive.google.com/drive/folders/folder-abc',
      refreshSession: vi.fn().mockResolvedValue(buildIndexedSession()),
      signIn: vi.fn(),
      signOut: vi.fn(),
    })
    mockedUseIngestionJob.mockReturnValue({
      isProcessing: false,
      progress: 100,
      statusMessage: 'Ingestion complete.',
      error: null,
      syncSummary: null,
    })
    mockedStreamChatMessage.mockImplementation(async (_message, _selectedFiles, onEvent) => {
      onEvent({ type: 'assistant_delta', delta: 'Here are the files:\n\n1. Replit' })
      onEvent({ type: 'message_completed', answer: 'Here are the files: 1. Replit', citations: [] })
    })

    render(<DashboardPage />)

    const input = screen.getByPlaceholderText('Ask something about the ingested folder... (type @ to add a file)')
    await userEvent.type(input, 'Which files mention Amjad?')
    await userEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => {
      expect(screen.getByText('Here are the files:')).toBeInTheDocument()
      expect(screen.getByText('Replit')).toBeInTheDocument()
    })
  })
})
