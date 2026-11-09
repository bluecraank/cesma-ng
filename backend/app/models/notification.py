"""Notifications: events that need a human to look at them (offline devices, uplink changes...)."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, str_enum, utcnow


class NotificationKind(StrEnum):
    DEVICE_OFFLINE = "device_offline"
    DEVICE_ONLINE = "device_online"
    DEVICE_REBOOTED = "device_rebooted"
    UPLINK_DOWN = "uplink_down"
    UPLINK_UP = "uplink_up"
    SPEED_CHANGED = "speed_changed"
    BACKUP_FAILED = "backup_failed"
    DEVICE_DISCOVERED = "device_discovered"


class NotificationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_open", "site_id", "acknowledged_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    kind: Mapped[NotificationKind] = mapped_column(str_enum(NotificationKind, 32))
    severity: Mapped[NotificationSeverity] = mapped_column(str_enum(NotificationSeverity, 16))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    port_name: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    acknowledged_at: Mapped[datetime | None]
    acknowledged_by: Mapped[str | None] = mapped_column(String(255))
