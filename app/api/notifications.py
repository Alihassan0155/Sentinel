from app.api.auth import current_account
from app.models.auth import Account
from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Notification, WatchSource
from app.services.notification import dispatch_notification, email_configured

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _serialize(item: Notification) -> dict:
    return {
        "id": item.id,
        "watch_change_id": item.watch_change_id,
        "status": item.status,
        "reason": item.reason,
        "urgent": item.urgent,
        "subject": item.subject,
        "body": item.body,
        "created_at": item.created_at,
        "sent_at": item.sent_at,
        "attempts": item.attempts,
        "next_attempt_at": item.next_attempt_at,
    }


@router.get("")
def list_notifications(limit: int = 50, account: Account = Depends(current_account), db: Session = Depends(get_db)):
    items = (db.query(Notification).join(WatchSource, WatchSource.id == Notification.watch_source_id)
             .filter(WatchSource.account_id == account.id)
             .order_by(Notification.created_at.desc())
             .limit(min(max(limit, 1), 100)).all())
    return {"email_configured": email_configured(),
            "notifications": [_serialize(item) for item in items]}


@router.post("/dispatch")
def dispatch_pending(account: Account = Depends(current_account), db: Session = Depends(get_db)):
    if not email_configured():
        return {"email_configured": False, "processed": 0}
    items = (db.query(Notification).join(WatchSource, WatchSource.id == Notification.watch_source_id)
             .filter(WatchSource.account_id == account.id)
             .filter(Notification.status == "pending")
             .filter((Notification.next_attempt_at.is_(None)) |
                     (Notification.next_attempt_at <= datetime.now(timezone.utc)))
             .order_by(Notification.created_at)
             .limit(50).all())
    return {
        "email_configured": True,
        "processed": len(items),
        "notifications": [_serialize(dispatch_notification(db, item)) for item in items],
    }
