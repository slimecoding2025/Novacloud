# ADR-0004: Server-side sessions with HMAC-derived CSRF tokens

Status: accepted

## Context
The console is a same-origin SPA. Architecture.md requires server-side sessions, HttpOnly/SameSite cookies, CSRF protection, rotation on login and revocation on logout.

## Decision
- Opaque 256-bit session tokens; only their SHA-256 is stored in PostgreSQL.
- Cookie `nc_session`: HttpOnly, SameSite=Strict, Secure outside development.
- CSRF token = HMAC-SHA256(secret key, session token), returned by login and `/auth/me`, required in `X-CSRF-Token` for POST/PUT/PATCH/DELETE. No extra table; bound to the session.
- A new token is issued at every login; logout revokes the session; membership removal invalidates it at the next request.
- Passwords: Argon2id via argon2-cffi, 12-character minimum with simple composition rule.
- Unknown-user and wrong-password logins are indistinguishable (same error, comparable cost) and rate limited per IP+email.

## Consequences
Sessions can be revoked instantly. The rate limiter is in-process (limits multiply with replicas); a shared limiter is future work.
