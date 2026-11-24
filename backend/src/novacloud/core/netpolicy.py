"""Validation of per-subnet egress allow-lists, shared by the API and the runner (stdlib only)."""
import ipaddress

MAX_ALLOW = 16


def validate_egress_allow(items: object) -> list[str]:
    """Return a normalised, de-duplicated list of IPv4 destination CIDRs, or raise ValueError.

    Loopback, link-local (cloud metadata lives at 169.254.169.254), multicast and the all-zero range are refused:
    an allow-list is meant for specific external services, never for the host itself."""
    if not isinstance(items, (list, tuple)) or len(items) > MAX_ALLOW:
        raise ValueError(f"egress_allow must be a list of at most {MAX_ALLOW} CIDRs")
    out: list[str] = []
    for raw in items:
        if not isinstance(raw, str) or len(raw) > 18:
            raise ValueError("invalid egress CIDR")
        net = ipaddress.IPv4Network(raw, strict=True)
        if net.prefixlen == 0 or net.is_loopback or net.is_link_local or net.is_multicast or net.is_unspecified:
            raise ValueError(f"egress CIDR not allowed: {net}")
        if str(net) not in out:
            out.append(str(net))
    return out
