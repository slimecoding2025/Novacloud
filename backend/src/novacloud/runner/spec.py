"""Builds docker CLI argument lists from validated templates. Pure functions; no shell is ever used."""
import ipaddress
import re

from novacloud.compute.domain import TEMPLATES

ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
REF_RE = re.compile(r"^novacloud-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
LABEL = "novacloud.managed=true"


def container_name(instance_id: str) -> str:
    if not ID_RE.match(instance_id):
        raise ValueError("invalid instance id")
    return f"novacloud-{instance_id}"


NET_RE = re.compile(r"^novacloud-net-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def network_name(subnet_id: str) -> str:
    if not ID_RE.match(subnet_id):
        raise ValueError("invalid subnet id")
    return f"novacloud-net-{subnet_id}"


def validate_net_ref(ref: str) -> str:
    if not NET_RE.match(ref):
        raise ValueError("invalid network reference")
    return ref


PUBLISH_MIN, PUBLISH_MAX = 20000, 29999


def build_network_args(subnet_id: str, cidr: str, gateway: str, egress: bool = False) -> list[str]:
    """Private IPv4 bridge. Default --internal: members reach each other but not the outside world.
    egress=True drops --internal (outbound NAT); bridges stay isolated from each other either way."""
    net = ipaddress.IPv4Network(cidr, strict=True)
    gw = ipaddress.IPv4Address(gateway)
    if not net.is_private or gw not in net or not (8 <= net.prefixlen <= 29):
        raise ValueError("invalid subnet definition")
    return ["docker", "network", "create", "--driver", "bridge", *([] if egress else ["--internal"]), "--label", LABEL,
            "--subnet", str(net), "--gateway", str(gw), network_name(subnet_id)]


def build_run_args(instance_id: str, organization_id: str, template: str,
                   network: str | None = None, ip: str | None = None,
                   published_port: int | None = None) -> list[str]:
    if template not in TEMPLATES:
        raise ValueError("unknown template")
    if not ID_RE.match(organization_id):
        raise ValueError("invalid organization id")
    t = TEMPLATES[template]
    if network is not None:
        net_args = ["--network", network_name(network), "--ip", str(ipaddress.IPv4Address(ip or ""))]
        if published_port is not None:
            if t.port is None or type(published_port) is not int or not PUBLISH_MIN <= published_port <= PUBLISH_MAX:
                raise ValueError("invalid published port")
            net_args += ["--publish", f"127.0.0.1:{int(published_port)}:{t.port}"]  # loopback only, never 0.0.0.0
    else:
        if published_port is not None:
            raise ValueError("a published port needs a network")
        net_args = ["--network", "none"]
    return [
        "docker", "run", "-d", "--name", container_name(instance_id),
        "--label", LABEL, "--label", f"novacloud.org={organization_id}",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--read-only", "--tmpfs", "/tmp", "--tmpfs", "/var/cache/nginx", "--tmpfs", "/var/run",
        "--pids-limit", "128", "--memory", f"{t.memory_mb}m", "--cpus", str(t.cpus),
        *net_args,
        t.image, *t.command,
    ]


def validate_ref(ref: str) -> str:
    if not REF_RE.match(ref):
        raise ValueError("invalid container reference")
    return ref
