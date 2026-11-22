"""initial schema (executes sql/0001_initial.sql, which is also tested directly against PostgreSQL)

Revision ID: 0001
Revises:
"""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None

SQL = Path(__file__).resolve().parents[1] / "sql" / "0001_initial.sql"


def upgrade():
    op.get_bind().exec_driver_sql(SQL.read_text())


def downgrade():
    op.execute("""
        DROP TABLE IF EXISTS ip_allocations, subnets, networks, storage_objects, jobs, instances,
                             audit_log, sessions, memberships, users, organizations CASCADE;
        DROP FUNCTION IF EXISTS audit_log_immutable();
    """)
