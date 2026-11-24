"""HTTP client for the privileged runner. The API never holds the Docker socket (ADR-0003)."""
import json
import urllib.error
import urllib.request

from novacloud.core.errors import Conflict, ProviderError


class RunnerComputeProvider:
    def __init__(self, base_url: str, token: str, timeout: float = 30.0):
        if not token:
            raise ValueError("RUNNER_TOKEN is required")
        self.base, self.token, self.timeout = base_url.rstrip("/"), token, timeout

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            self.base + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 (fixed internal URL)
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"status": None}
            if e.code == 409:
                raise Conflict("address range unavailable or resource still in use on this host") from None
            raise ProviderError(f"runner returned {e.code}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise ProviderError(f"runner unreachable: {e}") from None

    def create(self, instance_id, organization_id, template, network=None):
        body = {"instance_id": instance_id, "organization_id": organization_id, "template": template.name}
        if network:
            body["network"] = {"subnet_id": network.subnet_id, "ip": network.ip}
        return self._call("POST", "/v1/containers", body)["ref"]

    def create_subnet(self, subnet_id, cidr, gateway):
        self._call("POST", "/v1/networks", {"subnet_id": subnet_id, "cidr": cidr, "gateway": gateway})

    def delete_subnet(self, subnet_id):
        self._call("DELETE", f"/v1/networks/novacloud-net-{subnet_id}")

    def start(self, ref): self._call("POST", f"/v1/containers/{ref}/start")
    def stop(self, ref): self._call("POST", f"/v1/containers/{ref}/stop")
    def delete(self, ref): self._call("DELETE", f"/v1/containers/{ref}")

    def status(self, ref):
        return self._call("GET", f"/v1/containers/{ref}").get("status")
