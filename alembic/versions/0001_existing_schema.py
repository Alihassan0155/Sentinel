"""Baseline existing Sentinel schema for fresh and pre-Alembic databases.

Revision ID: 0001_existing_schema
Revises:
"""

from alembic import op

revision = "0001_existing_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY,
            skills JSONB NOT NULL DEFAULT '[]'::jsonb,
            degree VARCHAR(150),
            interests JSONB NOT NULL DEFAULT '[]'::jsonb,
            desired_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
            locations JSONB NOT NULL DEFAULT '[]'::jsonb,
            preferred_categories JSONB NOT NULL DEFAULT '[]'::jsonb,
            salary_min INTEGER, salary_max INTEGER,
            available_resources JSONB NOT NULL DEFAULT '[]'::jsonb
        )
    """)
    op.execute("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferred_categories JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS available_resources JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("""
        CREATE TABLE IF NOT EXISTS watch_sources (
            id SERIAL PRIMARY KEY, name VARCHAR(255) NOT NULL,
            url TEXT NOT NULL UNIQUE, category VARCHAR(100) NOT NULL,
            check_interval_minutes INTEGER NOT NULL DEFAULT 30,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            last_checked_at TIMESTAMP, created_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS watch_snapshots (
            id SERIAL PRIMARY KEY,
            watch_source_id INTEGER NOT NULL REFERENCES watch_sources(id),
            content_hash TEXT NOT NULL, content_text TEXT NOT NULL,
            fetched_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS watch_changes (
            id SERIAL PRIMARY KEY,
            watch_source_id INTEGER NOT NULL REFERENCES watch_sources(id),
            snapshot_id INTEGER NOT NULL REFERENCES watch_snapshots(id),
            importance VARCHAR(20) NOT NULL, change_type VARCHAR(50) NOT NULL,
            summary TEXT NOT NULL, why_it_matters TEXT NOT NULL,
            should_notify BOOLEAN NOT NULL DEFAULT FALSE,
            entities JSONB NOT NULL DEFAULT '[]'::jsonb,
            detected_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS investigations (
            id SERIAL PRIMARY KEY,
            watch_change_id INTEGER NOT NULL UNIQUE REFERENCES watch_changes(id),
            status VARCHAR(20) NOT NULL, result JSONB, error TEXT,
            investigated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            id SERIAL PRIMARY KEY,
            watch_change_id INTEGER NOT NULL UNIQUE REFERENCES watch_changes(id),
            recommendation VARCHAR(20) NOT NULL, priority VARCHAR(20) NOT NULL,
            reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
            relevance_score INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS action_steps (
            id SERIAL PRIMARY KEY,
            watch_change_id INTEGER NOT NULL REFERENCES watch_changes(id),
            position INTEGER NOT NULL, title TEXT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            resource TEXT, resource_status VARCHAR(20),
            source_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
            supporting_quote TEXT, deadline TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_action_step_position UNIQUE (watch_change_id, position)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            watch_change_id INTEGER NOT NULL UNIQUE REFERENCES watch_changes(id),
            watch_source_id INTEGER NOT NULL REFERENCES watch_sources(id),
            status VARCHAR(20) NOT NULL, reason TEXT, subject TEXT NOT NULL,
            body TEXT NOT NULL, urgent BOOLEAN NOT NULL DEFAULT FALSE,
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(), sent_at TIMESTAMPTZ
        )
    """)
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_cooldown ON notifications (watch_source_id, status, sent_at)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS weekly_digests (
            id SERIAL PRIMARY KEY, period_start DATE NOT NULL UNIQUE,
            period_end DATE NOT NULL, status VARCHAR(20) NOT NULL,
            subject TEXT NOT NULL, body TEXT NOT NULL, content JSONB NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TIMESTAMPTZ,
            reason TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            sent_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id BIGSERIAL PRIMARY KEY, kind VARCHAR(30) NOT NULL,
            content TEXT NOT NULL, source_key TEXT NOT NULL UNIQUE,
            source_url TEXT, metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            embedding vector(768) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_memories_kind ON memories (kind)")


def downgrade():
    raise RuntimeError("The baseline migration cannot safely remove existing user data")
