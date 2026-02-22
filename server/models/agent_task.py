from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import make_id


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("task_"))
    task_type: Mapped[str] = mapped_column(String, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_task_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("agent_tasks.id"), nullable=True
    )
    agent_type: Mapped[str] = mapped_column(String, nullable=False, default="general")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sub_task_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_sub_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conversation_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("conversations.id"), nullable=True
    )
    message_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("messages.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_agent_tasks_status", "status"),
        Index("idx_agent_tasks_conversation_id", "conversation_id"),
        Index("idx_agent_tasks_parent", "parent_task_id"),
    )
