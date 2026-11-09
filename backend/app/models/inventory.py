"""State read from the switches: ports, VLANs, MAC/ARP tables, LLDP neighbours, poll status."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, str_enum, utcnow
from app.domain.switch import PoeStatus, PortKind


class Port(Base):
    __tablename__ = "ports"
    __table_args__ = (UniqueConstraint("device_id", "if_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    if_index: Mapped[int]
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[PortKind] = mapped_column(str_enum(PortKind, 16))
    description: Mapped[str] = mapped_column(String(255), default="")
    admin_up: Mapped[bool] = mapped_column(default=True)
    oper_up: Mapped[bool] = mapped_column(default=False)
    speed_mbps: Mapped[int | None]
    mac_address: Mapped[str | None] = mapped_column(String(17))
    pvid: Mapped[int | None]
    poe: Mapped[PoeStatus | None] = mapped_column(str_enum(PoeStatus, 16))
    #: last time the link went up or down (as seen by the poller)
    last_change_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    vlans: Mapped[list["PortVlan"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="PortVlan.vid"
    )


class PortVlan(Base):
    __tablename__ = "port_vlans"

    port_id: Mapped[int] = mapped_column(
        ForeignKey("ports.id", ondelete="CASCADE"), primary_key=True
    )
    vid: Mapped[int] = mapped_column(primary_key=True)
    tagged: Mapped[bool]


class DeviceVlan(Base):
    """A VLAN as configured on one switch (actual state)."""

    __tablename__ = "device_vlans"
    __table_args__ = (UniqueConstraint("device_id", "vid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    vid: Mapped[int]
    name: Mapped[str] = mapped_column(String(64), default="")


class FdbEntry(Base):
    __tablename__ = "fdb_entries"
    __table_args__ = (Index("ix_fdb_entries_mac", "mac_address"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    port_id: Mapped[int | None] = mapped_column(
        ForeignKey("ports.id", ondelete="CASCADE"), index=True
    )
    vid: Mapped[int | None]
    mac_address: Mapped[str] = mapped_column(String(17))
    seen_at: Mapped[datetime] = mapped_column(default=utcnow)


class ArpEntry(Base):
    __tablename__ = "arp_entries"
    __table_args__ = (
        Index("ix_arp_entries_mac", "mac_address"),
        Index("ix_arp_entries_ip", "ip_address"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    #: source: a polled switch/router device, or an SNMP gateway
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    gateway_id: Mapped[int | None] = mapped_column(
        ForeignKey("snmp_gateways.id", ondelete="CASCADE"), index=True
    )
    ip_address: Mapped[str] = mapped_column(String(45))
    mac_address: Mapped[str] = mapped_column(String(17))
    if_index: Mapped[int | None]
    seen_at: Mapped[datetime] = mapped_column(default=utcnow)


class LldpNeighbor(Base):
    __tablename__ = "lldp_neighbors"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    port_id: Mapped[int | None] = mapped_column(ForeignKey("ports.id", ondelete="CASCADE"))
    local_port_name: Mapped[str] = mapped_column(String(64))
    chassis_id: Mapped[str] = mapped_column(String(255))
    remote_port: Mapped[str] = mapped_column(String(255))
    remote_port_description: Mapped[str] = mapped_column(String(255), default="")
    system_name: Mapped[str] = mapped_column(String(255), default="")
    system_description: Mapped[str] = mapped_column(Text, default="")
    management_address: Mapped[str | None] = mapped_column(String(45))
    #: the neighbour, if it is a switch managed by Cesma
    remote_device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL")
    )
    seen_at: Mapped[datetime] = mapped_column(default=utcnow)


class PortCounterSample(Base):
    """Raw interface counters at one point in time; rates are computed when reading."""

    __tablename__ = "port_counter_samples"
    __table_args__ = (Index("ix_port_counter_samples_port_ts", "port_id", "sampled_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    port_id: Mapped[int] = mapped_column(ForeignKey("ports.id", ondelete="CASCADE"))
    sampled_at: Mapped[datetime] = mapped_column(default=utcnow)
    in_octets: Mapped[int] = mapped_column(BigInteger)
    out_octets: Mapped[int] = mapped_column(BigInteger)
    in_errors: Mapped[int] = mapped_column(BigInteger)
    out_errors: Mapped[int] = mapped_column(BigInteger)


class PollTask(StrEnum):
    INVENTORY = "inventory"  # system, ports, VLANs
    FDB = "fdb"  # MAC address table
    ARP = "arp"
    LLDP = "lldp"
    COUNTERS = "counters"  # traffic and error counters (port statistics)


class DevicePollState(Base):
    """Schedule and result of each poll task per device (drives the worker)."""

    __tablename__ = "device_poll_states"

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    task: Mapped[PollTask] = mapped_column(str_enum(PollTask, 16), primary_key=True)
    next_due_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    last_run_at: Mapped[datetime | None]
    last_success_at: Mapped[datetime | None]
    failures: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_duration_ms: Mapped[int | None]
