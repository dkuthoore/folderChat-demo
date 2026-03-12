import type { DriveFileMetadata } from '../types/api'
import { iconBySourceType } from '../lib/icons'

interface FileChipProps {
  file: DriveFileMetadata
  onRemove?: () => void
}

export function FileChip({ file, onRemove }: FileChipProps) {
  const iconSrc = iconBySourceType[file.source_type]

  return (
    <div className="file-chip">
      <span className="file-chip-icon">
        <img src={iconSrc} alt="" className="file-chip-icon-img" aria-hidden />
      </span>
      <span className="file-chip-name">{file.name}</span>
      {onRemove ? (
        <button
          type="button"
          className="file-chip-remove"
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
          aria-label={`Remove ${file.name}`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      ) : null}
    </div>
  )
}
