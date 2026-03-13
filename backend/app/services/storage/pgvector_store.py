from __future__ import annotations

import json
from contextlib import closing

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

from app.models.documents import ActiveFolderRecord, ChunkRecord, ChunkMetadata, DriveFileMetadata, IndexedFileRecord
from app.services.storage.base import StorageBackend


def _get_conn(database_url: str):
    conn = psycopg2.connect(database_url)
    register_vector(conn)
    return conn


class PgVectorStorageBackend(StorageBackend):
    def __init__(self, database_url: str, table_name: str) -> None:
        self.database_url = database_url
        self.table_name = table_name

    def get_file(self, owner_google_id: str, file_id: str) -> IndexedFileRecord | None:
        with closing(_get_conn(self.database_url)) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT owner_google_id, file_id, name, mime_type, web_view_link,
                           source_type, modified_time, folder_ids, folder_path, last_synced_at
                    FROM indexed_files
                    WHERE owner_google_id = %s AND file_id = %s
                    """,
                    (owner_google_id, file_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return _row_to_indexed_file(row)

    def upsert_file(self, file_record: IndexedFileRecord) -> IndexedFileRecord:
        with closing(_get_conn(self.database_url)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO indexed_files
                        (owner_google_id, file_id, name, mime_type, web_view_link,
                         source_type, modified_time, folder_ids, folder_path, last_synced_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (owner_google_id, file_id) DO UPDATE SET
                        name            = EXCLUDED.name,
                        mime_type       = EXCLUDED.mime_type,
                        web_view_link   = EXCLUDED.web_view_link,
                        source_type     = EXCLUDED.source_type,
                        modified_time   = EXCLUDED.modified_time,
                        folder_ids      = EXCLUDED.folder_ids,
                        folder_path     = EXCLUDED.folder_path,
                        last_synced_at  = EXCLUDED.last_synced_at
                    """,
                    (
                        file_record.owner_google_id,
                        file_record.file_id,
                        file_record.name,
                        file_record.mime_type,
                        file_record.web_view_link,
                        file_record.source_type,
                        file_record.modified_time,
                        file_record.folder_ids,
                        file_record.folder_path,
                        file_record.last_synced_at,
                    ),
                )
            conn.commit()
        return file_record

    def associate_file_with_folder(self, owner_google_id: str, file_id: str, folder_id: str) -> None:
        with closing(_get_conn(self.database_url)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE indexed_files
                    SET folder_ids = (
                        SELECT array_agg(DISTINCT elem ORDER BY elem)
                        FROM unnest(array_append(folder_ids, %s)) AS elem
                    )
                    WHERE owner_google_id = %s AND file_id = %s
                      AND NOT (folder_ids @> ARRAY[%s]::text[])
                    """,
                    (folder_id, owner_google_id, file_id, folder_id),
                )
                cur.execute(
                    """
                    UPDATE chunks
                    SET folder_ids = (
                        SELECT array_agg(DISTINCT elem ORDER BY elem)
                        FROM unnest(array_append(folder_ids, %s)) AS elem
                    )
                    WHERE owner_google_id = %s AND file_id = %s
                      AND NOT (folder_ids @> ARRAY[%s]::text[])
                    """,
                    (folder_id, owner_google_id, file_id, folder_id),
                )
            conn.commit()

    def replace_file_chunks(
        self,
        owner_google_id: str,
        file_id: str,
        chunks: list[ChunkRecord],
    ) -> None:
        import numpy as np
        with closing(_get_conn(self.database_url)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM chunks WHERE owner_google_id = %s AND file_id = %s",
                    (owner_google_id, file_id),
                )
                if chunks:
                    psycopg2.extras.execute_values(
                        cur,
                        """
                        INSERT INTO chunks
                            (owner_google_id, file_id, chunk_id, file_name, mime_type, source_type,
                             drive_url, folder_ids, chunk_index, text, embedding)
                        VALUES %s
                        """,
                        [
                            (
                                chunk.metadata.owner_google_id,
                                chunk.metadata.file_id,
                                chunk.metadata.chunk_id,
                                chunk.metadata.file_name,
                                chunk.metadata.mime_type,
                                chunk.metadata.source_type,
                                chunk.metadata.drive_url,
                                chunk.metadata.folder_ids,
                                chunk.metadata.chunk_index,
                                chunk.metadata.text,
                                np.array(chunk.embedding),
                            )
                            for chunk in chunks
                        ],
                    )
            conn.commit()

    def delete_file_chunks(self, owner_google_id: str, file_id: str) -> None:
        with closing(_get_conn(self.database_url)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM chunks WHERE owner_google_id = %s AND file_id = %s",
                    (owner_google_id, file_id),
                )
            conn.commit()

    def get_file_chunks(self, owner_google_id: str, file_id: str) -> list[ChunkRecord]:
        with closing(_get_conn(self.database_url)) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT owner_google_id, file_id, chunk_id, file_name, mime_type, source_type,
                           drive_url, folder_ids, chunk_index, text, embedding
                    FROM chunks
                    WHERE owner_google_id = %s AND file_id = %s
                    ORDER BY chunk_index ASC
                    """,
                    (owner_google_id, file_id),
                )
                rows = cur.fetchall()
        return [_row_to_chunk(row) for row in rows]

    def query_chunks(
        self,
        owner_google_id: str,
        folder_id: str,
        query_embedding: list[float],
        top_k: int = 5,
        file_name: str | None = None,
        min_similarity: float = 0.0,
    ) -> list[ChunkRecord]:
        import numpy as np
        vec = np.array(query_embedding)
        with closing(_get_conn(self.database_url)) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if file_name:
                    cur.execute(
                        """
                        SELECT owner_google_id, file_id, chunk_id, file_name, mime_type, source_type,
                               drive_url, folder_ids, chunk_index, text, embedding,
                               1 - (embedding <=> %s::vector) AS similarity
                        FROM chunks
                        WHERE owner_google_id = %s
                          AND folder_ids @> ARRAY[%s]::text[]
                          AND lower(file_name) LIKE %s
                          AND 1 - (embedding <=> %s::vector) >= %s
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (vec, owner_google_id, folder_id,
                         f"%{file_name.strip().lower()}%",
                         vec, min_similarity, vec, top_k),
                    )
                else:
                    cur.execute(
                        """
                        SELECT owner_google_id, file_id, chunk_id, file_name, mime_type, source_type,
                               drive_url, folder_ids, chunk_index, text, embedding,
                               1 - (embedding <=> %s::vector) AS similarity
                        FROM chunks
                        WHERE owner_google_id = %s
                          AND folder_ids @> ARRAY[%s]::text[]
                          AND 1 - (embedding <=> %s::vector) >= %s
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (vec, owner_google_id, folder_id, vec, min_similarity, vec, top_k),
                    )
                rows = cur.fetchall()
        return [_row_to_chunk(row) for row in rows]

    def get_folder_files(self, owner_google_id: str, folder_id: str) -> list[DriveFileMetadata]:
        with closing(_get_conn(self.database_url)) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT file_id, name, mime_type, web_view_link, source_type,
                           modified_time, folder_ids, folder_path
                    FROM indexed_files
                    WHERE owner_google_id = %s AND folder_ids @> ARRAY[%s]::text[]
                    """,
                    (owner_google_id, folder_id),
                )
                rows = cur.fetchall()
        return [
            DriveFileMetadata(
                file_id=row["file_id"],
                name=row["name"],
                mime_type=row["mime_type"],
                web_view_link=row["web_view_link"],
                source_type=row["source_type"],
                modified_time=row["modified_time"],
                folder_ids=list(row["folder_ids"] or []),
                folder_path=row["folder_path"] or "",
            )
            for row in rows
        ]

    def get_active_folder(self, owner_google_id: str) -> ActiveFolderRecord | None:
        with closing(_get_conn(self.database_url)) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT owner_google_id, folder_id, folder_name, folder_url
                    FROM active_folders
                    WHERE owner_google_id = %s
                    """,
                    (owner_google_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return ActiveFolderRecord(
            owner_google_id=row["owner_google_id"],
            folder_id=row["folder_id"],
            folder_name=row["folder_name"],
            folder_url=row["folder_url"],
        )

    def set_active_folder(self, active_folder: ActiveFolderRecord) -> None:
        with closing(_get_conn(self.database_url)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO active_folders (owner_google_id, folder_id, folder_name, folder_url)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (owner_google_id) DO UPDATE SET
                        folder_id   = EXCLUDED.folder_id,
                        folder_name = EXCLUDED.folder_name,
                        folder_url  = EXCLUDED.folder_url
                    """,
                    (
                        active_folder.owner_google_id,
                        active_folder.folder_id,
                        active_folder.folder_name,
                        active_folder.folder_url,
                    ),
                )
            conn.commit()

    def clear_active_folder(self, owner_google_id: str) -> None:
        with closing(_get_conn(self.database_url)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM active_folders WHERE owner_google_id = %s",
                    (owner_google_id,),
                )
            conn.commit()

    def clear_user_data(self, owner_google_id: str) -> None:
        with closing(_get_conn(self.database_url)) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chunks WHERE owner_google_id = %s", (owner_google_id,))
                cur.execute("DELETE FROM indexed_files WHERE owner_google_id = %s", (owner_google_id,))
                cur.execute("DELETE FROM active_folders WHERE owner_google_id = %s", (owner_google_id,))
            conn.commit()


def _row_to_indexed_file(row: dict) -> IndexedFileRecord:
    return IndexedFileRecord(
        owner_google_id=row["owner_google_id"],
        file_id=row["file_id"],
        name=row["name"],
        mime_type=row["mime_type"],
        web_view_link=row["web_view_link"],
        source_type=row["source_type"],
        modified_time=row["modified_time"],
        folder_ids=list(row["folder_ids"] or []),
        folder_path=row["folder_path"] or "",
        last_synced_at=row["last_synced_at"],
    )


def _row_to_chunk(row: dict) -> ChunkRecord:
    embedding = row["embedding"]
    if hasattr(embedding, "tolist"):
        embedding = embedding.tolist()
    elif not isinstance(embedding, list):
        embedding = list(embedding)
    return ChunkRecord(
        metadata=ChunkMetadata(
            chunk_id=row["chunk_id"],
            owner_google_id=row["owner_google_id"],
            file_id=row["file_id"],
            file_name=row["file_name"],
            mime_type=row["mime_type"],
            source_type=row["source_type"],
            drive_url=row["drive_url"],
            folder_ids=list(row["folder_ids"] or []),
            chunk_index=row["chunk_index"],
            text=row["text"],
        ),
        embedding=embedding,
    )
