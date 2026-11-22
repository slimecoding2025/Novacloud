# Security policy

NOVACLOUD is **pre-alpha** and has had no external security review. Do not expose it to untrusted networks.

## Reporting a vulnerability

Please report privately through GitHub's *Report a vulnerability* (Security tab) rather than a public issue.
Include affected version/commit, reproduction steps and impact. You will get an acknowledgement; there is no bounty.

## Scope and design

See [docs/threat-model.md](docs/threat-model.md) for the threat model and the status of each control.
The highest-risk component is the runner, which holds Docker access (see ADR-0003).
