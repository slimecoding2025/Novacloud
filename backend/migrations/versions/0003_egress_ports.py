"""subnet egress policy and instance published port

Revision ID: 0003
Revises: 0002
"""
from pathlib import Path

from alembic import op

revision = "0003"
down_revision = "0002"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0003_egress_ports.sql"


def upgrade():
    op.get_bind().exec_driver_sql(SQL.read_text())


def downgrade():
    op.execute("DROP INDEX instances_published_port_uniq")
    op.execute("ALTER TABLE instances DROP CONSTRAINT instances_published_port_range, DROP COLUMN published_port")
    op.execute("ALTER TABLE subnets DROP COLUMN egress")
