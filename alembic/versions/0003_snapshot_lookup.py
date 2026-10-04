"""Index prior snapshot lookup for change deduplication.

Revision ID: 0003_snapshot_lookup
Revises: 0002_worker_hardening
"""

from alembic import op

revision = "0003_snapshot_lookup"
down_revision = "0002_worker_hardening"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_watch_snapshots_source_hash
        ON watch_snapshots (watch_source_id, content_hash)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_watch_snapshots_source_hash")
