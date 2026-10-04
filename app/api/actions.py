from app.api.auth import current_account
from app.models.auth import Account
from app.services.ownership import owned_change, owned_step, profile_for
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Literal

from app.database import get_db
from app.models import ActionStep, Investigation, Recommendation, UserProfile, WatchChange, WatchSource
from app.services.action import build_action_plan

router = APIRouter(prefix="/actions", tags=["Actions"])


class StatusUpdate(BaseModel):
    status: Literal["pending", "in_progress", "completed"]


def serialize_step(step: ActionStep) -> dict:
    return {
        "id": step.id,
        "watch_change_id": step.watch_change_id,
        "position": step.position,
        "title": step.title,
        "status": step.status,
        "resource": step.resource,
        "resource_status": step.resource_status,
        "source_urls": step.source_urls,
        "supporting_quote": step.supporting_quote,
        "deadline": step.deadline,
        "updated_at": step.updated_at,
    }


def steps_for_change(db: Session, change_id: int) -> list[ActionStep]:
    return (db.query(ActionStep)
            .filter(ActionStep.watch_change_id == change_id)
            .order_by(ActionStep.position).all())


@router.get("/changes/{change_id}")
def get_action_plan(change_id: int, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    owned_change(db, change_id, account.id)
    return [serialize_step(step) for step in steps_for_change(db, change_id)]


@router.post("/changes/{change_id}")
def create_action_plan(change_id: int, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    change = owned_change(db, change_id, account.id)
    if change is None:
        raise HTTPException(404, "Change not found")
    existing = steps_for_change(db, change_id)
    if existing:
        return [serialize_step(step) for step in existing]
    recommendation = (db.query(Recommendation)
                      .filter(Recommendation.watch_change_id == change_id).first())
    if recommendation is None or recommendation.recommendation != "recommended":
        raise HTTPException(409, "Finding is not recommended")
    investigation = (db.query(Investigation)
                     .filter(Investigation.watch_change_id == change_id).first())
    source = db.get(WatchSource, change.watch_source_id)
    plan = build_action_plan(
        investigation.result if investigation and investigation.status == "completed" else None,
        profile_for(db, account.id), source.url,
    )
    steps = [ActionStep(watch_change_id=change_id, **item) for item in plan]
    db.add_all(steps)
    db.commit()
    return [serialize_step(step) for step in steps]


@router.patch("/{step_id}")
def update_action_status(step_id: int, update: StatusUpdate, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    step = owned_step(db, step_id, account.id)
    if step is None:
        raise HTTPException(404, "Action step not found")
    step.status = update.status
    db.commit()
    db.refresh(step)
    return serialize_step(step)
