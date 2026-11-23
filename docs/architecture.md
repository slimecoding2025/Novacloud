# Architecture (proposal)

Status: implemented as described, with the deviations listed under *Implementation notes*. Decisions are recorded in [adr/](adr/).

## Goals and priorities

Correctness, security, reliability, maintainability, observability, performance, usability, visual quality, in that order. Zero budget, local-first.

## Shape: modular monolith

One deployable backend, split into modules with strict boundaries. Microservices are deliberately avoided at this stage (ADR-0001).

```
backend/src/novacloud/
  iam/            users, organizations, roles, sessions
  compute/        instance domain model, lifecycle state machine
  storage/        volume and object metadata, access policies
  network/        networks, subnets, IP allocation model
  orchestration/  execution plans, jobs, retries, idempotency
  monitoring/     metric collection with documented sources
  audit/          append-only audit log
  providers/      adapters implementing domain ports
  api/            FastAPI routers, versioned under /api/v1
  core/           config, db session, errors, correlation IDs
```

Rules:

- A module exposes a service interface. Other modules call it, never its tables or internals.
- Domain code depends on provider **ports** (interfaces). Concrete adapters live in `providers/` and are selected by configuration.
- Every database row that belongs to a tenant carries `organization_id`. Repositories require it as an argument.
- Authorization is checked server-side in the service layer, default deny.

## Ports and adapters

| Port | First adapter | Notes |
|---|---|---|
| ComputeProvider | Docker (via isolated runner) | Instances are **containers**, labeled as such, not VMs |
| StorageProvider | Local filesystem | Objects addressed by generated ID, never by user path |
| NetworkProvider | Docker networks | Isolation claims only where Docker enforces them |
| Fake providers | In-memory, for tests only | Never selectable in a normal deployment |

### Privileged runner

The application must not receive the Docker socket (ADR-0003). A small separate process, the runner, is the only component that talks to Docker. It:

- accepts a narrow, authenticated API: create, start, stop, delete from validated templates;
- never executes user-supplied commands or arbitrary image options;
- never uses privileged mode and drops Linux capabilities;
- is documented as the highest-risk component.

Whether the runner uses rootless Docker, Podman, or a socket proxy is an open decision to be recorded after testing on a real machine.

## Resource lifecycle

States: `planned`, `provisioning`, `running`, `stopping`, `stopped`, `failed`, `deleting`, `deleted`.

Allowed transitions:

```
planned       -> provisioning | deleted
provisioning  -> running | failed
running       -> stopping | deleting | failed
stopping      -> stopped | failed
stopped       -> provisioning (start) | deleting
failed        -> deleting | provisioning (explicit retry)
deleting      -> deleted | failed
```

Any other transition is rejected. A database record is not a running instance: `running` is set only after the provider confirms it, and a reconciliation job compares recorded state with provider state.

## Orchestration and jobs

- Jobs are stored in PostgreSQL and claimed with `SELECT ... FOR UPDATE SKIP LOCKED` (ADR-0002). Redis is added only if measured need appears.
- Each mutating request carries an idempotency key; a unique constraint prevents duplicate jobs.
- Destructive operations are never retried automatically.
- Execution plans express dependencies between resources; failures trigger compensation where possible and are recorded in the operation log.

## Identity and sessions (planned)

Argon2 password hashing, server-side sessions stored in PostgreSQL, HttpOnly and SameSite cookies, CSRF tokens, rotation on login, revocation on logout. Roles are scoped to an organization.

## Audit

Append-only table with actor, action, resource, timestamp, result, correlation ID and redacted metadata. The application database role has no UPDATE or DELETE permission on it. Passwords, tokens and keys are never logged.

## Observability

Structured JSON logs, `/health` (liveness) and `/ready` (dependency status checked for real), Prometheus metrics endpoint. Every metric will have a documented source; unavailable values are shown as unavailable.

## Evolution paths

- Job workers can become a separate process on the same code base, then a separate service.
- The runner is already a separate process boundary.
- Module interfaces are the seams where services could later be split.

## Open questions

- Runner isolation mechanism (rootless Docker, Podman, socket proxy).
- Object storage backend beyond the local filesystem; licensing must be checked before choosing.
- Multi-organization user model details.

## Implementation notes

- Repositories are Protocols with an in-memory implementation (tests) and a PostgreSQL implementation (`infra/sql.py`).
- Networks are cached in the API process and written through to PostgreSQL; run a single API replica.
- The runner is a stdlib HTTP server driving the Docker CLI with argument lists (never a shell); it is the only service that mounts the Docker socket and sits on an internal compose network.
- Each subnet maps to an internal Docker bridge `novacloud-net-<subnet id>` created by the runner; instances are attached with a fixed address from the allocator. Instances without a subnet use `--network none`. The runner only touches networks labelled `novacloud.managed=true`.
- Compute and job handling run in a separate `worker` process; the API only enqueues jobs.
