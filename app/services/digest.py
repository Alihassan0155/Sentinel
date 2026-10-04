"""Weekly intelligence digest from persisted findings and user actions."""

import logging
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Account, ActionStep, Investigation, Recommendation, UserProfile,
    WatchChange, WatchSource, WeeklyDigest,
)
from app.services.notification import _deadline_date, email_configured, send_email, verified_deadline
from app.services.ownership import profile_for, require_account_id
from app.services.relevance import assess_relevance
from app.services.recommendation import recommend

logger = logging.getLogger(__name__)
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "ignore": 4}


def previous_week(today: date) -> date:
    return today - timedelta(days=today.weekday() + 7)


def _utc_naive_bounds(start: date) -> tuple[datetime, datetime]:
    zone = ZoneInfo(settings.notification_timezone)
    start_local = datetime.combine(start, time.min, tzinfo=zone)
    end_local = datetime.combine(start + timedelta(days=7), time.min, tzinfo=zone)
    return (start_local.astimezone(timezone.utc).replace(tzinfo=None),
            end_local.astimezone(timezone.utc).replace(tzinfo=None))


def _item_line(item: dict) -> str:
    action = item["suggested_action"] or "Review the source."
    return (
        f"- What changed: {item['summary']}\n"
        f"  Why it matters: {item['why_it_matters']}\n"
        f"  Recommendation: {item['recommendation']} ({item['priority']})\n"
        f"  Suggested action: {action}\n"
        f"  Source: {item['source_url']}"
    )


def build_digest_content(db: Session, start: date, *, account_id: int, today: date) -> dict:
    require_account_id(account_id)
    start_utc, end_utc = _utc_naive_bounds(start)
    rows = (
        db.query(WatchChange, WatchSource)
        .join(WatchSource, WatchSource.id == WatchChange.watch_source_id)
        .filter(WatchSource.account_id == account_id, WatchChange.detected_at >= start_utc,
                WatchChange.detected_at < end_utc)
        .order_by(WatchChange.detected_at.desc())
        .all()
    )
    change_ids = [change.id for change, _ in rows]
    watch_ids = {source.id for _, source in rows}
    weekly_watch_counts = Counter(source.id for _, source in rows)
    recommendations = {
        item.watch_change_id: item for item in (
            db.query(Recommendation)
            .filter(Recommendation.watch_change_id.in_(change_ids)).all()
            if change_ids else []
        )
    }
    investigations = {
        item.watch_change_id: item for item in (
            db.query(Investigation)
            .filter(Investigation.watch_change_id.in_(change_ids)).all()
            if change_ids else []
        )
    }
    weekly_steps = defaultdict(list)
    for step in (
        db.query(ActionStep)
        .filter(ActionStep.watch_change_id.in_(change_ids))
        .order_by(ActionStep.position).all()
        if change_ids else []
    ):
        weekly_steps[step.watch_change_id].append(step)
    prior_watches = {
        watch_id for (watch_id,) in (
            db.query(WatchChange.watch_source_id)
            .filter(WatchChange.watch_source_id.in_(watch_ids),
                    WatchChange.detected_at < start_utc)
            .distinct().all()
            if watch_ids else []
        )
    }
    profile = profile_for(db, account_id)
    relevant = []
    ignored = []
    deadlines = []
    tracked = []
    category_counts = Counter()
    type_counts = Counter()

    for change, source in rows:
        investigation = investigations.get(change.id)
        result = investigation.result if investigation and investigation.status == "completed" else None
        saved = recommendations.get(change.id)
        if saved:
            decision = {
                "recommendation": saved.recommendation,
                "priority": saved.priority,
                "relevance_score": saved.relevance_score,
            }
        else:
            relevance = assess_relevance(
                profile, category=source.category, summary=change.summary,
                why_it_matters=change.why_it_matters, entities=change.entities,
                importance=change.importance, change_type=change.change_type,
            )
            decision = recommend(
                profile=profile, relevance=relevance, investigation=result,
                investigation_status=investigation.status if investigation else None,
            )
        entry = {
            "change_id": change.id,
            "watch_source_id": source.id,
            "category": source.category,
            "summary": change.summary,
            "why_it_matters": change.why_it_matters,
            "recommendation": decision["recommendation"],
            "priority": decision["priority"],
            "relevance_score": decision["relevance_score"],
            "suggested_action": (
                next((step.title for step in weekly_steps[change.id]
                      if step.status != "completed"), None)
            ),
            "deadline": verified_deadline(result),
            "source_url": source.url,
        }
        if (decision["recommendation"] != "skip"
                and decision["relevance_score"] >= 30
                and change.change_type != "cosmetic"):
            relevant.append(entry)
            category_counts[source.category] += 1
            type_counts[change.change_type] += 1
            if source.id in prior_watches or weekly_watch_counts[source.id] > 1:
                tracked.append(entry)
            if entry["deadline"]:
                parsed = _deadline_date(entry["deadline"], today)
                if parsed and 0 <= (parsed - today).days <= 14:
                    deadlines.append(entry)
        else:
            ignored.append(entry)

    relevant.sort(key=lambda item: (
        PRIORITY_ORDER.get(item["priority"], 5), -item["relevance_score"], item["change_id"]
    ))
    deadlines.sort(key=lambda item: _deadline_date(item["deadline"], today))
    pending_rows = (
        db.query(ActionStep, WatchChange, WatchSource)
        .join(WatchChange, WatchChange.id == ActionStep.watch_change_id)
        .join(WatchSource, WatchSource.id == WatchChange.watch_source_id)
        .filter(WatchSource.account_id == account_id, ActionStep.status != "completed")
        .order_by(ActionStep.updated_at.desc())
        .limit(20).all()
    )
    pending = [
        {"step_id": step.id, "change_id": change.id, "title": step.title,
         "status": step.status, "source_url": source.url, "deadline": step.deadline}
        for step, change, source in pending_rows
    ]
    trends = [
        f"{category}: {count} relevant finding{'s' if count != 1 else ''}"
        for category, count in category_counts.most_common()
    ] + [
        f"{kind} updates: {count}" for kind, count in type_counts.most_common()
        if kind in {"deadline", "eligibility", "requirement", "availability"}
    ]
    grouped: dict[str, dict[str, list[dict]]] = {}
    for item in relevant:
        grouped.setdefault(item["priority"], {}).setdefault(item["category"], []).append(item)
    return {
        "period_start": start.isoformat(),
        "period_end": (start + timedelta(days=6)).isoformat(),
        "total_findings": len(rows),
        "relevant_count": len(relevant),
        "grouped_findings": grouped,
        "top_opportunities": relevant[:5],
        "upcoming_deadlines": deadlines,
        "tracked_updates": tracked,
        "pending_actions": pending,
        "deprioritized": ignored,
        "trends": trends,
    }


