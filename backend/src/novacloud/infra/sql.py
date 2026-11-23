"""PostgreSQL repositories (SQLAlchemy Core, bound parameters only). Every tenant query filters by organization_id."""
from __future__ import annotations

import json

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from novacloud.audit.domain import GENESIS, AuditEvent
from novacloud.compute.domain import Instance, State
from novacloud.core.errors import Conflict
from novacloud.iam.domain import SessionRecord
from novacloud.orchestration.domain import Job
from novacloud.storage.service import ObjectMeta


def make_engine(url: str):
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


class SqlAuditRepository:
    def __init__(self, engine):
        self.e = engine

    def append_chained(self, make):
        with self.e.begin() as c:
            c.execute(text("SELECT pg_advisory_xact_lock(7001)"))  # serialise appends => linear chain
            row = c.execute(text("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1")).first()
            ev = make(row[0] if row else GENESIS)
            c.execute(text(
                "INSERT INTO audit_log(actor_id,organization_id,action,resource_type,resource_id,result,"
                "correlation_id,ts,metadata,prev_hash,hash) VALUES (:a,:o,:ac,:rt,:ri,:r,:c,:ts,CAST(:m AS jsonb),:p,:h)"),
                dict(a=ev.actor_id, o=ev.organization_id, ac=ev.action, rt=ev.resource_type, ri=ev.resource_id,
                     r=ev.result, c=ev.correlation_id, ts=ev.timestamp, m=json.dumps(ev.metadata),
                     p=ev.prev_hash, h=ev.hash))
        return ev

    @staticmethod
    def _ev(r) -> AuditEvent:
        return AuditEvent(r.actor_id, str(r.organization_id) if r.organization_id else None, r.action,
                          r.resource_type, r.resource_id, r.result, r.correlation_id, r.ts, r.prev_hash,
                          r.hash, r.metadata)

    def all(self):
        with self.e.connect() as c:
            return [self._ev(r) for r in c.execute(text("SELECT * FROM audit_log ORDER BY id"))]

    def for_org(self, org, limit):
        with self.e.connect() as c:
            rows = c.execute(text("SELECT * FROM audit_log WHERE organization_id=:o ORDER BY id DESC LIMIT :l"),
                             dict(o=org, l=limit)).all()
        return [self._ev(r) for r in reversed(rows)]


class SqlIamRepository:
    def __init__(self, engine):
        self.e = engine

    def create_org(self, org_id, name):
        with self.e.begin() as c:
            c.execute(text("INSERT INTO organizations(id,name) VALUES (:i,:n)"), dict(i=org_id, n=name))

    def create_user(self, user_id, email, password_hash):
        try:
            with self.e.begin() as c:
                c.execute(text("INSERT INTO users(id,email,password_hash) VALUES (:i,:e,:p)"),
                          dict(i=user_id, e=email, p=password_hash))
        except IntegrityError:
            raise Conflict("email already registered") from None

    def get_user_by_email(self, email):
        with self.e.connect() as c:
            r = c.execute(text("SELECT id,email,password_hash,is_active FROM users WHERE email=:e"), dict(e=email)).first()
        return {"id": str(r.id), "email": r.email, "password_hash": r.password_hash, "is_active": r.is_active} if r else None

    def add_membership(self, user_id, org_id, role):
        with self.e.begin() as c:
            c.execute(text("INSERT INTO memberships(user_id,organization_id,role) VALUES (:u,:o,:r)"),
                      dict(u=user_id, o=org_id, r=role))

    def get_membership(self, user_id, org_id):
        with self.e.connect() as c:
            r = c.execute(text("SELECT role FROM memberships WHERE user_id=:u AND organization_id=:o"),
                          dict(u=user_id, o=org_id)).first()
        return r[0] if r else None

    def list_memberships(self, user_id):
        with self.e.connect() as c:
            return [(str(r.organization_id), r.role) for r in c.execute(
                text("SELECT organization_id, role FROM memberships WHERE user_id=:u ORDER BY organization_id"), dict(u=user_id))]

    def list_members(self, org_id):
        with self.e.connect() as c:
            return [{"user_id": str(r.user_id), "email": r.email, "role": r.role} for r in c.execute(text(
                "SELECT m.user_id, u.email, m.role FROM memberships m JOIN users u ON u.id=m.user_id "
                "WHERE m.organization_id=:o ORDER BY u.email"), dict(o=org_id))]

    def set_role(self, user_id, org_id, role):
        with self.e.begin() as c:
            c.execute(text("UPDATE memberships SET role=:r WHERE user_id=:u AND organization_id=:o"),
                      dict(r=role, u=user_id, o=org_id))

    def add_session(self, s: SessionRecord):
        with self.e.begin() as c:
            c.execute(text("INSERT INTO sessions(id,token_hash,user_id,organization_id,created_at,expires_at) "
                           "VALUES (:i,:t,:u,:o,:c,:x)"),
                      dict(i=s.id, t=s.token_hash, u=s.user_id, o=s.organization_id, c=s.created_at, x=s.expires_at))

    def get_session_by_hash(self, token_hash):
        with self.e.connect() as c:
            r = c.execute(text("SELECT * FROM sessions WHERE token_hash=:t"), dict(t=token_hash)).first()
        return SessionRecord(str(r.id), r.token_hash, str(r.user_id), str(r.organization_id),
                             r.created_at, r.expires_at, r.revoked_at) if r else None

    def revoke_session(self, session_id, at):
        with self.e.begin() as c:
            c.execute(text("UPDATE sessions SET revoked_at=:a WHERE id=:i"), dict(a=at, i=session_id))


