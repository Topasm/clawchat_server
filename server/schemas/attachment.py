from datetime import datetime

from pydantic import BaseModel


class AttachmentResponse(BaseModel):
    id: str
    filename: str
    stored_filename: str
    content_type: str
    size_bytes: int
    memo_id: str | None = None
    todo_id: str | None = None
    url: str
    created_at: datetime

    model_config = {"from_attributes": True}
