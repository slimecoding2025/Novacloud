from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.domain.audit import GENESIS, AuditEntry, new_entry, verify_chain
from app.infra.db import SessionLocal
from app.infra.models import AuditLog

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditIn(BaseModel):
    actor: str
    action: str
    resource: str


def _row_to_entry(r: AuditLog) -> AuditEntry:
    return AuditEntry(r.actor, r.action, r.resource, r.timestamp, r.prev_hash, r.hash)


@router.post("", status_code=201)
def append(body: AuditIn):
    with SessionLocal() as s:
        last = s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).first()
        e = new_entry(body.actor, body.action, body.resource, last.hash if last else GENESIS)
        s.add(AuditLog(**e.__dict__))
        s.commit()
        return e.__dict__


@router.get("/verify")
def verify():
    with SessionLocal() as s:
        rows = s.scalars(select(AuditLog).order_by(AuditLog.id)).all()
        return {"entries": len(rows), "valid": verify_chain([_row_to_entry(r) for r in rows])}
