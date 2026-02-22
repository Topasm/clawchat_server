from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import make_id


class TaskRelationship(Base):
    __tablename__ = "task_relationships"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("trel_"))
    source_todo_id: Mapped[str] = mapped_column(
        String, ForeignKey("todos.id", ondelete="CASCADE"), nullable=False
    )
    target_todo_id: Mapped[str] = mapped_column(
        String, ForeignKey("todos.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_trel_source", "source_todo_id"),
        Index("idx_trel_target", "target_todo_id"),
        Index("idx_trel_type", "relationship_type"),
    )
