from __future__ import annotations
"""Jobs (PostgreSQL-backed queue, ADR-0002), idempotency and execution plans with compensation."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

DESTRUCTIVE = {"instance.delete", "volume.delete"}


@dataclass
class Job:
    id: str
    organization_id: str
    kind: str
    payload: dict
    idempotency_key: str
    status: str = "queued"  # queued | running | succeeded | failed
    attempts: int = 0
    max_attempts: int = 3
    error: str | None = None
    result: dict | None = None


def new_job(organization_id: str, kind: str, payload: dict, idempotency_key: str, max_attempts: int = 3) -> Job:
    # Destructive operations are never retried automatically.
    return Job(str(uuid.uuid4()), organization_id, kind, payload, idempotency_key,
               max_attempts=1 if kind in DESTRUCTIVE else max_attempts)


class InMemoryJobRepository:
    def __init__(self):
        self.jobs: dict[str, Job] = {}

    def enqueue(self, job: Job) -> tuple[Job, bool]:
        """Return (job, created). A repeated (org, idempotency_key) returns the original job."""
        for j in self.jobs.values():
            if j.organization_id == job.organization_id and j.idempotency_key == job.idempotency_key:
                return j, False
        self.jobs[job.id] = job
        return job, True

    def find_by_key(self, organization_id: str, key: str) -> Job | None:
        return next((j for j in self.jobs.values()
                     if j.organization_id == organization_id and j.idempotency_key == key), None)

    def claim(self) -> Job | None:
        for j in self.jobs.values():
            if j.status == "queued":
                j.status, j.attempts = "running", j.attempts + 1
                return j
        return None

    def finish(self, job: Job, ok: bool, error: str | None = None, result: dict | None = None) -> None:
        if ok:
            job.status, job.result, job.error = "succeeded", result, None
        elif job.attempts < job.max_attempts:
            job.status, job.error = "queued", error  # retry
        else:
            job.status, job.error = "failed", error

    def get(self, organization_id: str, job_id: str) -> Job | None:
        j = self.jobs.get(job_id)
        return j if j and j.organization_id == organization_id else None

    def list(self, organization_id: str, limit: int = 100) -> list[Job]:
        return [j for j in self.jobs.values() if j.organization_id == organization_id][-limit:]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for j in self.jobs.values():
            out[j.status] = out.get(j.status, 0) + 1
        return out


class Worker:
    def __init__(self, repo, handlers: dict[str, Callable[[Job], dict | None]]):
        self.repo, self.handlers = repo, handlers

    def run_once(self) -> bool:
        job = self.repo.claim()
        if job is None:
            return False
        try:
            handler = self.handlers[job.kind]
            self.repo.finish(job, True, result=handler(job) or {})
        except Exception as e:  # noqa: BLE001 - job failures are recorded, not raised
            self.repo.finish(job, False, error=f"{type(e).__name__}: {e}"[:500])
        return True


@dataclass
class Step:
    name: str
    run: Callable[[], None]
    compensate: Callable[[], None] | None = None
    depends_on: tuple[str, ...] = ()


@dataclass
class PlanResult:
    completed: list[str] = field(default_factory=list)
    compensated: list[str] = field(default_factory=list)
    failed_step: str | None = None
    error: str | None = None
    log: list[str] = field(default_factory=list)


def order_steps(steps: list[Step]) -> list[Step]:
    by_name = {s.name: s for s in steps}
    if len(by_name) != len(steps):
        raise ValueError("duplicate step names")
    out: list[Step] = []
    state: dict[str, int] = {}

    def visit(s: Step):
        if state.get(s.name) == 2:
            return
        if state.get(s.name) == 1:
            raise ValueError(f"dependency cycle at {s.name}")
        state[s.name] = 1
        for d in s.depends_on:
            if d not in by_name:
                raise ValueError(f"unknown dependency {d}")
            visit(by_name[d])
        state[s.name] = 2
        out.append(s)

    for s in steps:
        visit(s)
    return out


def execute_plan(steps: list[Step]) -> PlanResult:
    res, done = PlanResult(), []
    for s in order_steps(steps):
        try:
            s.run()
            done.append(s)
            res.completed.append(s.name)
            res.log.append(f"ok {s.name}")
        except Exception as e:  # noqa: BLE001
            res.failed_step, res.error = s.name, f"{type(e).__name__}: {e}"
            res.log.append(f"failed {s.name}: {e}")
            for d in reversed(done):
                if d.compensate:
                    try:
                        d.compensate()
                        res.compensated.append(d.name)
                        res.log.append(f"compensated {d.name}")
                    except Exception as ce:  # noqa: BLE001
                        res.log.append(f"compensation failed {d.name}: {ce}")
            break
    return res
