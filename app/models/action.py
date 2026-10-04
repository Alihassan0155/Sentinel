from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ActionStep(Base):
    __tablename__ = "action_steps"
    __table_args__ = (
        UniqueConstraint("watch_change_id", "position", name="uq_action_step_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    watch_change_id: Mapped[int] = mapped_column(
        ForeignKey("watch_changes.id"), nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    resource: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_urls: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    supporting_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )
