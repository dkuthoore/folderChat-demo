import { createContext } from 'react'

import type { DriveFileMetadata, SessionResponse, UserProfile } from '../types/api'

export interface AuthContextValue {
  isLoading: boolean
  isAuthenticated: boolean
  user: UserProfile | null
  files: DriveFileMetadata[]
  currentFolderId: string | null
  currentFolderName: string | null
  currentFolderUrl: string | null
  refreshSession: () => Promise<SessionResponse>
  signIn: () => void
  signOut: () => void
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined)
