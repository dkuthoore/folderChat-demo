interface FolderInputBarProps {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  isLoading: boolean
  activeFolderUrl: string | null
}

export function FolderInputBar({
  value,
  onChange,
  onSubmit,
  isLoading,
  activeFolderUrl,
}: FolderInputBarProps) {
  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <h2>Paste in a Google Drive folder URL</h2>
          <p>You can chat with your Docs, Sheets, Slides, or PDFs.</p>
        </div>
      </div>
      <div className="folder-input-row">
        <input
          className="text-input"
          type="url"
          placeholder="https://drive.google.com/drive/folders/..."
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={isLoading}
        />
        <button className="primary-button" onClick={onSubmit} disabled={isLoading || !value.trim()}>
          {isLoading ? 'Ingesting...' : activeFolderUrl ? 'Sync Folder' : 'Ingest'}
        </button>
      </div>
    </div>
  )
}
