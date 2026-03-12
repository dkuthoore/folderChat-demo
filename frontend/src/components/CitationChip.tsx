import type { Citation } from '../types/api'

export function CitationChip({ citation }: { citation: Citation }) {
  return (
    <a
      className="citation-chip"
      href={citation.drive_url}
      target="_blank"
      rel="noreferrer"
      title={citation.chunk_excerpt}
    >
      {citation.file_name}
    </a>
  )
}
