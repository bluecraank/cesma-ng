"""Users, their per-site roles and login sessions."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JsonType, TimestampMixin, utcnow


class Permission(StrEnum):
    """What a role allows on a site, beyond seeing it (every role may see and poll)."""

    DEVICES_MANAGE = "devices.manage"  # devices, buildings, rooms, discovery
    PORTS_EDIT = "ports.edit"  # description, enabled, VLANs of ports
    VLANS_MANAGE = "vlans.manage"  # site VLANs, port profiles, VLAN sync
    BACKUPS_RUN = "backups.run"
    BACKUPS_READ = "backups.read"  # download and compare (contains switch secrets)
    BACKUPS_RESTORE = "backups.restore"
    CONSOLE = "console"  # read-only commands on the switch
    SSH_KEYS_PUSH = "ssh_keys.push"  # upload the SSH key list to the switches


class BuiltinRole(StrEnum):
    VIEWER = "viewer"
    ADMIN = "admin"


class Role(TimestampMixin, Base):
    """A named set of permissions, assigned to users per site."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    permissions: Mapped[list[str]] = mapped_column(JsonType, default=list)
    #: built-in roles ("viewer", "admin") cannot be deleted
    builtin: Mapped[str | None] = mapped_column(String(20), unique=True)

    def allows(self, permission: Permission) -> bool:
        return permission.value in self.permissions


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str | None] = mapped_column(String(255))
    is_superadmin: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    locale: Mapped[str] = mapped_column(String(5), default="de")
    last_login_at: Mapped[datetime | None]
    #: emergency password, only accepted while the directory (LDAP) is unreachable
    local_password_hash: Mapped[str | None] = mapped_column(String(255))

    site_roles: Mapped[list["UserSiteRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def has_local_password(self) -> bool:
        return self.local_password_hash is not None


class UserSiteRole(Base):
    __tablename__ = "user_site_roles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))

    user: Mapped[User] = relationship(back_populates="site_roles")
    role: Mapped[Role] = relationship(lazy="selectin")

    @property
    def role_name(self) -> str:
        return self.role.name

    @property
    def permissions(self) -> list[str]:
        return list(self.role.permissions)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    ip_address: Mapped[str | None] = mapped_column(String(45))

    user: Mapped[User] = relationship(lazy="joined")
