# NOVACLOUD

Open-source cloud management platform for developers, sysadmins, labs and small organizations: one API and web console for compute, storage, networking, identity and orchestration, built on local, free software only.

## Status

**Pre-alpha. There is no application code yet.**

The repository currently contains design documents only. Nothing described in `docs/` is implemented, tested or secured until the roadmap says so. No production-readiness or security claims are made.

## Constraints

- Budget: €0. No paid services, no mandatory subscriptions, no payment card.
- Local-first: development must not need any external service.
- No fake resources or fabricated metrics. Anything unavailable is shown as unavailable.

## Documents

| Document | Purpose |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Proposed architecture, module boundaries, resource lifecycle |
| [docs/threat-model.md](docs/threat-model.md) | Initial threat model and required controls |
| [docs/roadmap.md](docs/roadmap.md) | Phases, milestone 1 plan, acceptance criteria |
| [docs/dependencies.md](docs/dependencies.md) | Zero-budget dependency plan and items to verify |
| [docs/adr/](docs/adr/) | Architecture decision records |

## Planned stack

Python, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL; React and TypeScript; Docker Compose; Prometheus and Grafana. Versions will be pinned when the backend is bootstrapped.

## Known limitations

- No code, no tests, no CI yet.
- Licensed under MIT (see [LICENSE](LICENSE)). Dependency licenses are still to be verified (see docs/dependencies.md).

## Contributing

Contribution guidelines will be added with the first implementation milestone.
