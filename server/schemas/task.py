"""Pydantic schemas for agent tasks."""

from datetime import datetime

from pydantic import BaseModel


class AgentTaskResponse(BaseModel):
    id: str
    task_type: str
    instruction: str
    status: str
    result: str | None = None
    error: str | None = None
    parent_task_id: str | None = None
    agent_type: str = "general"
    progress: int = 0
    progress_message: str | None = None
    sub_task_count: int = 0
    completed_sub_tasks: int = 0
    conversation_id: str | None = None
    message_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    sub_tasks: list["AgentTaskResponse"] | None = None

    model_config = {"from_attributes": True}
