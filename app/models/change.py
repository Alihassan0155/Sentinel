from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WatchChange(Base):
    __tablename__ = "watch_changes"

    id: Mapped[int] = mapped_column(primary_key=True)

    watch_source_id: Mapped[int] = mapped_column(
        ForeignKey("watch_sources.id"),
        nullable=False,
    )

    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("watch_snapshots.id"),
        nullable=False,
    )

    importance: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    change_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    why_it_matters: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    should_notify: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    entities: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    detected_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )