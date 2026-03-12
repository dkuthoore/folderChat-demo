import type {
  ChatResetResponse,
  ChatResponse,
  ChatStreamEvent,
  DriveFileMetadata,
  IngestAcceptedResponse,
  IngestAlreadySyncedResponse,
  SessionResponse,
} from '../types/api'

const _rawApiBase = import.meta.env.VITE_API_BASE_URL ?? ''
const apiBaseUrl = _rawApiBase && !_rawApiBase.includes('localhost') ? _rawApiBase : ''

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = 'Request failed.'
    try {
      const payload = (await response.json()) as { detail?: string }
      detail = payload.detail ?? detail
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }

  return (await response.json()) as T
}

export function getApiBaseUrl(): string {
  return apiBaseUrl
}

export async function fetchSession(): Promise<SessionResponse> {
  const response = await fetch(`${apiBaseUrl}/api/session`, {
    credentials: 'include',
  })
  return readJson<SessionResponse>(response)
}

export async function clearUserData(): Promise<{ status: string }> {
  const response = await fetch(`${apiBaseUrl}/api/user/data`, {
    method: 'DELETE',
    credentials: 'include',
  })
  return readJson<{ status: string }>(response)
}

export type IngestFolderResult =
  | { alreadySynced: true }
  | { alreadySynced: false; job: IngestAcceptedResponse }

export async function ingestFolder(
  folderUrl: string,
): Promise<IngestFolderResult> {
  const response = await fetch(`${apiBaseUrl}/api/ingest`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ folder_url: folderUrl, check_first: true }),
  })
  const data = await readJson<IngestAcceptedResponse | IngestAlreadySyncedResponse>(
    response,
  )
  if ('already_synced' in data && data.already_synced) {
    return { alreadySynced: true }
  }
  return { alreadySynced: false, job: data as IngestAcceptedResponse }
}

export function getIngestionStreamUrl(jobId: string): string {
  return `${apiBaseUrl}/api/jobs/${jobId}/stream`
}

function parseSseEvent(rawEvent: string): ChatStreamEvent | null {
  const lines = rawEvent
    .split('\n')
    .map((line) => line.trimEnd())
    .filter(Boolean)

  if (lines.length === 0) {
    return null
  }

  const dataLines = lines.filter((line) => line.startsWith('data:'))
  if (dataLines.length === 0) {
    return null
  }

  const data = dataLines.map((line) => line.slice(5).trimStart()).join('\n')
  return JSON.parse(data) as ChatStreamEvent
}

export async function sendChatMessage(
  message: string,
  selectedFiles: DriveFileMetadata[] = [],
): Promise<ChatResponse> {
  const response = await fetch(`${apiBaseUrl}/api/chat`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      selected_files: selectedFiles.map((file) => ({
        file_id: file.file_id,
        file_name: file.name,
      })),
    }),
  })
  return readJson<ChatResponse>(response)
}

export async function streamChatMessage(
  message: string,
  selectedFiles: DriveFileMetadata[],
  onEvent: (event: ChatStreamEvent) => void,
): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/chat/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      selected_files: selectedFiles.map((file) => ({
        file_id: file.file_id,
        file_name: file.name,
      })),
    }),
  })

  if (!response.ok) {
    let detail = 'Chat request failed.'
    try {
      const payload = (await response.json()) as { detail?: string }
      detail = payload.detail ?? detail
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }

  if (!response.body) {
    throw new Error('Chat streaming is unavailable.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })

    let separatorIndex = buffer.indexOf('\n\n')
    while (separatorIndex !== -1) {
      const rawEvent = buffer.slice(0, separatorIndex)
      buffer = buffer.slice(separatorIndex + 2)
      const parsedEvent = parseSseEvent(rawEvent)
      if (parsedEvent) {
        onEvent(parsedEvent)
      }
      separatorIndex = buffer.indexOf('\n\n')
    }

    if (done) {
      break
    }
  }
}

export async function resetChatContext(): Promise<ChatResetResponse> {
  const response = await fetch(`${apiBaseUrl}/api/chat/reset`, {
    method: 'POST',
    credentials: 'include',
  })
  return readJson<ChatResetResponse>(response)
}
