"""The runner: the only component that talks to Docker. Small, token-authenticated, template-only.

Run:  RUNNER_TOKEN=... python -m novacloud.runner.server
"""
import hmac
import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from novacloud.runner.spec import LABEL, build_run_args, container_name, validate_ref

TOKEN = os.environ.get("RUNNER_TOKEN", "")
PATH_RE = re.compile(r"^/v1/containers(?:/(?P<ref>[^/]+)(?:/(?P<act>start|stop))?)?$")


def docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60, check=False)  # noqa: S603


def status_of(ref: str):
    p = docker("inspect", "-f", "{{.State.Running}}|{{index .Config.Labels \"novacloud.managed\"}}", ref)
    if p.returncode != 0:
        return None
    running, managed = p.stdout.strip().split("|")
    if managed != "true":  # never touch containers we did not create
        return None
    return "running" if running == "true" else "stopped"


class Handler(BaseHTTPRequestHandler):
    server_version = "novacloud-runner"

    def log_message(self, *a):  # keep tokens/paths out of default stderr noise
        pass

    def _send(self, code: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _auth(self) -> bool:
        got = self.headers.get("Authorization", "")
        return bool(TOKEN) and hmac.compare_digest(got, f"Bearer {TOKEN}")

    def _route(self, method: str):
        if not self._auth():
            return self._send(401, {"error": "unauthorized"})
        m = PATH_RE.match(self.path)
        if not m:
            return self._send(404, {"error": "not found"})
        ref, act = m.group("ref"), m.group("act")
        try:
            if method == "POST" and ref is None:
                n = int(self.headers.get("Content-Length", "0"))
                if n > 4096:
                    return self._send(413, {"error": "too large"})
                body = json.loads(self.rfile.read(n) or b"{}")
                args = build_run_args(str(body.get("instance_id", "")), str(body.get("organization_id", "")),
                                      str(body.get("template", "")))
                name = container_name(body["instance_id"])
                if status_of(name) is not None:  # idempotent create
                    return self._send(200, {"ref": name})
                p = docker(*args[1:])
                return self._send(200, {"ref": name}) if p.returncode == 0 else self._send(500, {"error": "create failed"})
            ref = validate_ref(ref or "")
            if method == "GET":
                s = status_of(ref)
                return self._send(200 if s else 404, {"status": s})
            if status_of(ref) is None:
                return self._send(404, {"error": "not found"})
            cmd = {"POST/start": ["start"], "POST/stop": ["stop"], "DELETE/": ["rm", "-f"]}.get(f"{method}/{act or ''}")
            if not cmd:
                return self._send(405, {"error": "method not allowed"})
            p = docker(*cmd, ref)
            return self._send(200 if p.returncode == 0 else 500, {"ok": p.returncode == 0})
        except (ValueError, KeyError, json.JSONDecodeError):
            return self._send(400, {"error": "bad request"})

    def do_GET(self): self._route("GET")
    def do_POST(self): self._route("POST")
    def do_DELETE(self): self._route("DELETE")


def main():
    if not TOKEN:
        raise SystemExit("RUNNER_TOKEN is required")
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("RUNNER_PORT", "8100"))), Handler).serve_forever()  # noqa: S104


if __name__ == "__main__":
    main()
