"""Verifies the real PostgreSQL schema with psql. Needs a reachable server:
   export PGHOST=... PGPORT=... PGUSER=...   (skipped automatically otherwise)."""
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    not (shutil.which("psql") and os.environ.get("PGHOST")), reason="no PostgreSQL available (set PGHOST)")

O1, O2 = str(uuid.uuid4()), str(uuid.uuid4())


def psql(db, sql=None, file=None, user=None, check=True):
    cmd = ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", db, "-t", "-A"]
    if user:
        cmd += ["-U", user]
    cmd += ["-f", file] if file else ["-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode:
        raise AssertionError(r.stderr)
    return r


@pytest.fixture(scope="module")
def db():
    name = "nc_test_" + uuid.uuid4().hex[:8]
    psql("postgres", f"CREATE DATABASE {name}")
    psql(name, file=str(ROOT / "migrations/sql/0001_initial.sql"))
    psql(name, file=str(ROOT.parent / "deploy/postgres/roles.sql"))
    psql(name, f"INSERT INTO organizations(id,name) VALUES ('{O1}','a'),('{O2}','b')")
    yield name
    psql("postgres", f"DROP DATABASE {name}", check=False)


def audit_insert(h, prev):
    return (f"INSERT INTO audit_log(actor_id,action,resource_type,resource_id,result,ts,prev_hash,hash) "
            f"VALUES ('u','a','r','1','success','t','{prev}','{h}')")


def test_audit_log_append_only_even_for_superuser(db):
    psql(db, audit_insert("h1", "p0"))
    assert "append-only" in psql(db, "UPDATE audit_log SET action='x'", check=False).stderr
    assert "append-only" in psql(db, "DELETE FROM audit_log", check=False).stderr
    assert "append-only" in psql(db, "TRUNCATE audit_log", check=False).stderr


def test_audit_chain_cannot_fork(db):
    assert psql(db, audit_insert("h2", "p0"), check=False).returncode != 0  # same prev_hash twice


def test_app_role_has_no_update_delete_on_audit(db):
    r = psql(db, "SET ROLE novacloud_app; UPDATE audit_log SET action='x'", check=False)
    assert "permission denied" in r.stderr
    assert psql(db, "SET ROLE novacloud_app; SELECT count(*) FROM audit_log").stdout.strip().splitlines()[-1] == "1"


def test_idempotency_key_unique_per_org(db):
    ins = lambda org, key: (f"INSERT INTO jobs(id,organization_id,kind,payload,idempotency_key) "  # noqa: E731
                            f"VALUES ('{uuid.uuid4()}','{org}','k','{{}}','{key}')")
    psql(db, ins(O1, "same"))
    assert psql(db, ins(O1, "same"), check=False).returncode != 0
    psql(db, ins(O2, "same"))  # other tenant may reuse the key


def test_skip_locked_claims_are_disjoint(db):
    for i in range(2):
        psql(db, f"INSERT INTO jobs(id,organization_id,kind,payload,idempotency_key) "
                 f"VALUES ('{uuid.uuid4()}','{O1}','claim','{{}}','c{i}')")
    claim = ("SELECT id FROM jobs WHERE status='queued' AND kind='claim' ORDER BY created_at "
             "FOR UPDATE SKIP LOCKED LIMIT 1")
    # Two concurrent sessions hold their row locks at the same time.
    script = f"BEGIN; {claim}; SELECT pg_sleep(1.5); COMMIT;"
    import re
    run = lambda: subprocess.Popen(["psql", "-X", "-q", "-d", db, "-t", "-A"], stdin=subprocess.PIPE,  # noqa: E731
                                   stdout=subprocess.PIPE, text=True)
    p1, p2 = run(), run()
    for p in (p1, p2):  # start both before waiting on either, so the lock windows overlap
        p.stdin.write(script)
        p.stdin.close()
    outs = [p.stdout.read() for p in (p1, p2)]
    ids = {m.group(0) for o in outs if (m := re.search(r"[0-9a-f-]{36}", o))}
    assert len(ids) == 2  # each session got a different job; neither blocked nor duplicated


def test_network_overlap_and_tenant_scoping(db):
    net = lambda org, name, cidr: (f"INSERT INTO networks(id,organization_id,name,cidr) "  # noqa: E731
                                   f"VALUES ('{uuid.uuid4()}','{org}','{name}','{cidr}')")
    psql(db, net(O1, "n1", "10.0.0.0/16"))
    assert psql(db, net(O1, "n2", "10.0.5.0/24"), check=False).returncode != 0
    psql(db, net(O2, "n1", "10.0.0.0/16"))  # other tenant: allowed


def test_instance_name_unique_among_active_only(db):
    ins = lambda state: (f"INSERT INTO instances(id,organization_id,name,template,state) "  # noqa: E731
                         f"VALUES ('{uuid.uuid4()}','{O1}','web','alpine-small','{state}')")
    psql(db, ins("running"))
    assert psql(db, ins("planned"), check=False).returncode != 0
    psql(db, "UPDATE instances SET state='deleted'")
    psql(db, ins("planned"))  # name reusable after deletion


def test_state_check_constraint(db):
    r = psql(db, f"INSERT INTO instances(id,organization_id,name,template,state) "
                 f"VALUES ('{uuid.uuid4()}','{O1}','x1','t','hacked')", check=False)
    assert r.returncode != 0
