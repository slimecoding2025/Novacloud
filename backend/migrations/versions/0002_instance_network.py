"""instances: network attachment columns

Revision ID: 0002
Revises: 0001
"""
from pathlib import Path

from alembic import op

revision = "0002"
down_revision = "0001"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0002_instance_network.sql"


def upgrade():
    op.get_bind().exec_driver_sql(SQL.read_text())


def downgrade():
    op.execute("ALTER TABLE instances DROP CONSTRAINT instances_network_all_or_none, "
               "DROP COLUMN ip, DROP COLUMN subnet_id, DROP COLUMN network_id")
