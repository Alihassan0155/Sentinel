from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UserProfile
from app.schemas.profile import ProfileResponse, ProfileUpdate


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

    db.commit()
    db.refresh(profile)
    return profile
