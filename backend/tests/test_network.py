import pytest

from novacloud.core.errors import Conflict, Forbidden, InvalidInput, NotFound
from novacloud.network.service import NetworkService
from tests.test_iam import PW


@pytest.fixture
def env(iam, audit):
    svc = NetworkService(iam, audit)
    iam.register_organization("A", "a@example.com", PW); _, owner = iam.login("a@example.com", PW)
    iam.add_member(owner, "v@example.com", PW, "viewer"); _, viewer = iam.login("v@example.com", PW)
    iam.register_organization("B", "b@example.com", PW); _, other = iam.login("b@example.com", PW)
    return svc, owner, viewer, other


@pytest.mark.parametrize("bad", ["8.8.8.0/24", "10.0.0.1/24", "10.0.0.0/30", "fd00::/64", "abc", "10.0.0.0/7"])
def test_invalid_cidrs(env, bad):
    svc, owner, *_ = env
    with pytest.raises(InvalidInput):
        svc.create_network(owner, "net-a", bad)


def test_overlap_and_relationships(env):
    svc, owner, *_ = env
    n = svc.create_network(owner, "net-a", "10.0.0.0/16")
    with pytest.raises(Conflict):
        svc.create_network(owner, "net-b", "10.0.1.0/24")
    with pytest.raises(InvalidInput):
        svc.create_subnet(owner, n.id, "out", "192.168.0.0/24")  # outside parent
    s = svc.create_subnet(owner, n.id, "sub-a", "10.0.1.0/24")
    with pytest.raises(Conflict):
        svc.create_subnet(owner, n.id, "sub-b", "10.0.1.128/25")
    assert s.gateway == "10.0.1.1"
    with pytest.raises(Conflict):
        svc.delete_network(owner, n.id)  # still has subnets


def test_ip_allocation_skips_gateway_and_is_idempotent(env):
    svc, owner, *_ = env
    n = svc.create_network(owner, "net-a", "10.0.0.0/24")
    s = svc.create_subnet(owner, n.id, "sub-a", "10.0.0.0/29")  # hosts .1-.6, gateway .1
    ips = [svc.allocate_ip(owner, n.id, s.id, f"vm{i}") for i in range(5)]
    assert ips == [f"10.0.0.{i}" for i in range(2, 7)]
    assert svc.allocate_ip(owner, n.id, s.id, "vm0") == "10.0.0.2"
    with pytest.raises(Conflict):
        svc.allocate_ip(owner, n.id, s.id, "vm-extra")
    with pytest.raises(Conflict):
        svc.delete_subnet(owner, n.id, s.id)


def test_isolation_and_roles(env):
    svc, owner, viewer, other = env
    n = svc.create_network(owner, "net-a", "10.0.0.0/24")
    with pytest.raises(NotFound):
        svc.create_subnet(other, n.id, "sub", "10.0.0.0/25")
    assert svc.list_networks(other) == []
    svc.create_network(other, "net-a", "10.0.0.0/24")  # same CIDR is fine in another org
    with pytest.raises(Forbidden):
        svc.create_network(viewer, "net-z", "10.9.0.0/24")


class RecordingStore:
    """Fake write-through store: lets us prove every mutation is persisted and a restart reloads it."""
    def __init__(self):
        self.nets = {}
    def load(self): return self.nets
    def save_network(self, n): self.nets[n.id] = n
    def save_subnet(self, s): pass  # subnet objects live inside the network object in this fake
    def save_allocation(self, *a): self.saved_alloc = a
    def delete_network(self, i): self.nets.pop(i, None)
    def delete_subnet(self, i): self.deleted_subnet = i


def test_write_through_and_reload(iam, audit):
    store = RecordingStore()
    svc = NetworkService(iam, audit, store=store)
    iam.register_organization("A", "a@example.com", PW); _, owner = iam.login("a@example.com", PW)
    n = svc.create_network(owner, "net-a", "10.0.0.0/24")
    s = svc.create_subnet(owner, n.id, "sub-a", "10.0.0.0/25")
    svc.allocate_ip(owner, n.id, s.id, "vm1")
    assert store.saved_alloc == (s.id, "10.0.0.2", "vm1")
    restarted = NetworkService(iam, audit, store=store)  # simulated restart
    assert [x.name for x in restarted.list_networks(owner)] == ["net-a"]
