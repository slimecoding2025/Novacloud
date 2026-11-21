# Threat model (initial)

Status: initial, written before implementation. Controls listed here are **requirements**, not implemented features.

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
