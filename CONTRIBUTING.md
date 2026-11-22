# Contributing

1. Fork, branch from `main`, keep changes small and focused (one vertical slice per PR).
2. Run the checks locally (see [docs/development.md](docs/development.md)): `ruff`, `mypy`, `pytest`, frontend `typecheck`.
3. Add or update tests with every behaviour change; security-relevant changes need a test that fails without the fix.
4. Update `README.md` and the relevant document in `docs/` in the same PR.
5. Rules of the project: no paid services, no fake data or fabricated metrics, no secrets in the repository.

Commit messages: imperative mood, e.g. `feat: add subnet allocation`, `fix: reject traversal in object ids`.
