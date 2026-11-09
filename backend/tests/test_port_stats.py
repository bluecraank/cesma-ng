from datetime import UTC, datetime, timedelta

from app.models import PortCounterSample
from app.services.port_stats import rates

T0 = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def _sample(minutes: int, in_octets: int, out_octets: int, in_err: int = 0) -> PortCounterSample:
    return PortCounterSample(
        sampled_at=T0 + timedelta(minutes=minutes),
        in_octets=in_octets,
        out_octets=out_octets,
        in_errors=in_err,
        out_errors=0,
    )


def test_rates_from_counter_deltas() -> None:
    points = rates([_sample(0, 0, 0), _sample(5, 375_000_000, 37_500_000, in_err=3)])
    assert points[0]["in_bps"] == 10_000_000  # 375 MB in 300 s = 10 Mbit/s
    assert points[0]["out_bps"] == 1_000_000
    assert points[0]["in_errors"] == 3


def test_counter_reset_after_reboot_is_skipped() -> None:
    points = rates([_sample(0, 900, 900), _sample(5, 100, 100), _sample(10, 400, 400)])
    assert len(points) == 1
    assert points[0]["in_bps"] == 8  # (400 - 100) * 8 / 300
