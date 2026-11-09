"""IP address and DNS name of a device, derived from the address it is polled under."""

import asyncio
import ipaddress
import socket
from datetime import timedelta

from app.core.db import ensure_utc, utcnow
from app.models import Device
from app.services.clients import DNS_TIMEOUT, reverse_dns

RECHECK = timedelta(hours=1)


async def forward_dns(name: str) -> str | None:
    try:
        async with asyncio.timeout(DNS_TIMEOUT):
            infos = await asyncio.get_running_loop().getaddrinfo(
                name, None, type=socket.SOCK_STREAM
            )
    except (OSError, TimeoutError):
        return None
    addresses = [str(info[4][0]) for info in infos]
    # Prefer IPv4: that is what the switch tables and SNMP use.
    return next((a for a in addresses if ":" not in a), addresses[0] if addresses else None)


async def resolve(hostname: str) -> tuple[str | None, str | None]:
    """(ip_address, dns_name) for a host given either as IP or as DNS name."""
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return await forward_dns(hostname), hostname
    return hostname, await reverse_dns(hostname)


async def refresh(device: Device, *, force: bool = False) -> None:
    """Update ``ip_address``/``dns_name`` if the last check is older than an hour."""
    checked = device.address_checked_at
    if not force and checked is not None and utcnow() - ensure_utc(checked) < RECHECK:
        return
    device.ip_address, device.dns_name = await resolve(device.hostname)
    device.address_checked_at = utcnow()
