from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field

from novacloud.api.deps import COOKIE, cid, container, principal
from novacloud.core.errors import InvalidInput, Unauthorized
from novacloud.iam.domain import Principal
from novacloud.iam.sessions import csrf_for

router = APIRouter(prefix="/api/v1")


class RegisterIn(BaseModel):
    organization: str = Field(max_length=80)
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)
    organization_id: str | None = None


class MemberIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)
    role: str


class RoleIn(BaseModel):
    role: str


class InstanceIn(BaseModel):
    name: str = Field(max_length=40)
    template: str = Field(max_length=40)
    network_id: str | None = Field(default=None, max_length=36)
    subnet_id: str | None = Field(default=None, max_length=36)
    published_port: int | None = Field(default=None, ge=20000, le=29999)


class NetworkIn(BaseModel):
    name: str = Field(max_length=40)
    cidr: str = Field(max_length=18)


class SubnetIn(NetworkIn):
    egress: bool = False


class AllocIn(BaseModel):
    resource_id: str = Field(max_length=128)


def _inst(i):
    return {"id": i.id, "name": i.name, "template": i.template, "state": i.state.value, "error": i.error,
            "network_id": i.network_id, "subnet_id": i.subnet_id, "ip": i.ip, "published_port": i.published_port}
def _job(j): return {"id": j.id, "kind": j.kind, "status": j.status, "attempts": j.attempts, "error": j.error, "result": j.result}


# ---- auth ---------------------------------------------------------------------------------------------
@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, request: Request, c=Depends(container)):
    from novacloud.core.errors import Forbidden
    if not c.settings.registration_enabled:
        raise Forbidden("registration is disabled")
    org, user = c.iam.register_organization(body.organization, body.email, body.password, cid(request))
    return {"organization_id": org, "user_id": user}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, c=Depends(container)):
    ip = request.client.host if request.client else ""
    token, p = c.iam.login(body.email, body.password, body.organization_id, ip, cid(request))
    response.set_cookie(COOKIE, token, max_age=c.settings.session_ttl_seconds, httponly=True,
                        secure=c.settings.cookie_secure, samesite="strict", path="/")
    return {"user_id": p.user_id, "organization_id": p.organization_id, "role": p.role.value,
            "csrf_token": csrf_for(token, c.settings.secret_key)}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, p: Principal = Depends(principal), c=Depends(container)):
    c.iam.logout(p, cid(request))
    response.delete_cookie(COOKIE, path="/")


@router.get("/auth/me")
def me(request: Request, p: Principal = Depends(principal), c=Depends(container)):
    token = request.cookies.get(COOKIE)
    if not token:
        raise Unauthorized("not authenticated")
    return {"user_id": p.user_id, "organization_id": p.organization_id, "role": p.role.value,
            "csrf_token": csrf_for(token, c.settings.secret_key)}


# ---- members ------------------------------------------------------------------------------------------
@router.get("/members")
def members(p: Principal = Depends(principal), c=Depends(container)):
    return c.iam.list_members(p)


@router.post("/members", status_code=201)
def add_member(body: MemberIn, request: Request, p: Principal = Depends(principal), c=Depends(container)):
    return {"user_id": c.iam.add_member(p, body.email, body.password, body.role, cid(request))}


@router.patch("/members/{user_id}", status_code=204)
def change_role(user_id: str, body: RoleIn, request: Request, p: Principal = Depends(principal), c=Depends(container)):
    c.iam.change_role(p, user_id, body.role, cid(request))


# ---- instances ----------------------------------------------------------------------------------------
@router.get("/instances")
def list_instances(p: Principal = Depends(principal), c=Depends(container)):
    return [_inst(i) for i in c.compute.list_instances(p)]


@router.post("/instances", status_code=202)
def create_instance(body: InstanceIn, request: Request, idempotency_key: str | None = Header(default=None),
                    p: Principal = Depends(principal), c=Depends(container)):
    inst, job = c.compute.create_instance(p, body.name, body.template, idempotency_key or "", cid(request),
                                          body.network_id, body.subnet_id, body.published_port)
    return {"instance": _inst(inst), "job": _job(job)}


@router.get("/instances/{instance_id}")
def get_instance(instance_id: str, p: Principal = Depends(principal), c=Depends(container)):
    return _inst(c.compute.get_instance(p, instance_id))


@router.post("/instances/{instance_id}/{action}", status_code=202)
def instance_action(instance_id: str, action: str, request: Request, idempotency_key: str | None = Header(default=None),
                    p: Principal = Depends(principal), c=Depends(container)):
    if action not in ("start", "stop"):
        raise InvalidInput("unknown action")
    return _job(c.compute.request_action(p, instance_id, action, idempotency_key or "", None, cid(request)))


@router.delete("/instances/{instance_id}", status_code=202)
def delete_instance(instance_id: str, request: Request, confirm_name: str = Query(default=""),
                    idempotency_key: str | None = Header(default=None),
                    p: Principal = Depends(principal), c=Depends(container)):
    return _job(c.compute.request_action(p, instance_id, "delete", idempotency_key or "", confirm_name, cid(request)))


