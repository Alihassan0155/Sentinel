"""Schedules queue polling and outbound delivery in the worker process."""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import SessionLocal
from app.models import Account, Notification, WatchSource, WeeklyDigest
from app.services.check_jobs import (
    enqueue_due_watches, process_next_check, recover_stale_jobs,
)
from app.services.digest import dispatch_digest, generate_weekly_digest, previous_week
from app.services.notification import dispatch_notification, email_configured

scheduler = BackgroundScheduler()
logger = logging.getLogger(__name__)


def run_notification_dispatch():
    if not email_configured():
        return
    db: Session = SessionLocal()
    try:
        items = (
            db.query(Notification)
            .join(WatchSource, WatchSource.id == Notification.watch_source_id)
            .filter(WatchSource.account_id.is_not(None))
            .filter(Notification.status == "pending")
            .filter((Notification.next_attempt_at.is_(None)) |
                    (Notification.next_attempt_at <= datetime.now(timezone.utc)))
            .order_by(Notification.created_at)
            .limit(50)
            .all()
        )
        for item in items:
            dispatch_notification(db, item)
    except Exception:
        db.rollback()
        logger.exception("Scheduled notification dispatch failed")
    finally:
        db.close()


def run_weekly_digest():
    db: Session = SessionLocal()
    try:
        today = datetime.now(ZoneInfo(settings.notification_timezone)).date()
        for (account_id,) in db.query(Account.id).all():
            try:
                digest = generate_weekly_digest(db, previous_week(today), account_id=account_id, today=today)
                dispatch_digest(db, digest)
            except Exception:
                db.rollback()
                logger.exception("Weekly digest failed for account %s", account_id)
    except Exception:
        db.rollback()
        logger.exception("Scheduled weekly digest failed")
    finally:
        db.close()


def run_digest_dispatch():
    if not email_configured():
        return
    db: Session = SessionLocal()
    try:
        items = (
            db.query(WeeklyDigest)
            .filter(WeeklyDigest.account_id.is_not(None))
            .filter(WeeklyDigest.status == "pending")
            .filter((WeeklyDigest.next_attempt_at.is_(None)) |
                    (WeeklyDigest.next_attempt_at <= datetime.now(timezone.utc)))
            .order_by(WeeklyDigest.period_start)
            .limit(10).all()
        )
        for item in items:
            dispatch_digest(db, item)
    except Exception:
        db.rollback()
        logger.exception("Scheduled digest dispatch failed")
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        enqueue_due_watches, trigger="interval", seconds=30,
        id="enqueue_due_watches", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        process_next_check, trigger="interval", seconds=settings.worker_poll_seconds,
        id="process_check_job", replace_existing=True, max_instances=4,
        coalesce=False,
    )
    scheduler.add_job(
        recover_stale_jobs, trigger="interval", minutes=5,
        id="recover_stale_jobs", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        run_notification_dispatch, trigger="interval", minutes=5,
        id="notification_dispatch", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        run_digest_dispatch, trigger="interval", minutes=5,
        id="digest_dispatch", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        run_weekly_digest,
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=0,
                            timezone=ZoneInfo(settings.notification_timezone)),
        id="weekly_digest", replace_existing=True, max_instances=1,
    )
    if not scheduler.running:
        scheduler.start()
    recover_stale_jobs()
    enqueue_due_watches()
    run_notification_dispatch()
    run_digest_dispatch()
    run_weekly_digest()
