# Google Drive AI Agent

## Overview
A full-stack web app that lets users explore a Google Drive folder through an AI chat interface using RAG (Retrieval-Augmented Generation).

## Stack
- **Frontend**: React 19 + Vite + TypeScript (port 5000)
- **Backend**: FastAPI + Python 3.12 (port 8000)
- **Auth**: Google OAuth with `drive.readonly` scope
- **RAG**: LlamaIndex for chunking/indexing, OpenAI for embeddings and chat
- **Storage**: Replit Postgres + pgvector (production) — file-backed local store available for dev via `VECTOR_STORE_BACKEND=local`

## Project Layout
- `frontend/` — React SPA (Vite dev server on port 5000, proxies `/api` and `/auth` to backend)
- `backend/` — FastAPI app on port 8000
- `data/storage/` — Local vector store files (gitignored)
- `data/uploads/` — Uploaded file cache (gitignored)
- `.env` — Environment config (overridden by Replit Secrets)

## Workflows
- **Start application** — `cd frontend && npm run dev` (webview, port 5000)
- **Backend API** — `cd backend && uvicorn app.main:app --host localhost --port 8000 --reload` (console)

## Vite Proxy
The frontend Vite dev server proxies `/api/*` and `/auth/*` to `http://localhost:8000`, so the browser always talks to port 5000 and never reaches localhost:8000 directly.

## Database (Replit Postgres + pgvector)
Schema applied: `backend/migrations/001_init_schema.sql`
- `indexed_files` — indexed Drive files per user
- `chunks` — text chunks with `vector(1536)` embeddings and HNSW index
- `active_folders` — current active folder per user
- `sessions` — server-side session records
- `conversations` — per-user/folder conversation state

`DATABASE_URL` is auto-resolved from Replit's `PG*` env vars. Sessions and conversations always use Postgres when connected. Vector/file storage uses Postgres when `VECTOR_STORE_BACKEND=pgvector`.

## Environment Variables (Replit Secrets)
All configured via Replit Secrets:
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` — Google OAuth
- `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL`, `OPENAI_EMBEDDING_MODEL` — OpenAI
- `FRONTEND_URL`, `BACKEND_URL` — Service URLs
- `SESSION_SECRET`, `SESSION_TTL_SECONDS` — Session management
- `VECTOR_STORE_BACKEND` — `pgvector` (production) or `local` (dev)
- `LOCAL_STORAGE_DIR`, `LOCAL_UPLOADS_DIR` — Data paths (local dev only)
- `DATABASE_URL`, `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` — Set by Replit Postgres

## Important Notes for Google OAuth
For the app to work with Google OAuth on Replit, these secrets need the Replit domain:
- `GOOGLE_REDIRECT_URI` → `https://<replit-domain>/auth/google/callback`
- `FRONTEND_URL` → `https://<replit-domain>`
- Register the redirect URI in Google Cloud Console

## Deployment
Configured for VM deployment (persistent state needed for local file storage):
- **Build**: `cd frontend && npm install && npm run build`
- **Run**: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 5000`
  - In production, FastAPI serves both the API and the built React SPA via StaticFiles

## Dependencies
- Backend: `backend/requirements.txt` (FastAPI, uvicorn, llama-index, openai, google APIs, aiofiles)
- Frontend: `frontend/package.json` (React, Vite, react-router-dom, react-markdown)
