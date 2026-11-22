"""Builds docker CLI argument lists from validated templates. Pure functions; no shell is ever used."""
import re

from novacloud.compute.domain import TEMPLATES

ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
REF_RE = re.compile(r"^novacloud-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
LABEL = "novacloud.managed=true"


def container_name(instance_id: str) -> str:
    if not ID_RE.match(instance_id):
        raise ValueError("invalid instance id")
    return f"novacloud-{instance_id}"


def build_run_args(instance_id: str, organization_id: str, template: str) -> list[str]:
    if template not in TEMPLATES:
        raise ValueError("unknown template")
    if not ID_RE.match(organization_id):
        raise ValueError("invalid organization id")
    t = TEMPLATES[template]
    return [
        "docker", "run", "-d", "--name", container_name(instance_id),
        "--label", LABEL, "--label", f"novacloud.org={organization_id}",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--read-only", "--tmpfs", "/tmp", "--tmpfs", "/var/cache/nginx", "--tmpfs", "/var/run",
        "--pids-limit", "128", "--memory", f"{t.memory_mb}m", "--cpus", str(t.cpus),
        "--network", "none",
        t.image, *t.command,
    ]


def validate_ref(ref: str) -> str:
    if not REF_RE.match(ref):
        raise ValueError("invalid container reference")
    return ref
