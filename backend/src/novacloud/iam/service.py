import uuid
from datetime import datetime, timedelta, timezone
from typing import Protocol

from novacloud.audit.service import AuditService
from novacloud.core.errors import Conflict, Forbidden, InvalidInput, NotFound, RateLimited, Unauthorized
from novacloud.core.ratelimit import RateLimiter
from novacloud.iam.domain import RANK, Principal, Role, SessionRecord, has_permission, normalize_email
from novacloud.iam.passwords import PasswordHasher, validate_password_policy
from novacloud.iam.sessions import hash_token, new_token


class IamRepository(Protocol):
    def create_org(self, org_id: str, name: str) -> None: ...
    def create_user(self, user_id: str, email: str, password_hash: str) -> None: ...
    def get_user_by_email(self, email: str) -> dict | None: ...
    def add_membership(self, user_id: str, org_id: str, role: str) -> None: ...
    def get_membership(self, user_id: str, org_id: str) -> str | None: ...
    def list_memberships(self, user_id: str) -> list[tuple[str, str]]: ...
    def list_members(self, org_id: str) -> list[dict]: ...
    def set_role(self, user_id: str, org_id: str, role: str) -> None: ...
    def add_session(self, s: SessionRecord) -> None: ...
    def get_session_by_hash(self, token_hash: str) -> SessionRecord | None: ...
    def revoke_session(self, session_id: str, at: datetime) -> None: ...


class InMemoryIamRepository:
    def __init__(self):
        self.orgs, self.users, self.members, self.sessions = {}, {}, {}, {}

    def create_org(self, org_id, name):
        self.orgs[org_id] = name

    def create_user(self, user_id, email, password_hash):
        if any(u["email"] == email for u in self.users.values()):
            raise Conflict("email already registered")
        self.users[user_id] = {"id": user_id, "email": email, "password_hash": password_hash, "is_active": True}

    def get_user_by_email(self, email):
        return next((u for u in self.users.values() if u["email"] == email), None)

    def add_membership(self, user_id, org_id, role):
        self.members[(user_id, org_id)] = role

    def get_membership(self, user_id, org_id):
        return self.members.get((user_id, org_id))

    def list_memberships(self, user_id):
        return [(o, r) for (u, o), r in self.members.items() if u == user_id]

    def list_members(self, org_id):
        return [{"user_id": u, "email": self.users[u]["email"], "role": r}
                for (u, o), r in self.members.items() if o == org_id]

    def set_role(self, user_id, org_id, role):
        self.members[(user_id, org_id)] = role

    def add_session(self, s):
        self.sessions[s.token_hash] = s

    def get_session_by_hash(self, token_hash):
        return self.sessions.get(token_hash)

    def revoke_session(self, session_id, at):
        for h, s in self.sessions.items():
            if s.id == session_id:
                self.sessions[h] = SessionRecord(**{**s.__dict__, "revoked_at": at})


