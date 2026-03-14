import type { SyncSummary } from '../types/api'

interface IngestionStatusBarProps {
  isProcessing: boolean
  progress: number
  statusMessage: string
  syncSummary: SyncSummary | null
  folderName?: string | null
}

export function IngestionStatusBar({
  isProcessing,
  progress,
  statusMessage,
  syncSummary,
  folderName,
}: IngestionStatusBarProps) {
  if (!isProcessing) {
    return null
  }

  return (
    <section className="panel ingestion-status-panel">
      <div className={`panel-header ${folderName ? 'panel-header--stacked' : ''}`}>
        {folderName ? <h2 className="ingestion-folder-title">{folderName}</h2> : null}
        <span className={`status-pill ${isProcessing ? 'status-working' : 'status-ready'}`}>
          {isProcessing ? `${progress}%` : 'Ready'}
        </span>
      </div>
      <div className="progress-track" aria-hidden="true">
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>
      <p className="progress-message">{statusMessage}</p>
      {syncSummary ? (
        <div className="sync-summary-row">
          <div className="sync-summary-card">
            <strong>{syncSummary.new_files}</strong>
            <span>New</span>
          </div>
          <div className="sync-summary-card">
            <strong>{syncSummary.skipped_files}</strong>
            <span>Cached</span>
          </div>
          <div className="sync-summary-card">
            <strong>{syncSummary.updated_files}</strong>
            <span>Updated</span>
          </div>
          <div className="sync-summary-card">
            <strong>{syncSummary.total_files}</strong>
            <span>Total</span>
          </div>
        </div>
      ) : null}
    </section>
  )
}

