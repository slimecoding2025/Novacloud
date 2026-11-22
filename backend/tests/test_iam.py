import pytest

from novacloud.core.errors import Conflict, Forbidden, InvalidInput, RateLimited, Unauthorized
from novacloud.core.ratelimit import RateLimiter
from novacloud.iam.domain import Role, has_permission
from novacloud.iam.passwords import validate_password_policy
from novacloud.iam.service import IamService, InMemoryIamRepository
from novacloud.iam.sessions import csrf_for, csrf_valid
from tests.conftest import FakeHasher

PW = "Correct-Horse-9"


def setup(iam):
    org, _ = iam.register_organization("Acme", "Owner@Example.com", PW)
    tok, owner = iam.login("owner@example.com", PW)
    return org, tok, owner


def test_default_deny():
    assert not has_permission(None, "instance:read")
    assert not has_permission("bogus", "instance:read")
    assert not has_permission(Role.VIEWER, "instance:create")
    assert not has_permission(Role.MEMBER, "instance:delete")
    assert has_permission(Role.ADMIN, "instance:delete")
    assert not has_permission(Role.ADMIN, "member:grant_owner")


def test_password_policy():
    for bad in ["short1A", "alllowercase123", "ALLUPPERCASE123", "NoDigitsHereAtAll"]:
        with pytest.raises(InvalidInput):
            validate_password_policy(bad)
    validate_password_policy(PW)


def test_login_and_session_lifecycle(iam):
    org, tok, p = setup(iam)
    assert iam.authenticate(tok).organization_id == org
    iam.logout(p)
    with pytest.raises(Unauthorized):
        iam.authenticate(tok)


def test_wrong_password_and_unknown_user_same_error(iam, audit):
    setup(iam)
    for email, pw in [("owner@example.com", "wrong"), ("nobody@example.com", PW)]:
        with pytest.raises(Unauthorized) as e:
            iam.login(email, pw)
        assert str(e.value) == "invalid credentials"
    assert sum(1 for e in audit.repo.all() if e.result == "denied") == 2


def test_each_login_issues_new_token(iam):
    setup(iam)
    t2, _ = iam.login("owner@example.com", PW)
    t3, _ = iam.login("owner@example.com", PW)
    assert t2 != t3


def test_session_expiry(audit):
    from datetime import datetime, timedelta, timezone
    now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    iam = IamService(InMemoryIamRepository(), FakeHasher(), audit, session_ttl_seconds=60, clock=lambda: now[0])
    iam.register_organization("A", "a@example.com", PW)
    tok, _ = iam.login("a@example.com", PW)
    iam.authenticate(tok)
    now[0] += timedelta(seconds=61)
    with pytest.raises(Unauthorized):
        iam.authenticate(tok)


def test_login_rate_limit(audit):
    iam = IamService(InMemoryIamRepository(), FakeHasher(), audit, login_limiter=RateLimiter(3))
    iam.register_organization("A", "a@example.com", PW)
    for _ in range(3):
        with pytest.raises(Unauthorized):
            iam.login("a@example.com", "bad", ip="1.1.1.1")
    with pytest.raises(RateLimited):
        iam.login("a@example.com", PW, ip="1.1.1.1")


def test_duplicate_email(iam):
    setup(iam)
    with pytest.raises(Conflict):
        iam.register_organization("B", "owner@example.com", PW)


def test_no_privilege_escalation(iam, audit):
    org, _, owner = setup(iam)
    iam.add_member(owner, "admin@example.com", PW, "admin")
    iam.add_member(owner, "member@example.com", PW, "member")
    _, admin = iam.login("admin@example.com", PW)
    _, member = iam.login("member@example.com", PW)
    with pytest.raises(Forbidden):  # member cannot manage members
        iam.change_role(member, member.user_id, "admin")
    with pytest.raises(Forbidden):  # admin cannot mint owners
        iam.add_member(admin, "x@example.com", PW, "owner")
    with pytest.raises(Forbidden):  # admin cannot touch another admin/owner
        iam.change_role(admin, owner.user_id, "viewer")
    with pytest.raises(Forbidden):  # nobody changes own role
        iam.change_role(owner, owner.user_id, "viewer")
    iam.change_role(admin, member.user_id, "viewer")
    assert iam.repo.get_membership(member.user_id, org) == "viewer"
    assert any(e.result == "denied" for e in audit.repo.all())


def test_csrf_token_binding():
    assert csrf_valid("tok", csrf_for("tok", "k" * 32), "k" * 32)
    assert not csrf_valid("tok2", csrf_for("tok", "k" * 32), "k" * 32)
    assert not csrf_valid("tok", "", "k" * 32)
