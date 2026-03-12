import { useAuth } from '../context/useAuth'

export function AuthPage() {
  const { signIn, isLoading } = useAuth()

  return (
    <main className="auth-layout">
      <section className="hero-card">
        <span className="eyebrow">Talk to a Folder</span>
        <h1>Chat with your files</h1>
        <p>
          Sign in, paste in a Google Drive folder URL, and chat with your Docs, Sheets, Slides, and
          PDFs.
        </p>
        <button className="primary-button hero-button" onClick={signIn} disabled={isLoading}>
          {isLoading ? 'Checking session...' : 'Sign in with Google'}
        </button>
      </section>
    </main>
  )
}