class SqlInstanceRepository:
    def __init__(self, engine):
        self.e = engine

    @staticmethod
    def _i(r) -> Instance:
        return Instance(str(r.id), str(r.organization_id), r.name, r.template, State(r.state), r.provider_ref, r.error,
                        str(r.network_id) if r.network_id else None, str(r.subnet_id) if r.subnet_id else None,
                        str(r.ip) if r.ip else None)

    def add(self, i: Instance):
        try:
            with self.e.begin() as c:
                c.execute(text("INSERT INTO instances(id,organization_id,name,template,state) VALUES (:i,:o,:n,:t,:s)"),
                          dict(i=i.id, o=i.organization_id, n=i.name, t=i.template, s=i.state.value))
        except IntegrityError:
            raise Conflict("instance name already in use") from None

    def get(self, org, instance_id):
        with self.e.connect() as c:
            r = c.execute(text("SELECT id,organization_id,name,template,state,provider_ref,error,network_id,subnet_id,host(ip) AS ip FROM instances WHERE id=:i AND organization_id=:o"),
                          dict(i=instance_id, o=org)).first()
        return self._i(r) if r else None

    def list(self, org):
        with self.e.connect() as c:
            return [self._i(r) for r in c.execute(text(
                "SELECT id,organization_id,name,template,state,provider_ref,error,network_id,subnet_id,host(ip) AS ip FROM instances WHERE organization_id=:o AND state<>'deleted' ORDER BY created_at"), dict(o=org))]

    def save(self, i: Instance):
        with self.e.begin() as c:
            c.execute(text("UPDATE instances SET state=:s, provider_ref=:p, error=:e, network_id=:n, subnet_id=:sn, "
                           "ip=CAST(:ip AS inet), updated_at=now() WHERE id=:i AND organization_id=:o"),
                      dict(s=i.state.value, p=i.provider_ref, e=i.error, n=i.network_id, sn=i.subnet_id, ip=i.ip,
                           i=i.id, o=i.organization_id))

    def count_active(self, org):
        with self.e.connect() as c:
            return c.execute(text("SELECT count(*) FROM instances WHERE organization_id=:o AND state<>'deleted'"),
                             dict(o=org)).scalar_one()

    def all_with_refs(self):
        with self.e.connect() as c:
            return [self._i(r) for r in c.execute(text(
                "SELECT id,organization_id,name,template,state,provider_ref,error,network_id,subnet_id,host(ip) AS ip FROM instances WHERE provider_ref IS NOT NULL AND state IN ('running','stopped')"))]


class SqlJobRepository:
    def __init__(self, engine):
        self.e = engine

    @staticmethod
    def _j(r) -> Job:
        return Job(str(r.id), str(r.organization_id), r.kind, r.payload, r.idempotency_key, r.status,
                   r.attempts, r.max_attempts, r.error, r.result)

    def find_by_key(self, org, key):
        with self.e.connect() as c:
            r = c.execute(text("SELECT * FROM jobs WHERE organization_id=:o AND idempotency_key=:k"),
                          dict(o=org, k=key)).first()
        return self._j(r) if r else None

    def enqueue(self, job: Job):
        with self.e.begin() as c:
            r = c.execute(text(
                "INSERT INTO jobs(id,organization_id,kind,payload,idempotency_key,max_attempts) "
                "VALUES (:i,:o,:k,CAST(:p AS jsonb),:ik,:m) ON CONFLICT (organization_id, idempotency_key) DO NOTHING"),
                dict(i=job.id, o=job.organization_id, k=job.kind, p=json.dumps(job.payload),
                     ik=job.idempotency_key, m=job.max_attempts))
            created = r.rowcount == 1
        return (job if created else self.find_by_key(job.organization_id, job.idempotency_key)), created

    def claim(self):
        with self.e.begin() as c:
            r = c.execute(text(
                "UPDATE jobs SET status='running', attempts=attempts+1, updated_at=now() WHERE id = ("
                " SELECT id FROM jobs WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"
                ") RETURNING *")).first()
        return self._j(r) if r else None

    def finish(self, job: Job, ok, error=None, result=None):
        with self.e.begin() as c:
            if ok:
                c.execute(text("UPDATE jobs SET status='succeeded', result=CAST(:r AS jsonb), error=NULL, updated_at=now() WHERE id=:i"),
                          dict(r=json.dumps(result or {}), i=job.id))
            else:
                c.execute(text("UPDATE jobs SET status=CASE WHEN attempts<max_attempts THEN 'queued' ELSE 'failed' END, "
                               "error=:e, updated_at=now() WHERE id=:i"), dict(e=error, i=job.id))

    def get(self, org, job_id):
        with self.e.connect() as c:
            r = c.execute(text("SELECT * FROM jobs WHERE id=:i AND organization_id=:o"), dict(i=job_id, o=org)).first()
        return self._j(r) if r else None

    def list(self, org, limit=100):
        with self.e.connect() as c:
            return [self._j(r) for r in c.execute(text(
                "SELECT * FROM jobs WHERE organization_id=:o ORDER BY created_at DESC LIMIT :l"), dict(o=org, l=limit))]

    def counts(self):
        with self.e.connect() as c:
            return {r.status: r.n for r in c.execute(text("SELECT status, count(*) n FROM jobs GROUP BY status"))}