class IamService:
    def __init__(self, repo: IamRepository, hasher: PasswordHasher, audit: AuditService,
                 session_ttl_seconds: int = 28800, login_limiter: RateLimiter | None = None,
                 clock=lambda: datetime.now(timezone.utc)):
        self.repo, self.hasher, self.audit = repo, hasher, audit
        self.ttl, self.limiter, self.clock = session_ttl_seconds, login_limiter, clock
        # Used so unknown-user logins cost the same as wrong-password logins.
        self._dummy_hash = hasher.hash("Dummy-password-1")

    # -- registration -------------------------------------------------
    def register_organization(self, org_name: str, email: str, password: str, correlation_id="") -> tuple[str, str]:
        name = (org_name or "").strip()
        if not (1 <= len(name) <= 80):
            raise InvalidInput("organization name must be 1-80 characters")
        email = normalize_email(email)
        validate_password_policy(password)
        org_id, user_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.repo.create_org(org_id, name)
        self.repo.create_user(user_id, email, self.hasher.hash(password))
        self.repo.add_membership(user_id, org_id, Role.OWNER.value)
        self.audit.record(actor_id=user_id, organization_id=org_id, action="org.create",
                          resource_type="organization", resource_id=org_id, correlation_id=correlation_id)
        return org_id, user_id

    # -- authentication ----------------------------------------------
    def login(self, email: str, password: str, org_id: str | None = None, ip: str = "",
              correlation_id="") -> tuple[str, Principal]:
        key = f"{ip}|{(email or '').lower()}"
        if self.limiter and not self.limiter.allow(key):
            raise RateLimited("too many login attempts")
        user = self.repo.get_user_by_email((email or "").strip().lower())
        ok = self.hasher.verify(user["password_hash"] if user else self._dummy_hash, password or "")
        if not (user and ok and user["is_active"]):
            self.audit.record(actor_id=user["id"] if user else "anonymous", organization_id=None,
                              action="auth.login", resource_type="session", resource_id="-",
                              result="denied", correlation_id=correlation_id)
            raise Unauthorized("invalid credentials")
        memberships = self.repo.list_memberships(user["id"])
        if not memberships:
            raise Unauthorized("invalid credentials")
        chosen = org_id or memberships[0][0]
        role = self.repo.get_membership(user["id"], chosen)
        if role is None:
            raise Unauthorized("invalid credentials")
        # A fresh token is issued on every login (no session fixation); old sessions stay valid until expiry/logout.
        token = new_token()
        now = self.clock()
        rec = SessionRecord(str(uuid.uuid4()), hash_token(token), user["id"], chosen, now,
                            now + timedelta(seconds=self.ttl))
        self.repo.add_session(rec)
        self.audit.record(actor_id=user["id"], organization_id=chosen, action="auth.login",
                          resource_type="session", resource_id=rec.id, correlation_id=correlation_id)
        return token, Principal(user["id"], chosen, Role(role), rec.id)

    def authenticate(self, token: str | None) -> Principal:
        if not token:
            raise Unauthorized("not authenticated")
        s = self.repo.get_session_by_hash(hash_token(token))
        if s is None or not s.is_active(self.clock()):
            raise Unauthorized("not authenticated")
        role = self.repo.get_membership(s.user_id, s.organization_id)
        if role is None:  # membership removed after login
            raise Unauthorized("not authenticated")
        return Principal(s.user_id, s.organization_id, Role(role), s.id)

    def logout(self, p: Principal, correlation_id="") -> None:
        self.repo.revoke_session(p.session_id, self.clock())
        self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action="auth.logout",
                          resource_type="session", resource_id=p.session_id, correlation_id=correlation_id)

    # -- authorization -------------------------------------------------
    def require(self, p: Principal, permission: str, resource_type="", resource_id="", correlation_id="") -> None:
        if not has_permission(p.role, permission):
            self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action=permission,
                              resource_type=resource_type or "-", resource_id=resource_id or "-",
                              result="denied", correlation_id=correlation_id)
            raise Forbidden("permission denied")

    # -- members -------------------------------------------------------
    def add_member(self, p: Principal, email: str, password: str, role: str, correlation_id="") -> str:
        self.require(p, "member:manage", "member", "-", correlation_id)
        target = self._role_checked(p, role, correlation_id)
        email = normalize_email(email)
        validate_password_policy(password)
        user_id = str(uuid.uuid4())
        self.repo.create_user(user_id, email, self.hasher.hash(password))
        self.repo.add_membership(user_id, p.organization_id, target.value)
        self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action="member.add",
                          resource_type="user", resource_id=user_id, correlation_id=correlation_id,
                          metadata={"role": target.value})
        return user_id

    def change_role(self, p: Principal, user_id: str, role: str, correlation_id="") -> None:
        self.require(p, "member:manage", "user", user_id, correlation_id)
        target = self._role_checked(p, role, correlation_id)
        current = self.repo.get_membership(user_id, p.organization_id)
        if current is None:
            raise NotFound("member not found")
        if user_id == p.user_id:
            raise Forbidden("cannot change your own role")
        if RANK[Role(current)] >= RANK[p.role] and p.role != Role.OWNER:
            self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action="member.role_change",
                              resource_type="user", resource_id=user_id, result="denied",
                              correlation_id=correlation_id)
            raise Forbidden("cannot modify a member of equal or higher role")
        self.repo.set_role(user_id, p.organization_id, target.value)
        self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action="member.role_change",
                          resource_type="user", resource_id=user_id, correlation_id=correlation_id,
                          metadata={"from": current, "to": target.value})

    def list_members(self, p: Principal) -> list[dict]:
        self.require(p, "org:read", "organization", p.organization_id)
        return self.repo.list_members(p.organization_id)

    def _role_checked(self, p: Principal, role: str, correlation_id: str) -> Role:
        try:
            target = Role(role)
        except ValueError:
            raise InvalidInput("unknown role") from None
        if target == Role.OWNER:
            self.require(p, "member:grant_owner", "member", "-", correlation_id)
        elif RANK[target] > RANK[p.role]:
            self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action="member.escalate",
                              resource_type="member", resource_id="-", result="denied",
                              correlation_id=correlation_id)
            raise Forbidden("cannot grant a role above your own")
        return target
