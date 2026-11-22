# Roadmap

Status: phases 1-6 implemented in code; see the *Verification* notes. Phases are only "done" where tests were actually run.

## Phase 0: design (this repository state)

Architecture, threat model, dependency plan, ADRs. No code.

## Phase 1: milestone 1, backend foundation

Goal: a running API that reports the real state of its database.

Steps:

1. Repository layout, license decision, contribution guide.
2. Backend bootstrap (FastAPI, typed config from environment, structured logs).
3. PostgreSQL connection through SQLAlchemy.
4. First Alembic migration and a migration test.
5. `/health` (liveness) and `/ready` (checks the database for real).
6. First integration test against a real PostgreSQL instance.
7. Docker Compose for local PostgreSQL and the API.
8. `docs/development.md` with prerequisites, commands and environment variables.

Acceptance criteria:

- The application starts.
- The database connection works and `/ready` fails when the database is down.
- Migrations apply on an empty database and the test proves it.
- Tests run and pass, with the output recorded.
- Configuration is documented; no credentials are committed.
- Local startup needs no paid or external service.

Requirements to verify this milestone: a machine with a working Docker daemon, outbound access to package registries, Python and Node. This is **not** available in the environment used to write these documents.

## Phase 2: identity and audit

Users, organizations, roles, sessions, CSRF, rate limiting, append-only audit log, tenant isolation tests.

## Phase 3: compute vertical slice

Instance model and state machine, runner, Docker adapter, jobs with idempotency, start, stop, delete with confirmation.

## Phase 4: storage and network metadata

Volume and object abstraction on the local filesystem, network and subnet models, relationship validation.

## Phase 5: monitoring and console

Prometheus metrics with documented sources, Grafana, React console pages backed by real data.

## Phase 6: CI and hardening

GitHub Actions with pinned actions, linting, type checks, dependency, secret and container scanning, review of runner isolation.

## Reporting at each milestone

Files changed, features actually implemented, commands run, test results, known limitations, security findings, resource requirements, next smallest verifiable step.

## Implementation status

| Phase | Implemented | Verified here |
|---|---|---|
| 1 Backend foundation | Config, logging, `/health`, `/ready`, SQLAlchemy, Alembic, compose, `docs/development.md` | Schema applied and tested on PostgreSQL 16; HTTP layer **not run** (FastAPI unavailable in the build environment) |
| 2 Identity and audit | Users, organizations, roles, sessions, CSRF, rate limit, hash-chained append-only audit | Unit tests + PostgreSQL tests |
| 3 Compute | State machine, templates, runner, jobs with idempotency, start/stop/delete with confirmation, reconciliation | State machine, jobs, runner argument builder tested; Docker adapter **not run** |
| 4 Storage and network | Local object store with quotas; networks, subnets, IP allocation with overlap checks (metadata only) | Unit tests |
| 5 Monitoring and console | `/metrics` with documented sources and explicit unavailability, Grafana provisioning, React console pages | Metrics unit-tested; console type-checked only |
| 6 CI and hardening | GitHub Actions (lint, types, tests, audits, secret/container scans), Dependabot, SECURITY.md | Workflow **not yet executed** on GitHub |

Next smallest verifiable step: run `docker compose up --build` on a machine with Docker, then the API tests (`pytest`) with FastAPI installed, and fix whatever fails.
