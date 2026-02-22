from datetime import datetime

from pydantic import BaseModel


VALID_RELATIONSHIP_TYPES = {"blocks", "blocked_by", "related", "duplicate_of"}


class TaskRelationshipCreate(BaseModel):
    source_todo_id: str
    target_todo_id: str
    relationship_type: str


class TaskRelationshipResponse(BaseModel):
    id: str
    source_todo_id: str
    target_todo_id: str
    relationship_type: str
    created_at: datetime

    model_config = {"from_attributes": True}
