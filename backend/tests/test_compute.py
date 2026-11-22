import pytest

from novacloud.compute.domain import TRANSITIONS, State, transition, validate_name
from novacloud.compute.service import ComputeService, InMemoryInstanceRepository
from novacloud.core.errors import Conflict, Forbidden, InvalidInput, NotFound
from novacloud.orchestration.domain import InMemoryJobRepository, Worker
from novacloud.providers.fake import FakeComputeProvider
from tests.test_iam import PW


@pytest.fixture
def env(iam, audit):
    jobs, prov = InMemoryJobRepository(), FakeComputeProvider()
    svc = ComputeService(InMemoryInstanceRepository(), jobs, prov, iam, audit, max_instances=2)
    worker = Worker(jobs, svc.handlers())
    iam.register_organization("A", "a@example.com", PW)
    _, owner = iam.login("a@example.com", PW)
    iam.add_member(owner, "v@example.com", PW, "viewer")
    _, viewer = iam.login("v@example.com", PW)
    iam.register_organization("B", "b@example.com", PW)
    _, other = iam.login("b@example.com", PW)
    return svc, worker, prov, owner, viewer, other


def test_all_documented_transitions():
    allowed = {(a, b) for a, bs in TRANSITIONS.items() for b in bs}
    assert len(allowed) == 15
    for a in State:
        for b in State:
            if (a, b) in allowed:
                assert transition(a, b) == b
            else:
                with pytest.raises(Conflict):
                    transition(a, b)


def test_name_validation():
    for bad in ["A", "ab", "1abc", "has space", "x" * 41, "UPPER", "a;rm -rf"]:
        with pytest.raises(InvalidInput):
            validate_name(bad)
    validate_name("web-01")


def test_create_flow_sets_running_only_after_provider(env):
    svc, worker, prov, owner, *_ = env
    inst, job = svc.create_instance(owner, "web-01", "alpine-small", "k1")
    assert inst.state == State.PLANNED
    prov.fail_next = "create"
    worker.run_once()
    assert svc.get_instance(owner, inst.id).state == State.FAILED  # provider failed -> never "running"
    assert prov.containers == {}


def test_full_lifecycle(env):
    svc, worker, prov, owner, *_ = env
    inst, _ = svc.create_instance(owner, "web-01", "alpine-small", "k1")
    worker.run_once()
    assert svc.get_instance(owner, inst.id).state == State.RUNNING
    svc.request_action(owner, inst.id, "stop", "k2"); worker.run_once()
    assert svc.get_instance(owner, inst.id).state == State.STOPPED
    svc.request_action(owner, inst.id, "start", "k3"); worker.run_once()
    assert svc.get_instance(owner, inst.id).state == State.RUNNING
    with pytest.raises(InvalidInput):
        svc.request_action(owner, inst.id, "delete", "k4")  # confirmation required
    svc.request_action(owner, inst.id, "delete", "k4", confirm_name="web-01"); worker.run_once()
    assert svc.list_instances(owner) == [] and prov.containers == {}


def test_idempotent_create_and_no_duplicate_jobs(env):
    svc, worker, _, owner, *_ = env
    a, ja = svc.create_instance(owner, "web-01", "alpine-small", "same")
    b, jb = svc.create_instance(owner, "web-01", "alpine-small", "same")
    assert a.id == b.id and ja.id == jb.id
    assert len(svc.jobs.jobs) == 1


def test_duplicate_name_quota_and_template(env):
    svc, _, _, owner, *_ = env
    svc.create_instance(owner, "web-01", "alpine-small", "k1")
    with pytest.raises(Conflict):
        svc.create_instance(owner, "web-01", "alpine-small", "k2")
    svc.create_instance(owner, "web-02", "alpine-small", "k3")
    with pytest.raises(Conflict):
        svc.create_instance(owner, "web-03", "alpine-small", "k4")  # quota 2
    with pytest.raises(InvalidInput):
        svc.create_instance(owner, "web-09", "ubuntu:latest --privileged", "k5")


def test_cross_tenant_isolation(env):
    svc, worker, _, owner, _, other = env
    inst, _ = svc.create_instance(owner, "web-01", "alpine-small", "k1")
    with pytest.raises(NotFound):
        svc.get_instance(other, inst.id)
    for action in ("start", "stop", "delete"):
        with pytest.raises(NotFound):
            svc.request_action(other, inst.id, action, "x", confirm_name="web-01")
    assert svc.list_instances(other) == []


def test_authorization(env):
    svc, _, _, owner, viewer, _ = env
    with pytest.raises(Forbidden):
        svc.create_instance(viewer, "web-01", "alpine-small", "k1")
    inst, _ = svc.create_instance(owner, "web-01", "alpine-small", "k1")
    assert svc.get_instance(viewer, inst.id).id == inst.id
    with pytest.raises(Forbidden):
        svc.request_action(viewer, inst.id, "stop", "k2")


def test_destructive_job_not_retried(env):
    svc, worker, prov, owner, *_ = env
    inst, _ = svc.create_instance(owner, "web-01", "alpine-small", "k1"); worker.run_once()
    prov.fail_next = "delete"
    j = svc.request_action(owner, inst.id, "delete", "k2", confirm_name="web-01"); worker.run_once()
    assert j.max_attempts == 1 and j.status == "failed"
    assert worker.run_once() is False


def test_reconcile_detects_drift(env):
    svc, worker, prov, owner, *_ = env
    inst, _ = svc.create_instance(owner, "web-01", "alpine-small", "k1"); worker.run_once()
    prov.containers.clear()  # container disappeared behind our back
    assert svc.reconcile()[0]["actual"] is None
    assert svc.get_instance(owner, inst.id).state == State.FAILED
