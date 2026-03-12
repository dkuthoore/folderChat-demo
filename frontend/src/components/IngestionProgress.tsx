import type { IngestStage, SyncSummary } from '../types/api'

interface IngestionProgressProps {
  stages: IngestStage[]
  isLoading: boolean
  syncSummary?: SyncSummary | null
}

export function IngestionProgress({ stages, isLoading, syncSummary }: IngestionProgressProps) {
  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <h2>Ingestion progress</h2>
          <p>Track the pipeline from Drive fetch to embeddings.</p>
        </div>
        <span className={`status-pill ${isLoading ? 'status-working' : 'status-ready'}`}>
          {isLoading ? 'Working' : 'Ready'}
        </span>
      </div>

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

      {stages.length === 0 ? (
        <p className="empty-state">No ingestion has been run yet.</p>
      ) : (
        <div className="stage-list">
          {stages.map((stage) => (
            <div className="stage-item" key={`${stage.label}-${stage.detail}`}>
              <strong>{stage.label}</strong>
              <span>{stage.detail}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
