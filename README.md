# Google Drive AI Agent Prototype

This repo contains a webapp enabling users to explore a Google Drive folder via a familiar AI chat experience.

## Stack
- Frontend: React + Vite + TypeScript
- Backend: FastAPI + Python
- Auth: Google OAuth with `drive.readonly`
- RAG: LlamaIndex for chunking, OpenAI for embeddings and chat
- Local dev storage: file-backed vector store abstraction with file-level Smart Sync
- Future production storage: Replit Postgres + `pgvector`

## Repo Layout
- `frontend/`: React app
- `backend/`: FastAPI API
- `.env.example`: environment variable template

## Environment
Create a root `.env` file using `.env.example`.

Important variables:
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `OPENAI_API_KEY`
- `SESSION_SECRET`
- `SESSION_TTL_SECONDS`
- `VITE_API_BASE_URL`
- `VECTOR_STORE_BACKEND`
- `DATABASE_URL`

## Local Development
1. Install frontend dependencies:
   `cd frontend && npm install`
2. Install backend dependencies:
   `cd backend && pip install -r requirements.txt`
   (Dependencies are pinned for reproducible installs.)
3. Start the backend:
   `cd backend && uvicorn app.main:app --reload`
4. Start the frontend:
   `cd frontend && npm run dev`

## Supported File Types
- Google Docs
- Google Sheets
- Google Slides
- PDFs

## Demo Flow
1. Sign in with Google.
2. Paste a Google Drive folder URL.
3. Wait for ingestion to finish.
4. Ask questions in chat and inspect the citation chips.

## Retrieval Notes
- `search_folder` is used for semantic and keyword-style retrieval across the active folder.
- `read_file` lets the model inspect a single indexed file more deeply when a question is about one file or search results need follow-up.
- Google Sheets are chunked in a row-aware way during ingestion so row-level values survive retrieval better than generic sentence chunking.

## Smart Sync
- Files are cached by Google Drive `file_id`, not just by folder.
- If a file is new, it is exported, chunked, embedded, and stored.
- If a file is unchanged, the existing cached embeddings are reused.
- If a file has a newer `modifiedTime`, its old chunks are invalidated and re-ingested.
- Folder context is still preserved so chat remains scoped to the currently active folder.

## Data Lifecycle
- Indexed data is retained until the user deletes it.
- The dashboard includes a `Clear My Data` action that removes user-scoped indexed files, chunks, and local cached artifacts.
- Session records expire automatically based on `SESSION_TTL_SECONDS` (default 7 days).

## Testing
Frontend:
- `cd frontend && npm test`

Backend:
- `python3 -m venv .venv`
- `./.venv/bin/pip install -r backend/requirements.txt`
- `cd backend && ../.venv/bin/pytest`

## Database Handoff
The current implementation uses a local storage backend selected by `VECTOR_STORE_BACKEND=local`.

When Replit Postgres is ready:
1. Set `VECTOR_STORE_BACKEND=pgvector`
2. Replace `DATABASE_URL` with your Replit Postgres connection string
3. Implement the `PgVectorStorageBackend` methods in `backend/app/services/storage/pgvector_store.py`
