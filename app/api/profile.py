from app.api.auth import current_account
from app.models.auth import Account
from app.services.ownership import profile_for
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
def get_profile(account: Account = Depends(current_account), db: Session = Depends(get_db)):
    profile = profile_for(db, account.id)
    return profile or ProfileResponse()


@router.put("", response_model=ProfileResponse)
def update_profile(
    profile_data: ProfileUpdate,
    account: Account = Depends(current_account), db: Session = Depends(get_db),
):
    profile = profile_for(db, account.id)
    values = profile_data.model_dump()

    if profile is None:
        profile = UserProfile(account_id=account.id, **values)
        db.add(profile)
    else:
        for field, value in values.items():
            setattr(profile, field, value)

    summary = ". ".join(
        f"{field}: {', '.join(value) if isinstance(value, list) else value}"
        for field, value in values.items() if value
    )
    if summary:
        db.flush()
        remember(db, account_id=account.id, kind="preference", content=summary,
                 source_key="profile", metadata={"profile_id": profile.id})
    else:
        db.execute(text("DELETE FROM memories WHERE account_id = :account_id AND source_key = 'profile'"), {"account_id": account.id})
    db.commit()
    db.refresh(profile)
    return profile
