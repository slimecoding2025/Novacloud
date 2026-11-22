import uuid

import pytest

from novacloud.core.errors import Conflict, Forbidden, InvalidInput, NotFound
from novacloud.storage.service import InMemoryObjectRepository, LocalObjectStore
from tests.test_iam import PW


@pytest.fixture
def env(tmp_path, iam, audit):
    store = LocalObjectStore(str(tmp_path / "root"), InMemoryObjectRepository(), iam, audit, 100, 150)
    iam.register_organization("A", "a@example.com", PW); _, owner = iam.login("a@example.com", PW)
    iam.add_member(owner, "v@example.com", PW, "viewer"); _, viewer = iam.login("v@example.com", PW)
    iam.register_organization("B", "b@example.com", PW); _, other = iam.login("b@example.com", PW)
    return store, owner, viewer, other, tmp_path


def test_roundtrip_and_checksum(env):
    store, owner, *_ = env
    m = store.put(owner, "report.txt", b"hello")
    meta, data = store.get(owner, m.id)
    assert data == b"hello" and meta.sha256 == m.sha256 and meta.size == 5


def test_path_traversal_in_name_is_harmless(env):
    store, owner, *_, tmp = env
    m = store.put(owner, "../../etc/passwd", b"x")
    files = [p for p in (tmp / "root").rglob("*") if p.is_file()]
    assert len(files) == 1 and files[0].name == m.id  # label never reaches the filesystem


def test_traversal_in_id_rejected(env):
    store, owner, *_ = env
    for bad in ["../../x", "..", "/etc/passwd"]:
        with pytest.raises((ValueError, NotFound, InvalidInput)):
            store.get(owner, bad)


def test_limits_and_quota(env):
    store, owner, *_ = env
    with pytest.raises(InvalidInput):
        store.put(owner, "big", b"x" * 101)
    store.put(owner, "a", b"x" * 100)
    with pytest.raises(Conflict):
        store.put(owner, "b", b"x" * 51)
    with pytest.raises(InvalidInput):
        store.put(owner, "bad\x00name", b"x")


def test_cross_tenant_and_roles(env):
    store, owner, viewer, other, _ = env
    m = store.put(owner, "a", b"secret")
    with pytest.raises(NotFound):
        store.get(other, m.id)
    with pytest.raises(NotFound):
        store.delete(other.__class__(**{**other.__dict__, "role": other.role.__class__("owner")}), m.id)
    with pytest.raises(Forbidden):
        store.put(viewer, "x", b"1")
    with pytest.raises(Forbidden):
        store.delete(viewer, m.id)
    assert store.get(viewer, m.id)[1] == b"secret"


def test_delete_removes_file(env):
    store, owner, *_, tmp = env
    m = store.put(owner, "a", b"1")
    store.delete(owner, m.id)
    assert not any(p.is_file() for p in (tmp / "root").rglob("*"))
    assert store.usage(owner)["used_bytes"] == 0
