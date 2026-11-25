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


# ---- network attachment ------------------------------------------------------------------------
@pytest.fixture
def net_env(iam, audit):
    from novacloud.network.service import NetworkService
    jobs, prov = InMemoryJobRepository(), FakeComputeProvider()
    net = NetworkService(iam, audit, provider=prov)
    svc = ComputeService(InMemoryInstanceRepository(), jobs, prov, iam, audit, network=net)
    iam.register_organization("A", "a@example.com", PW)
    _, owner = iam.login("a@example.com", PW)
    n = net.create_network(owner, "net-a", "10.0.0.0/16")
    s = net.create_subnet(owner, n.id, "sub-a", "10.0.1.0/29")
    return svc, Worker(jobs, svc.handlers()), prov, net, owner, n, s


def test_subnet_creates_real_bridge_and_deletes_it(net_env):
    svc, _, prov, net, owner, n, s = net_env
    assert prov.subnets[s.id] == ("10.0.1.0/29", "10.0.1.1")
    net.delete_subnet(owner, n.id, s.id)
    assert prov.subnets == {}


def test_provider_refusal_records_nothing(net_env):
    svc, _, prov, net, owner, n, _ = net_env
    prov.fail_next = "create_subnet"
    with pytest.raises(RuntimeError):
        net.create_subnet(owner, n.id, "sub-b", "10.0.2.0/29")
    assert len(net.networks[n.id].subnets) == 1


def test_instance_gets_ip_and_attachment_then_releases_on_delete(net_env):
    svc, worker, prov, net, owner, n, s = net_env
    inst, _ = svc.create_instance(owner, "web-01", "alpine-small", "k1", network_id=n.id, subnet_id=s.id)
    assert inst.ip == "10.0.1.2" and inst.subnet_id == s.id
    worker.run_once()
    assert prov.attachments[f"fake-{inst.id}"] == (s.id, "10.0.1.2")
    with pytest.raises(Conflict):
        net.delete_subnet(owner, n.id, s.id)  # address still allocated
    svc.request_action(owner, inst.id, "delete", "k2", confirm_name="web-01"); worker.run_once()
    assert net.networks[n.id].subnets[s.id].allocations == {}
    net.delete_subnet(owner, n.id, s.id)


def test_full_subnet_marks_instance_deleted_and_no_ip_leak(net_env):
    svc, _, _, net, owner, n, s = net_env  # /29: hosts .1-.6, gateway .1 -> 5 usable
    for i in range(5):
        svc.create_instance(owner, f"web-0{i}", "alpine-small", f"k{i}", network_id=n.id, subnet_id=s.id)
    with pytest.raises(Conflict):
        svc.create_instance(owner, "web-09", "alpine-small", "k9", network_id=n.id, subnet_id=s.id)
    assert [i.name for i in svc.repo.list(owner.organization_id)].count("web-09") == 0


def test_attachment_arguments_validated(net_env):
    svc, _, _, _, owner, n, s = net_env
    with pytest.raises(InvalidInput):
        svc.create_instance(owner, "web-01", "alpine-small", "k1", network_id=n.id)  # subnet missing
    with pytest.raises(NotFound):
        svc.create_instance(owner, "web-01", "alpine-small", "k2", network_id=n.id, subnet_id="nope")


def test_cannot_attach_to_another_orgs_subnet(net_env, iam):
    svc, _, _, _, _, n, s = net_env
    iam.register_organization("B", "b@example.com", PW)
    _, other = iam.login("b@example.com", PW)
    with pytest.raises(NotFound):
        svc.create_instance(other, "web-01", "alpine-small", "k1", network_id=n.id, subnet_id=s.id)


# ---- egress policy and published ports -----------------------------------------------------------
def test_subnet_is_internal_by_default_and_egress_is_opt_in(net_env):
    _, _, prov, net, owner, n, s = net_env
    assert prov.egress[s.id] is False and net.networks[n.id].subnets[s.id].egress is False
    e = net.create_subnet(owner, n.id, "sub-egress", "10.0.2.0/29", egress=True)
    assert prov.egress[e.id] is True


def test_published_port_requires_egress_subnet_and_template_port(net_env):
    svc, worker, prov, net, owner, n, s = net_env
    with pytest.raises(InvalidInput):  # internal subnet: Docker cannot publish
        svc.create_instance(owner, "web-01", "nginx-small", "k1", network_id=n.id, subnet_id=s.id, published_port=20001)
    e = net.create_subnet(owner, n.id, "sub-egress", "10.0.2.0/29", egress=True)
    with pytest.raises(InvalidInput):  # alpine exposes no port
        svc.create_instance(owner, "web-02", "alpine-small", "k2", network_id=n.id, subnet_id=e.id, published_port=20001)
    for bad in (80, 19999, 30000, True):
        with pytest.raises(InvalidInput):
            svc.create_instance(owner, "web-03", "nginx-small", "k3", network_id=n.id, subnet_id=e.id, published_port=bad)
    with pytest.raises(InvalidInput):  # no subnet at all
        svc.create_instance(owner, "web-04", "nginx-small", "k4", published_port=20001)
    inst, _ = svc.create_instance(owner, "web-05", "nginx-small", "k5", network_id=n.id, subnet_id=e.id, published_port=20001)
    worker.run_once()
    assert prov.published[f"fake-{inst.id}"] == 20001


def test_published_port_is_unique_and_freed_on_delete(net_env):
    svc, worker, prov, net, owner, n, _ = net_env
    e = net.create_subnet(owner, n.id, "sub-egress", "10.0.2.0/29", egress=True)
    a, _ = svc.create_instance(owner, "web-01", "nginx-small", "k1", network_id=n.id, subnet_id=e.id, published_port=20002)
    worker.run_once()
    with pytest.raises(Conflict):
        svc.create_instance(owner, "web-02", "nginx-small", "k2", network_id=n.id, subnet_id=e.id, published_port=20002)
    svc.request_action(owner, a.id, "delete", "k3", confirm_name="web-01"); worker.run_once()
    assert svc.repo.get(owner.organization_id, a.id).published_port is None
    svc.create_instance(owner, "web-02", "nginx-small", "k4", network_id=n.id, subnet_id=e.id, published_port=20002)


def test_egress_allowlist_is_validated_and_forwarded(net_env):
    _, _, prov, net, owner, n, _ = net_env
    s = net.create_subnet(owner, n.id, "sub-allow", "10.0.2.0/29", egress=True, egress_allow=["1.1.1.1/32", "1.1.1.1/32"])
    assert prov.allow[s.id] == ["1.1.1.1/32"]  # normalised and de-duplicated
    with pytest.raises(InvalidInput):
        net.create_subnet(owner, n.id, "sub-x", "10.0.3.0/29", egress=False, egress_allow=["1.1.1.1/32"])
    for bad in (["127.0.0.1/32"], ["169.254.169.254/32"], ["0.0.0.0/0"], ["nope"], ["1.1.1.0/24"] * 17):
        with pytest.raises(InvalidInput):
            net.create_subnet(owner, n.id, "sub-y", "10.0.4.0/29", egress=True, egress_allow=bad)
