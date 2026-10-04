"""PostgreSQL-backed work queue for watch checks."""

import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import CheckJob, WatchSnapshot, WatchSource
from app.services.monitor import check_watch

logger = logging.getLogger(__name__)


def enqueue_check(db: Session, watch_id: int, *, mode: str = "normal") -> CheckJob:
    watch = db.get(WatchSource, watch_id)
    if watch is None or watch.account_id is None:
        raise ValueError("Check requires an owned watch")
    existing = db.query(CheckJob).filter(
        CheckJob.watch_source_id == watch_id,
        CheckJob.status.in_(["pending", "running"]),
    ).first()
    if existing:
        return existing
    job = CheckJob(watch_source_id=watch_id, mode=mode, status="pending")
    try:
        db.add(job)
        db.commit()
        logger.info("Check job queued", extra={
            "event": "check_queued", "watch_id": watch_id, "job_id": job.id,
        })
        return job
    except IntegrityError:
        db.rollback()
        return db.query(CheckJob).filter(
            CheckJob.watch_source_id == watch_id,
            CheckJob.status.in_(["pending", "running"]),
        ).one()


def enqueue_due_watches() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        watches = db.query(WatchSource).filter(WatchSource.active.is_(True), WatchSource.account_id.is_not(None)).all()
        for watch in watches:
            latest = (db.query(CheckJob)
                      .filter(CheckJob.watch_source_id == watch.id)
                      .order_by(CheckJob.created_at.desc()).first())
            last_attempt = latest.created_at.replace(tzinfo=None) if latest else None
            last = max(
                (value for value in (watch.last_checked_at, last_attempt) if value),
                default=None,
            )
            if last is None or last + timedelta(minutes=watch.check_interval_minutes) <= now:
                enqueue_check(db, watch.id)
    except Exception:
        db.rollback()
        logger.exception("Could not enqueue due watches", extra={"event": "enqueue_due_failed"})
    finally:
        db.close()


def recover_stale_jobs() -> None:
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.worker_stale_minutes)
        stale = db.query(CheckJob).filter(
            CheckJob.status == "running", CheckJob.started_at < cutoff,
        ).all()
        for job in stale:
            job.status = "pending" if job.attempts < settings.check_job_max_attempts else "failed"
            job.available_at = datetime.now(timezone.utc)
            job.error = "Worker stopped before completing this check"
            logger.warning("Recovered stale check job", extra={
                "event": "check_recovered", "job_id": job.id,
                "watch_id": job.watch_source_id,
            })
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not recover stale check jobs")
    finally:
        db.close()


def process_next_check() -> None:
    db = SessionLocal()
    try:
        job = (db.query(CheckJob)
               .join(WatchSource, WatchSource.id == CheckJob.watch_source_id)
               .filter(WatchSource.account_id.is_not(None), CheckJob.status == "pending",
                       CheckJob.available_at <= datetime.now(timezone.utc))
               .order_by(CheckJob.available_at, CheckJob.id)
               .with_for_update(skip_locked=True, of=CheckJob)
               .first())
        if job is None:
            db.rollback()
            return
        job.status = "running"
        job.attempts += 1
        job.started_at = datetime.now(timezone.utc)
        job_id = job.id
        watch_id = job.watch_source_id
        mode = job.mode
        attempt = job.attempts
        db.commit()

        started = time.monotonic()
        try:
            watch = db.get(WatchSource, watch_id)
            if watch is None or watch.account_id is None:
                raise ValueError("Watch no longer exists")
            if mode == "test_change":
                previous = (db.query(WatchSnapshot)
                            .filter(WatchSnapshot.watch_source_id == watch_id)
                            .order_by(WatchSnapshot.fetched_at.desc()).first())
                if previous is None:
                    raise ValueError("Create a normal snapshot first")
                content = previous.content_text + """
NEW JOB POSTING
Position: AI/ML Engineer
Deadline: October 15, 2026
Eligibility: Bachelor's degree in Computer Science or related field.
"""
                result = check_watch(
                    watch, db, content_override=content,
                    allow_investigation=False, allow_notification=False,
                )
            else:
                result = check_watch(watch, db)
            job = db.get(CheckJob, job_id)
            job.status = "completed"
            job.result = jsonable_encoder(result)
            job.error = None
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            logger.info("Check job completed", extra={
                "event": "check_completed", "job_id": job_id,
                "watch_id": watch_id, "attempt": attempt,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            })
        except Exception as error:
            db.rollback()
            job = db.get(CheckJob, job_id)
            job.status = (
                "failed" if attempt >= settings.check_job_max_attempts
                or isinstance(error, ValueError) else "pending"
            )
            job.error = str(error)[:1000]
            job.finished_at = datetime.now(timezone.utc) if job.status == "failed" else None
            if job.status == "pending":
                job.available_at = datetime.now(timezone.utc) + timedelta(
                    minutes=min(60, 2 ** attempt),
                )
            db.commit()
            logger.exception("Check job failed", extra={
                "event": "check_failed", "job_id": job_id,
                "watch_id": watch_id, "attempt": attempt,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "status": job.status,
            })
    finally:
        db.close()
