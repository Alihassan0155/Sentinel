from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models import UserProfile
from app.schemas.profile import ProfileResponse, ProfileUpdate
from app.services.memory import remember


router = APIRouter(
    prefix="/profile",
    tags=["Profile"],
)


@router.get("", response_model=ProfileResponse)
def get_profile(db: Session = Depends(get_db)):
    profile = db.get(UserProfile, 1)
    return profile or ProfileResponse()


@router.put("", response_model=ProfileResponse)
def update_profile(
    profile_data: ProfileUpdate,
    db: Session = Depends(get_db),
):
    profile = db.get(UserProfile, 1)
    values = profile_data.model_dump()

    if profile is None:
        profile = UserProfile(id=1, **values)
        db.add(profile)
    else:
        for field, value in values.items():
            setattr(profile, field, value)

    summary = ". ".join(
        f"{field}: {', '.join(value) if isinstance(value, list) else value}"
        for field, value in values.items() if value
    )
    if summary:
        remember(db, kind="preference", content=summary,
                 source_key="profile:1", metadata={"profile_id": 1})
    else:
        db.execute(text("DELETE FROM memories WHERE source_key = 'profile:1'"))
    db.commit()
    db.refresh(profile)
    return profile
