from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from novacloud.api.container import build
from novacloud.api.v1.routes import router as v1
from novacloud.core.config import Settings
from novacloud.core.errors import NovaError
from novacloud.core.logging import configure_logging

log = logging.getLogger("novacloud.api")
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def create_app(container=None) -> FastAPI:
    settings = container.settings if container else Settings()
    c = container or build(settings)
    configure_logging()
    app = FastAPI(title="NOVACLOUD", version=settings.app_version, docs_url="/docs" if settings.environment != "production" else None,
                  redoc_url=None, openapi_url="/openapi.json" if settings.environment != "production" else None)
    app.state.container = c

    @app.middleware("http")
    async def guard(request: Request, call_next):
        request.state.correlation_id = request.headers.get("X-Correlation-ID", "")[:64] or str(uuid.uuid4())
        try:
            n = int(request.headers.get("content-length") or 0)
        except ValueError:
            n = 0
        ip = request.client.host if request.client else "?"
        if n > settings.max_body_bytes:
            resp = JSONResponse({"error": {"code": "too_large", "message": "request body too large"}}, 413)
        elif not c.api_limiter.allow(ip):
            resp = JSONResponse({"error": {"code": "rate_limited", "message": "too many requests"}}, 429)
        else:
            resp = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            resp.headers.setdefault(k, v)
        resp.headers["X-Correlation-ID"] = request.state.correlation_id
        c.metrics.inc("novacloud_http_requests_total", (request.method, str(resp.status_code)))
        log.info("request", extra={"fields": {"method": request.method, "path": request.url.path,
                                              "status": resp.status_code, "correlation_id": request.state.correlation_id}})
        return resp

    @app.exception_handler(NovaError)
    async def nova_error(request: Request, exc: NovaError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, exc.status)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.error("unhandled", exc_info=exc, extra={"fields": {"correlation_id": getattr(request.state, "correlation_id", "")}})
        return JSONResponse({"error": {"code": "internal_error", "message": "internal error"}}, 500)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": settings.app_version}

    @app.get("/ready")
    def ready():
        try:
            c.ping()
        except Exception:  # noqa: BLE001
            return JSONResponse({"status": "unavailable", "database": "down"}, 503)
        return {"status": "ready", "database": "up"}

    @app.get("/metrics")
    def metrics(request: Request):
        tok = settings.metrics_token
        if not tok:
            return JSONResponse({"error": {"code": "not_found", "message": "metrics disabled"}}, 404)
        import hmac
        if not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {tok}"):
            return JSONResponse({"error": {"code": "unauthorized", "message": "unauthorized"}}, 401)
        return PlainTextResponse(c.metrics.render(), media_type="text/plain; version=0.0.4")

    app.include_router(v1)
    return app


def app_factory() -> FastAPI:  # uvicorn --factory novacloud.api.app:app_factory
    return create_app()
