from __future__ import annotations

import builtins
import uuid
from typing import Protocol

from novacloud.audit.service import AuditService
from novacloud.compute.domain import Instance, NetworkAttachment, State, get_template, transition, validate_name
from novacloud.compute.ports import ComputeProvider
from novacloud.core.errors import Conflict, InvalidInput, NotFound
from novacloud.iam.domain import Principal
from novacloud.iam.service import IamService
from novacloud.orchestration.domain import Job, new_job


class InstanceRepository(Protocol):
    def add(self, i: Instance) -> None: ...
    def get(self, organization_id: str, instance_id: str) -> Instance | None: ...
    def list(self, organization_id: str) -> builtins.list[Instance]: ...
    def save(self, i: Instance) -> None: ...
    def count_active(self, organization_id: str) -> int: ...
    def all_with_refs(self) -> builtins.list[Instance]: ...


class InMemoryInstanceRepository:
    def __init__(self):
        self.items: dict[str, Instance] = {}

    def add(self, i):
        if any(x.organization_id == i.organization_id and x.name == i.name and x.state != State.DELETED
               for x in self.items.values()):
            raise Conflict("instance name already in use")
        self.items[i.id] = i

    def get(self, organization_id, instance_id):
        i = self.items.get(instance_id)
        return i if i and i.organization_id == organization_id else None

    def list(self, organization_id):
        return [i for i in self.items.values() if i.organization_id == organization_id and i.state != State.DELETED]

    def save(self, i):
        self.items[i.id] = i

    def port_taken(self, port):
        return any(x.published_port == port for x in self.items.values())

    def count_active(self, organization_id):
        return len(self.list(organization_id))

    def all_with_refs(self):
        return [i for i in self.items.values() if i.provider_ref and i.state in (State.RUNNING, State.STOPPED)]


