"""Wires services together. `build()` uses PostgreSQL; `build_in_memory()` is for tests only."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from novacloud.audit.service import AuditService, InMemoryAuditRepository
from novacloud.compute.service import ComputeService, InMemoryInstanceRepository
from novacloud.core.config import Settings
from novacloud.core.ratelimit import RateLimiter
from novacloud.iam.service import IamService, InMemoryIamRepository
from novacloud.monitoring.metrics import Metric, MetricsRegistry
from novacloud.network.service import NetworkService
from novacloud.orchestration.domain import InMemoryJobRepository, Worker
from novacloud.storage.service import InMemoryObjectRepository, LocalObjectStore


@dataclass
class Container:
    settings: Settings
    audit: AuditService
    iam: IamService
    compute: ComputeService
    jobs: object
    storage: LocalObjectStore
    network: NetworkService
    metrics: MetricsRegistry
    api_limiter: RateLimiter
    ping: Callable[[], None]  # raises if the database is unreachable

    def worker(self) -> Worker:
        return Worker(self.jobs, self.compute.handlers())


def _provider(s: Settings):
    if s.compute_provider == "fake":
        from novacloud.providers.fake import FakeComputeProvider
        return FakeComputeProvider()
    from novacloud.providers.runner_client import RunnerComputeProvider
    return RunnerComputeProvider(s.runner_url, s.runner_token)


def _assemble(s, audit_repo, iam_repo, inst_repo, job_repo, obj_repo, provider, ping, hasher, net_store=None) -> Container:
    audit = AuditService(audit_repo)
    iam = IamService(iam_repo, hasher, audit, s.session_ttl_seconds, RateLimiter(s.login_rate_per_minute))
    network = NetworkService(iam, audit, store=net_store, provider=provider)
    compute = ComputeService(inst_repo, job_repo, provider, iam, audit, s.max_instances_per_org, network=network)
    storage = LocalObjectStore(s.storage_root, obj_repo, iam, audit, s.max_object_bytes, s.org_storage_quota_bytes)
    m = MetricsRegistry()
    m.register(Metric("novacloud_build_info", "Always 1; version label", "static config", "gauge",
                      lambda: {(s.app_version,): 1}, ("version",)))
    m.register(Metric("novacloud_jobs", "Jobs by status", "table jobs (PostgreSQL)", "gauge",
                      lambda: {(k,): v for k, v in job_repo.counts().items()} or {("none",): 0}, ("status",)))
    m.register(Metric("novacloud_database_up", "1 if a SELECT 1 succeeds", "live database ping", "gauge",
                      lambda: (ping(), 1)[1]))
    m.counter_metric("novacloud_http_requests_total", "HTTP requests", "API middleware counter", ("method", "status"))
    return Container(s, audit, iam, compute, job_repo, storage, network, m,
                     RateLimiter(s.api_rate_per_minute), ping)


def build(settings: Settings) -> Container:
    from sqlalchemy import text

    from novacloud.iam.passwords import Argon2Hasher
    from novacloud.infra import sql
    settings.validate()
    e = sql.make_engine(settings.database_url)

    def ping():
        with e.connect() as c:
            c.execute(text("SELECT 1"))
    return _assemble(settings, sql.SqlAuditRepository(e), sql.SqlIamRepository(e), sql.SqlInstanceRepository(e),
                     sql.SqlJobRepository(e), sql.SqlObjectRepository(e), _provider(settings), ping, Argon2Hasher(),
                     sql.SqlNetworkStore(e))


def build_in_memory(settings: Settings, provider, hasher) -> Container:
    return _assemble(settings, InMemoryAuditRepository(), InMemoryIamRepository(), InMemoryInstanceRepository(),
                     InMemoryJobRepository(), InMemoryObjectRepository(), provider, lambda: None, hasher)
