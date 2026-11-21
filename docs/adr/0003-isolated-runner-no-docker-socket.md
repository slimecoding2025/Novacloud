# ADR-0003: Isolated runner; the application never holds the Docker socket

Status: proposed

## Context

Compute needs a real infrastructure adapter. Access to the Docker socket is equivalent to root on the host, so giving it to the web-facing application would turn any application bug into host compromise.

## Decision

Only a small, separate runner process talks to the container runtime. The application calls it through a narrow authenticated API that accepts validated templates, not shell commands or raw container options. Containers run without privileged mode and with capabilities dropped.

Instances are described and labeled as containers, not virtual machines.

## Open point

The exact isolation mechanism (rootless Docker, Podman, or a socket proxy) will be decided after testing on a real machine, and recorded in a follow-up ADR.

## Consequences

- Smaller blast radius for application vulnerabilities.
- One more component to build, document and review.
- The runner is the highest-risk component and needs its own security review.
