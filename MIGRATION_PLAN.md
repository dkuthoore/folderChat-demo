# Migration Plan: Local Storage → Postgres + pgvector

## Overview

This plan describes migrating the Google Drive AI Agent from local file-based storage (`/data` folder) to Replit Postgres with pgvector extensions for storing embeddings and metadata.

**Current State:** The app uses `LocalStorageBackend` (JSON files in `/data`).  
**Target State:** The app uses `PgVectorStorageBackend` (Postgres + pgvector).  
**No Changes Required To:** StorageBackend interface, API endpoints, or ingestion/chat logic—the abstraction keeps them insulated.

---

## Architecture Overview

### Storage Backend Abstraction (Already Exists)
- **Base Class:** `StorageBackend` (abstract)
- **Current Implementation:** `LocalStorageBackend` (file-based)
- **Target Implementation:** `PgVectorStorageBackend` (Postgres)
- **Selection:** Controlled by `VECTOR_STORE_BACKEND` env var (`"local"` or `"pgvector"`)
- **Config:** `get_storage_backend()` in `backend/app/services/ingestion.py` handles instantiation

### Data Models (Defined, Unchanged)
- **`IndexedFileRecord`:** One per indexed Drive file (owner, file_id, name, mime_type, web_view_link, source_type, modified_time, folder_ids, folder_path, last_synced_at)
- **`ChunkRecord`:** One per text chunk (metadata + embedding vector)
  - **Metadata:** chunk_id, owner_google_id, file_id, file_name, mime_type, source_type, drive_url, folder_ids, chunk_index, text
  - **Embedding:** list[float] (OpenAI text-embedding-3-small)
- **`ActiveFolderRecord`:** One per owner (owner_google_id, folder_id, folder_name, folder_url)
- **`DriveFileMetadata`:** File info returned from Google Drive (used in listing and sync decisions)

---

## Implementation Plan

### Phase 1: Database Setup

**Goal:** Enable pgvector in Replit Postgres and create the schema.

#### 1.1 Create Replit Postgres Instance
1. In Replit, create a new Postgres database (managed, built-in).
2. Capture the `DATABASE_URL` connection string.
3. Test connection locally (e.g., `psql <database_url>`).

#### 1.2 Enable pgvector Extension
Run the following SQL:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

#### 1.3 Create Schema
Create three main tables plus indexes:

**Table: `indexed_files`**
- `owner_google_id` (text, not null)
- `file_id` (text, not null)
- `name` (text, not null)
- `mime_type` (text, not null)
- `web_view_link` (text, not null)
- `source_type` (text, not null)
- `modified_time` (text, not null)
- `folder_ids` (text[], defaults to empty, stores list of folder IDs)
- `folder_path` (text, defaults to empty)
- `last_synced_at` (text, ISO 8601 timestamp)
- Primary key: `(owner_google_id, file_id)`
- Index on `(owner_google_id)` for quick user lookups

**Table: `chunks`**
- `owner_google_id` (text, not null)
- `file_id` (text, not null)
- `chunk_id` (text, not null, unique per owner/file combo)
- `file_name` (text, not null)
- `mime_type` (text, not null)
- `source_type` (text, not null)
- `drive_url` (text, not null)
- `folder_ids` (text[], defaults to empty)
- `chunk_index` (int, not null)
- `text` (text, not null, the chunk content)
- `embedding` (vector(1536), not null) — 1536 dimensions for text-embedding-3-small
- Primary key: `(owner_google_id, file_id, chunk_id)`
- **Vector Index:** HNSW or IVFFlat on embedding column for fast similarity search
- Index on `(owner_google_id, folder_ids)` for folder-scoped queries

**Table: `active_folders`**
- `owner_google_id` (text, primary key)
- `folder_id` (text, not null)
- `folder_name` (text, not null)
- `folder_url` (text, not null)

**Indexes:**
- `indexed_files(owner_google_id, file_id)`
- `chunks(owner_google_id, folder_ids)`
- `chunks(owner_google_id, file_id, chunk_index)`
- `chunks` vector index on `embedding` (HNSW or IVFFlat)

