from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WatchChange
from app.services.memory import recall, remember

router = APIRouter(prefix="/memory", tags=["Memory"])


class MemoryInput(BaseModel):
    kind: str = Field(pattern="^(preference|interaction|decision|outcome)$")
    content: str = Field(min_length=3, max_length=4000)
    change_id: int | None = None


class FeedbackInput(BaseModel):
    decision: str = Field(pattern="^(interested|saved|applied|dismissed|irrelevant)$")
    note: str | None = Field(default=None, max_length=1000)


@router.post("")
def add_memory(item: MemoryInput, db: Session = Depends(get_db)):
    if item.change_id is not None and db.get(WatchChange, item.change_id) is None:
        raise HTTPException(404, "Change not found")
    try:
        import uuid
        key = f"{item.kind}:{uuid.uuid4()}"
        memory_id = remember(db, kind=item.kind, content=item.content,
                             source_key=key, metadata={"change_id": item.change_id})
        db.commit()
        return {"id": memory_id, "source_key": key}
    except Exception:
        db.rollback()
        raise


@router.post("/changes/{change_id}/feedback")
def record_feedback(change_id: int, feedback: FeedbackInput, db: Session = Depends(get_db)):
    change = db.get(WatchChange, change_id)
    if change is None:
        raise HTTPException(404, "Change not found")
    content = f"User {feedback.decision} finding: {change.summary}. {change.why_it_matters}"
    if feedback.note:
        content += f". User note: {feedback.note}"
    try:
        memory_id = remember(db, kind="decision", content=content,
                             source_key=f"decision:change:{change_id}",
                             metadata={"change_id": change_id, "decision": feedback.decision})
        db.commit()
        return {"id": memory_id, "decision": feedback.decision}
    except Exception:
        db.rollback()
        raise


@router.get("/search")
def search_memory(q: str, limit: int = 5, db: Session = Depends(get_db)):
    return recall(db, q, limit=limit)


@router.get("")
def list_memories(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT id, kind, content, source_key, source_url, metadata, updated_at
        FROM memories ORDER BY updated_at DESC LIMIT :limit
    """), {"limit": min(max(limit, 1), 100)}).mappings().all()
    return [dict(row) for row in rows]
