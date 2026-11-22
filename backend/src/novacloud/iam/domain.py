"""Roles and permissions. Authorization is default-deny: unknown role or permission => False."""
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from novacloud.core.errors import InvalidInput


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


READ = {"instance:read", "volume:read", "network:read", "job:read", "audit:read", "org:read", "metrics:read"}
WRITE = {"instance:create", "instance:start", "instance:stop", "volume:write", "network:write"}
ADMIN = {"instance:delete", "volume:delete", "network:delete", "member:manage"}
OWNER_ONLY = {"member:grant_owner"}

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.VIEWER: set(READ),
    Role.MEMBER: READ | WRITE,
    Role.ADMIN: READ | WRITE | ADMIN,
    Role.OWNER: READ | WRITE | ADMIN | OWNER_ONLY,
}
RANK = {Role.VIEWER: 0, Role.MEMBER: 1, Role.ADMIN: 2, Role.OWNER: 3}


def has_permission(role: Role | str | None, permission: str) -> bool:
    try:
        r = Role(role)
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS[r]


EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")


def normalize_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not EMAIL_RE.match(e):
        raise InvalidInput("invalid email")
    return e


@dataclass(frozen=True)
class Principal:
    """Authenticated caller bound to exactly one organization."""
    user_id: str
    organization_id: str
    role: Role
    session_id: str


@dataclass(frozen=True)
class SessionRecord:
    id: str
    token_hash: str
    user_id: str
    organization_id: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and now < self.expires_at
