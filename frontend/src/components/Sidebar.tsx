import { useEffect, useRef, useState } from 'react'

import type { DriveFileMetadata } from '../types/api'
import { iconBySourceType } from '../lib/icons'

function groupFilesByPath(
  files: DriveFileMetadata[],
): Array<{ path: string; label: string; files: DriveFileMetadata[] }> {
  const groups = new Map<string, DriveFileMetadata[]>()
  for (const file of files) {
    const path = file.folder_path ?? ''
    const list = groups.get(path) ?? []
    list.push(file)
    groups.set(path, list)
  }
  const sortedPaths = [...groups.keys()].sort((a, b) => {
    if (!a) return 1
    if (!b) return -1
    return a.localeCompare(b)
  })
  return sortedPaths.map((path) => ({
    path,
    label: path ? path.replace(/\//g, ' / ') : '',
    files: groups.get(path) ?? [],
  }))
}

interface SidebarUser {
  name?: string | null
  email?: string | null
}

interface SidebarProps {
  files: DriveFileMetadata[]
  onSelectFile: (file: DriveFileMetadata) => void
  isOpen: boolean
  onToggle: () => void
  user: SidebarUser | null
  onResync: () => void
  onNewFolder: () => void
  onClearData: () => void
  onSignOut: () => void
  isIngesting: boolean
  isDeleting: boolean
  showWorkspace: boolean
}

export function Sidebar({
  files,
  onSelectFile,
  isOpen,
  onToggle,
  user,
  onResync,
  onNewFolder,
  onClearData,
  onSignOut,
  isIngesting,
  isDeleting,
  showWorkspace,
}: SidebarProps) {
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set())
  const sidebarRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!isOpen) return
    const handleClickOutside = (event: MouseEvent) => {
      if (sidebarRef.current && !sidebarRef.current.contains(event.target as Node)) {
        onToggle()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen, onToggle])

  const togglePath = (path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }

  return (
    <aside
      ref={sidebarRef}
      className={`sidebar sidebar--left ${isOpen ? 'sidebar--open' : 'sidebar--collapsed'}`}
    >
      <button
        type="button"
        className="sidebar-toggle"
        onClick={onToggle}
        aria-label={isOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        title={isOpen ? 'Collapse' : 'Expand'}
      >
        <svg className="sidebar-toggle-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      {isOpen ? (
        <>
          <div className="sidebar-body">
            <div className="sidebar-user-block">
              <span className="eyebrow">Signed in</span>
              <span className="sidebar-user-name">{user?.name ?? 'Drive agent'}</span>
              {user?.email ? (
                <span className="sidebar-user-email">{user.email}</span>
              ) : null}
            </div>

            {showWorkspace ? (
              <div className="sidebar-actions">
                <button
                  type="button"
                  className="sidebar-action-btn"
                  onClick={onResync}
                  disabled={isIngesting}
                  aria-label={isIngesting ? 'Syncing...' : 'Re-sync folder'}
                  title={isIngesting ? 'Syncing...' : 'Re-sync folder'}
                >
                  {isIngesting ? (
                    <span
                      className="topbar-btn-spinner"
                      style={{ width: 14, height: 14 }}
                      aria-hidden
                    />
                  ) : (
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden
                    >
                      <polyline points="23 4 23 10 17 10" />
                      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                    </svg>
                  )}
                </button>
                <button
                  type="button"
                  className="sidebar-action-btn"
                  onClick={onNewFolder}
                  aria-label="New folder"
                  title="New folder"
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden
                  >
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                    <line x1="12" y1="11" x2="12" y2="17" />
                    <line x1="9" y1="14" x2="15" y2="14" />
                  </svg>
                </button>
              </div>
            ) : null}

            <div className="sidebar-files-section">
              <h2>Indexed files</h2>
              {files.length === 0 ? (
                <p className="empty-state">Ingest a folder to populate the file list.</p>
              ) : (
                <div className="sidebar-files-list sidebar-file-list">
                  {groupFilesByPath(files).map(({ path, label, files: groupFiles }) => (
                    <div
                      key={path}
                      className={`sidebar-folder-group ${label ? 'sidebar-folder-group--nested' : ''}`}
                    >
                      {label ? (
                        <button
                          type="button"
                          className="sidebar-folder-toggle"
                          onClick={() => togglePath(path)}
                          aria-expanded={expandedPaths.has(path)}
                          aria-label={expandedPaths.has(path) ? `Collapse ${label}` : `Expand ${label}`}
                        >
                          <img
                            src="/folder.svg"
                            alt=""
                            className="sidebar-folder-icon"
                            aria-hidden
                          />
                          <span className="sidebar-folder-path">{label}</span>
                        </button>
                      ) : null}
                      {(!label || expandedPaths.has(path)) &&
                        groupFiles.map((file) => (
                          <button
                            type="button"
                            className="sidebar-file"
                            key={file.file_id}
                            onClick={() => onSelectFile(file)}
                          >
                            <span className="sidebar-file-icon">
                              <img
                                src={iconBySourceType[file.source_type]}
                                alt=""
                                className="sidebar-file-icon-img"
                                aria-hidden
                              />
                            </span>
                            <span className="sidebar-file-name">{file.name}</span>
                          </button>
                        ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="sidebar-bottom">
            {showWorkspace ? (
              <button
                type="button"
                className="secondary-button danger-button sidebar-bottom-btn"
                onClick={onClearData}
                disabled={isDeleting}
              >
                {isDeleting ? 'Clearing...' : 'Clear My Data'}
              </button>
            ) : null}
            <button
              type="button"
              className="secondary-button sidebar-bottom-btn"
              onClick={onSignOut}
            >
              Sign out
            </button>
          </div>
        </>
      ) : (
        <>
          {showWorkspace ? (
            <div className="sidebar-collapsed-top">
              <button
                type="button"
                className="sidebar-action-btn sidebar-collapsed-folder"
                onClick={onToggle}
                aria-label="Expand sidebar to view files"
                title="View indexed files"
              >
                <img src="/folder.svg" alt="" className="sidebar-folder-icon" aria-hidden />
              </button>
              <button
                type="button"
                className="sidebar-action-btn"
                onClick={onResync}
                disabled={isIngesting}
                aria-label={isIngesting ? 'Syncing...' : 'Re-sync folder'}
                title={isIngesting ? 'Syncing...' : 'Re-sync folder'}
              >
                {isIngesting ? (
                  <span
                    className="topbar-btn-spinner"
                    style={{ width: 14, height: 14 }}
                    aria-hidden
                  />
                ) : (
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden
                  >
                    <polyline points="23 4 23 10 17 10" />
                    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                  </svg>
                )}
              </button>
              <button
                type="button"
                className="sidebar-action-btn"
                onClick={onNewFolder}
                aria-label="New folder"
                title="New folder"
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden
                >
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                  <line x1="12" y1="11" x2="12" y2="17" />
                  <line x1="9" y1="14" x2="15" y2="14" />
                </svg>
              </button>
            </div>
          ) : null}
          <div className="sidebar-collapsed-actions">
            <button
              type="button"
              className="sidebar-action-btn"
              onClick={onSignOut}
              aria-label="Sign out"
              title="Sign out"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </div>
        </>
      )}
    </aside>
  )
}
