from sqlalchemy import text

from app.database import engine


def upgrade_schema():
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(
            text(
                "ALTER TABLE user_profiles "
                "ADD COLUMN IF NOT EXISTS preferred_categories "
                "JSONB NOT NULL DEFAULT '[]'::jsonb"
            )
        )
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS memories (
                id BIGSERIAL PRIMARY KEY,
                kind VARCHAR(30) NOT NULL,
                content TEXT NOT NULL,
                source_key TEXT NOT NULL UNIQUE,
                source_url TEXT,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                embedding vector(768) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_memories_kind ON memories (kind)
        """))
