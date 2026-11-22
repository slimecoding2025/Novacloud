import pytest

from novacloud.audit.service import AuditService, InMemoryAuditRepository
from novacloud.iam.service import IamService, InMemoryIamRepository


class FakeHasher:
    """Test double: NOT a real hash. Production uses Argon2Hasher."""
    def hash(self, p): return "h:" + p
    def verify(self, h, p): return h == "h:" + p


@pytest.fixture
def audit():
    return AuditService(InMemoryAuditRepository())


@pytest.fixture
def iam(audit):
    return IamService(InMemoryIamRepository(), FakeHasher(), audit)
