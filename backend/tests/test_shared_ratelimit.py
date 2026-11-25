"""The shared limiter against a real PostgreSQL (CI). Skipped without a server or without SQLAlchemy/psycopg."""
import os
import shutil
import uuid

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("psycopg")
pytestmark = pytest.mark.skipif(
    not (shutil.which("psql") and os.environ.get("PGHOST")), reason="no PostgreSQL available (set PGHOST)")

from sqlalchemy import create_engine, text  # noqa: E402

from novacloud.core.ratelimit import SharedRateLimiter  # noqa: E402
from tests.test_postgres_schema import ROOT, psql  # noqa: E402


@pytest.fixture(scope="module")
def engine():
    name = "nc_rl_" + uuid.uuid4().hex[:8]
    psql("postgres", f"CREATE DATABASE {name}")
    psql(name, file=str(ROOT / "migrations/sql/0005_rate_limits.sql"))
    host, port, user = os.environ["PGHOST"], os.environ.get("PGPORT", "5432"), os.environ.get("PGUSER", "postgres")
    pw = os.environ.get("PGPASSWORD", "")
    url = f"postgresql+psycopg://{user}:{pw}@{host}:{port}/{name}" if not host.startswith("/") else \
        f"postgresql+psycopg://{user}@/{name}?host={host}&port={port}"
    e = create_engine(url)
    yield e
    e.dispose()
    psql("postgres", f"DROP DATABASE {name}", check=False)


def test_two_replicas_share_one_budget_and_window_resets(engine):
    t = [1_000_000.0]
    a = SharedRateLimiter(engine, "login", 3, 60, clock=lambda: t[0])
    b = SharedRateLimiter(engine, "login", 3, 60, clock=lambda: t[0])  # a second API replica
    assert [a.allow("ip1"), b.allow("ip1"), a.allow("ip1")] == [True, True, True]
    assert not b.allow("ip1") and not a.allow("ip1")  # the budget is shared, not per process
    assert a.allow("ip2")  # other keys are independent
    t[0] += 61
    assert b.allow("ip1")  # next window


def test_keys_are_hashed_and_old_windows_purged(engine):
    t = [2_000_000.0]
    lim = SharedRateLimiter(engine, "api", 5, 60, clock=lambda: t[0])
    lim.allow("someone@example.com")
    t[0] += 600
    lim.allow("other")
    with engine.connect() as c:
        keys = [r[0] for r in c.execute(text("SELECT key FROM rate_limits"))]
        old = c.execute(text("SELECT count(*) FROM rate_limits WHERE window_start < :w"), dict(w=int(t[0] // 60) - 1)).scalar_one()
    assert all(len(k) == 64 and "@" not in k for k in keys)
    assert old == 0


def test_database_failure_degrades_to_process_limit():
    broken = create_engine("postgresql+psycopg://nobody@127.0.0.1:1/none", connect_args={"connect_timeout": 1})
    lim = SharedRateLimiter(broken, "login", 2, 60)
    assert [lim.allow("k"), lim.allow("k"), lim.allow("k")] == [True, True, False]
