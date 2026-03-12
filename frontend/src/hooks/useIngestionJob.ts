import { useEffect, useState } from 'react'

import { getIngestionStreamUrl } from '../lib/api'
import type { IngestionJobEvent, SyncSummary } from '../types/api'

interface UseIngestionJobResult {
  isProcessing: boolean
  progress: number
  statusMessage: string
  error: string | null
  syncSummary: SyncSummary | null
}

export function useIngestionJob(
  jobId: string | null,
  onComplete?: (event: IngestionJobEvent) => void,
): UseIngestionJobResult {
  const [isProcessing, setIsProcessing] = useState(false)
  const [progress, setProgress] = useState(0)
  const [statusMessage, setStatusMessage] = useState('Waiting to start ingestion.')
  const [error, setError] = useState<string | null>(null)
  const [syncSummary, setSyncSummary] = useState<SyncSummary | null>(null)

  useEffect(() => {
    if (!jobId) {
      return
    }

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsProcessing(true)
    setError(null)
    const eventSource = new EventSource(getIngestionStreamUrl(jobId), {
      withCredentials: true,
    })

    const handleEvent = (event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as IngestionJobEvent
      setProgress(payload.progress_percentage)
      setStatusMessage(payload.current_step_message)
      setSyncSummary(payload.sync_summary ?? null)
    }

    eventSource.addEventListener('progress', handleEvent as EventListener)
    eventSource.addEventListener('complete', ((event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as IngestionJobEvent
      setProgress(100)
      setStatusMessage(payload.current_step_message)
      setSyncSummary(payload.sync_summary ?? null)
      setIsProcessing(false)
      onComplete?.(payload)
      eventSource.close()
    }) as EventListener)
    eventSource.addEventListener('failed', ((event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as IngestionJobEvent
      setProgress(payload.progress_percentage)
      setStatusMessage(payload.current_step_message)
      setError(payload.error_message ?? 'Folder ingestion failed.')
      setIsProcessing(false)
      eventSource.close()
    }) as EventListener)
    eventSource.onerror = () => {
      setStatusMessage('Reconnecting to live ingestion updates...')
    }

    return () => {
      eventSource.close()
    }
  }, [jobId, onComplete])

  if (!jobId) {
    return {
      isProcessing: false,
      progress: 0,
      statusMessage: 'Waiting to start ingestion.',
      error: null,
      syncSummary: null,
    }
  }

  return { isProcessing, progress, statusMessage, error, syncSummary }
}

