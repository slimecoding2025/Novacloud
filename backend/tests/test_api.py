"""HTTP-level tests. Require fastapi + httpx (pip install -r requirements-dev.txt); skipped otherwise."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from novacloud.api.app import create_app  # noqa: E402
from novacloud.api.container import build_in_memory  # noqa: E402
from novacloud.core.config import Settings  # noqa: E402
from novacloud.providers.fake import FakeComputeProvider  # noqa: E402
from tests.conftest import FakeHasher  # noqa: E402

PW = "Correct-Horse-9"


@pytest.fixture
def ctx(tmp_path):
    s = Settings(secret_key="k" * 32, storage_root=str(tmp_path), metrics_token="m-token")
    c = build_in_memory(s, FakeComputeProvider(), FakeHasher())
    return TestClient(create_app(c)), c


def session(client, org="Acme", email="a@example.com"):
    client.post("/api/v1/auth/register", json={"organization": org, "email": email, "password": PW})
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_health_ready_and_security_headers(ctx):
    client, _ = ctx
    assert client.get("/health").json()["status"] == "ok"
    r = client.get("/ready")
    assert r.status_code == 200 and r.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]


def test_unauthenticated_rejected(ctx):
    client, _ = ctx
    assert client.get("/api/v1/instances").status_code == 401


def test_cookie_flags_and_csrf_required(ctx):
    client, _ = ctx
    client.post("/api/v1/auth/register", json={"organization": "A", "email": "a@example.com", "password": PW})
    r = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": PW})
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=strict" in sc
    r = client.post("/api/v1/instances", json={"name": "web-01", "template": "alpine-small"},
                    headers={"Idempotency-Key": "k"})
    assert r.status_code == 403  # no CSRF header
    h = {"X-CSRF-Token": "wrong", "Idempotency-Key": "k"}
    assert client.post("/api/v1/instances", json={"name": "web-01", "template": "alpine-small"}, headers=h).status_code == 403


def test_instance_flow_and_idor(ctx):
    client, c = ctx
    h = session(client)
    r = client.post("/api/v1/instances", json={"name": "web-01", "template": "alpine-small"}, headers=h | {"Idempotency-Key": "k1"})
    assert r.status_code == 202
    iid = r.json()["instance"]["id"]
    c.worker().run_once()
    assert client.get(f"/api/v1/instances/{iid}").json()["state"] == "running"
    other = TestClient(client.app)
    session(other, "Other", "b@example.com")
    assert other.get(f"/api/v1/instances/{iid}").status_code == 404
    assert other.get("/api/v1/instances").json() == []


def test_missing_idempotency_key_and_bad_template(ctx):
    client, _ = ctx
    h = session(client)
    assert client.post("/api/v1/instances", json={"name": "web-01", "template": "alpine-small"}, headers=h).status_code == 422
    assert client.post("/api/v1/instances", json={"name": "web-01", "template": "evil"}, headers=h | {"Idempotency-Key": "x"}).status_code == 422


def test_metrics_requires_token(ctx):
    client, _ = ctx
    assert client.get("/metrics").status_code == 401
    r = client.get("/metrics", headers={"Authorization": "Bearer m-token"})
    assert r.status_code == 200 and "novacloud_database_up" in r.text


def test_object_upload_limit_and_roundtrip(ctx):
    client, _ = ctx
    h = session(client)
    r = client.post("/api/v1/objects?name=a.txt", content=b"hello", headers=h)
    assert r.status_code == 201
    oid = r.json()["id"]
    assert client.get(f"/api/v1/objects/{oid}/content").content == b"hello"
    big = b"x" * (10 * 1024 * 1024 + 1)
    assert client.post("/api/v1/objects?name=big", content=big, headers=h).status_code in (413, 422)


def test_internal_errors_are_not_leaked(ctx):
    client, c = ctx
    c.ping = lambda: (_ for _ in ()).throw(RuntimeError("db password=hunter2"))
    r = client.get("/ready")
    assert r.status_code == 503 and "hunter2" not in r.text