class ComputeService:
    def __init__(self, repo: InstanceRepository, jobs, provider: ComputeProvider, iam: IamService,
                 audit: AuditService, max_instances: int = 20, network=None):
        self.repo, self.jobs, self.provider, self.iam, self.audit = repo, jobs, provider, iam, audit
        self.network = network  # NetworkService, needed only when instances are attached to subnets
        self.max_instances = max_instances

    # -- API-facing (authorized, tenant-scoped); work is done asynchronously by the worker ----------
    def create_instance(self, p: Principal, name: str, template: str, idempotency_key: str, cid="",
                        network_id: str | None = None, subnet_id: str | None = None,
                        published_port: int | None = None) -> tuple[Instance, Job]:
        self.iam.require(p, "instance:create", "instance", "-", cid)
        validate_name(name)
        tpl = get_template(template)
        if not idempotency_key or len(idempotency_key) > 128:
            raise InvalidInput("Idempotency-Key header is required (max 128 chars)")
        existing = self._job_for_key(p.organization_id, idempotency_key)
        if existing:
            found = self.repo.get(p.organization_id, existing.payload["instance_id"])
            if found is None:
                raise NotFound("instance for this idempotency key no longer exists")
            return found, existing
        if self.repo.count_active(p.organization_id) >= self.max_instances:
            raise Conflict("instance quota reached")
        if bool(network_id) != bool(subnet_id):
            raise InvalidInput("network_id and subnet_id must be given together")
        if subnet_id and self.network is None:
            raise InvalidInput("networking is not enabled")
        if published_port is not None:
            if type(published_port) is not int or not 20000 <= published_port <= 29999:
                raise InvalidInput("published_port must be between 20000 and 29999")
            if tpl.port is None:
                raise InvalidInput("this template exposes no port")
            if not subnet_id or not network_id:
                raise InvalidInput("a published port needs a subnet")
            if not self.network.subnet_egress(p, network_id, subnet_id):
                raise InvalidInput("publishing a port needs a subnet with egress enabled (Docker cannot publish on internal networks)")
            if self.repo.port_taken(published_port):
                raise Conflict("host port already in use")
        inst = Instance(str(uuid.uuid4()), p.organization_id, name, template, State.PLANNED)
        self.repo.add(inst)
        if subnet_id and network_id:
            try:
                inst.ip = self.network.allocate_ip(p, network_id, subnet_id, inst.id, cid)
            except Exception:
                inst.state = State.DELETED  # planned -> deleted: nothing was provisioned
                self.repo.save(inst)
                raise
            inst.network_id, inst.subnet_id, inst.published_port = network_id, subnet_id, published_port
            self.repo.save(inst)
        job, _ = self.jobs.enqueue(new_job(p.organization_id, "instance.create",
                                           {"instance_id": inst.id}, idempotency_key))
        self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action="instance.create",
                          resource_type="instance", resource_id=inst.id, correlation_id=cid,
                          metadata={"name": name, "template": template, "ip": inst.ip, "published_port": published_port})
        return inst, job

    def _job_for_key(self, org, key):
        return self.jobs.find_by_key(org, key)

    def request_action(self, p: Principal, instance_id: str, action: str, idempotency_key: str,
                       confirm_name: str | None = None, cid="") -> Job:
        perm = {"start": "instance:start", "stop": "instance:stop", "delete": "instance:delete"}[action]
        self.iam.require(p, perm, "instance", instance_id, cid)
        inst = self.repo.get(p.organization_id, instance_id)
        if inst is None:
            raise NotFound("instance not found")
        if action == "delete" and confirm_name != inst.name:
            raise InvalidInput("deletion requires confirm_name equal to the instance name")
        if not idempotency_key:
            raise InvalidInput("Idempotency-Key header is required")
        job, created = self.jobs.enqueue(new_job(p.organization_id, f"instance.{action}",
                                                 {"instance_id": instance_id}, idempotency_key))
        if created:
            self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action=f"instance.{action}",
                              resource_type="instance", resource_id=instance_id, correlation_id=cid)
        return job

    def list_instances(self, p: Principal) -> builtins.list[Instance]:
        self.iam.require(p, "instance:read", "instance")
        return self.repo.list(p.organization_id)

    def get_instance(self, p: Principal, instance_id: str) -> Instance:
        self.iam.require(p, "instance:read", "instance", instance_id)
        inst = self.repo.get(p.organization_id, instance_id)
        if inst is None:
            raise NotFound("instance not found")
        return inst

    # -- worker handlers ----------------------------------------------------------------------------
    def handlers(self):
        return {"instance.create": self._h_create, "instance.start": self._h_start,
                "instance.stop": self._h_stop, "instance.delete": self._h_delete}

    @staticmethod
    def _attachment(inst: Instance) -> NetworkAttachment | None:
        return NetworkAttachment(inst.subnet_id, inst.ip, inst.published_port) if inst.subnet_id and inst.ip else None

    def _load(self, job: Job) -> Instance:
        inst = self.repo.get(job.organization_id, job.payload["instance_id"])
        if inst is None:
            raise NotFound("instance vanished")
        return inst

    def _set(self, inst: Instance, state: State, **kw):
        inst.state = transition(inst.state, state)
        for k, v in kw.items():
            setattr(inst, k, v)
        self.repo.save(inst)

    def _h_create(self, job: Job):
        inst = self._load(job)
        if inst.state != State.PLANNED:  # retried job after success: nothing to do
            return {"state": inst.state.value}
        self._set(inst, State.PROVISIONING)
        try:
            ref = self.provider.create(inst.id, inst.organization_id, get_template(inst.template), self._attachment(inst))
        except Exception as e:  # noqa: BLE001
            self._set(inst, State.FAILED, error=str(e)[:300])
            raise
        self._set(inst, State.RUNNING, provider_ref=ref, error=None)  # only after provider confirmed
        return {"state": "running"}

    def _h_start(self, job: Job):
        inst = self._load(job)
        self._set(inst, State.PROVISIONING)
        try:
            if inst.provider_ref and self.provider.status(inst.provider_ref):
                self.provider.start(inst.provider_ref)
            else:
                inst.provider_ref = self.provider.create(inst.id, inst.organization_id, get_template(inst.template), self._attachment(inst))
        except Exception as e:  # noqa: BLE001
            self._set(inst, State.FAILED, error=str(e)[:300])
            raise
        self._set(inst, State.RUNNING, error=None)
        return {"state": "running"}

    def _h_stop(self, job: Job):
        inst = self._load(job)
        if not inst.provider_ref:
            raise Conflict("instance has no provider reference")
        self._set(inst, State.STOPPING)
        try:
            self.provider.stop(inst.provider_ref)
        except Exception as e:  # noqa: BLE001
            self._set(inst, State.FAILED, error=str(e)[:300])
            raise
        self._set(inst, State.STOPPED)
        return {"state": "stopped"}

    def _h_delete(self, job: Job):
        inst = self._load(job)
        self._set(inst, State.DELETING)
        try:
            if inst.provider_ref:
                self.provider.delete(inst.provider_ref)
        except Exception as e:  # noqa: BLE001
            self._set(inst, State.FAILED, error=str(e)[:300])
            raise
        self._set(inst, State.DELETED)
        if inst.subnet_id and inst.network_id and self.network:
            self.network.release_ip(inst.organization_id, inst.network_id, inst.subnet_id, inst.id)
            # the address is free again; drop the reference so the subnet can be deleted (history lives in the audit log)
            inst.network_id = inst.subnet_id = inst.ip = inst.published_port = None
            self.repo.save(inst)
        return {"state": "deleted"}

    # -- reconciliation: recorded state vs provider state ---------------------------------------------
    def reconcile(self) -> list[dict]:
        drift = []
        for inst in self.repo.all_with_refs():
            if not inst.provider_ref:
                continue
            actual = self.provider.status(inst.provider_ref)
            expected = "running" if inst.state == State.RUNNING else "stopped"
            if actual != expected:
                drift.append({"instance_id": inst.id, "expected": expected, "actual": actual})
                if inst.state == State.RUNNING:
                    self._set(inst, State.FAILED, error=f"drift: provider reports {actual or 'missing'}")
                else:
                    inst.error = f"drift: provider reports {actual or 'missing'}"
                    self.repo.save(inst)
        return drift
