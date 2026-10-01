"""Persistent semantic memory for one user."""

import logging
from functools import lru_cache

from google import genai
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)
DIMENSIONS = 768


@lru_cache(maxsize=1)
def _client():
    return genai.Client(api_key=settings.gemini_api_key)


def _embedding(content: str) -> list[float]:
    response = _client().models.embed_content(
        model=settings.embedding_model,
        contents=content[:8000],
        config={"output_dimensionality": DIMENSIONS},
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
    kind: str,
    content: str,
    source_key: str,
    source_url: str | None = None,
    metadata: dict | None = None,
) -> int:
    """Upsert a memory. Caller owns the transaction."""
    import json

    vector = _vector(_embedding(content))
    row = db.execute(text("""
        INSERT INTO memories (kind, content, source_key, source_url, metadata, embedding)
        VALUES (:kind, :content, :source_key, :source_url,
                CAST(:metadata AS jsonb), CAST(:embedding AS vector))
        ON CONFLICT (source_key) DO UPDATE SET
            content = EXCLUDED.content,
            source_url = EXCLUDED.source_url,
            metadata = EXCLUDED.metadata,
            embedding = EXCLUDED.embedding,
            updated_at = now()
        RETURNING id
    """), {
        "kind": kind, "content": content, "source_key": source_key,
        "source_url": source_url, "metadata": json.dumps(metadata or {}),
        "embedding": vector,
    }).scalar_one()
    return row


def recall(
    db: Session, query: str, *, limit: int = 5,
    kinds: tuple[str, ...] = ("preference", "interaction", "decision", "outcome", "finding"),
    exclude_key: str | None = None,
) -> list[dict]:
    if not query.strip():
        return []
    vector = _vector(_embedding(query))
    rows = db.execute(text("""
        SELECT id, kind, content, source_key, source_url, metadata,
               1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM memories
        WHERE kind = ANY(:kinds)
          AND (:exclude_key IS NULL OR source_key <> :exclude_key)
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """), {
        "embedding": vector, "kinds": list(kinds),
        "exclude_key": exclude_key, "limit": min(max(limit, 1), 20),
    }).mappings().all()
    return [dict(row) for row in rows if row["similarity"] >= 0.55]


def finding_text(category: str, summary: str, why_it_matters: str, entities: list[str]) -> str:
    return f"Category: {category}. {summary}. {why_it_matters}. Entities: {', '.join(entities)}"


def relevant_context(db: Session, content: str, *, exclude_key: str | None = None) -> list[dict]:
    try:
        return recall(db, content, exclude_key=exclude_key)
    except Exception:
        logger.exception("Memory retrieval failed")
        db.rollback()
        return []
