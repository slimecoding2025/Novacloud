"""In-memory provider for tests ONLY. Config validation rejects it in production."""


class FakeComputeProvider:
    def __init__(self):
        self.containers: dict[str, str] = {}
        self.fail_next: str | None = None

    def _maybe_fail(self, op):
        if self.fail_next == op:
            self.fail_next = None
            raise RuntimeError(f"injected failure in {op}")

    def create(self, instance_id, organization_id, template):
        self._maybe_fail("create")
        ref = f"fake-{instance_id}"
        self.containers[ref] = "running"
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

    def status(self, ref):
        return self.containers.get(ref)
