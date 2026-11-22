from dataclasses import replace

from novacloud.audit.domain import build_event, verify_chain


def test_chain_valid_tamper_reorder(audit):
    for i in range(3):
        audit.record(actor_id="u", organization_id="o", action="a", resource_type="r", resource_id=str(i))
    ev = audit.repo.all()
    assert audit.verify() == {"entries": 3, "valid": True}
    assert not verify_chain([replace(ev[1], action="x"), *ev[2:]][:1] + ev[1:2])
    assert not verify_chain([ev[1], ev[0], ev[2]])
    assert not verify_chain([replace(ev[0], result="denied"), *ev[1:]])


def test_metadata_redacted():
    e = build_event(actor_id="u", organization_id=None, action="a", resource_type="r", resource_id="1",
                    result="success", metadata={"password": "hunter2", "nested": {"api_key": "k", "ok": 1}})
    assert e.metadata == {"password": "[REDACTED]", "nested": {"api_key": "[REDACTED]", "ok": 1}}


def test_org_scoped_listing(audit):
    audit.record(actor_id="u", organization_id="a", action="x", resource_type="r", resource_id="1")
    audit.record(actor_id="u", organization_id="b", action="x", resource_type="r", resource_id="2")
    assert [e.resource_id for e in audit.list_for_org("a")] == ["1"]
