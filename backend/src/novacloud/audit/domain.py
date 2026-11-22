"""Append-only, hash-chained audit events. Metadata is always redacted before hashing."""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from novacloud.core.logging import redact

GENESIS = "0" * 64


@dataclass(frozen=True)
class AuditEvent:
    actor_id: str
    organization_id: str | None
    action: str
    resource_type: str
    resource_id: str
    result: str  # "success" | "denied" | "failure"
    correlation_id: str
    timestamp: str
    prev_hash: str
    hash: str
    metadata: dict = field(default_factory=dict)


def compute_hash(e_fields: dict, prev_hash: str) -> str:
    payload = json.dumps([e_fields, prev_hash], sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _fields(actor_id, organization_id, action, resource_type, resource_id, result, correlation_id, timestamp, metadata):
    return {"actor_id": actor_id, "organization_id": organization_id, "action": action,
            "resource_type": resource_type, "resource_id": resource_id, "result": result,
            "correlation_id": correlation_id, "timestamp": timestamp, "metadata": metadata}


def build_event(*, actor_id, organization_id, action, resource_type, resource_id, result,
                correlation_id="", metadata=None, prev_hash=GENESIS, now=None) -> AuditEvent:
    ts = (now or datetime.now(timezone.utc)).isoformat()
    meta = redact(metadata or {})
    f = _fields(actor_id, organization_id, action, resource_type, resource_id, result, correlation_id, ts, meta)
    return AuditEvent(actor_id, organization_id, action, resource_type, resource_id, result,
                      correlation_id, ts, prev_hash, compute_hash(f, prev_hash), meta)


def verify_chain(events: list[AuditEvent]) -> bool:
    prev = GENESIS
    for e in events:
        f = _fields(e.actor_id, e.organization_id, e.action, e.resource_type, e.resource_id,
                    e.result, e.correlation_id, e.timestamp, e.metadata)
        if e.prev_hash != prev or e.hash != compute_hash(f, e.prev_hash):
            return False
        prev = e.hash
    return True
