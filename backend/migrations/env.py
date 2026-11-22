from alembic import context
from sqlalchemy import create_engine

from novacloud.core.config import Settings

with create_engine(Settings().database_url).connect() as conn:
    context.configure(connection=conn, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()
