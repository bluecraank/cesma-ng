"""Organisational structure: sites, buildings and rooms."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin


class Site(TimestampMixin, Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    buildings: Mapped[list["Building"]] = relationship(
        back_populates="site", cascade="all, delete-orphan", order_by="Building.name"
    )


class Building(TimestampMixin, Base):
    __tablename__ = "buildings"
    __table_args__ = (UniqueConstraint("site_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))

    site: Mapped[Site] = relationship(back_populates="buildings")
    rooms: Mapped[list["Room"]] = relationship(
        back_populates="building", cascade="all, delete-orphan", order_by="Room.name"
    )


class Room(TimestampMixin, Base):
    __tablename__ = "rooms"
    __table_args__ = (UniqueConstraint("building_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(
        ForeignKey("buildings.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))

    building: Mapped[Building] = relationship(back_populates="rooms")
