from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UserProfile, WatchChange, WatchSource
from app.services.relevance import assess_relevance


router = APIRouter(
    prefix="/changes",
    tags=["Changes"],
)


@router.get("")
def get_changes(
    db: Session = Depends(get_db),
):
    changes = (
        db.query(WatchChange, WatchSource.category)
        .join(WatchSource, WatchSource.id == WatchChange.watch_source_id)
        .order_by(WatchChange.detected_at.desc())
        .all()
    )
    profile = db.get(UserProfile, 1)

    results = []
    for change, category in changes:
        relevance = assess_relevance(
            profile,
            category=category,
            summary=change.summary,
            why_it_matters=change.why_it_matters,
            entities=change.entities,
            importance=change.importance,
        )
        results.append({
            "id": change.id,
            "watch_source_id": change.watch_source_id,
            "importance": change.importance,
            "change_type": change.change_type,
            "summary": change.summary,
            "why_it_matters": change.why_it_matters,
            "should_notify": (
                change.should_notify and relevance["priority"] != "ignore"
            ),
            "entities": change.entities,
            "detected_at": change.detected_at,
            **relevance,
        })

    return results