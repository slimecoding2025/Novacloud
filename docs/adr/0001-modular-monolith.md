# ADR-0001: Start as a modular monolith

Status: proposed

## Context

A small team and a zero budget. The domain boundaries (identity, compute, storage, network, orchestration, monitoring, audit) are not yet proven by real usage.

## Decision

Build one deployable backend with strict module boundaries. Modules communicate through explicit service interfaces and never read each other's tables.

## Consequences

- Simple to run, test and debug locally.
- Transactions across modules stay possible.
- Boundaries must be enforced by review and tests, because the compiler will not enforce them.
- Splitting into services later is possible along the existing interfaces.
