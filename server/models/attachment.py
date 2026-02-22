from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import make_id


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("att_"))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memo_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("memos.id", ondelete="CASCADE"), nullable=True
    )
    todo_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("todos.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_attachments_memo_id", "memo_id"),
        Index("idx_attachments_todo_id", "todo_id"),
    )
