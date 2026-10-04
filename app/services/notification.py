"""Email alert policy, durable outbox, and SMTP delivery."""

import logging
import re
import smtplib
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Account, Notification, WatchChange, WatchSource

logger = logging.getLogger(__name__)


def _deadline_date(value: str, today: date) -> date | None:
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value, flags=re.IGNORECASE)
    iso = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", text)
    if iso:
        try:
            return date(*map(int, iso.groups()))
        except ValueError:
            return None
    day_first = re.search(
        r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
        r"September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|"
        r"Sep|Sept|Oct|Nov|Dec)\.?\s*(20\d{2})?\b",
        text, re.IGNORECASE,
    )
    if day_first:
        day_text, month_text, year_text = day_first.groups()
        month_number = datetime.strptime(month_text[:3].title(), "%b").month
        try:
            candidate = date(int(year_text) if year_text else today.year,
                             month_number, int(day_text))
            if year_text is None and candidate < today:
                candidate = candidate.replace(year=today.year + 1)
            return candidate
        except ValueError:
            return None
    month = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
        r"\.?\s+(\d{1,2})(?:,?\s+(20\d{2}))?\b",
        text, re.IGNORECASE,
    )
    if not month:
        return None
    month_text, day_text, year_text = month.groups()
    month_number = datetime.strptime(month_text[:3].title(), "%b").month
    try:
        candidate = date(int(year_text) if year_text else today.year,
                         month_number, int(day_text))
        if year_text is None and candidate < today:
            candidate = candidate.replace(year=today.year + 1)
        return candidate
    except ValueError:
        return None


def verified_deadline(investigation: dict | None) -> str | None:
    fact = (investigation or {}).get("deadline")
    if not isinstance(fact, dict) or not fact.get("source_urls"):
        return None
    return fact.get("value") or None


def alert_decision(
    change: WatchChange,
    recommendation: dict,
    investigation: dict | None,
    *,
    today: date,
) -> tuple[bool, bool]:
    deadline = verified_deadline(investigation)
    parsed = _deadline_date(deadline, today) if deadline else None
    urgent = parsed is not None and 0 <= (parsed - today).days <= 2
    should_alert = (
        change.should_notify
        and recommendation["recommendation"] == "recommended"
        and (recommendation["priority"] in {"high", "critical"} or urgent)
    )
    return should_alert, urgent


def compose_email(
    change: WatchChange,
    recommendation: dict,
    actions: list,
    source_url: str,
    investigation: dict | None,
) -> tuple[str, str]:
    deadline = verified_deadline(investigation)
    action = actions[0].title if actions else "Review the finding and its source."
    short_summary = " ".join(change.summary.split())[:120]
    subject = f"[Sentinel {recommendation['priority']}] {short_summary}"
    body = (
        f"What changed: {change.summary}\n\n"
        f"Why it matters: {change.why_it_matters}\n\n"
        f"Recommended action: {action}\n"
        f"Recommendation: {recommendation['recommendation']}\n"
        f"Priority: {recommendation['priority']}\n"
        f"Deadline: {deadline or 'Not verified'}\n"
        f"Source: {source_url}\n"
    )
    return subject, body


def _recent_sent(db: Session, watch_id: int, now: datetime) -> bool:
    if settings.notification_cooldown_minutes == 0:
        return False
    cutoff = now - timedelta(minutes=settings.notification_cooldown_minutes)
    return db.query(Notification.id).filter(
        Notification.watch_source_id == watch_id,
        Notification.status == "sent",
        Notification.sent_at >= cutoff,
    ).first() is not None


def queue_notification(
    db: Session,
    change: WatchChange,
    watch: WatchSource,
    recommendation: dict,
    investigation: dict | None,
    actions: list,
) -> Notification | None:
    if watch.account_id is None or change.watch_source_id != watch.id:
        raise ValueError("Notification requires an owned watch and its finding")
    existing = db.query(Notification).filter(
        Notification.watch_change_id == change.id
    ).first()
    if existing is not None:
        return existing
    now = datetime.now(timezone.utc)
    local_today = now.astimezone(ZoneInfo(settings.notification_timezone)).date()
    should_alert, urgent = alert_decision(
        change, recommendation, investigation, today=local_today,
    )
    if not should_alert:
        return None
    subject, body = compose_email(change, recommendation, actions, watch.url, investigation)
    cooling = not urgent and _recent_sent(db, watch.id, now)
    item = Notification(
        watch_change_id=change.id, watch_source_id=watch.id,
        status="suppressed" if cooling else "pending",
        reason="cooldown" if cooling else None,
        subject=subject, body=body, urgent=urgent,
    )
    db.add(item)
    db.commit()
    return item


def email_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def send_email(subject: str, body: str, *, recipient: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.ehlo()
        if settings.smtp_starttls:
            smtp.starttls()
            smtp.ehlo()
        if settings.smtp_username:
            smtp.login(
                settings.smtp_username,
                settings.smtp_password.get_secret_value() if settings.smtp_password else "",
            )
        smtp.send_message(message)


def dispatch_notification(db: Session, item: Notification) -> Notification:
    watch = db.get(WatchSource, item.watch_source_id)
    account = db.get(Account, watch.account_id) if watch and watch.account_id is not None else None
    if account is None or item.status != "pending" or not email_configured():
        return item
    now = datetime.now(timezone.utc)
    if item.next_attempt_at and item.next_attempt_at > now:
        return item
    if not item.urgent and _recent_sent(db, item.watch_source_id, now):
        item.status = "suppressed"
        item.reason = "cooldown"
        db.commit()
        return item
    reserved = db.execute(
        update(Notification)
        .where(Notification.id == item.id, Notification.status == "pending")
        .values(status="sending")
    ).rowcount
    db.commit()
    if not reserved:
        return db.get(Notification, item.id)
    try:
        send_email(item.subject, item.body, recipient=account.email)
        item.status = "sent"
        item.sent_at = datetime.now(timezone.utc)
        item.reason = None
        db.commit()
    except Exception as error:
        db.rollback()
        item = db.get(Notification, item.id)
        item.attempts += 1
        item.status = "failed" if item.attempts >= 5 else "pending"
        item.next_attempt_at = (
            None if item.status == "failed" else
            datetime.now(timezone.utc) + timedelta(minutes=min(60, 2 ** item.attempts))
        )
        item.reason = str(error)[:500]
        db.commit()
        logger.exception("Email delivery failed for notification %s", item.id)
    return item