class SqlObjectRepository:
    def __init__(self, engine):
        self.e = engine

    def add(self, m: ObjectMeta):
        with self.e.begin() as c:
            c.execute(text("INSERT INTO storage_objects(id,organization_id,name,size,sha256) VALUES (:i,:o,:n,:s,:h)"),
                      dict(i=m.id, o=m.organization_id, n=m.name, s=m.size, h=m.sha256))

    @staticmethod
    def _m(r): return ObjectMeta(str(r.id), str(r.organization_id), r.name, r.size, r.sha256)

    def get(self, org, oid):
        with self.e.connect() as c:
            r = c.execute(text("SELECT * FROM storage_objects WHERE id=:i AND organization_id=:o"), dict(i=oid, o=org)).first()
        return self._m(r) if r else None

    def list(self, org):
        with self.e.connect() as c:
            return [self._m(r) for r in c.execute(text("SELECT * FROM storage_objects WHERE organization_id=:o ORDER BY created_at"), dict(o=org))]

    def remove(self, oid):
        with self.e.begin() as c:
            c.execute(text("DELETE FROM storage_objects WHERE id=:i"), dict(i=oid))

    def used_bytes(self, org):
        with self.e.connect() as c:
            return c.execute(text("SELECT COALESCE(sum(size),0) FROM storage_objects WHERE organization_id=:o"), dict(o=org)).scalar_one()


class SqlNetworkStore:
    """Write-through persistence for NetworkService (see its docstring for the caching caveat)."""

    def __init__(self, engine):
        self.e = engine

    def load(self):
        from novacloud.network.service import Network, Subnet
        nets: dict[str, Network] = {}
        with self.e.connect() as c:
            for r in c.execute(text("SELECT id, organization_id, name, cidr::text AS cidr FROM networks")):
                nets[str(r.id)] = Network(str(r.id), str(r.organization_id), r.name, r.cidr)
            subs = {}
            for r in c.execute(text("SELECT id, network_id, organization_id, name, cidr::text AS cidr, host(gateway) AS gw FROM subnets")):
                s = Subnet(str(r.id), str(r.network_id), str(r.organization_id), r.name, r.cidr, r.gw)
                subs[s.id] = s
                nets[s.network_id].subnets[s.id] = s
            for r in c.execute(text("SELECT subnet_id, host(ip) AS ip, resource_id FROM ip_allocations")):
                subs[str(r.subnet_id)].allocations[r.ip] = r.resource_id
        return nets

    def save_network(self, n):
        with self.e.begin() as c:
            c.execute(text("INSERT INTO networks(id,organization_id,name,cidr) VALUES (:i,:o,:n,CAST(:c AS cidr))"),
                      dict(i=n.id, o=n.organization_id, n=n.name, c=n.cidr))

    def save_subnet(self, s):
        with self.e.begin() as c:
            c.execute(text("INSERT INTO subnets(id,network_id,organization_id,name,cidr,gateway) "
                           "VALUES (:i,:n,:o,:name,CAST(:c AS cidr),CAST(:g AS inet))"),
                      dict(i=s.id, n=s.network_id, o=s.organization_id, name=s.name, c=s.cidr, g=s.gateway))

    def save_allocation(self, subnet_id, ip, resource_id):
        with self.e.begin() as c:
            c.execute(text("INSERT INTO ip_allocations(subnet_id,ip,resource_id) VALUES (:s,CAST(:ip AS inet),:r)"),
                      dict(s=subnet_id, ip=ip, r=resource_id))

    def delete_network(self, network_id):
        with self.e.begin() as c:
            c.execute(text("DELETE FROM networks WHERE id=:i"), dict(i=network_id))

    def delete_subnet(self, subnet_id):
        with self.e.begin() as c:
            c.execute(text("DELETE FROM subnets WHERE id=:i"), dict(i=subnet_id))

    def delete_allocation(self, subnet_id, ip):
        with self.e.begin() as c:
            c.execute(text("DELETE FROM ip_allocations WHERE subnet_id=:s AND ip=CAST(:ip AS inet)"), dict(s=subnet_id, ip=ip))
