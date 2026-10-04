"""Durable check jobs, shared request limits, and change deduplication.

Revision ID: 0002_worker_hardening
Revises: 0001_existing_schema
"""

from alembic import op

revision = "0002_worker_hardening"
down_revision = "0001_existing_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE watch_changes ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_watch_changes_source_hash
        ON watch_changes (watch_source_id, content_hash)
        WHERE content_hash IS NOT NULL
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS check_jobs (
            id SERIAL PRIMARY KEY,
            watch_source_id INTEGER NOT NULL REFERENCES watch_sources(id),
            mode VARCHAR(20) NOT NULL DEFAULT 'normal',
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
            error TEXT, result JSONB
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_check_jobs_due ON check_jobs (status, available_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_check_jobs_watch_created ON check_jobs (watch_source_id, created_at)")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_check_jobs_active_watch
        ON check_jobs (watch_source_id) WHERE status IN ('pending', 'running')
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            key VARCHAR(255) PRIMARY KEY,
            next_allowed_at TIMESTAMPTZ NOT NULL
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS rate_limits")
    op.execute("DROP TABLE IF EXISTS check_jobs")
    op.execute("DROP INDEX IF EXISTS uq_watch_changes_source_hash")
    op.execute("ALTER TABLE watch_changes DROP COLUMN IF EXISTS content_hash")
