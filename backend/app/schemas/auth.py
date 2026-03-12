from pydantic import BaseModel, Field

from app.models.documents import DriveFileMetadata


class AuthenticatedUser(BaseModel):
    google_id: str
    email: str
    name: str
    picture: str | None = None


class SessionResponse(BaseModel):
    is_authenticated: bool
    user: AuthenticatedUser | None = None
    current_folder_id: str | None = None
    current_folder_name: str | None = None
    current_folder_url: str | None = None
    files: list[DriveFileMetadata] = Field(default_factory=list)