#### 1.4 Create Migration Script
Store the schema SQL in a new file:
- **File:** `backend/migrations/001_init_pgvector_schema.sql`
- **Usage:** Run once via `psql` when Postgres is first configured.

---

### Phase 2: Implement PgVectorStorageBackend

**Goal:** Implement all 11 abstract methods in `PgVectorStorageBackend`.

#### 2.1 Connection Management
- Use `asyncpg` (async Postgres driver) or `psycopg2` (synchronous) with connection pooling.
- Instantiate the backend in `get_storage_backend()` when `VECTOR_STORE_BACKEND=pgvector`.
- Store `database_url` and `table_name` as instance variables (already in `__init__`).

#### 2.2 File Operations

**`get_file(owner_google_id, file_id) → IndexedFileRecord | None`**
- Query `indexed_files` table: `SELECT ... FROM indexed_files WHERE owner_google_id = ? AND file_id = ?`
- Return `IndexedFileRecord` or `None` if not found.

**`upsert_file(file_record: IndexedFileRecord) → IndexedFileRecord`**
- Insert or update `indexed_files` row: `INSERT INTO indexed_files (...) VALUES (...) ON CONFLICT (...) DO UPDATE SET ...`
- Return the record unchanged.

**`associate_file_with_folder(owner_google_id, file_id, folder_id) → None`**
- Fetch the file from `indexed_files`.
- Add `folder_id` to its `folder_ids` array if not present.
- Update the row: `UPDATE indexed_files SET folder_ids = ARRAY_APPEND(...) WHERE ...`
- Also update all chunks for that file: `UPDATE chunks SET folder_ids = ARRAY_APPEND(...) WHERE owner_google_id = ? AND file_id = ?`

#### 2.3 Chunk Operations

**`replace_file_chunks(owner_google_id, file_id, chunks: list[ChunkRecord]) → None`**
- Delete all chunks for the file: `DELETE FROM chunks WHERE owner_google_id = ? AND file_id = ?`
- Insert new chunks: `INSERT INTO chunks (...) VALUES (...), (...), ...`
- Each row: metadata fields + embedding vector.

**`delete_file_chunks(owner_google_id, file_id) → None`**
- `DELETE FROM chunks WHERE owner_google_id = ? AND file_id = ?`

**`get_file_chunks(owner_google_id, file_id) → list[ChunkRecord]`**
- `SELECT ... FROM chunks WHERE owner_google_id = ? AND file_id = ? ORDER BY chunk_index ASC`
- Reconstruct `ChunkRecord` objects (metadata + embedding).

#### 2.4 Search & Retrieval

**`query_chunks(owner_google_id, folder_id, query_embedding, top_k=5, file_name=None, min_similarity=0.0) → list[ChunkRecord]`**
- Filter by `owner_google_id` and `folder_id` (array contains check).
- Optional: filter by file_name if provided.
- Order by pgvector similarity: `ORDER BY embedding <=> query_embedding::vector LIMIT top_k`
- Apply `min_similarity` threshold (either in SQL with dot product / cosine, or in Python after fetch).
- Return top-k `ChunkRecord` objects.

#### 2.5 Folder Operations

**`get_folder_files(owner_google_id, folder_id) → list[DriveFileMetadata]`**
- `SELECT ... FROM indexed_files WHERE owner_google_id = ? AND folder_ids @> ARRAY[?]`
- Convert each row to `DriveFileMetadata`.
- Return the list.

#### 2.6 Active Folder

**`get_active_folder(owner_google_id) → ActiveFolderRecord | None`**
- `SELECT ... FROM active_folders WHERE owner_google_id = ?`
- Return `ActiveFolderRecord` or `None`.

**`set_active_folder(active_folder: ActiveFolderRecord) → None`**
- `INSERT INTO active_folders (...) VALUES (...) ON CONFLICT (owner_google_id) DO UPDATE SET ...`

**`clear_active_folder(owner_google_id) → None`**
- `DELETE FROM active_folders WHERE owner_google_id = ?`

