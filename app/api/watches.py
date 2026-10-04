from app.api.auth import current_account
from app.models.auth import Account
from app.services.ownership import owned_watch
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.watch import WatchCreate, WatchResponse
from app.services.check_jobs import enqueue_check

from app.models import CheckJob, WatchSnapshot, WatchSource

router = APIRouter(
    prefix="/watches",
    tags=["Watches"],
)


@router.post("", response_model=WatchResponse)
def create_watch(
    watch: WatchCreate,
    account: Account = Depends(current_account), db: Session = Depends(get_db),
):
    source = WatchSource(
        account_id=account.id,
        name=watch.name,
        url=str(watch.url),
        category=watch.category,
        check_interval_minutes=watch.check_interval_minutes,
    )

    db.add(source)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This URL is already being monitored")
    db.refresh(source)
    if source.active:
        enqueue_check(db, source.id)

    return source


@router.get("", response_model=list[WatchResponse])
def get_watches(
    account: Account = Depends(current_account), db: Session = Depends(get_db),
):
    return db.query(WatchSource).filter(WatchSource.account_id == account.id).all()


@router.post("/{watch_id}/check", status_code=status.HTTP_202_ACCEPTED)
def check_watch_endpoint(
    watch_id: int,
    account: Account = Depends(current_account), db: Session = Depends(get_db),
):
    watch = owned_watch(db, watch_id, account.id)

    if not watch:
        raise HTTPException(
            status_code=404,
            detail="Watch not found",
        )

    job = enqueue_check(db, watch.id)
    return {"job_id": job.id, "status": job.status, "watch_id": watch.id}

@router.get("/check-jobs/{job_id}")
def get_check_job(job_id: int, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    job = (db.query(CheckJob).join(WatchSource, WatchSource.id == CheckJob.watch_source_id)
           .filter(CheckJob.id == job_id, WatchSource.account_id == account.id).first())
    if job is None:
        raise HTTPException(404, "Check job not found")
    return {
        "job_id": job.id, "watch_id": job.watch_source_id,
        "mode": job.mode, "status": job.status,
        "attempts": job.attempts, "error": job.error,
        "result": job.result, "created_at": job.created_at,
        "started_at": job.started_at, "finished_at": job.finished_at,
    }


@router.post("/{watch_id}/test-change", status_code=status.HTTP_202_ACCEPTED)
def test_change(
    watch_id: int,
    account: Account = Depends(current_account), db: Session = Depends(get_db),
):
    watch = owned_watch(db, watch_id, account.id)

    if not watch:
        raise HTTPException(
            status_code=404,
            detail="Watch not found",
        )

    previous_snapshot = (
        db.query(WatchSnapshot)
        .filter(
            WatchSnapshot.watch_source_id == watch.id
        )
        .order_by(
            WatchSnapshot.fetched_at.desc()
        )
        .first()
    )

    if not previous_snapshot:
        raise HTTPException(
            status_code=400,
            detail="Create a normal snapshot first.",
        )

    job = enqueue_check(db, watch.id, mode="test_change")
    return {"job_id": job.id, "status": job.status, "watch_id": watch.id}


class WatchUpdate(BaseModel):
    active: bool


@router.patch("/{watch_id}", response_model=WatchResponse)
def update_watch(watch_id: int, update: WatchUpdate, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    watch = owned_watch(db, watch_id, account.id)
    if watch is None:
        raise HTTPException(404, "Watch not found")
    watch.active = update.active
    db.commit()
    db.refresh(watch)
    if watch.active:
        enqueue_check(db, watch.id)
    return watch
