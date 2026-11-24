"""Network and subnet metadata with validated relationships and IP allocation (metadata only)."""
import ipaddress
import re
import uuid
from dataclasses import dataclass, field

from novacloud.core.errors import Conflict, InvalidInput, NotFound
from novacloud.iam.domain import Principal

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$")


def parse_private_cidr(cidr: str) -> ipaddress.IPv4Network:
    try:
        n = ipaddress.ip_network(cidr, strict=True)
    except ValueError:
        raise InvalidInput("invalid CIDR (host bits must be zero)") from None
    if n.version != 4 or not n.is_private or n.prefixlen < 8 or n.prefixlen > 29:
        raise InvalidInput("CIDR must be IPv4, private, with prefix /8 to /29")
    return n


@dataclass
class Network:
    id: str
    organization_id: str
    name: str
    cidr: str
    subnets: dict[str, "Subnet"] = field(default_factory=dict)


@dataclass
class Subnet:
    id: str
    network_id: str
    organization_id: str
    name: str
    cidr: str
    gateway: str
    allocations: dict[str, str] = field(default_factory=dict)  # ip -> resource id


class NetworkService:
    def __init__(self, iam, audit, max_networks: int = 10, store=None, provider=None):
        """`store` (optional) persists every mutation (write-through) and is loaded once at start-up.
        State is re-read from the store before every operation, so the API and worker processes agree."""
        self.iam, self.audit, self.max_networks, self.store = iam, audit, max_networks, store
        self.provider = provider  # optional NetworkProvider: create_subnet(id, cidr, gw) / delete_subnet(id)
        self.networks: dict[str, Network] = store.load() if store else {}

    def _sync(self) -> None:
        """Read-through: the API and the worker are separate processes sharing one database, so the
        persisted state (not a start-up snapshot) is authoritative before every decision."""
        if self.store:
            self.networks = self.store.load()

    def _net(self, p, nid) -> Network:
        self._sync()
        n = self.networks.get(nid)
        if n is None or n.organization_id != p.organization_id:
            raise NotFound("network not found")
        return n

    def create_network(self, p: Principal, name: str, cidr: str, cid="") -> Network:
        self.iam.require(p, "network:write", "network", "-", cid)
        if not NAME_RE.match(name or ""):
            raise InvalidInput("invalid network name")
        net = parse_private_cidr(cidr)
        self._sync()
        mine = [n for n in self.networks.values() if n.organization_id == p.organization_id]
        if len(mine) >= self.max_networks:
            raise Conflict("network quota reached")
        if any(n.name == name for n in mine):
            raise Conflict("network name already in use")
        for n in mine:
            if net.overlaps(ipaddress.IPv4Network(n.cidr)):
                raise Conflict(f"CIDR overlaps network {n.name}")
        obj = Network(str(uuid.uuid4()), p.organization_id, name, str(net))
        self.networks[obj.id] = obj
        if self.store:
            self.store.save_network(obj)
        self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action="network.create",
                          resource_type="network", resource_id=obj.id, correlation_id=cid, metadata={"cidr": str(net)})
        return obj

    def create_subnet(self, p: Principal, network_id: str, name: str, cidr: str, cid="") -> Subnet:
        self.iam.require(p, "network:write", "subnet", "-", cid)
        net = self._net(p, network_id)
        if not NAME_RE.match(name or ""):
            raise InvalidInput("invalid subnet name")
        sub = parse_private_cidr(cidr)
        if not sub.subnet_of(ipaddress.IPv4Network(net.cidr)):
            raise InvalidInput("subnet must lie inside its network CIDR")
        if sub.prefixlen > 29:
            raise InvalidInput("subnet too small")
        for s in net.subnets.values():
            if s.name == name:
                raise Conflict("subnet name already in use")
            if sub.overlaps(ipaddress.IPv4Network(s.cidr)):
                raise Conflict(f"CIDR overlaps subnet {s.name}")
        obj = Subnet(str(uuid.uuid4()), net.id, p.organization_id, name, str(sub), str(sub.network_address + 1))
        if self.provider:  # real bridge first; nothing is recorded if the host refuses it
            self.provider.create_subnet(obj.id, obj.cidr, obj.gateway)
        net.subnets[obj.id] = obj
        if self.store:
            self.store.save_subnet(obj)
        self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action="subnet.create",
                          resource_type="subnet", resource_id=obj.id, correlation_id=cid, metadata={"cidr": str(sub)})
        return obj

    def allocate_ip(self, p: Principal, network_id: str, subnet_id: str, resource_id: str, cid="") -> str:
        self.iam.require(p, "network:write", "subnet", subnet_id, cid)
        sub = self._net(p, network_id).subnets.get(subnet_id)
        if sub is None:
            raise NotFound("subnet not found")
        if resource_id in sub.allocations.values():
            return next(ip for ip, r in sub.allocations.items() if r == resource_id)
        for host in ipaddress.IPv4Network(sub.cidr).hosts():
            ip = str(host)
            if ip != sub.gateway and ip not in sub.allocations:
                sub.allocations[ip] = resource_id
                if self.store:
                    self.store.save_allocation(sub.id, ip, resource_id)
                self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action="ip.allocate",
                                  resource_type="subnet", resource_id=subnet_id, correlation_id=cid,
                                  metadata={"ip": ip})
                return ip
        raise Conflict("subnet has no free addresses")

    def release_ip(self, organization_id: str, network_id: str, subnet_id: str, resource_id: str) -> None:
        """System operation (no principal): called when the resource that owned the address is deleted."""
        self._sync()
        net = self.networks.get(network_id)
        sub = net.subnets.get(subnet_id) if net and net.organization_id == organization_id else None
        if sub is None:
            return
        for ip, rid in list(sub.allocations.items()):
            if rid == resource_id:
                del sub.allocations[ip]
                if self.store:
                    self.store.delete_allocation(subnet_id, ip)
                self.audit.record(actor_id="system", organization_id=organization_id, action="ip.release",
                                  resource_type="subnet", resource_id=subnet_id, metadata={"ip": ip})

    def delete_network(self, p: Principal, network_id: str, cid="") -> None:
        self.iam.require(p, "network:delete", "network", network_id, cid)
        net = self._net(p, network_id)
        if net.subnets:
            raise Conflict("network still has subnets")
        del self.networks[network_id]
        if self.store:
            self.store.delete_network(network_id)
        self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action="network.delete",
                          resource_type="network", resource_id=network_id, correlation_id=cid)

    def delete_subnet(self, p: Principal, network_id: str, subnet_id: str, cid="") -> None:
        self.iam.require(p, "network:delete", "subnet", subnet_id, cid)
        net = self._net(p, network_id)
        sub = net.subnets.get(subnet_id)
        if sub is None:
            raise NotFound("subnet not found")
        if sub.allocations:
            raise Conflict("subnet still has allocated addresses")
        if self.provider:
            self.provider.delete_subnet(subnet_id)
        del net.subnets[subnet_id]
        if self.store:
            self.store.delete_subnet(subnet_id)
        self.audit.record(actor_id=p.user_id, organization_id=p.organization_id, action="subnet.delete",
                          resource_type="subnet", resource_id=subnet_id, correlation_id=cid)

    def list_networks(self, p: Principal) -> list[Network]:
        self.iam.require(p, "network:read", "network")
        self._sync()
        return [n for n in self.networks.values() if n.organization_id == p.organization_id]
