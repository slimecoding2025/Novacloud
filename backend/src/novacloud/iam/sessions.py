import hashlib
import hmac
import secrets


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Only the SHA-256 of a session token is stored; a database leak does not yield usable cookies."""
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_for(token: str, secret_key: str) -> str:
    return hmac.new(secret_key.encode(), b"csrf:" + token.encode(), hashlib.sha256).hexdigest()


def csrf_valid(token: str, supplied: str, secret_key: str) -> bool:
    return bool(supplied) and hmac.compare_digest(csrf_for(token, secret_key), supplied)