def render_digest(content: dict) -> tuple[str, str]:
    subject = (
        f"Sentinel weekly intelligence: {content['period_start']} to {content['period_end']}"
    )
    lines = [
        subject,
        f"{content['relevant_count']} relevant of {content['total_findings']} findings this week.",
        "",
    ]
    if content["top_opportunities"]:
        lines.append("Most relevant opportunities:")
        lines.extend(
            f"- {item['summary']} ({item['priority']}, score {item['relevance_score']})"
            f" — {item['source_url']}"
            for item in content["top_opportunities"]
        )
        lines.append("")
    if content["upcoming_deadlines"]:
        lines.append("Upcoming verified deadlines:")
        lines.extend(
            f"- {item['deadline']}: {item['summary']} — {item['source_url']}"
            for item in content["upcoming_deadlines"]
        )
        lines.append("")
    if content["grouped_findings"]:
        lines.append("Findings by priority and category:")
        for priority in sorted(content["grouped_findings"], key=lambda p: PRIORITY_ORDER.get(p, 5)):
            for category, items in sorted(content["grouped_findings"][priority].items()):
                lines.append(f"{priority.title()} / {category} ({len(items)}):")
                lines.extend(_item_line(item) for item in items)
        lines.append("")
    if content["tracked_updates"]:
        lines.append("Updates to previously tracked sources:")
        lines.extend(f"- {item['summary']} — {item['source_url']}" for item in content["tracked_updates"])
        lines.append("")
    if content["pending_actions"]:
        lines.append("Actions still pending:")
        lines.extend(
            f"- {item['title']} ({item['status']})"
            + (f" — deadline {item['deadline']}" if item["deadline"] else "")
            + f" — {item['source_url']}"
            for item in content["pending_actions"]
        )
        lines.append("")
    if content["deprioritized"]:
        lines.append("Ignored or deprioritized this week:")
        lines.extend(
            f"- {item['summary']} ({item['recommendation']}, {item['priority']})"
            f" — {item['source_url']}"
            for item in content["deprioritized"]
        )
        lines.append("")
    if content["trends"]:
        lines.extend(["Patterns this week:", *[f"- {trend}" for trend in content["trends"]]])
    if not content["total_findings"] and not content["pending_actions"]:
        lines.append("No meaningful findings or pending actions this week.")
    return subject, "\n".join(lines).strip() + "\n"


def generate_weekly_digest(db: Session, start: date, *, account_id: int, today: date) -> WeeklyDigest:
    require_account_id(account_id)
    if start.weekday() != 0 or start + timedelta(days=7) > today:
        raise ValueError("week_start must be a completed Monday–Sunday week")
    existing = db.query(WeeklyDigest).filter(WeeklyDigest.account_id == account_id, WeeklyDigest.period_start == start).first()
    if existing:
        return existing
    content = build_digest_content(db, start, account_id=account_id, today=today)
    subject, body = render_digest(content)
    status = "pending" if content["total_findings"] or content["pending_actions"] else "empty"
    digest = WeeklyDigest(
        account_id=account_id, period_start=start, period_end=start + timedelta(days=6),
        status=status, subject=subject, body=body, content=content,
    )
    db.add(digest)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(WeeklyDigest).filter(WeeklyDigest.account_id == account_id, WeeklyDigest.period_start == start).first()
        if existing is None:
            raise
        return existing
    return digest


def dispatch_digest(db: Session, digest: WeeklyDigest) -> WeeklyDigest:
    account = db.get(Account, digest.account_id) if digest.account_id is not None else None
    if account is None or digest.status != "pending" or not email_configured():
        return digest
    now = datetime.now(timezone.utc)
    if digest.next_attempt_at and digest.next_attempt_at > now:
        return digest
    reserved = db.execute(
        update(WeeklyDigest)
        .where(WeeklyDigest.id == digest.id, WeeklyDigest.status == "pending")
        .values(status="sending")
    ).rowcount
    db.commit()
    if not reserved:
        return db.get(WeeklyDigest, digest.id)
    try:
        send_email(digest.subject, digest.body, recipient=account.email)
        digest.status = "sent"
        digest.sent_at = datetime.now(timezone.utc)
        digest.reason = None
        db.commit()
    except Exception as error:
        db.rollback()
        digest = db.get(WeeklyDigest, digest.id)
        digest.attempts += 1
        digest.status = "failed" if digest.attempts >= 5 else "pending"
        digest.next_attempt_at = (
            None if digest.status == "failed" else
            datetime.now(timezone.utc) + timedelta(minutes=min(60, 2 ** digest.attempts))
        )
        digest.reason = str(error)[:500]
        db.commit()
        logger.exception("Weekly digest email failed for %s", digest.period_start)
    return digest
