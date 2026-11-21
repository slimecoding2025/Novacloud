from dataclasses import replace

from app.domain.audit import GENESIS, new_entry, verify_chain


def _chain(n=3):
    out, prev = [], GENESIS
    for i in range(n):
        e = new_entry("admin", "create", f"vm-{i}", prev)
        out.append(e)
        prev = e.hash
    return out


def test_valid_chain():
    assert verify_chain(_chain())


def test_empty_chain_is_valid():
    assert verify_chain([])


def test_tamper_detected():
    c = _chain()
    c[1] = replace(c[1], action="delete")
    assert not verify_chain(c)


def test_reorder_detected():
    c = _chain()
    assert not verify_chain([c[1], c[0], c[2]])
