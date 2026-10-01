import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import WatchSource
from app.services.monitor import check_watch

scheduler = BackgroundScheduler()
logger = logging.getLogger(__name__)


def run_watch_check(watch_id: int):
    db: Session = SessionLocal()

    try:
        watch = db.get(WatchSource, watch_id)
        if watch is None:
            logger.warning("Skipping check for missing watch %s", watch_id)
            return

        check_watch(watch, db)
    except Exception:
        logger.exception("Scheduled check failed for watch %s", watch_id)
    finally:
        db.close()


def schedule_watch(watch: WatchSource):
    scheduler.add_job(
        run_watch_check,
        trigger="interval",
        minutes=watch.check_interval_minutes,
        args=[watch.id],
        id=f"watch_{watch.id}",
        replace_existing=True,
    )


def start_scheduler():
    db = SessionLocal()

    try:
        watches = (
            db.query(WatchSource)
            .filter(WatchSource.active.is_(True))
            .all()
        )

        for watch in watches:
            schedule_watch(watch)

    finally:
        db.close()

    if not scheduler.running:
        scheduler.start()