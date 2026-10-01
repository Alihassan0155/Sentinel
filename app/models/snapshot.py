from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WatchSnapshot(Base):
    __tablename__ = "watch_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)

    watch_source_id: Mapped[int] = mapped_column(
        ForeignKey("watch_sources.id"),
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    content_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )