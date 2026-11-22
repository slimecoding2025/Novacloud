<div align="center">

# NOVACLOUD

**Open-source cloud management platform: one API and web console for compute, storage, networking, identity and orchestration.**

![Status](https://img.shields.io/badge/status-pre--alpha-orange)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.12-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)
![React](https://img.shields.io/badge/React-TypeScript-61DAFB)

</div>

---

## Overview

NOVACLOUD lets developers, sysadmins, labs and small organizations manage infrastructure through a single API and console, using only local, free software.

**Principles**

- **Zero budget.** No paid services, no subscriptions, no payment card.
- **Local-first.** Development and operation need no external service.
- **Honest by construction.** No fake resources or fabricated metrics; anything unavailable is shown as unavailable.
- **Secure by default.** Default-deny authorization, tenant isolation in the service layer, tamper-evident audit log, hardened container runner.
- **Modular monolith** with ports-and-adapters boundaries ([ADR-0001](docs/adr/0001-modular-monolith.md)).

## Status

> **Pre-alpha.** All six roadmap phases are implemented and the GitHub Actions pipeline is green, but the Docker runner and the full `docker compose` stack have **not been run against a real Docker daemon** yet. No production-readiness or security claims are made; there has been no external review.

| Area | Implemented | Verification |
|---|---|---|
| Identity: organizations, users, roles, sessions, CSRF, rate limiting | Yes | Unit-tested |
| Audit log: hash-chained, append-only (DB triggers + restricted role) | Yes | Unit-tested and tested on real PostgreSQL 16 |
| Compute: instance state machine, jobs, idempotency, reconciliation | Yes | Unit-tested |
| Runner (only component touching Docker) and Docker adapter | Yes | Argument builder tested; **not run against a Docker daemon** |
| Storage: local object store, quotas, path-traversal protection | Yes | Unit-tested |
| Network: networks, subnets, IP allocation, overlap checks (metadata only) | Yes | Unit-tested; SQL checked on PostgreSQL |
| Monitoring: Prometheus metrics with documented sources, Grafana provisioning | Yes | Metrics unit-tested |
| HTTP API (FastAPI) | Yes | 8 HTTP-level tests pass in CI (auth, CSRF, IDOR, limits, metrics, error hygiene) |
| Web console (React/TypeScript) | Yes | Type-checked and built in CI; not exercised in a browser |
| CI (GitHub Actions), Dependabot, security policy | Yes | Green: ruff, mypy, bandit, pip-audit, pytest on PostgreSQL 16, Alembic upgrade/downgrade, npm typecheck/build/audit, gitleaks, hadolint, trivy, compose validation |

Test suite in CI: **73 passing** (unit, HTTP and real-PostgreSQL tests).

## Features

- **Multi-tenant IAM** with roles `owner`, `admin`, `member`, `viewer`; privilege escalation is blocked and every denial is audited.
- **Instances** are containers launched from allow-listed templates only; lifecycle `planned → provisioning → running → stopping → stopped → deleting → deleted` (plus `failed`). `running` is set only after the provider confirms it; a reconciliation loop detects drift. Deletion requires typing the instance name.
- **Jobs** in PostgreSQL (`FOR UPDATE SKIP LOCKED`), idempotency keys per organization, no automatic retry for destructive operations, execution plans with compensation.
- **Object storage** addressed by generated IDs, size limits, per-organization quota.
- **Network metadata:** private IPv4 CIDRs, subnet containment, overlap detection, IP allocation (does not configure real networks).
- **Observability:** JSON logs with secret redaction, correlation IDs, `/health`, `/ready` (real database check), `/metrics`.

## Architecture

```
Browser ──▶ nginx (CSP) ──▶ API (FastAPI) ──▶ PostgreSQL
                              │   ▲               ▲
                              │   └── worker ─────┘   (jobs, reconciliation)
                              ▼
                           runner ──▶ Docker      (only service with the Docker socket; internal network)
Prometheus ──▶ /metrics (bearer token)      Grafana ──▶ Prometheus
```

```
backend/src/novacloud/
  iam/ audit/ compute/ orchestration/ storage/ network/ monitoring/   domain + services
  providers/    runner client, in-memory fake (tests only)
  runner/       the privileged runner
  infra/        PostgreSQL repositories
  api/          FastAPI app, routes under /api/v1
  core/         config, errors, logging, rate limiting
backend/migrations/sql/   schema (applied by Alembic, tested directly on PostgreSQL)
frontend/                 React + TypeScript console
deploy/                   Prometheus, Grafana, PostgreSQL role hardening
docs/                     architecture, threat model, roadmap, ADRs, development guide
```

## Quick start

**Prerequisites:** Docker with Compose v2.

```bash
cp .env.example .env     # replace every "change-me" value
docker compose up --build
```

| Service | URL |
|---|---|
| Console | http://localhost:8080 |
| API docs | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 |

Open the console, choose **Create an organization**; the first user is the `owner`. Set `REGISTRATION_ENABLED=false` afterwards.

Run the tests: `cd backend && pip install -r requirements-dev.txt && pytest` — set `PGHOST`/`PGUSER`/`PGPASSWORD` to include the real-PostgreSQL tests. Full instructions: [docs/development.md](docs/development.md).

## Security

Threat model with per-control implementation status: [docs/threat-model.md](docs/threat-model.md). Report vulnerabilities privately: [SECURITY.md](SECURITY.md).

## Known limitations

- Runner/Docker integration and the console in a browser have not been exercised yet (see Status).
- Instances run with `--network none`; real network attachment is not implemented.
- Networks are cached per API process: run a single API replica. Rate limiting is also per process.
- No TLS termination is provided; use a reverse proxy and `COOKIE_SECURE=true` outside development.
- GitHub Actions are referenced by version tag, not commit SHA; Dependabot (minor/patch updates only) keeps them current. `npm audit` ignores dev-only advisories (Vite/esbuild dev server).
- Dependency licenses still need a formal review ([docs/dependencies.md](docs/dependencies.md)). Grafana is AGPL-licensed.

## Documentation

| Document | Purpose |
|---|---|
| [docs/development.md](docs/development.md) | Setup, configuration, API conventions |
| [docs/architecture.md](docs/architecture.md) | Architecture, module boundaries, lifecycle |
| [docs/threat-model.md](docs/threat-model.md) | Threats, controls, implementation status |
| [docs/roadmap.md](docs/roadmap.md) | Phases and status |
| [docs/dependencies.md](docs/dependencies.md) | Zero-budget dependency plan |
| [docs/adr/](docs/adr/) | Architecture decision records |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Released under the [MIT License](LICENSE).
