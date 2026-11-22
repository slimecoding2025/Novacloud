from __future__ import annotations
"""Object storage on the local filesystem. Objects are addressed by generated ID, never by user path."""
import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from novacloud.core.errors import Conflict, InvalidInput, NotFound
from novacloud.iam.domain import Principal


@dataclass
class ObjectMeta:
    id: str
    organization_id: str
    name: str  # display label only; never used to build a path
    size: int
    sha256: str


class InMemoryObjectRepository:
    def __init__(self):
        self.items: dict[str, ObjectMeta] = {}

    def add(self, m): self.items[m.id] = m
    def get(self, org, oid):
        m = self.items.get(oid)
        return m if m and m.organization_id == org else None
    def list(self, org): return [m for m in self.items.values() if m.organization_id == org]
    def remove(self, oid): self.items.pop(oid, None)
    def used_bytes(self, org): return sum(m.size for m in self.list(org))


class LocalObjectStore:
    def __init__(self, root: str, repo, iam, audit, max_object_bytes: int, org_quota_bytes: int):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.repo, self.iam, self.audit = repo, iam, audit
        self.max_object, self.quota = max_object_bytes, org_quota_bytes

    def _path(self, org: str, oid: str) -> Path:
        # Both parts are validated UUIDs; the resolved path must still lie under root.
        uuid.UUID(org)
        uuid.UUID(oid)
        p = (self.root / org / oid).resolve()
        if self.root not in p.parents:
            raise InvalidInput("invalid object path")
        return p

    def put(self, p: Principal, name: str, data: bytes, cid="") -> ObjectMeta:
        self.iam.require(p, "volume:write", "object", "-", cid)
        label = (name or "").strip()
        if not (1 <= len(label) <= 255) or any(ord(c) < 32 for c in label):
            raise InvalidInput("invalid object name")
        if len(data) > self.max_object:
            raise InvalidInput(f"object exceeds {self.max_object} bytes")
        if self.repo.used_bytes(p.organization_id) + len(data) > self.quota:
            raise Conflict("storage quota exceeded")
        oid = str(uuid.uuid4())
        path = self._path(p.organization_id, oid)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        meta = ObjectMeta(oid, p.organization_id, label, len(data), hashlib.sha256(data).hexdigest())
        self.repo.add(meta)
        self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action="object.put",
                          resource_type="object", resource_id=oid, correlation_id=cid, metadata={"size": len(data)})
        return meta

    def get(self, p: Principal, oid: str) -> tuple[ObjectMeta, bytes]:
        self.iam.require(p, "volume:read", "object", oid)
        m = self.repo.get(p.organization_id, oid)
        if m is None:
            raise NotFound("object not found")
        return m, self._path(p.organization_id, oid).read_bytes()

    def list(self, p: Principal) -> list[ObjectMeta]:
        self.iam.require(p, "volume:read", "object")
        return self.repo.list(p.organization_id)

    def delete(self, p: Principal, oid: str, cid="") -> None:
        self.iam.require(p, "volume:delete", "object", oid, cid)
        m = self.repo.get(p.organization_id, oid)
        if m is None:
            raise NotFound("object not found")
        self._path(p.organization_id, oid).unlink(missing_ok=True)
        self.repo.remove(oid)
        self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action="object.delete",
                          resource_type="object", resource_id=oid, correlation_id=cid)

    def usage(self, p: Principal) -> dict:
        self.iam.require(p, "volume:read", "object")
        return {"used_bytes": self.repo.used_bytes(p.organization_id), "quota_bytes": self.quota}
