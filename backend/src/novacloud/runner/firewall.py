"""Per-subnet egress allow-lists, enforced with iptables in the DOCKER-USER chain.

The runner never runs iptables itself: every command executes in a short-lived helper container (the runner's own
image, `--network host`, only NET_ADMIN/NET_RAW) started through the Docker CLI with argument lists. All values that
reach iptables are validated (chain name from a UUID, CIDRs from `ipaddress`), and no shell is involved."""
import ipaddress
import re

from novacloud.core.netpolicy import validate_egress_allow

ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def chain_name(subnet_id: str) -> str:
    if not ID_RE.match(subnet_id):
        raise ValueError("invalid subnet id")
    return "NOVA-" + subnet_id.replace("-", "")[:20]


def helper_prefix(image: str) -> list[str]:
    return ["run", "--rm", "--network", "host", "--user", "0", "--cap-drop", "ALL", "--cap-add", "NET_ADMIN",
            "--cap-add", "NET_RAW", "--security-opt", "no-new-privileges", "--read-only", "--label", "novacloud.helper=true",
            image, "iptables", "-w", "5"]


def jump_rule(subnet_id: str, cidr: str) -> list[str]:
    net = ipaddress.IPv4Network(cidr, strict=True)
    return ["DOCKER-USER", "-s", str(net), "!", "-d", str(net), "-j", chain_name(subnet_id)]


def apply_plan(subnet_id: str, cidr: str, allow: list[str]) -> list[list[str]]:
    """iptables argument lists (after `iptables -w 5`) that rebuild the chain; the jump is added separately."""
    allow = validate_egress_allow(allow)
    ch = chain_name(subnet_id)
    plan = [["-N", ch], ["-F", ch],
            ["-A", ch, "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "RETURN"]]
    plan += [["-A", ch, "-d", a, "-j", "RETURN"] for a in allow]
    plan.append(["-A", ch, "-j", "DROP"])
    return plan


def apply(docker, image: str, subnet_id: str, cidr: str, allow: list[str]) -> bool:
    base = helper_prefix(image)
    jump = jump_rule(subnet_id, cidr)
    docker(*base, "-N", chain_name(subnet_id))  # may already exist: idempotent re-apply
    for args in apply_plan(subnet_id, cidr, allow)[1:]:
        if docker(*base, *args).returncode != 0:
            return False
    if docker(*base, "-C", *jump).returncode != 0:
        return docker(*base, "-I", jump[0], "1", *jump[1:]).returncode == 0
    return True


def remove(docker, image: str, subnet_id: str, cidr: str) -> None:
    base = helper_prefix(image)
    ch = chain_name(subnet_id)
    for _ in range(5):  # a duplicated jump (should not happen) is removed too; bounded on purpose
        if docker(*base, "-D", *jump_rule(subnet_id, cidr)).returncode != 0:
            break
    docker(*base, "-F", ch)
    docker(*base, "-X", ch)
