"""Password hashing through argon2-cffi (no custom crypto)."""
from typing import Protocol

from novacloud.core.errors import InvalidInput

MIN_LENGTH = 12
MAX_LENGTH = 256


def validate_password_policy(password: str) -> None:
    if not isinstance(password, str) or not (MIN_LENGTH <= len(password) <= MAX_LENGTH):
        raise InvalidInput(f"password must be {MIN_LENGTH}-{MAX_LENGTH} characters")
    if password.lower() == password or password.upper() == password or not any(c.isdigit() for c in password):
        raise InvalidInput("password must mix upper/lower case letters and include a digit")


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password_hash: str, password: str) -> bool: ...


class Argon2Hasher:
    def __init__(self):
        from argon2 import PasswordHasher as _PH  # lazy: optional at import time
        from argon2.exceptions import InvalidHashError, VerificationError
        self._ph = _PH()
        self._errors = (VerificationError, InvalidHashError)

    def hash(self, password: str) -> str:
        return self._ph.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._ph.verify(password_hash, password)
        except self._errors:
            return False
