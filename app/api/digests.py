from app.api.auth import current_account
from app.models.auth import Account
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import WeeklyDigest
from app.services.digest import dispatch_digest, generate_weekly_digest, previous_week

router = APIRouter(prefix="/digests/weekly", tags=["Weekly Digests"])


def _serialize(digest: WeeklyDigest, *, full: bool = False) -> dict:
    result = {
        "id": digest.id,
        "period_start": digest.period_start,
        "period_end": digest.period_end,
        "status": digest.status,
        "subject": digest.subject,
        "created_at": digest.created_at,
        "sent_at": digest.sent_at,
        "attempts": digest.attempts,
        "next_attempt_at": digest.next_attempt_at,
        "reason": digest.reason,
    }
    if full:
        result.update({"body": digest.body, "content": digest.content})
    return result


@router.get("")
def list_digests(limit: int = 20, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    items = (db.query(WeeklyDigest).filter(WeeklyDigest.account_id == account.id)
             .order_by(WeeklyDigest.period_start.desc())
             .limit(min(max(limit, 1), 100)).all())
    return [_serialize(item) for item in items]


@router.get("/{digest_id}")
def get_digest(digest_id: int, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    digest = db.query(WeeklyDigest).filter(WeeklyDigest.id == digest_id, WeeklyDigest.account_id == account.id).first()
    if digest is None:
        raise HTTPException(404, "Digest not found")
    return _serialize(digest, full=True)


@router.post("")
def create_digest(week_start: date | None = None, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    today = datetime.now(ZoneInfo(settings.notification_timezone)).date()
    try:
        digest = generate_weekly_digest(db, week_start or previous_week(today), account_id=account.id, today=today)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return _serialize(dispatch_digest(db, digest), full=True)


@router.post("/{digest_id}/send")
def send_digest(digest_id: int, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    digest = db.query(WeeklyDigest).filter(WeeklyDigest.id == digest_id, WeeklyDigest.account_id == account.id).first()
    if digest is None:
        raise HTTPException(404, "Digest not found")
    return _serialize(dispatch_digest(db, digest), full=True)
