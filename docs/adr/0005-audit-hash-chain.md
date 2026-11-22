# ADR-0005: Hash-chained audit log enforced in PostgreSQL

Status: accepted

## Decision
Each audit event stores SHA-256 over its canonical JSON content plus the previous hash. Appends are serialised with an advisory lock; `prev_hash` is UNIQUE so the chain cannot fork. Triggers reject UPDATE, DELETE and TRUNCATE for every role; the application role additionally lacks those privileges (`deploy/postgres/roles.sql`). Metadata is redacted (passwords, tokens, secrets, cookies, keys) before hashing.

## Consequences
Edits by someone with direct superuser access are detectable through `GET /api/audit/verify` but not prevented (a superuser can drop the trigger). Anchoring the head hash outside the database is future work. A global lock makes audit writes sequential, which is acceptable at the intended scale.
