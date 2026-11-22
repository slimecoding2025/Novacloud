"""Exercises the runner's HTTP handler with a fake `docker` command (no Docker daemon needed)."""
import json
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from novacloud.runner import server

ID = "123e4567-e89b-12d3-a456-426614174000"
NAME = f"novacloud-{ID}"
TOKEN = "t" * 24


class FakeDocker:
    def __init__(self):
        self.running: dict[str, bool] = {}
        self.unmanaged = {"someone-elses-db"}
        self.calls: list[tuple] = []

    def __call__(self, *args):
        self.calls.append(args)
        cmd, ok = args[0], lambda out="": subprocess.CompletedProcess(args, 0, out, "")
        bad = subprocess.CompletedProcess(args, 1, "", "no such container")
        if cmd == "inspect":
            ref = args[-1]
            if ref in self.running:
                return ok(f"{'true' if self.running[ref] else 'false'}|true")
            return ok("true|") if ref in self.unmanaged else bad
        if cmd == "run":
            self.running[args[args.index("--name") + 1]] = True
            return ok()
        ref = args[-1]
        if cmd == "start":
            self.running[ref] = True
        elif cmd == "stop":
            self.running[ref] = False
        elif cmd == "rm":
            self.running.pop(ref, None)
        return ok()


@pytest.fixture
def runner(monkeypatch):
    fake = FakeDocker()
    monkeypatch.setattr(server, "docker", fake)
    monkeypatch.setattr(server, "TOKEN", TOKEN)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(method, path, body=None, token=TOKEN):
        req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {token}"} if token else {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    yield call, fake
    httpd.shutdown()


def test_auth_required(runner):
    call, fake = runner
    assert call("GET", f"/v1/containers/{NAME}", token=None)[0] == 401
    assert call("GET", f"/v1/containers/{NAME}", token="wrong")[0] == 401
    assert fake.calls == []  # nothing reaches docker without a valid token


def test_create_is_idempotent_and_hardened(runner):
    call, fake = runner
    body = {"instance_id": ID, "organization_id": ID, "template": "alpine-small"}
    assert call("POST", "/v1/containers", body) == (200, {"ref": NAME})
    assert call("POST", "/v1/containers", body) == (200, {"ref": NAME})
    runs = [c for c in fake.calls if c[0] == "run"]
    assert len(runs) == 1 and "--cap-drop" in runs[0] and "--privileged" not in runs[0]


def test_rejects_unknown_template_and_bad_ids(runner):
    call, fake = runner
    assert call("POST", "/v1/containers", {"instance_id": ID, "organization_id": ID, "template": "ubuntu"})[0] == 400
    assert call("POST", "/v1/containers", {"instance_id": "x; rm -rf /", "organization_id": ID, "template": "alpine-small"})[0] == 400
    assert not [c for c in fake.calls if c[0] == "run"]


def test_lifecycle(runner):
    call, fake = runner
    call("POST", "/v1/containers", {"instance_id": ID, "organization_id": ID, "template": "alpine-small"})
    assert call("GET", f"/v1/containers/{NAME}") == (200, {"status": "running"})
    assert call("POST", f"/v1/containers/{NAME}/stop")[0] == 200
    assert call("GET", f"/v1/containers/{NAME}")[1] == {"status": "stopped"}
    assert call("POST", f"/v1/containers/{NAME}/start")[0] == 200
    assert call("DELETE", f"/v1/containers/{NAME}")[0] == 200
    assert call("GET", f"/v1/containers/{NAME}")[0] == 404


def test_never_touches_foreign_containers(runner):
    call, fake = runner
    assert call("DELETE", "/v1/containers/someone-elses-db")[0] == 400  # not a novacloud-<uuid> reference
    assert not [c for c in fake.calls if c[0] in ("rm", "stop", "start")]
    fake.running["novacloud-" + ID.replace("1", "2")] = True
    other = "novacloud-" + ID.replace("1", "3")
    assert call("DELETE", f"/v1/containers/{other}")[0] == 404  # unknown to docker
