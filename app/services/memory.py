"""Persistent semantic memory scoped to an account."""

import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.services.llm import embed
from app.services.ownership import require_account_id

logger = logging.getLogger(__name__)
DIMENSIONS = 768


def _embedding(content: str) -> list[float]:
    response = embed(
        model=settings.embedding_model,
        content=content[:8000], dimensions=DIMENSIONS,
    )
    values = response.embeddings[0].values
    if len(values) != DIMENSIONS:
        raise ValueError("Unexpected embedding dimension")
    return values


def _vector(values: list[float]) -> str:
    return "[" + ",".join(str(value) for value in values) + "]"


def remember(
    db: Session,
    *,
    account_id: int,
    kind: str,
    content: str,
    source_key: str,
    source_url: str | None = None,
    metadata: dict | None = None,
) -> int:
    """Upsert a memory. Caller owns the transaction."""
    import json

    require_account_id(account_id)
    vector = _vector(_embedding(content))
    row = db.execute(text("""
        INSERT INTO memories (account_id, kind, content, source_key, source_url, metadata, embedding)
        VALUES (:account_id, :kind, :content, :source_key, :source_url,
                CAST(:metadata AS jsonb), CAST(:embedding AS vector))
        ON CONFLICT (account_id, source_key) DO UPDATE SET
            content = EXCLUDED.content,
            source_url = EXCLUDED.source_url,
            metadata = EXCLUDED.metadata,
            embedding = EXCLUDED.embedding,
            updated_at = now()
        RETURNING id
    """), {
        "account_id": account_id, "kind": kind, "content": content, "source_key": source_key,
        "source_url": source_url, "metadata": json.dumps(metadata or {}),
        "embedding": vector,
    }).scalar_one()
    return row


def recall(
    db: Session, query: str, *, account_id: int, limit: int = 5,
    kinds: tuple[str, ...] = ("preference", "interaction", "decision", "outcome", "finding"),
    exclude_key: str | None = None,
) -> list[dict]:
    require_account_id(account_id)
    if not query.strip():
        return []
    vector = _vector(_embedding(query))
    rows = db.execute(text("""
        SELECT id, kind, content, source_key, source_url, metadata,
               1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM memories
        WHERE account_id = :account_id AND kind = ANY(:kinds)
          AND (CAST(:exclude_key AS text) IS NULL OR source_key <> CAST(:exclude_key AS text))
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """), {
        "account_id": account_id, "embedding": vector, "kinds": list(kinds),
        "exclude_key": exclude_key, "limit": min(max(limit, 1), 20),
    }).mappings().all()
    return [dict(row) for row in rows if row["similarity"] >= 0.55]


def finding_text(category: str, summary: str, why_it_matters: str, entities: list[str]) -> str:
    return f"Category: {category}. {summary}. {why_it_matters}. Entities: {', '.join(entities)}"


def relevant_context(db: Session, content: str, *, account_id: int, exclude_key: str | None = None) -> list[dict]:
    try:
        return recall(db, content, account_id=account_id, exclude_key=exclude_key)
    except Exception:
        logger.exception("Memory retrieval failed")
        db.rollback()
        return []
