from pydantic import BaseModel


class BulkTodoUpdate(BaseModel):
    ids: list[str]
    status: str | None = None
    priority: str | None = None
    tags: list[str] | None = None
    delete: bool = False


class BulkTodoResponse(BaseModel):
    updated: int
    deleted: int
    errors: list[str]
