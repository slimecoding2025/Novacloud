# Development guide

## Prerequisites

Docker with Compose v2, Python 3.12+, Node.js 20+, `psql` (for the PostgreSQL schema tests).

## Run the whole stack

```bash
cp .env.example .env          # then replace every "change-me" value
docker compose up --build
```

| Service | URL | Notes |
|---|---|---|
| Console | http://localhost:8080 | React app behind nginx (CSP, same-origin API proxy) |
| API docs | http://localhost:8000/docs | Disabled when `NOVACLOUD_ENV=production` |
| Prometheus | http://localhost:9090 | Scrapes `/metrics` with a bearer token |
| Grafana | http://localhost:3001 | admin / `GRAFANA_ADMIN_PASSWORD` |

Create an organization on the console's sign-in page (first user becomes `owner`).

## Backend without Docker

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q                      # unit + API tests
PGHOST=localhost PGUSER=postgres PGPASSWORD=... pytest -q tests/test_postgres_schema.py   # real PostgreSQL
```

Without `PGHOST` the PostgreSQL tests are skipped; without `fastapi`/`httpx` the API tests are skipped.

Lint and types: `ruff check src tests`, `mypy`, `bandit -r src`, `pip-audit -r requirements.txt`.

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `NOVACLOUD_ENV` | `development` | `production` enforces a 32+ char secret, secure cookies, no fake provider |
| `DATABASE_URL` | local PostgreSQL | SQLAlchemy URL (`postgresql+psycopg://…`) |
| `NOVACLOUD_SECRET_KEY` | none | HMAC key for CSRF tokens |
| `COOKIE_SECURE` | `false` | Must be `true` behind HTTPS |
| `REGISTRATION_ENABLED` | `true` | Set `false` after creating your organization |
| `DOCKER_GID` | `999` | Host group id of the Docker socket; the runner runs as a non-root user in that group |
| `SESSION_TTL_SECONDS` | `28800` | Session lifetime |
| `RUNNER_URL`, `RUNNER_TOKEN` | – | Runner endpoint and shared secret |
| `METRICS_TOKEN` | empty | `/metrics` returns 404 unless set |
| `STORAGE_ROOT` | `./data/objects` | Object storage directory |
| `MAX_OBJECT_BYTES`, `ORG_STORAGE_QUOTA_BYTES`, `MAX_INSTANCES_PER_ORG` | 10 MiB, 1 GiB, 20 | Limits and quotas |
| `LOGIN_RATE_PER_MINUTE`, `API_RATE_PER_MINUTE` | 10, 300 | In-process rate limits |

## Database

Schema: `backend/migrations/sql/0001_initial.sql`, applied by Alembic (`alembic upgrade head`).
Hardening: `deploy/postgres/roles.sql` creates the `novacloud_app` role without UPDATE/DELETE on `audit_log`
(the table also has triggers that reject UPDATE, DELETE and TRUNCATE for every role).

## API conventions

- All endpoints under `/api/v1`; errors are `{"error": {"code", "message"}}`.
- Session cookie `nc_session` (HttpOnly, SameSite=Strict); unsafe methods need the `X-CSRF-Token` returned by login/`me`.
- Mutating instance requests need an `Idempotency-Key` header; work is asynchronous and returns a job (HTTP 202).
- Deleting an instance requires `confirm_name` equal to its name.
