<div align="center">

# NOVACLOUD

**Open-source cloud management platform: one API and web console for compute, storage, networking, identity and orchestration.**

![Status](https://img.shields.io/badge/status-pre--alpha-orange)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.12-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)

</div>

---

## Overview

NOVACLOUD targets developers, sysadmins, labs and small organizations that want to manage infrastructure through a single API and console, using only local, free software.

**Design principles**

- **Zero budget.** No paid services, no mandatory subscriptions, no payment card.
- **Local-first.** Development and operation require no external service.
- **Honest by construction.** No fake resources or fabricated metrics; anything unavailable is reported as unavailable.
- **Auditable.** Security-relevant actions are recorded in a tamper-evident log.
- **Modular monolith** with ports-and-adapters boundaries (see [ADR 0001](docs/adr/0001-modular-monolith.md)).

## Status

> **Pre-alpha.** Milestone 1 (foundation) is implemented but has **not yet been run end-to-end** against a real PostgreSQL/Docker environment. No production-readiness or security claims are made.

| Area | State |
|---|---|
| Architecture, threat model, ADRs | Proposed (see `docs/`) |
| Backend skeleton (FastAPI) | Implemented, health endpoint only |
| Tamper-evident audit log | Implemented; domain logic unit-tested |
| Database migrations (Alembic) | Initial migration written, not yet applied in a test |
| Web console (React/TypeScript) | Minimal status page |
| Local stack (Docker Compose) | Written, not yet executed |
| Identity, compute, storage, network | Not started |

## Features (milestone 1)

- `GET /api/health` returns service status and version.
- `POST /api/audit` appends an entry to a hash-chained audit log; each entry commits to the previous one with SHA-256.
- `GET /api/audit/verify` recomputes the chain and reports whether it is intact; edits and reordering are detected.
- Interactive API docs at `/docs`.

## Architecture

```
frontend/ (React + Vite)  ──HTTP──▶  backend/ (FastAPI)  ──SQLAlchemy──▶  PostgreSQL
                                          │
                              Prometheus ◀┘   Grafana
```

```
backend/
  app/
    api/       HTTP routers
    core/      configuration
    domain/    pure business logic (no I/O)
    infra/     database and persistence
  alembic/     schema migrations
  tests/
frontend/      React + TypeScript console
deploy/        Prometheus configuration
docs/          architecture, threat model, roadmap, ADRs
```

## Getting started

**Prerequisites:** Docker with Compose, Python 3.12+, Node.js 20+.

```bash
# Full local stack (PostgreSQL, API, Prometheus, Grafana)
docker compose up --build
```

| Service | URL |
|---|---|
| API docs | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 |

```bash
# Web console (development)
cd frontend && npm install && npm run dev

# Backend tests
cd backend && pip install -r requirements-dev.txt && pytest
```

**Configuration:** `DATABASE_URL` (default: `postgresql+psycopg://novacloud:novacloud@localhost:5432/novacloud`). The Compose credentials are for local development only.

## Roadmap

See [docs/roadmap.md](docs/roadmap.md). Next planned work: readiness endpoint that checks the database, integration tests against real PostgreSQL, then identity (users, roles, sessions) integrated with the audit log.

## Known limitations

- No authentication or authorization yet: the audit endpoints are open.
- No `/ready` endpoint, no structured logging, no CI.
- Backend metrics endpoint and Grafana datasource provisioning are not implemented.
- Compose and migrations are unverified in a running environment.
- Dependency licenses are still to be verified (see [docs/dependencies.md](docs/dependencies.md)).

## Documentation

| Document | Purpose |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Architecture, module boundaries, resource lifecycle |
| [docs/threat-model.md](docs/threat-model.md) | Threat model and required controls |
| [docs/roadmap.md](docs/roadmap.md) | Phases, milestones, acceptance criteria |
| [docs/dependencies.md](docs/dependencies.md) | Zero-budget dependency plan |
| [docs/adr/](docs/adr/) | Architecture decision records |

## Contributing

Contribution guidelines will be added in a later milestone. Issues and pull requests are welcome in the meantime.

## License

Released under the [MIT License](LICENSE).
