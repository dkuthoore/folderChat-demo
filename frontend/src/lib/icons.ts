import type { SourceType } from '../types/api'

export const iconBySourceType: Record<SourceType, string> = {
  document: '/google-doc.svg',
  spreadsheet: '/google-sheet.png',
  presentation: '/google-slides.png',
  pdf: '/pdf.png',
}
