import hashlib
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Investigation,
    Recommendation,
    UserProfile,
    WatchChange,
    WatchSnapshot,
    WatchSource,
)
from app.services.diff import detect_changes
from app.services.investigation import investigate_change
from app.services.memory import finding_text, relevant_context, remember
from app.services.relevance import assess_relevance, qualifies_for_investigation
from app.services.recommendation import recommend
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
        user_profile = None
        change_record = None
        change_id = None
        investigation_record = None
        recommendation_record = None
        memory_context = []
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
            user_profile = db.get(UserProfile, 1)
            semantic_analysis = analyze_change(
                source_name=watch.name,
                category=watch.category,
                added=change_data["added"],
                removed=change_data["removed"],
                replaced=change_data["replaced"],
            )
            memory_content = finding_text(
                watch.category, semantic_analysis.summary,
                semantic_analysis.why_it_matters, semantic_analysis.entities,
            )
            memory_context = relevant_context(db, memory_content)
            relevance = assess_relevance(
                user_profile,
                category=watch.category,
                summary=semantic_analysis.summary,
                why_it_matters=semantic_analysis.why_it_matters,
                entities=semantic_analysis.entities,
                importance=semantic_analysis.importance,
                change_type=semantic_analysis.change_type,
                memories=memory_context,
            )

        snapshot = WatchSnapshot(
            watch_source_id=watch.id,
            content_hash=content_hash,
            content_text=content,
        )
        db.add(snapshot)
        db.flush()

        if semantic_analysis:
            change_record = WatchChange(
                watch_source_id=watch.id,
                snapshot_id=snapshot.id,
                importance=semantic_analysis.importance,
                change_type=semantic_analysis.change_type,
                summary=semantic_analysis.summary,
                why_it_matters=semantic_analysis.why_it_matters,
                should_notify=semantic_analysis.should_notify,
                entities=semantic_analysis.entities,
            )
            db.add(change_record)
            db.flush()
            change_id = change_record.id

        watch.last_checked_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()
        raise

    if change_record is not None:
        try:
            remember(
                db, kind="finding", source_key=f"finding:change:{change_id}",
                source_url=watch.url,
                content=finding_text(watch.category, change_record.summary,
                                     change_record.why_it_matters, change_record.entities),
                metadata={"change_id": change_id, "watch_id": watch.id},
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not remember change %s", change_id)

    if (
        change_record is not None
        and change_id is not None
        and qualifies_for_investigation(
            relevance["relevance_score"],
            relevance["priority"],
            settings.investigation_threshold,
        )
    ):
        logger.info(
            "Starting investigation for change %s (score=%s, priority=%s)",
            change_id,
            relevance["relevance_score"],
            relevance["priority"],
        )
        try:
            result = investigate_change(
                change_record,
                watch.url,
                watch.category,
                user_profile,
                memories=memory_context,
            )
            investigation_record = Investigation(
                watch_change_id=change_id,
                status="completed",
                result=result.model_dump(mode="json"),
            )
            db.add(investigation_record)
            db.commit()
            logger.info("Investigation completed for change %s", change_id)
        except Exception as error:
            db.rollback()
            logger.exception("Investigation failed for change %s", change_id)
            try:
                investigation_record = Investigation(
                    watch_change_id=change_id,
                    status="failed",
                    error=str(error)[:1000],
                )
                db.add(investigation_record)
                db.commit()
            except Exception:
                db.rollback()
                investigation_record = None
                logger.exception(
                    "Could not persist failed investigation for change %s",
                    change_id,
                )

    if change_record is not None:
        recommendation_data = recommend(
            profile=user_profile,
            relevance=relevance,
            memories=memory_context,
            investigation=(
                investigation_record.result if investigation_record
                and investigation_record.status == "completed" else None
            ),
            investigation_status=(
                investigation_record.status if investigation_record else None
            ),
        )
        recommendation_record = Recommendation(
            watch_change_id=change_id,
            **recommendation_data,
        )
        try:
            db.add(recommendation_record)
            db.commit()
        except Exception:
            db.rollback()
            recommendation_record = None
            logger.exception("Could not persist recommendation for change %s", change_id)

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
            and recommendation_record is not None
            and recommendation_record.recommendation == "recommended"
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
        "recommendation": (
            {
                "recommendation": recommendation_record.recommendation,
                "reasons": recommendation_record.reasons,
                "priority": recommendation_record.priority,
                "relevance_score": recommendation_record.relevance_score,
            }
            if recommendation_record else None
        ),
        "investigation": (
            {
                "status": investigation_record.status,
                "result": investigation_record.result,
                "investigated_at": investigation_record.investigated_at,
            }
            if investigation_record
            else None
        ),
        "content_length": len(content),
        "checked_at": watch.last_checked_at,
    }
