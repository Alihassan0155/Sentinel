from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Investigation, Recommendation, UserProfile, WatchChange, WatchSource
from app.services.relevance import assess_relevance
from app.services.recommendation import recommend


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
    change_ids = [change.id for change, _ in changes]
    investigations = (
        db.query(Investigation)
        .filter(Investigation.watch_change_id.in_(change_ids))
        .all()
        if change_ids
        else []
    )
    investigation_by_change = {
        investigation.watch_change_id: investigation
        for investigation in investigations
    }
    recommendations = (
        db.query(Recommendation)
        .filter(Recommendation.watch_change_id.in_(change_ids))
        .all()
        if change_ids else []
    )
    recommendation_by_change = {
        item.watch_change_id: item for item in recommendations
    }

    results = []
    for change, category in changes:
        relevance = assess_relevance(
            profile,
            category=category,
            summary=change.summary,
            why_it_matters=change.why_it_matters,
            entities=change.entities,
            importance=change.importance,
            change_type=change.change_type,
        )
        investigation = investigation_by_change.get(change.id)
        saved_recommendation = recommendation_by_change.get(change.id)
        recommendation = (
            {
                "recommendation": saved_recommendation.recommendation,
                "reasons": saved_recommendation.reasons,
                "priority": saved_recommendation.priority,
                "relevance_score": saved_recommendation.relevance_score,
            }
            if saved_recommendation else recommend(
                profile=profile,
                relevance=relevance,
                investigation=(investigation.result if investigation and
                               investigation.status == "completed" else None),
                investigation_status=investigation.status if investigation else None,
            )
        )
        results.append({
            "id": change.id,
            "watch_source_id": change.watch_source_id,
            "importance": change.importance,
            "change_type": change.change_type,
            "summary": change.summary,
            "why_it_matters": change.why_it_matters,
            "should_notify": (
                change.should_notify and recommendation["recommendation"] == "recommended"
            ),
            "recommendation": recommendation,
            "entities": change.entities,
            "detected_at": change.detected_at,
            "investigation": (
                {
                    "status": investigation_by_change[change.id].status,
                    "result": investigation_by_change[change.id].result,
                    "investigated_at": (
                        investigation_by_change[change.id].investigated_at
                    ),
                }
                if change.id in investigation_by_change
                else None
            ),
            **relevance,
        })

    return results
