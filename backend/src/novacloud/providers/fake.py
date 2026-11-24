"""In-memory provider for tests ONLY. Config validation rejects it in production."""


class FakeComputeProvider:
    """Implements both the compute and the network provider ports."""

    def __init__(self):
        self.containers: dict[str, str] = {}
        self.attachments: dict[str, tuple[str, str] | None] = {}
        self.subnets: dict[str, tuple[str, str]] = {}
        self.egress: dict[str, bool] = {}
        self.allow: dict[str, list[str]] = {}
        self.published: dict[str, int | None] = {}
        self.fail_next: str | None = None

    def _maybe_fail(self, op):
        if self.fail_next == op:
            self.fail_next = None
            raise RuntimeError(f"injected failure in {op}")

    def create(self, instance_id, organization_id, template, network=None):
        self._maybe_fail("create")
        ref = f"fake-{instance_id}"
        self.containers[ref] = "running"
        self.attachments[ref] = (network.subnet_id, network.ip) if network else None
        self.published[ref] = network.published_port if network else None
        return ref

    def start(self, ref):
        self._maybe_fail("start")
        self.containers[ref] = "running"

    def stop(self, ref):
        self._maybe_fail("stop")
        self.containers[ref] = "stopped"

    def delete(self, ref):
        self._maybe_fail("delete")
        self.containers.pop(ref, None)
        self.attachments.pop(ref, None)

    def status(self, ref):
        return self.containers.get(ref)

    # network port
    def create_subnet(self, subnet_id, cidr, gateway, egress=False, egress_allow=None):
        self._maybe_fail("create_subnet")
        self.subnets[subnet_id] = (cidr, gateway)
        self.egress[subnet_id] = egress
        self.allow[subnet_id] = list(egress_allow or [])

    def delete_subnet(self, subnet_id):
        self._maybe_fail("delete_subnet")
        self.subnets.pop(subnet_id, None)
