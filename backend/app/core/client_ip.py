from __future__ import annotations

import ipaddress
from functools import lru_cache

from fastapi import Request

from app.core.config import get_settings


@lru_cache
def _trusted_networks() -> tuple[ipaddress._BaseNetwork, ...]:
    networks = []
    for value in get_settings().TRUSTED_PROXY_CIDRS:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _normalized_ip(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().strip('"')
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _is_trusted(value: str | None) -> bool:
    normalized = _normalized_ip(value)
    if not normalized:
        return False
    address = ipaddress.ip_address(normalized)
    return any(address in network for network in _trusted_networks())


def get_client_ip(request: Request) -> str:
    """Return a spoof-resistant client IP behind an explicit proxy allowlist.

    The chain is walked from right to left. Only hops belonging to trusted
    proxy networks are discarded, so a client-supplied leftmost value cannot
    override the address appended by the first trusted reverse proxy.
    """

    peer = _normalized_ip(request.client.host if request.client else None) or "unknown"
    if not _is_trusted(peer):
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    chain = [_normalized_ip(item) for item in forwarded.split(",")]
    valid_chain = [item for item in chain if item]
    for candidate in reversed([*valid_chain, peer]):
        if not _is_trusted(candidate):
            return candidate

    # Do not fall back to X-Real-IP: unless every proxy is known to overwrite it,
    # that single-value header is client-spoofable. A fully trusted chain safely
    # collapses to the immediate trusted peer.
    return peer


def is_loopback_client(request: Request) -> bool:
    try:
        return ipaddress.ip_address(get_client_ip(request)).is_loopback
    except ValueError:
        return False
