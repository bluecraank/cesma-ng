"""Port history: link and configuration events, and the devices seen on a port."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JsonType, str_enum, utcnow


class PortEventKind(StrEnum):
    LINK_UP = "link_up"
    LINK_DOWN = "link_down"
    SPEED = "speed"
    #: changed through cesma-ng (actor = user)
    CONFIGURED = "configured"
    #: changed on the switch itself, noticed by polling
    CHANGED = "changed"


class PortEvent(Base):
    __tablename__ = "port_events"
    __table_args__ = (Index("ix_port_events_port_at", "port_id", "at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    port_id: Mapped[int] = mapped_column(ForeignKey("ports.id", ondelete="CASCADE"))
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    kind: Mapped[PortEventKind] = mapped_column(str_enum(PortEventKind, 16))
    actor: Mapped[str | None] = mapped_column(String(255))
    #: {"old": {...}, "new": {...}} for configuration changes, speeds for SPEED
    detail: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)


class PortMacSighting(Base):
    """A device (MAC) seen on an access port: first and last time."""

    __tablename__ = "port_mac_sightings"
    __table_args__ = (UniqueConstraint("port_id", "mac_address"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    port_id: Mapped[int] = mapped_column(ForeignKey("ports.id", ondelete="CASCADE"), index=True)
    mac_address: Mapped[str] = mapped_column(String(17), index=True)
    vid: Mapped[int | None]
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
