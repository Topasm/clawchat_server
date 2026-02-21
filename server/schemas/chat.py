from datetime import datetime

from pydantic import BaseModel


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
    created_at: datetime

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    conversation_id: str
    content: str


class SendMessageResponse(BaseModel):
    message_id: str
    conversation_id: str
    status: str = "delivered"


class StreamSendRequest(BaseModel):
    conversation_id: str
    content: str


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
