"""Explicit ownership checks for API resources and worker context."""
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models import ActionStep, UserProfile, WatchChange, WatchSource


def owned_watch(db: Session, watch_id: int, account_id: int) -> WatchSource:
    watch = db.query(WatchSource).filter(WatchSource.id == watch_id, WatchSource.account_id == account_id).first()
    if watch is None:
        raise HTTPException(404, "Watch not found")
    return watch


def owned_change(db: Session, change_id: int, account_id: int) -> WatchChange:
    change = (db.query(WatchChange).join(WatchSource, WatchSource.id == WatchChange.watch_source_id)
              .filter(WatchChange.id == change_id, WatchSource.account_id == account_id).first())
    if change is None:
        raise HTTPException(404, "Change not found")
    return change


def owned_step(db: Session, step_id: int, account_id: int) -> ActionStep:
    step = (db.query(ActionStep).join(WatchChange, WatchChange.id == ActionStep.watch_change_id)
            .join(WatchSource, WatchSource.id == WatchChange.watch_source_id)
            .filter(ActionStep.id == step_id, WatchSource.account_id == account_id).first())
    if step is None:
        raise HTTPException(404, "Action step not found")
    return step


def require_account_id(account_id: int) -> None:
    if not isinstance(account_id, int) or account_id <= 0:
        raise ValueError("An explicit account owner is required")


def profile_for(db: Session, account_id: int) -> UserProfile | None:
    require_account_id(account_id)
    return db.query(UserProfile).filter(UserProfile.account_id == account_id).first()
