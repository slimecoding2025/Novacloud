from fastapi import Depends, Header, Request

from novacloud.core.errors import Forbidden, Unauthorized
from novacloud.iam.domain import Principal
from novacloud.iam.sessions import csrf_valid

COOKIE = "nc_session"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def container(request: Request):
    return request.app.state.container


def cid(request: Request) -> str:
    return getattr(request.state, "correlation_id", "")


def principal(request: Request, c=Depends(container), x_csrf_token: str | None = Header(default=None)) -> Principal:
    token = request.cookies.get(COOKIE)
    if token is None:
        raise Unauthorized("not authenticated")
    p = c.iam.authenticate(token)  # raises Unauthorized
    if request.method in UNSAFE and not csrf_valid(token, x_csrf_token or "", c.settings.secret_key):
        raise Forbidden("missing or invalid CSRF token")
    return p
