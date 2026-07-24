"""initial persistent platform models

Revision ID: 20260724_0001
Revises:
Create Date: 2026-07-24
"""

from alembic import op

from telegram_codex_agent.db.models import Base

revision = "20260724_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=connection)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
