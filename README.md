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

> **Pre-alpha.** All six roadmap phases are implemented. The GitHub Actions pipeline is green and includes an **end-to-end test of the full `docker compose` stack on a real Docker daemon** (sign-up, container create/stop/start/delete, audit verification). No production-readiness or security claims are made; there has been no external review.

| Area | Implemented | Verification |
|---|---|---|
| Identity: organizations, users, roles, sessions, CSRF, rate limiting | Yes | Unit-tested |
| Audit log: hash-chained, append-only (DB triggers + restricted role) | Yes | Unit-tested and tested on real PostgreSQL 16 |
| Compute: instance state machine, jobs, idempotency, reconciliation | Yes | Unit-tested |
| Runner (only component touching Docker) and Docker adapter | Yes | Handler unit-tested; end-to-end in CI against real Docker (container created, hardened flags confirmed with `docker inspect`, deleted) |
| Storage: local object store, quotas, path-traversal protection | Yes | Unit-tested |
| Network: networks, subnets (each a real internal Docker bridge), IP allocation, overlap checks, instance attachment, outbound policy, loopback-published ports | Yes | Unit-tested; SQL checked on PostgreSQL; isolation verified in CI (see below) |
| Monitoring: Prometheus metrics with documented sources, Grafana provisioning | Yes | Metrics unit-tested |
| HTTP API (FastAPI) | Yes | 8 HTTP-level tests pass in CI (auth, CSRF, IDOR, limits, metrics, error hygiene) |
| Web console (React/TypeScript): overview dashboard, instances, jobs, objects, networks, audit, members; light/dark theme | Yes | Type-checked and built in CI; not exercised in a browser |
| CI (GitHub Actions), Dependabot, security policy | Yes | Green: ruff, mypy, bandit, pip-audit, pytest on PostgreSQL 16, Alembic upgrade/downgrade, npm typecheck/build/audit, gitleaks, hadolint, trivy, compose validation |

Test suite in CI: unit, HTTP, runner and real-PostgreSQL tests plus the `scripts/e2e.sh` end-to-end run (containers, hardening flags, same-subnet connectivity, cross-subnet isolation) and Playwright browser tests of the console (`ui-tests/`: sign-in, instance lifecycle, objects, members, networks, audit log, sign-out).

## Features

- **Multi-tenant IAM** with roles `owner`, `admin`, `member`, `viewer`; privilege escalation is blocked and every denial is audited.
- **Instances** are containers launched from allow-listed templates only; lifecycle `planned → provisioning → running → stopping → stopped → deleting → deleted` (plus `failed`). `running` is set only after the provider confirms it; a reconciliation loop detects drift. Deletion requires typing the instance name.
- **Jobs** in PostgreSQL (`FOR UPDATE SKIP LOCKED`), idempotency keys per organization, no automatic retry for destructive operations, execution plans with compensation.
- **Object storage** addressed by generated IDs, size limits, per-organization quota.
- **Networking:** private IPv4 CIDRs, subnet containment, overlap detection and IP allocation. Every subnet becomes a **Docker bridge**, **internal by default** (no route out); an instance can be attached to a subnet with an allocated address. Instances in the same subnet reach each other; other subnets and the internet are unreachable (CI proves this with real containers). A subnet created with `egress: true` gets outbound NAT, and an `nginx-small` instance in such a subnet can publish one host port (20000-29999), bound to `127.0.0.1` only. Instances without a subnet run with no network at all.
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

> **Hosting:** the full stack needs Docker and PostgreSQL, so it cannot run on Vercel-style static/serverless hosts (a frontend-only deployment shows the sign-in page but cannot sign in). See *Where can it run for free?* in [docs/development.md](docs/development.md).

Run the end-to-end test against a running stack with `./scripts/e2e.sh` (needs `curl`, `jq`, Docker). Browser tests: `cd ui-tests && npm install && npx playwright install chromium && npx playwright test` (stack on `http://localhost:8080`, or set `WEB_URL`).

Run the tests: `cd backend && pip install -r requirements-dev.txt && pytest` — set `PGHOST`/`PGUSER`/`PGPASSWORD` to include the real-PostgreSQL tests. Full instructions: [docs/development.md](docs/development.md).

## Security

Threat model with per-control implementation status: [docs/threat-model.md](docs/threat-model.md). Report vulnerabilities privately: [SECURITY.md](SECURITY.md).

## Known limitations

- Browser tests cover every console page except Jobs and Overview (both are read-only views).
- Subnet CIDRs must be unique across the whole Docker host (Docker refuses overlapping bridges), even between organizations. Published ports exist only on egress subnets (Docker cannot publish from internal networks), one per instance, loopback only; exposing them beyond the host is left to your own reverse proxy.
- Network state is re-read from PostgreSQL before every operation (API and worker agree). Rate limiting is still per process, so it is per replica.
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