#### 2.7 User Data Cleanup

**`clear_user_data(owner_google_id) → None`**
- Delete all rows for the user across all three tables:
  - `DELETE FROM chunks WHERE owner_google_id = ?`
  - `DELETE FROM indexed_files WHERE owner_google_id = ?`
  - `DELETE FROM active_folders WHERE owner_google_id = ?`

---

### Phase 3: Configuration & Dependencies

#### 3.1 Environment Setup
- **`.env` on Replit:** Set `VECTOR_STORE_BACKEND=pgvector` and `DATABASE_URL=<replit-postgres-url>`
- **Local dev:** Keep `VECTOR_STORE_BACKEND=local` to use `LocalStorageBackend` (no database required).
- **`.env.example`:** Already lists both; no changes needed.

#### 3.2 Dependency Installation
- Add PostgreSQL driver to `backend/requirements.txt`:
  - `asyncpg>=0.29.0` (async) or `psycopg2-binary>=2.9.0` (sync), whichever is chosen.
- Run `pip install -r backend/requirements.txt` on Replit.

#### 3.3 Initialization
- `get_storage_backend()` in `ingestion.py` already handles switching; no code changes needed.
- On first Replit deploy: run the schema migration script (`001_init_pgvector_schema.sql`).

---

### Phase 4: Testing & Validation

#### 4.1 Unit Tests
Add tests in `backend/tests/services/test_pgvector_store.py`:
- **Setup:** Spin up a Postgres container or use a test DB.
- **Coverage:**
  - `upsert_file()` and `get_file()`
  - `replace_file_chunks()` and `delete_file_chunks()`
  - `query_chunks()` with embedding similarity
  - `get_folder_files()` and folder association
  - `set_active_folder()` and `clear_active_folder()`
  - `clear_user_data()` (all tables cleared)
- **Assertions:** Check that data round-trips correctly and queries return expected results.

#### 4.2 Integration Tests
Run the existing app workflows against pgvector:
1. Sign in → ingest a folder → verify files/chunks stored in DB.
2. Ask a chat question → verify retrieval returns correct chunks.
3. Check citations → ensure metadata (drive_url, file_name) is preserved.
4. Clear data → verify all user rows deleted.

#### 4.3 Smoke Test on Replit
1. Deploy backend with `VECTOR_STORE_BACKEND=pgvector`.
2. Ingest a small test folder.
3. Ask a question and verify the answer matches expectations.
4. Check `SELECT COUNT(*) FROM chunks;` to confirm data is stored.

#### 4.4 Backward Compatibility
Ensure `LocalStorageBackend` still works:
- Local dev can use `VECTOR_STORE_BACKEND=local` without touching the database.
- No breaking changes to the `StorageBackend` interface.

---

### Phase 5: Data Migration (Optional)

**If preserving existing local data:**

#### 5.1 Migration Script
Create `backend/scripts/migrate_local_to_pgvector.py`:
- Read all data from `LocalStorageBackend` (files, chunks, active folder).
- Connect to Postgres.
- Insert all data into the new schema.
- Verify row counts match.

#### 5.2 Execution
1. Backup `/data` folder (in case rollback is needed).
2. Run the migration script.
3. Verify data in both backends (local and Postgres) matches.
4. Switch `VECTOR_STORE_BACKEND=pgvector` in `.env`.
5. Test the app on Replit with migrated data.

**If starting fresh:** Skip this phase (no local data to preserve).

---

## Order of Work (Recommended)

1. **Create Postgres instance** on Replit and capture `DATABASE_URL`.
2. **Create schema & indexes** (run SQL migration script).
3. **Implement `PgVectorStorageBackend`** (file operations → chunks → query → folder → active folder → cleanup).
4. **Add dependencies** (`asyncpg` or `psycopg2`) to `requirements.txt`.
5. **Write unit tests** for the backend.
6. **Run integration test** (ingest → search → chat) on Replit.
7. **(Optional) Migrate local data** if needed.
8. **Deploy** with `VECTOR_STORE_BACKEND=pgvector` in `.env`.
9. **Monitor** and validate in production.

