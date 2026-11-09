"""Wanted configuration (site VLANs, port profiles), backups and background jobs."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JsonType, TimestampMixin, str_enum, utcnow

if TYPE_CHECKING:
    from app.models.user import User


class SiteVlan(TimestampMixin, Base):
    """A VLAN as it should exist at a site (the old 'VLANs' page, the source for VLAN sync)."""

    __tablename__ = "site_vlans"
    __table_args__ = (UniqueConstraint("site_id", "vid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    vid: Mapped[int]
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(255), default="")
    ip_range: Mapped[str | None] = mapped_column(String(43))  # CIDR, e.g. 10.1.20.0/24
    is_client_vlan: Mapped[bool] = mapped_column(default=True)
    scan_enabled: Mapped[bool] = mapped_column(default=False)
    sync_enabled: Mapped[bool] = mapped_column(default=True)


class PortProfile(TimestampMixin, Base):
    """Named port preset, e.g. 'Office: untagged 10, tagged 20 (voice)'."""

    __tablename__ = "port_profiles"
    __table_args__ = (UniqueConstraint("site_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    untagged_vid: Mapped[int | None]
    tagged_vids: Mapped[list[int]] = mapped_column(JsonType, default=list)
    description: Mapped[str | None] = mapped_column(String(255))  # set as port description


class BackupStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"


class Backup(Base):
    __tablename__ = "backups"
    __table_args__ = (Index("ix_backups_device_created", "device_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    status: Mapped[BackupStatus] = mapped_column(str_enum(BackupStatus, 10))
    config_encrypted: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(default=0)
    #: configuration differs from the previous successful backup
    changed: Mapped[bool] = mapped_column(default=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), default="system")


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Job(Base):
    """Long running work (VLAN sync, backups, key upload), executed by the worker."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[JobStatus] = mapped_column(
        str_enum(JobStatus, 10), default=JobStatus.PENDING, index=True
    )
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    log: Mapped[str] = mapped_column(Text, default="")
    progress: Mapped[int] = mapped_column(default=0)  # 0..100
    error: Mapped[str | None] = mapped_column(Text)


class SshPublicKey(TimestampMixin, Base):
    """A user's public key; uploaded to the switches of sites where the user has SSH access.

    Keys without owner (e.g. imported from cesma-on-premise) go to every switch.
    """

    __tablename__ = "ssh_public_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(String(100))
    key: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(100), unique=True)

    user: Mapped["User | None"] = relationship()

    @property
    def owner(self) -> str | None:
        return self.user.username if self.user else None
