"""shared rate limiter table

Revision ID: 0005
Revises: 0004
"""
from pathlib import Path

from alembic import op

revision = "0005"
down_revision = "0004"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0005_rate_limits.sql"


def upgrade():
    op.get_bind().exec_driver_sql(SQL.read_text())


def downgrade():
    op.execute("DROP TABLE rate_limits")
