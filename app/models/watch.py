from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WatchSource(Base):
    __tablename__ = "watch_sources"
    __table_args__ = (UniqueConstraint("account_id", "url", name="uq_watch_sources_account_url"),)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), index=True)

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text)

    category: Mapped[str] = mapped_column(String(100))

    check_interval_minutes: Mapped[int] = mapped_column(
    Integer,
    default=30,
    nullable=False,
)

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )