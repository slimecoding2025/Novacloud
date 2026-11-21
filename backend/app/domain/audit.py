"""Tamper-evident audit chain: each entry hashes its content plus the previous hash."""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

GENESIS = "0" * 64


@dataclass(frozen=True)
class AuditEntry:
    actor: str
    action: str
    resource: str
    timestamp: str
    prev_hash: str
    hash: str


def compute_hash(actor: str, action: str, resource: str, timestamp: str, prev_hash: str) -> str:
    payload = json.dumps([actor, action, resource, timestamp, prev_hash], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def new_entry(actor: str, action: str, resource: str, prev_hash: str = GENESIS) -> AuditEntry:
    ts = datetime.now(timezone.utc).isoformat()
    return AuditEntry(actor, action, resource, ts, prev_hash,
                      compute_hash(actor, action, resource, ts, prev_hash))


def verify_chain(entries: list[AuditEntry]) -> bool:
    prev = GENESIS
    for e in entries:
        if e.prev_hash != prev or e.hash != compute_hash(e.actor, e.action, e.resource, e.timestamp, e.prev_hash):
            return False
        prev = e.hash
    return True
