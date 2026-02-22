import json as _json
from datetime import datetime

from pydantic import BaseModel, model_validator


class CreateConversationRequest(BaseModel):
    title: str = ""


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    is_archived: bool
    last_message: str | None = None

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    message_type: str
    intent: str | None = None
    metadata: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _parse_metadata_json(cls, values):
        """Convert metadata_json (ORM column) to metadata (API field)."""
        raw = None
        if hasattr(values, "metadata_json"):
            raw = values.metadata_json
        elif isinstance(values, dict):
            raw = values.pop("metadata_json", None)
        if raw:
            parsed = _json.loads(raw) if isinstance(raw, str) else raw
            if hasattr(values, "__dict__"):
                # ORM object: convert to dict so Pydantic can set metadata
                d = {
                    "id": values.id,
                    "conversation_id": values.conversation_id,
                    "role": values.role,
                    "content": values.content,
                    "message_type": values.message_type,
                    "intent": values.intent,
                    "created_at": values.created_at,
                    "metadata": parsed,
                }
                return d
            values["metadata"] = parsed
        return values


class SendMessageRequest(BaseModel):
    conversation_id: str
    content: str


class SendMessageResponse(BaseModel):
    message_id: str
    conversation_id: str
    status: str = "delivered"


class MessageEditRequest(BaseModel):
    content: str


class ConversationDetailResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    is_archived: bool
    messages: list[MessageResponse] = []

    model_config = {"from_attributes": True}
