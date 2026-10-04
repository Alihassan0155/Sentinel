from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CheckJob(Base):
    __tablename__ = "check_jobs"
    __table_args__ = (
        Index("ix_check_jobs_due", "status", "available_at"),
        Index("ix_check_jobs_watch_created", "watch_source_id", "created_at"),
        Index("uq_check_jobs_active_watch", "watch_source_id", unique=True,
              postgresql_where=text("status IN ('pending', 'running')")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    watch_source_id: Mapped[int] = mapped_column(
        ForeignKey("watch_sources.id"), nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
