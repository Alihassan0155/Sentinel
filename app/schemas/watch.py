from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class WatchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: HttpUrl
    category: str = Field(min_length=1, max_length=100)
    check_interval_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,
    )

class WatchResponse(BaseModel):
    id: int
    name: str
    url: str
    category: str
    check_interval_minutes: int
    active: bool
    last_checked_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}