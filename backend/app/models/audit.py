"""Audit log: who changed what, logins, failures and device state changes."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JsonType, str_enum, utcnow


class AuditLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AuditEntry(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_site_created", "site_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    level: Mapped[AuditLevel] = mapped_column(str_enum(AuditLevel, 10), default=AuditLevel.INFO)
    action: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, default="")

    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_name: Mapped[str] = mapped_column(String(255), default="system")
    ip_address: Mapped[str | None] = mapped_column(String(45))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))

    old_values: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
