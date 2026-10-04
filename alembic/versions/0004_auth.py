"""Persistent accounts and revocable sessions."""
from alembic import op
import sqlalchemy as sa
revision = "0004_auth"
down_revision = "0003_snapshot_lookup"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("accounts", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("email", sa.String(254), nullable=False, unique=True),
                    sa.Column("name", sa.String(100), nullable=False),
                    sa.Column("password_hash", sa.String(256), nullable=False))
    op.create_table("auth_sessions", sa.Column("token_hash", sa.String(64), primary_key=True),
                    sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("expires_at", sa.DateTime(), nullable=False))
    op.create_index("ix_auth_sessions_account_id", "auth_sessions", ["account_id"])
    op.create_table("auth_attempts", sa.Column("key", sa.String(64), primary_key=True),
                    sa.Column("count", sa.Integer(), nullable=False),
                    sa.Column("window_start", sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table("auth_attempts")
    op.drop_table("auth_sessions")
    op.drop_table("accounts")
