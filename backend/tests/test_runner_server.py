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
        self.unmanaged = {"someone-elses-db", "bridge"}
        self.networks: dict[str, bool] = {}   # name -> managed
        self.overlap = False
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
        if cmd == "network":
            sub, name = args[1], args[-1]
            if sub == "inspect":
                if name in self.networks:
                    return ok("true" if self.networks[name] else "")
                return ok("") if name in self.unmanaged else bad
            if sub == "create":
                if self.overlap:
                    return subprocess.CompletedProcess(args, 1, "", "Pool overlaps with other one on this address space")
                self.networks[name] = True
                return ok()
            if sub == "rm":
                self.networks.pop(name, None)
                return ok()
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


SUB = "223e4567-e89b-12d3-a456-426614174000"
NET = f"novacloud-net-{SUB}"


def test_network_create_idempotent_conflict_and_delete(runner):
    call, fake = runner
    body = {"subnet_id": SUB, "cidr": "10.0.1.0/24", "gateway": "10.0.1.1"}
    assert call("POST", "/v1/networks", body) == (200, {"name": NET})
    assert call("POST", "/v1/networks", body) == (200, {"name": NET})
    assert len([c for c in fake.calls if c[:2] == ("network", "create")]) == 1
    assert call("DELETE", f"/v1/networks/{NET}")[0] == 200 and NET not in fake.networks
    fake.overlap = True
    assert call("POST", "/v1/networks", body)[0] == 409


def test_network_rejects_bad_input_and_foreign_networks(runner):
    call, fake = runner
    assert call("POST", "/v1/networks", {"subnet_id": SUB, "cidr": "8.8.8.0/24", "gateway": "8.8.8.1"})[0] == 400
    assert call("DELETE", "/v1/networks/bridge")[0] == 400
    assert not [c for c in fake.calls if c[:2] == ("network", "rm")]


def test_container_needs_an_existing_managed_network(runner):
    call, fake = runner
    body = {"instance_id": ID, "organization_id": ID, "template": "alpine-small", "network": {"subnet_id": SUB, "ip": "10.0.1.5"}}
    assert call("POST", "/v1/containers", body)[0] == 400  # network not created yet
    call("POST", "/v1/networks", {"subnet_id": SUB, "cidr": "10.0.1.0/24", "gateway": "10.0.1.1"})
    assert call("POST", "/v1/containers", body) == (200, {"ref": NAME})
    run = [c for c in fake.calls if c[0] == "run"][0]
    assert NET in run and "10.0.1.5" in run and "none" not in run


def test_egress_flag_controls_internal_and_published_port_is_loopback(runner):
    call, fake = runner
    call("POST", "/v1/networks", {"subnet_id": SUB, "cidr": "10.0.1.0/24", "gateway": "10.0.1.1", "egress": True})
    create = [c for c in fake.calls if c[:2] == ("network", "create")][0]
    assert "--internal" not in create
    body = {"instance_id": ID, "organization_id": ID, "template": "nginx-small",
            "network": {"subnet_id": SUB, "ip": "10.0.1.5", "published_port": 20080}}
    assert call("POST", "/v1/containers", body) == (200, {"ref": NAME})
    run = [c for c in fake.calls if c[0] == "run"][0]
    assert "127.0.0.1:20080:8080" in run
    bad = dict(body, instance_id="b" * 8 + ID[8:], network={"subnet_id": SUB, "ip": "10.0.1.6", "published_port": 80})
    assert call("POST", "/v1/containers", bad)[0] == 400
