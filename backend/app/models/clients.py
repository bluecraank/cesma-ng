"""End devices seen in the network, and the reference data used to describe them."""

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, utcnow


class Client(Base):
    """A MAC address seen on an access port, with its last location and address.

    Kept after it disappears (``last_seen_at``) so one can see where a device was connected.
    """

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    mac_address: Mapped[str] = mapped_column(String(17), unique=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), index=True)
    hostname: Mapped[str | None] = mapped_column(String(255), index=True)
    vid: Mapped[int | None]
    site_id: Mapped[int | None] = mapped_column(
        ForeignKey("sites.id", ondelete="SET NULL"), index=True
    )
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    port_id: Mapped[int | None] = mapped_column(ForeignKey("ports.id", ondelete="SET NULL"))
    port_name: Mapped[str | None] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    dns_checked_at: Mapped[datetime | None]


class MacVendor(Base):
    """IEEE OUI registry: first 3 bytes of a MAC -> manufacturer."""

    __tablename__ = "mac_vendors"

    prefix: Mapped[str] = mapped_column(String(8), primary_key=True)  # "aa:bb:cc"
    vendor: Mapped[str] = mapped_column(String(255))


class MacType(TimestampMixin, Base):
    """User defined classification by MAC prefix, e.g. 00:0b:82 -> phone."""

    __tablename__ = "mac_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    prefix: Mapped[str] = mapped_column(String(17), unique=True)  # 1..6 bytes, "aa:bb:cc"
    name: Mapped[str] = mapped_column(String(64))
    icon: Mapped[str] = mapped_column(String(32), default="device")


class SnmpGateway(TimestampMixin, Base):
    """A router/firewall whose ARP table provides IP <-> MAC for clients."""

    __tablename__ = "snmp_gateways"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    hostname: Mapped[str] = mapped_column(String(255), unique=True)
    credential_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("credential_profiles.id", ondelete="SET NULL")
    )
    enabled: Mapped[bool] = mapped_column(default=True)
    last_polled_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(String(500))
    entries: Mapped[int] = mapped_column(default=0)


class DiscoveredHost(Base):
    """Result of probing an address for a switch (avoids probing it again every time)."""

    __tablename__ = "discovered_hosts"

    ip_address: Mapped[str] = mapped_column(String(45), primary_key=True)
    last_probe_at: Mapped[datetime] = mapped_column(default=utcnow)
    result: Mapped[str] = mapped_column(String(100), default="")
    #: an admin deleted the discovered device: never add it again
    ignored: Mapped[bool] = mapped_column(default=False)
