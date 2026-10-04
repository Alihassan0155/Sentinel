"""Account ownership, preserving historical shared records as unassigned."""
from alembic import op
import sqlalchemy as sa
revision = "0005_user_isolation"
down_revision = "0004_auth"
branch_labels = None
depends_on = None


def replace_unique(table, old_columns, new_columns, name):
    for constraint in sa.inspect(op.get_bind()).get_unique_constraints(table):
        if constraint["column_names"] == old_columns:
            op.drop_constraint(constraint["name"], table, type_="unique")
    op.create_unique_constraint(name, table, new_columns)


def upgrade():
    # There is no trustworthy ownership metadata on legacy shared data. Never
    # assign it to the first signup or make it accessible to all accounts.
    for table in ("watch_sources", "user_profiles", "weekly_digests", "memories"):
        op.add_column(table, sa.Column("account_id", sa.Integer(), nullable=True))
        op.create_foreign_key(f"fk_{table}_account", table, "accounts", ["account_id"], ["id"])
        op.create_index(f"ix_{table}_account_id", table, ["account_id"])
    op.create_unique_constraint("uq_user_profiles_account", "user_profiles", ["account_id"])
    replace_unique("watch_sources", ["url"], ["account_id", "url"], "uq_watch_sources_account_url")
    replace_unique("weekly_digests", ["period_start"], ["account_id", "period_start"], "uq_weekly_digests_account_period")
    replace_unique("memories", ["source_key"], ["account_id", "source_key"], "uq_memories_account_source")
    # Legacy profiles used a manually allocated singleton primary key.
    op.execute("CREATE SEQUENCE IF NOT EXISTS user_profiles_id_seq OWNED BY user_profiles.id")
    op.execute("SELECT setval('user_profiles_id_seq', COALESCE((SELECT MAX(id) FROM user_profiles), 0) + 1, false)")
    op.execute("ALTER TABLE user_profiles ALTER COLUMN id SET DEFAULT nextval('user_profiles_id_seq')")


def downgrade():
    raise RuntimeError("Downgrading would merge private workspaces and remove ownership; restore a pre-migration backup instead")
