"""Instance lifecycle state machine and allow-listed templates. Instances are CONTAINERS, not VMs."""
import re
from dataclasses import dataclass
from enum import Enum

from novacloud.core.errors import Conflict, InvalidInput


class State(str, Enum):
    PLANNED = "planned"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"


S = State
TRANSITIONS: dict[State, set[State]] = {
    S.PLANNED: {S.PROVISIONING, S.DELETED},
    S.PROVISIONING: {S.RUNNING, S.FAILED},
    S.RUNNING: {S.STOPPING, S.DELETING, S.FAILED},
    S.STOPPING: {S.STOPPED, S.FAILED},
    S.STOPPED: {S.PROVISIONING, S.DELETING},
    S.FAILED: {S.DELETING, S.PROVISIONING},
    S.DELETING: {S.DELETED, S.FAILED},
    S.DELETED: set(),
}


def transition(current: State, target: State) -> State:
    if target not in TRANSITIONS[current]:
        raise Conflict(f"invalid transition {current.value} -> {target.value}")
    return target


@dataclass(frozen=True)
class Template:
    name: str
    image: str
    cpus: float
    memory_mb: int
    command: tuple[str, ...] = ()
    port: int | None = None  # container port that may be published on the host loopback


# Only these templates can be launched. Users choose a name, never an image or options.
TEMPLATES: dict[str, Template] = {
    "alpine-small": Template("alpine-small", "alpine:3.20", 0.5, 128, ("sleep", "infinity")),
    # Unprivileged nginx: runs as non-root on port 8080, so it works with every capability dropped.
    "nginx-small": Template("nginx-small", "nginxinc/nginx-unprivileged:1.27-alpine", 0.5, 128, (), 8080),
}

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$")


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise InvalidInput("name must be 3-40 chars: lowercase letters, digits, hyphen; start with a letter")
    return name


def get_template(name: str) -> Template:
    t = TEMPLATES.get(name)
    if t is None:
        raise InvalidInput(f"unknown template; allowed: {sorted(TEMPLATES)}")
    return t


@dataclass(frozen=True)
class NetworkAttachment:
    subnet_id: str
    ip: str
    published_port: int | None = None  # host port bound on 127.0.0.1 only


@dataclass
class Instance:
    id: str
    organization_id: str
    name: str
    template: str
    state: State
    provider_ref: str | None = None
    error: str | None = None
    network_id: str | None = None
    subnet_id: str | None = None
    ip: str | None = None
    published_port: int | None = None
