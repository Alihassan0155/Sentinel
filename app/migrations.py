from sqlalchemy import text

from app.database import engine


def upgrade_schema():
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE user_profiles "
                "ADD COLUMN IF NOT EXISTS preferred_categories "
                "JSONB NOT NULL DEFAULT '[]'::jsonb"
            )
        )