---

## Key Technical Decisions

### Vector Search Strategy
- **Operator:** pgvector `<=>` (cosine distance) or `<->` (L2 distance).
- **Index Type:** HNSW (faster, approximate) or IVFFlat (slower, exact).
- **Recommendation:** HNSW for production (faster similarity queries).

### Similarity Scoring
- **Current (Local):** Manual cosine similarity calculation in Python.
- **Postgres:** Use pgvector's built-in operators for efficiency.
- **Min similarity threshold:** Apply in SQL (if using `.`) or in Python (fetch all, filter in code).

### Connection Pooling
- **Async:** Use `asyncpg` with a connection pool for concurrent requests.
- **Sync:** Use `psycopg2.pool.SimpleConnectionPool` or a context manager.
- **Recommendation:** Async for high concurrency; sync is simpler to start.

### Array Storage (folder_ids)
- Store as PostgreSQL `text[]` (array of text).
- Query with `folder_ids @> ARRAY[?]` (array contains operator).
- Alternative: Separate `folder_file_mapping` table if many-to-many becomes complex.

---

## Risk Mitigation

| Risk | Mitigation |
| --- | --- |
| **Database connection failures** | Add retry logic with exponential backoff; fail fast if DB is misconfigured. |
| **Data corruption during migration** | Backup local data; test migration on a copy first; validate row counts. |
| **Vector search performance** | Use HNSW index; monitor query times; add logging for slow queries. |
| **Similarity threshold tuning** | Use same `min_similarity` as local backend (0.2 by default); validate in tests. |
| **Breaking changes to interface** | All methods already exist in `StorageBackend` abstract base; no changes to callers. |

---

## Files to Create/Modify

### New Files
- `backend/migrations/001_init_pgvector_schema.sql` — Schema definition.
- `backend/app/services/storage/pgvector_store.py` — Implementation (currently a stub).
- `backend/tests/services/test_pgvector_store.py` — Unit tests.
- `backend/scripts/migrate_local_to_pgvector.py` — (Optional) Data migration.

### Existing Files to Modify
- `backend/requirements.txt` — Add `asyncpg` or `psycopg2`.
- `backend/app/core/config.py` — No changes (env vars already defined).
- `backend/app/services/ingestion.py` — No changes (get_storage_backend already has logic).

### No Changes Needed
- `StorageBackend` abstract class — Interface is complete.
- API endpoints — Still use the same `StorageBackend` interface.
- Models — `IndexedFileRecord`, `ChunkRecord`, `ActiveFolderRecord` unchanged.
- Chat agent, retrieval service, ingestion logic — All use `StorageBackend` abstraction.

---

## Success Criteria

✅ All 11 `StorageBackend` methods implemented in `PgVectorStorageBackend`  
✅ Schema created with proper indexes (especially vector HNSW/IVFFlat)  
✅ Unit tests pass (CRUD operations, search, cleanup)  
✅ Integration test passes (ingest folder → search → chat with citations)  
✅ Existing `LocalStorageBackend` still works for local dev  
✅ Environment variables correctly configured on Replit  
✅ Data persists in Postgres across app restarts  
✅ Vector similarity queries return expected results  

---

## Timeline Estimate

- **Phase 1 (DB Setup):** 15–30 minutes (mostly waiting for Postgres to start)
- **Phase 2 (Implementation):** 2–3 hours (depends on DB driver familiarity)
- **Phase 3 (Config):** 15 minutes
- **Phase 4 (Testing):** 1–2 hours (includes integration test & smoke test)
- **Phase 5 (Migration, optional):** 30 minutes
- **Total:** ~4–6 hours (excluding debugging)

---

## Summary

This migration replaces the local file-based vector store with Replit Postgres + pgvector. The existing `StorageBackend` abstraction ensures **no changes to ingestion, chat, or API logic**. All work is isolated to:
1. Schema definition (SQL)
2. `PgVectorStorageBackend` implementation (Python)
3. Dependency and config management (simple env vars)

The app will continue to work identically to users; data is simply stored in a managed database instead of local JSON files.
