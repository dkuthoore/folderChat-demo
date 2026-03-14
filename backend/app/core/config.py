import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Google Drive AI Agent"
    api_prefix: str = "/api"
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")
    backend_url: str = Field(default="http://localhost:8000", alias="BACKEND_URL")
    session_secret: str = Field(alias="SESSION_SECRET")
    session_ttl_seconds: int = Field(
        default=60 * 60 * 24 * 7, alias="SESSION_TTL_SECONDS"
    )

    google_client_id: str = Field(alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(alias="GOOGLE_REDIRECT_URI")

    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_chat_model: str = Field(default="gpt-4o-mini", alias="OPENAI_CHAT_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="OPENAI_EMBEDDING_MODEL",
    )

    vector_store_backend: str = Field(default="local", alias="VECTOR_STORE_BACKEND")
    local_storage_dir: str = Field(default="./data/storage", alias="LOCAL_STORAGE_DIR")
    local_uploads_dir: str = Field(default="./data/uploads", alias="LOCAL_UPLOADS_DIR")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    pgvector_table_name: str = Field(
        default="document_chunks", alias="PGVECTOR_TABLE_NAME"
    )
    semantic_search_min_similarity: float = Field(
        default=0.2,
        alias="SEMANTIC_SEARCH_MIN_SIMILARITY",
    )
    read_file_max_chars: int = Field(default=12000, alias="READ_FILE_MAX_CHARS")

    @model_validator(mode="after")
    def resolve_database_url(self) -> "Settings":
        """
        If DATABASE_URL looks like a placeholder (contains literal 'username' or 'hostname'),
        try to construct a real connection string from the individual PG* environment variables
        that Replit sets when a Postgres database is provisioned.
        """
        pg_host = os.environ.get("PGHOST", "")
        pg_port = os.environ.get("PGPORT", "5432")
        pg_user = os.environ.get("PGUSER", "")
        pg_password = os.environ.get("PGPASSWORD", "")
        pg_database = os.environ.get("PGDATABASE", "")

        is_placeholder = (
            not self.database_url
            or "username" in (self.database_url or "")
            or "@host:" in (self.database_url or "")
        )

        if is_placeholder and pg_host and pg_user and pg_database:
            self.database_url = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"

        return self

    @property
    def storage_dir_path(self) -> Path:
        return (ROOT_DIR / self.local_storage_dir).resolve()

    @property
    def uploads_dir_path(self) -> Path:
        return (ROOT_DIR / self.local_uploads_dir).resolve()

    @property
    def session_https_only(self) -> bool:
        return urlparse(self.frontend_url).scheme.lower() == "https"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
