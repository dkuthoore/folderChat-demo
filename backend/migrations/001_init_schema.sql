-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Indexed files: one row per Drive file per user
CREATE TABLE IF NOT EXISTS indexed_files (
    owner_google_id TEXT        NOT NULL,
    file_id         TEXT        NOT NULL,
    name            TEXT        NOT NULL,
    mime_type       TEXT        NOT NULL,
    web_view_link   TEXT        NOT NULL,
    source_type     TEXT        NOT NULL,
    modified_time   TEXT        NOT NULL,
    folder_ids      TEXT[]      NOT NULL DEFAULT '{}',
    folder_path     TEXT        NOT NULL DEFAULT '',
    last_synced_at  TEXT        NOT NULL,
    PRIMARY KEY (owner_google_id, file_id)
);

CREATE INDEX IF NOT EXISTS idx_indexed_files_owner
    ON indexed_files (owner_google_id);

CREATE INDEX IF NOT EXISTS idx_indexed_files_folder_ids
    ON indexed_files USING GIN (folder_ids);

-- Chunks: one row per text chunk, with pgvector embedding column
-- text-embedding-3-small produces 1536-dimensional vectors
CREATE TABLE IF NOT EXISTS chunks (
    owner_google_id TEXT        NOT NULL,
    file_id         TEXT        NOT NULL,
    chunk_id        TEXT        NOT NULL,
    file_name       TEXT        NOT NULL,
    mime_type       TEXT        NOT NULL,
    source_type     TEXT        NOT NULL,
    drive_url       TEXT        NOT NULL,
    folder_ids      TEXT[]      NOT NULL DEFAULT '{}',
    chunk_index     INTEGER     NOT NULL,
    text            TEXT        NOT NULL,
    embedding       vector(1536) NOT NULL,
    PRIMARY KEY (owner_google_id, file_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_owner
    ON chunks (owner_google_id);

CREATE INDEX IF NOT EXISTS idx_chunks_owner_file
    ON chunks (owner_google_id, file_id);

CREATE INDEX IF NOT EXISTS idx_chunks_folder_ids
    ON chunks USING GIN (folder_ids);

-- HNSW index for fast approximate nearest-neighbour search (cosine distance)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Active folder: one row per user
CREATE TABLE IF NOT EXISTS active_folders (
    owner_google_id TEXT NOT NULL PRIMARY KEY,
    folder_id       TEXT NOT NULL,
    folder_name     TEXT NOT NULL,
    folder_url      TEXT NOT NULL
);

-- Sessions: one row per session (replaces file-based session store)
CREATE TABLE IF NOT EXISTS sessions (
    session_id       TEXT        NOT NULL PRIMARY KEY,
    user_json        JSONB       NOT NULL,
    credentials_json JSONB       NOT NULL,
    created_at       TEXT        NOT NULL,
    updated_at       TEXT        NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
    ON sessions (updated_at);

-- Conversations: one row per (user, folder) pair
CREATE TABLE IF NOT EXISTS conversations (
    owner_google_id  TEXT NOT NULL,
    folder_id        TEXT NOT NULL,
    conversation_id  TEXT NOT NULL,
    last_response_id TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (owner_google_id, folder_id)
);

CREATE INDEX IF NOT EXISTS idx_conversations_owner
    ON conversations (owner_google_id);
