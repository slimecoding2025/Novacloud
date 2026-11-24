# Threat model (initial)

Status: updated for milestones 1-6. The *Implementation status* column below says what exists in code and how it was verified. No external review has taken place.

## Assets

- Tenant data and resource metadata
- Credentials, session tokens, secrets
- Audit log integrity
- The host and the container runtime
- Availability of the API and job queue

## Actors

- Anonymous internet user
- Authenticated user of one organization
- Malicious or compromised user trying to reach another tenant
- Organization admin
- Platform operator
- Compromised workload (container) managed by the platform

## Trust boundaries

1. Browser to API
2. API to database
3. API to runner (privileged boundary)
4. Runner to container runtime
5. Platform to managed workloads

## Threats and required controls

| Threat | Example | Required control | Test |
|---|---|---|---|
| Broken access control, IDOR | User reads `/instances/{id}` of another org | Tenant-scoped repositories, authorization in service layer, default deny | Cross-tenant tests for every resource |
| Privilege escalation | Member grants themselves admin | Role changes require admin, audited | Authorization regression tests |
| SQL injection | Crafted filter or sort value | ORM with bound parameters, allow-listed sort fields | Injection test cases |
| XSS | Stored resource name rendered unsafely | React escaping, strict CSP, output validation | Frontend tests |
| CSRF | Cross-site request with session cookie | SameSite cookies plus CSRF token | API tests |
| SSRF | Storage or provider URL points to internal service | No user-supplied URLs in v1; allow-list if added | Validation tests |
| Path traversal | `../` in object name | Objects addressed by generated ID, resolved path checked under root | Traversal tests |
| Command injection | Instance parameters reach a shell | No shell invocation; template-only container specs | Static analysis, tests |
| Unsafe deserialization | Pickle or unsafe YAML | Only JSON and Pydantic; no pickle | Static analysis |
| Authentication bypass, session fixation | Reused session ID after login | Rotate session on login, expiry, revocation | Auth tests |
| Token and secret leakage | Secret in logs or errors | Log redaction, safe error responses, secret scanning in CI | Log tests, scanner |
| Insecure uploads | Oversized or hostile file | Size limits, ID-based storage, no execution | Limit tests |
| Race conditions, replay | Double delete, duplicate create | Idempotency keys, unique constraints, row locks | Concurrency tests |
| Resource exhaustion, DoS | Flood of create requests | Rate limits, request size limits, quotas | Load and limit tests |
| Container escape | Workload gains host access | No privileged mode, dropped capabilities, no Docker socket in app | Config review, container scan |
| Audit tampering | Editing past events | Append-only, DB role without UPDATE or DELETE | Permission test |

## Highest-risk component

The runner holds the power to create and destroy containers. Anyone who compromises it can affect the host. It must stay small, expose a narrow authenticated API, and be reviewed separately.

## Known gaps

- No code exists to test these controls yet.
- Network isolation will not be claimed unless the underlying Docker network setup enforces it and tests show it.
- This model has had no external review.

## Implementation status

Legend: **Tested** = automated test executed during development; **Written** = implemented but only reviewed by reading/static checks, not executed (needs Docker, FastAPI or a browser).

| Control | Status | Evidence |
|---|---|---|
| Tenant-scoped access, default deny, authorization in service layer | Tested | `test_iam.py`, `test_compute.py`, `test_storage.py`, `test_network.py` (cross-tenant cases) |
| Privilege escalation prevention, audited denials | Tested | `test_no_privilege_escalation` |
| SQL injection (bound parameters only) | Written | `infra/sql.py` uses SQLAlchemy `text()` with parameters; allow-listed values elsewhere |
| CSRF (SameSite=Strict + HMAC token) | Tested | `test_csrf_token_binding`, `test_api.py` (run in CI) |
| Session rotation, expiry, revocation | Tested | `test_iam.py` |
| Path traversal | Tested | `test_storage.py` |
| Command injection / privileged containers | Tested | `test_runner_spec.py` (no shell, template-only, hardened flags) |
| Race conditions, duplicate create | Tested on real PostgreSQL | `test_postgres_schema.py` (idempotency uniqueness, SKIP LOCKED) |
| Audit tampering | Tested on real PostgreSQL | triggers + role without UPDATE/DELETE |
| Secret/token leakage in logs | Tested | `test_monitoring.py` redaction |
| Rate limiting, body-size limits, quotas | Tested | limiter, quotas, upload limit (`test_api.py`) |
| Security headers, CSP | Tested (API) / Written (nginx) | `test_api.py`; `frontend/nginx.conf` not run |
| Container escape | Tested (configuration) | runner drops all capabilities, read-only FS, no network, no privileged mode, no mounts; CI confirms the flags on a real container with `docker inspect`. Kernel-level escape resistance is not tested |
| XSS | Written | React escaping; strict CSP; no `dangerouslySetInnerHTML` |
| SSRF | Mitigated by design | no user-supplied URLs anywhere |

## Remaining gaps

- The runner is verified only at configuration level on a real daemon; no escape testing or review has been done.
- Subnet bridges are `--internal` unless the subnet is created with `egress: true` (outbound NAT, chosen explicitly and audited); published ports bind `127.0.0.1` only, never `0.0.0.0`. Members can talk to each other and, with egress, to the internet. Isolation between subnets relies on Docker's bridge rules and is tested in CI only for the cases in `scripts/e2e.sh`; it is not a substitute for a security review.
- Rate limiting is in-process.
- Registration is open unless `REGISTRATION_ENABLED=false`.
- No TLS termination is provided; run behind a reverse proxy and set `COOKIE_SECURE=true`.
- Audit anchoring outside the database is not implemented.
