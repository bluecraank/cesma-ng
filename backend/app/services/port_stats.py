"""Port statistics: traffic and error rates computed from stored counter samples."""

import itertools
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import ensure_utc, utcnow
from app.core.errors import NotFoundError
from app.models import Port, PortCounterSample
from app.services.context import Caller
from app.services.devices import get_device


def rates(samples: Sequence[PortCounterSample]) -> list[dict[str, Any]]:
    """Per interval between two samples: bit/s and errors. Counter resets are skipped."""
    points = []
    for previous, current in itertools.pairwise(samples):
        seconds = (ensure_utc(current.sampled_at) - ensure_utc(previous.sampled_at)).total_seconds()
        deltas = (
            current.in_octets - previous.in_octets,
            current.out_octets - previous.out_octets,
            current.in_errors - previous.in_errors,
            current.out_errors - previous.out_errors,
        )
        if seconds <= 0 or min(deltas) < 0:  # reboot / counter reset
            continue
        points.append(
            {
                "at": current.sampled_at,
                "in_bps": round(deltas[0] * 8 / seconds),
                "out_bps": round(deltas[1] * 8 / seconds),
                "in_errors": deltas[2],
                "out_errors": deltas[3],
            }
        )
    return points


async def port_statistics(
    db: AsyncSession, caller: Caller, device_id: int, port_id: int, hours: int
) -> dict[str, Any]:
    await get_device(db, caller, device_id)
    port = await db.get(Port, port_id)
    if port is None or port.device_id != device_id:
        raise NotFoundError("Port not found")
    since = utcnow() - timedelta(hours=hours)
    samples = (
        (
            await db.execute(
                select(PortCounterSample)
                .where(PortCounterSample.port_id == port_id, PortCounterSample.sampled_at >= since)
                .order_by(PortCounterSample.sampled_at)
            )
        )
        .scalars()
        .all()
    )
    return {"port_id": port_id, "speed_mbps": port.speed_mbps, "points": rates(samples)}


async def purge_old_samples(db: AsyncSession, days: int) -> None:
    await db.execute(
        delete(PortCounterSample).where(
            PortCounterSample.sampled_at < utcnow() - timedelta(days=days)
        )
    )
