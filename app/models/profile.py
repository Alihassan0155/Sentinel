from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), unique=True, index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    degree: Mapped[str | None] = mapped_column(String(150), nullable=True)
    interests: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    desired_roles: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    locations: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    preferred_categories: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    available_resources: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
