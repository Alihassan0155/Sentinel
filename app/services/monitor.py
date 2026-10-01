import hashlib
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models import UserProfile, WatchChange, WatchSnapshot, WatchSource
from app.services.diff import detect_changes
from app.services.relevance import assess_relevance
from app.services.semantic import analyze_change


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36"
)
logger = logging.getLogger(__name__)


def fetch_page(url: str) -> str:
    with httpx.Client(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        response = client.get(url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    # Preserve block boundaries so diffing is meaningful.
    raw_text = soup.get_text(separator="\n")

    lines = []

    for line in raw_text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


def check_watch(watch: WatchSource, db: Session):
    logger.info("Starting check for watch %s (%s)", watch.id, watch.url)

    try:
        content = fetch_page(watch.url)
        content_hash = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

        previous_snapshot = (
            db.query(WatchSnapshot)
            .filter(WatchSnapshot.watch_source_id == watch.id)
            .order_by(WatchSnapshot.fetched_at.desc())
            .first()
        )

        change_data = {
            "changed": False,
            "added": [],
            "removed": [],
            "replaced": [],
            "added_count": 0,
            "removed_count": 0,
        }
        semantic_analysis = None
        relevance = {
            "relevance_score": 0,
            "reasons": ["No profile preferences configured."],
            "priority": "ignore",
        }

        if (
            previous_snapshot is not None
            and previous_snapshot.content_hash != content_hash
        ):
            change_data = detect_changes(
                previous_snapshot.content_text,
                content,
            )
            semantic_analysis = analyze_change(
                source_name=watch.name,
                category=watch.category,
                added=change_data["added"],
                removed=change_data["removed"],
                replaced=change_data["replaced"],
            )
            relevance = assess_relevance(
                db.get(UserProfile, 1),
                category=watch.category,
                summary=semantic_analysis.summary,
                why_it_matters=semantic_analysis.why_it_matters,
                entities=semantic_analysis.entities,
                importance=semantic_analysis.importance,
                change_type=semantic_analysis.change_type,
            )

        snapshot = WatchSnapshot(
            watch_source_id=watch.id,
            content_hash=content_hash,
            content_text=content,
        )
        db.add(snapshot)
        db.flush()

        if semantic_analysis:
            change = WatchChange(
                watch_source_id=watch.id,
                snapshot_id=snapshot.id,
                importance=semantic_analysis.importance,
                change_type=semantic_analysis.change_type,
                summary=semantic_analysis.summary,
                why_it_matters=semantic_analysis.why_it_matters,
                should_notify=semantic_analysis.should_notify,
                entities=semantic_analysis.entities,
            )
            db.add(change)

        watch.last_checked_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info(
        "Completed check for watch %s: changed=%s",
        watch.id,
        change_data["changed"],
    )
    semantic_result = (
        semantic_analysis.model_dump()
        if semantic_analysis
        else None
    )
    if semantic_result is not None:
        semantic_result["should_notify"] = (
            semantic_result["should_notify"]
            and relevance["priority"] != "ignore"
        )

    return {
        "watch_id": watch.id,
        "name": watch.name,
        "url": watch.url,
        "changed": change_data["changed"],
        "added_count": change_data["added_count"],
        "removed_count": change_data["removed_count"],
        "added": change_data["added"],
        "removed": change_data["removed"],
        "replaced": change_data["replaced"],
        "semantic_analysis": semantic_result,
        **relevance,
        "content_length": len(content),
        "checked_at": watch.last_checked_at,
    }