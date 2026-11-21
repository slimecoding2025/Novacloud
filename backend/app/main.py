from fastapi import FastAPI

from app.api import audit
from app.core.config import settings

app = FastAPI(title="NOVACLOUD", version=settings.app_version)
app.include_router(audit.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": settings.app_version}
