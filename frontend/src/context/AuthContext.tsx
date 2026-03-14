import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { fetchSession, getApiBaseUrl } from '../lib/api'
import type { DriveFileMetadata, UserProfile } from '../types/api'
import { AuthContext, type AuthContextValue } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isLoading, setIsLoading] = useState(true)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [user, setUser] = useState<UserProfile | null>(null)
  const [files, setFiles] = useState<DriveFileMetadata[]>([])
  const [currentFolderId, setCurrentFolderId] = useState<string | null>(null)
  const [currentFolderName, setCurrentFolderName] = useState<string | null>(null)
  const [currentFolderUrl, setCurrentFolderUrl] = useState<string | null>(null)

  const refreshSession = useCallback(async () => {
    try {
      const session = await fetchSession()
      setIsAuthenticated(session.is_authenticated)
      setUser(session.user)
      setFiles(session.files)
      setCurrentFolderId(session.current_folder_id)
      setCurrentFolderName(session.current_folder_name ?? null)
      setCurrentFolderUrl(session.current_folder_url ?? null)
      return session
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshSession()
  }, [refreshSession])

  const value = useMemo<AuthContextValue>(
    () => ({
      isLoading,
      isAuthenticated,
      user,
      files,
      currentFolderId,
      currentFolderName,
      currentFolderUrl,
      refreshSession,
      signIn: () => {
        window.location.href = `${getApiBaseUrl()}/auth/google`
      },
      signOut: () => {
        window.location.href = `${getApiBaseUrl()}/auth/logout`
      },
    }),
    [
      currentFolderId,
      currentFolderName,
      currentFolderUrl,
      files,
      isAuthenticated,
      isLoading,
      refreshSession,
      user,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
