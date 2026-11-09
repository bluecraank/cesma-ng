"""Switches and the credential profiles used to reach them."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, str_enum
from app.models.org import Room, Site


class DeviceModel(StrEnum):
    """Supported switch families. Each value maps to exactly one driver."""

    DELL_N1500 = "dell_n1500"  # Dell N1548P and siblings (DNOS 6)
    DELL_OS10 = "dell_os10"  # Dell PowerSwitch OS10
    ARUBA_OS_SWITCH = "aruba_os_switch"  # HP 2530-48G (ArubaOS-Switch / ProCurve)
    ARUBA_CX = "aruba_cx"  # HPE Aruba Networking CX (AOS-CX)


class DeviceStatus(StrEnum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    UNCONFIRMED = "unconfirmed"  # discovered automatically, waiting for an admin


class SnmpVersion(StrEnum):
    V2C = "v2c"
    V3 = "v3"


class CredentialProfile(TimestampMixin, Base):
    """Reusable access data. Secrets are stored encrypted as one JSON blob."""

    __tablename__ = "credential_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    snmp_version: Mapped[SnmpVersion] = mapped_column(
        str_enum(SnmpVersion, 10), default=SnmpVersion.V2C
    )
    snmp_v3_username: Mapped[str | None] = mapped_column(String(100))
    snmp_v3_auth_protocol: Mapped[str | None] = mapped_column(String(20))
    snmp_v3_priv_protocol: Mapped[str | None] = mapped_column(String(20))
    api_username: Mapped[str | None] = mapped_column(String(100))
    ssh_username: Mapped[str | None] = mapped_column(String(100))
    verify_tls: Mapped[bool] = mapped_column(default=False)
    api_https: Mapped[bool] = mapped_column(default=True, server_default="1")
    secrets_encrypted: Mapped[str] = mapped_column(Text, default="")


class Device(TimestampMixin, Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), index=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"))
    credential_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("credential_profiles.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(100), unique=True)
    hostname: Mapped[str] = mapped_column(String(255), unique=True)
    model: Mapped[DeviceModel] = mapped_column(str_enum(DeviceModel, 30))
    location_note: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[DeviceStatus] = mapped_column(
        str_enum(DeviceStatus, 20), default=DeviceStatus.UNKNOWN
    )

    # Facts reported by the switch, refreshed by the poller.
    sys_name: Mapped[str | None] = mapped_column(String(255))
    model_name: Mapped[str | None] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(100))
    firmware: Mapped[str | None] = mapped_column(String(100))
    mac_address: Mapped[str | None] = mapped_column(String(17))
    uptime_seconds: Mapped[int | None]
    last_seen_at: Mapped[datetime | None]

    site: Mapped[Site] = relationship()
    room: Mapped[Room | None] = relationship()
    credential_profile: Mapped[CredentialProfile | None] = relationship()
