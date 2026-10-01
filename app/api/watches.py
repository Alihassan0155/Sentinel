import hashlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.watch import WatchCreate, WatchResponse
from app.services.diff import detect_changes
from app.services.monitor import check_watch as run_watch_check
from app.services.scheduler import schedule_watch
from app.services.semantic import analyze_change

from app.models import Recommendation, UserProfile, WatchChange, WatchSnapshot, WatchSource, snapshot, watch
from app.services.memory import finding_text, relevant_context, remember
from app.services.relevance import assess_relevance
from app.services.recommendation import recommend

router = APIRouter(
    prefix="/watches",
    tags=["Watches"],
)


@router.post("", response_model=WatchResponse)
def create_watch(
    watch: WatchCreate,
    db: Session = Depends(get_db),
):
    source = WatchSource(
        name=watch.name,
        url=str(watch.url),
        category=watch.category,
        check_interval_minutes=watch.check_interval_minutes,
    )

    db.add(source)
    db.commit()
    db.refresh(source)
    if source.active:
        schedule_watch(source)

    return source


@router.get("", response_model=list[WatchResponse])
def get_watches(
    db: Session = Depends(get_db),
):
    return db.query(WatchSource).all()


@router.post("/{watch_id}/check")
def check_watch_endpoint(
    watch_id: int,
    db: Session = Depends(get_db),
):
    watch = db.get(WatchSource, watch_id)

    if not watch:
        raise HTTPException(
            status_code=404,
            detail="Watch not found",
        )

    return run_watch_check(watch, db)

@router.post("/{watch_id}/test-change")
def test_change(
    watch_id: int,
    db: Session = Depends(get_db),
):
    watch = db.get(WatchSource, watch_id)

    if not watch:
        raise HTTPException(
            status_code=404,
            detail="Watch not found",
        )

    previous_snapshot = (
        db.query(WatchSnapshot)
        .filter(
            WatchSnapshot.watch_source_id == watch.id
        )
        .order_by(
            WatchSnapshot.fetched_at.desc()
        )
        .first()
    )

    if not previous_snapshot:
        raise HTTPException(
            status_code=400,
            detail="Create a normal snapshot first.",
        )

    # Simulated website update
    new_content = previous_snapshot.content_text + """
NEW JOB POSTING
Position: AI/ML Engineer
Deadline: October 15, 2026
Eligibility: Bachelor's degree in Computer Science or related field.
"""

    change_data = detect_changes(
        previous_snapshot.content_text,
        new_content,
    )

    semantic_analysis = analyze_change(
        source_name=watch.name,
        category=watch.category,
        added=change_data["added"],
        removed=change_data["removed"],
        replaced=change_data["replaced"],
    )
    profile = db.get(UserProfile, 1)
    memories = relevant_context(db, finding_text(
        watch.category, semantic_analysis.summary,
        semantic_analysis.why_it_matters, semantic_analysis.entities,
    ))

    snapshot = WatchSnapshot(
        watch_source_id=watch.id,
        content_hash=hashlib.sha256(
            new_content.encode("utf-8")
        ).hexdigest(),
        content_text=new_content,
    )

    db.add(snapshot)
    db.flush()

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
    db.flush()
    relevance = assess_relevance(
        profile, category=watch.category, summary=change.summary,
        why_it_matters=change.why_it_matters, entities=change.entities,
        importance=change.importance, change_type=change.change_type,
        memories=memories,
    )
    recommendation = recommend(profile=profile, relevance=relevance, memories=memories)
    db.add(Recommendation(watch_change_id=change.id, **recommendation))
    db.commit()

    try:
        remember(
            db, kind="finding", source_key=f"finding:change:{change.id}",
            source_url=watch.url,
            content=finding_text(watch.category, change.summary,
                                 change.why_it_matters, change.entities),
            metadata={"change_id": change.id, "watch_id": watch.id},
        )
        db.commit()
    except Exception:
        db.rollback()

    return {
        "watch_id": watch.id,
        "changed": True,
        "change": semantic_analysis.model_dump(),
        "recommendation": recommendation,
        **relevance,
        "added": change_data["added"],
        "removed": change_data["removed"],
        "replaced": change_data["replaced"],
    }
