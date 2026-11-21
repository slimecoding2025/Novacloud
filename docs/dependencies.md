# Zero-budget dependency plan

Status: plan. Versions are not pinned yet; they will be pinned and recorded when the backend is bootstrapped. Licenses below must be re-checked at adoption time, they are not verified here.

## Rule

Every dependency must be free to use, require no account or payment card, and not be needed to run local development.

## Planned

| Area | Tool | Notes |
|---|---|---|
| Language | Python | Check wheel availability for the chosen minor version |
| API | FastAPI, Pydantic, Uvicorn | |
| Database | PostgreSQL, SQLAlchemy, Alembic, psycopg | |
| Password hashing | argon2-cffi | Established library, no custom crypto |
| Frontend | React, TypeScript, Vite | Component library to be decided |
| Containers | Docker Engine, Docker Compose | Local only |
| Metrics | Prometheus, Grafana | Grafana license (AGPL) to be reviewed |
| Tests | pytest, httpx | Real PostgreSQL for integration tests |
| Quality | ruff, mypy | |
| Security scanning | bandit, pip-audit, gitleaks, trivy, hadolint | All must be confirmed free for this use |
| CI | GitHub Actions | Free for public repositories; limits for private ones must be checked |
| Infrastructure as code | Terraform or OpenTofu | Only where appropriate; license differences to review |

## Deferred or not chosen

- Redis: not used until measurements justify it (ADR-0002).
- S3-compatible storage backend: choose only after checking current license and edition limits.
- Any paid cloud provider: out of scope.

## To verify before adoption

- Current license of each tool.
- That no account or payment card is required.
- GitHub Actions minutes if the repository becomes private.