# ---- jobs ---------------------------------------------------------------------------------------------
@router.get("/jobs")
def list_jobs(p: Principal = Depends(principal), c=Depends(container)):
    c.iam.require(p, "job:read", "job")
    return [_job(j) for j in c.jobs.list(p.organization_id)]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, p: Principal = Depends(principal), c=Depends(container)):
    from novacloud.core.errors import NotFound
    c.iam.require(p, "job:read", "job", job_id)
    j = c.jobs.get(p.organization_id, job_id)
    if j is None:
        raise NotFound("job not found")
    return _job(j)


# ---- objects ------------------------------------------------------------------------------------------
@router.post("/objects", status_code=201)
async def put_object(request: Request, name: str = Query(max_length=255), p: Principal = Depends(principal),
                     c=Depends(container)):
    data = bytearray()
    async for chunk in request.stream():  # enforce the limit while streaming, not after buffering everything
        data += chunk
        if len(data) > c.settings.max_object_bytes:
            raise InvalidInput(f"object exceeds {c.settings.max_object_bytes} bytes")
    m = c.storage.put(p, name, bytes(data), cid(request))
    return {"id": m.id, "name": m.name, "size": m.size, "sha256": m.sha256}


@router.get("/objects")
def list_objects(p: Principal = Depends(principal), c=Depends(container)):
    return [{"id": m.id, "name": m.name, "size": m.size, "sha256": m.sha256} for m in c.storage.list(p)]


@router.get("/objects/usage")
def usage(p: Principal = Depends(principal), c=Depends(container)):
    return c.storage.usage(p)


@router.get("/objects/{object_id}/content")
def object_content(object_id: str, p: Principal = Depends(principal), c=Depends(container)):
    m, data = c.storage.get(p, object_id)
    return Response(data, media_type="application/octet-stream", headers={
        "Content-Disposition": 'attachment; filename="object"', "X-Content-Type-Options": "nosniff"})


@router.delete("/objects/{object_id}", status_code=204)
def delete_object(object_id: str, request: Request, p: Principal = Depends(principal), c=Depends(container)):
    c.storage.delete(p, object_id, cid(request))


# ---- networks -----------------------------------------------------------------------------------------
def _net(n):
    return {"id": n.id, "name": n.name, "cidr": n.cidr,
            "subnets": [{k: v for k, v in asdict(s).items() if k != "allocations"} | {"allocated": len(s.allocations)}
                        for s in n.subnets.values()]}


@router.get("/networks")
def list_networks(p: Principal = Depends(principal), c=Depends(container)):
    return [_net(n) for n in c.network.list_networks(p)]


@router.post("/networks", status_code=201)
def create_network(body: NetworkIn, request: Request, p: Principal = Depends(principal), c=Depends(container)):
    return _net(c.network.create_network(p, body.name, body.cidr, cid(request)))


@router.delete("/networks/{network_id}", status_code=204)
def delete_network(network_id: str, request: Request, p: Principal = Depends(principal), c=Depends(container)):
    c.network.delete_network(p, network_id, cid(request))


@router.post("/networks/{network_id}/subnets", status_code=201)
def create_subnet(network_id: str, body: SubnetIn, request: Request, p: Principal = Depends(principal), c=Depends(container)):
    s = c.network.create_subnet(p, network_id, body.name, body.cidr, cid(request), body.egress)
    return {k: v for k, v in asdict(s).items() if k != "allocations"}


@router.delete("/networks/{network_id}/subnets/{subnet_id}", status_code=204)
def delete_subnet(network_id: str, subnet_id: str, request: Request, p: Principal = Depends(principal), c=Depends(container)):
    c.network.delete_subnet(p, network_id, subnet_id, cid(request))


@router.post("/networks/{network_id}/subnets/{subnet_id}/allocations", status_code=201)
def allocate(network_id: str, subnet_id: str, body: AllocIn, request: Request, p: Principal = Depends(principal), c=Depends(container)):
    return {"ip": c.network.allocate_ip(p, network_id, subnet_id, body.resource_id, cid(request))}


# ---- audit --------------------------------------------------------------------------------------------
@router.get("/audit")
def audit(limit: int = Query(default=100, ge=1, le=500), p: Principal = Depends(principal), c=Depends(container)):
    c.iam.require(p, "audit:read", "audit")
    return [{"timestamp": e.timestamp, "actor_id": e.actor_id, "action": e.action, "resource_type": e.resource_type,
             "resource_id": e.resource_id, "result": e.result, "correlation_id": e.correlation_id, "metadata": e.metadata}
            for e in c.audit.list_for_org(p.organization_id, limit)]


@router.get("/audit/verify")
def audit_verify(p: Principal = Depends(principal), c=Depends(container)):
    c.iam.require(p, "audit:read", "audit")
    return c.audit.verify()
