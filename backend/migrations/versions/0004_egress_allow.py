"""subnet egress allow-list

Revision ID: 0004
Revises: 0003
"""
from pathlib import Path

from alembic import op

revision = "0004"
down_revision = "0003"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0004_egress_allow.sql"


def upgrade():
    op.get_bind().exec_driver_sql(SQL.read_text())


def downgrade():
    op.execute("ALTER TABLE subnets DROP CONSTRAINT subnets_allow_needs_egress, DROP COLUMN egress_allow")
