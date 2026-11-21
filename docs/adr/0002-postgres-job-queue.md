# ADR-0002: PostgreSQL-backed job queue, no Redis at first

Status: proposed

## Context

Provisioning must be asynchronous, idempotent and observable. PostgreSQL is already required. The workload at this stage is small.

## Decision

Store jobs in PostgreSQL and claim them with `SELECT ... FOR UPDATE SKIP LOCKED`. Use unique idempotency keys to prevent duplicate jobs. Do not add Redis until measurements show the need.

## Consequences

- One fewer service to run, secure and monitor.
- Job state and business state can change in the same transaction.
- Throughput is lower than a dedicated broker; this is acceptable for the target scale.
- Revisit if queue latency or database load becomes a measured problem.
