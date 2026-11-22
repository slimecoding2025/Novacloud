from typing import Protocol

from novacloud.audit.domain import GENESIS, AuditEvent, build_event, verify_chain


class AuditRepository(Protocol):
    def append_chained(self, make) -> AuditEvent:
        """Atomically build (make(prev_hash)) and store the next event; SQL implementation takes a lock."""
    def all(self) -> list[AuditEvent]: ...
    def for_org(self, organization_id: str, limit: int) -> list[AuditEvent]: ...


class InMemoryAuditRepository:
    def __init__(self):
        self.events: list[AuditEvent] = []

    def append_chained(self, make):
        e = make(self.events[-1].hash if self.events else GENESIS)
        self.events.append(e)
        return e

    def all(self):
        return list(self.events)

    def for_org(self, organization_id, limit):
        return [e for e in self.events if e.organization_id == organization_id][-limit:]


class AuditService:
    def __init__(self, repo: AuditRepository):
        self.repo = repo

    def record(self, *, actor_id, organization_id, action, resource_type, resource_id,
               result="success", correlation_id="", metadata=None) -> AuditEvent:
        return self.repo.append_chained(lambda prev: build_event(
            actor_id=actor_id, organization_id=organization_id, action=action, resource_type=resource_type,
            resource_id=resource_id, result=result, correlation_id=correlation_id, metadata=metadata,
            prev_hash=prev))

    def verify(self) -> dict:
        events = self.repo.all()
        return {"entries": len(events), "valid": verify_chain(events)}

    def list_for_org(self, organization_id: str, limit: int = 100) -> list[AuditEvent]:
        return self.repo.for_org(organization_id, min(limit, 500))
