# FolderChat Agent

FolderChat is a web app that lets you explore your Google Drive folder through an AI chat interface. Sign in with Google, point it at a Drive folder URL, and ask questions about your documents. Answers are grounded in your files with citations.


## Stack

- **Frontend:** React + Vite + TypeScript
- **Backend:** FastAPI + Python
- **Auth:** Google OAuth with `drive.readonly`
- **RAG:** LlamaIndex for chunking, OpenAI for embeddings and chat
- **Storage:** Postgres + pgvector (production); file-backed local store for local development

## Local Development

1. **Install dependencies**
   - Frontend: `cd frontend && npm install`
   - Backend:
     - (Optional) Create and activate a venv: `python3 -m venv .venv`, then `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`).
     - `cd backend && pip install -r requirements.txt`

2. **Environment**  
   Create a root `.env` from `.env.example`. For local development use:

```env
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

OPENAI_API_KEY=your_openai_api_key
OPENAI_CHAT_MODEL=gpt-5-nano-2025-08-07
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

SESSION_SECRET=replace_with_a_long_random_secret
SESSION_TTL_SECONDS=86400

# Local dev: use file-backed storage (no database required)
VECTOR_STORE_BACKEND=local
# Omit DATABASE_URL for local — sessions/conversations use file-backed stores when unset

# Frontend talks to backend on port 8000 (or leave unset for same-origin relative URLs)
VITE_API_BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:5173
BACKEND_URL=http://localhost:8000
```

3. **Run**
   - Backend: `cd backend && uvicorn app.main:app --reload`
   - Frontend: `cd frontend && npm run dev`

## Testing

**Frontend:** `cd frontend && npm test`

**Frontend lint:** `cd frontend && npm run lint`

**Backend:** (with venv activated) `cd backend && pytest`

**Backend lint, format, types** (from `backend/`):

- Lint: `ruff check .`
- Format: `black --check .`
- Types: `mypy app`

## Database

On the **deployed site**, Replit Postgres with pgvector is used. Schema is in `backend/migrations/001_init_schema.sql`. Tables: `indexed_files`, `chunks` (vector(1536) + HNSW), `active_folders`, `sessions`, `conversations`.

To **run locally** without a database, set `VECTOR_STORE_BACKEND=local`. Indexed data, sessions, and conversations are then stored in local file storage (no Postgres required). For production or when `DATABASE_URL` is set (e.g. from Replit’s `PG*` env vars), the app uses Postgres for sessions and conversations; set `VECTOR_STORE_BACKEND=pgvector` to store vectors and chunks in Postgres as well.
