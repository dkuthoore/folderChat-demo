import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { MessageBubble } from './MessageBubble'

describe('MessageBubble', () => {
  it('renders markdown citation links from assistant content', () => {
    render(
      <MessageBubble
        message={{
          id: 'assistant-1',
          role: 'assistant',
          content:
            'The report cites a quarterly update [Quarterly_Report.pdf](https://drive.google.com/file/d/file-1/view).',
          citations: [
            {
              source_id: 'source_1',
              file_id: 'file-1',
              file_name: 'Quarterly_Report.pdf',
              drive_url: 'https://drive.google.com/file/d/file-1/view',
              chunk_excerpt: 'Quarterly update excerpt',
            },
          ],
        }}
      />,
    )

    const citationLink = screen.getByRole('link', { name: 'Quarterly_Report.pdf' })
    expect(citationLink).toBeInTheDocument()
    expect(citationLink).toHaveAttribute(
      'href',
      'https://drive.google.com/file/d/file-1/view',
    )
  })

  it('does not auto-convert source IDs when markdown link is absent', () => {
    render(
      <MessageBubble
        message={{
          id: 'assistant-2',
          role: 'assistant',
          content: 'This file is relevant (source_1).',
          citations: [
            {
              source_id: 'source_1',
              file_id: 'file-1',
              file_name: 'Quarterly_Report.pdf',
              drive_url: 'https://drive.google.com/file/d/file-1/view',
              chunk_excerpt: 'Quarterly update excerpt',
            },
          ],
        }}
      />,
    )
    expect(screen.queryByRole('link', { name: 'Quarterly_Report.pdf' })).not.toBeInTheDocument()
    expect(screen.getByText('This file is relevant (source_1).')).toBeInTheDocument()
  })

  it('renders tool steps with input arguments', async () => {
    render(
      <MessageBubble
        message={{
          id: 'assistant-1',
          role: 'assistant',
          content: 'Here are the results.',
          toolSteps: [
            {
              tool_name: 'search_folder',
              summary: 'Found 3 relevant source(s).',
              arguments: { query: 'stablecoins', top_k: 5, file_name: '' },
            },
            { tool_name: 'list_files', summary: 'Listed 5 indexed file(s).' },
          ],
        }}
      />,
    )

    const toggle = screen.getByRole('button', { name: /expand to see 2 tool calls/i })
    await userEvent.click(toggle)
    expect(screen.getByText(/search_folder for "stablecoins"/)).toBeInTheDocument()
    expect(screen.getByText('list_files')).toBeInTheDocument()
  })
})
