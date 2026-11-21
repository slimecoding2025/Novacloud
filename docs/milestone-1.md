# NOVACLOUD — Milestone 1 (foundation)

Run:  `docker compose up --build`  → API http://localhost:8000/docs, Prometheus :9090, Grafana :3001
Frontend (dev): `cd frontend && npm install && npm run dev`
Tests: `cd backend && pip install -r requirements-dev.txt && pytest`

Scope: FastAPI skeleton, `/api/health`, tamper-evident hash-chained audit log
(`POST /api/audit`, `GET /api/audit/verify`), Alembic migration, Postgres, Prometheus, Grafana.

Not done yet: IAM/auth, compute/storage/network modules, backend metrics endpoint,
Grafana datasource provisioning. Nothing here has been run against real Postgres/Docker.
