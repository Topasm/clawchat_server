from datetime import datetime

from pydantic import BaseModel


class MemoCreate(BaseModel):
    title: str | None = None
    content: str
    tags: list[str] | None = None


class MemoUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None


class MemoResponse(BaseModel):
    id: str
    title: str
    content: str
    tags: list[str] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
