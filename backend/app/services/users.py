"""User provisioning on login and user administration."""

from collections.abc import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.authenticators import Identity
from app.auth.passwords import MIN_LENGTH, hash_password, verify_password
from app.core.db import utcnow
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import BuiltinRole, Permission, Role, Site, User, UserSiteRole
from app.services import audit
from app.services.access import require_superadmin
from app.services.context import Caller

SUPPORTED_LOCALES = frozenset({"de", "en"})


async def provision_on_login(db: AsyncSession, identity: Identity) -> User:
    """Create or update the local user. The very first user becomes super administrator."""
    user = (
        await db.execute(select(User).where(User.username == identity.username))
    ).scalar_one_or_none()
    if user is None:
        is_first = (await db.scalar(select(func.count()).select_from(User))) == 0
        user = User(username=identity.username, is_superadmin=is_first, site_roles=[])
        db.add(user)
    user.display_name = identity.display_name
    user.email = identity.email
    user.last_login_at = utcnow()
    await db.flush()
    return user


async def emergency_login(db: AsyncSession, username: str, password: str) -> User | None:
    """The local user if the emergency password matches (only used while LDAP is down)."""
    user = (
        await db.execute(select(User).where(func.lower(User.username) == username.lower()))
    ).scalar_one_or_none()
    if user is None or not user.is_active or user.local_password_hash is None:
        return None
    if not verify_password(password, user.local_password_hash):
        return None
    user.last_login_at = utcnow()
    return user


async def list_users(db: AsyncSession, caller: Caller) -> Sequence[User]:
    require_superadmin(caller.user)
    return (await db.execute(select(User).order_by(User.username))).scalars().all()


async def update_user(
    db: AsyncSession,
    caller: Caller,
    user_id: int,
    *,
    is_superadmin: bool | None = None,
    is_active: bool | None = None,
    site_roles: dict[int, int] | None = None,
    local_password: str | None = None,
) -> User:
    require_superadmin(caller.user)
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    if caller.user.id == user.id and (is_superadmin is False or is_active is False):
        raise ValidationFailedError("You cannot remove your own super administrator access")

    before = _snapshot(user)
    if is_superadmin is not None:
        user.is_superadmin = is_superadmin
    if is_active is not None:
        user.is_active = is_active
    if site_roles is not None:
        await _ensure_sites_exist(db, site_roles.keys())
        roles = await _roles(db, site_roles.values())
        user.site_roles = [
            UserSiteRole(site_id=s, role_id=r, role=roles[r]) for s, r in site_roles.items()
        ]
    if local_password is not None:
        if local_password and len(local_password) < MIN_LENGTH:
            raise ValidationFailedError(
                f"The emergency password needs at least {MIN_LENGTH} characters"
            )
        user.local_password_hash = hash_password(local_password) if local_password else None
    await db.flush()

    old, new = audit.changes(before, _snapshot(user))
    if new:
        await audit.record(
            db, caller.actor, "user.update", f"User {user.username} changed", old=old, new=new
        )
    return user


async def set_locale(db: AsyncSession, user: User, locale: str) -> None:
    if locale not in SUPPORTED_LOCALES:
        raise ValidationFailedError("Unsupported locale")
    user.locale = locale
    await db.flush()


async def _ensure_sites_exist(db: AsyncSession, site_ids: Iterable[int]) -> None:
    ids = set(site_ids)
    found = set((await db.execute(select(Site.id).where(Site.id.in_(ids)))).scalars())
    if missing := ids - found:
        raise ValidationFailedError(f"Unknown site ids: {sorted(missing)}")


def _snapshot(user: User) -> dict[str, object]:
    return {
        "is_superadmin": user.is_superadmin,
        "is_active": user.is_active,
        "site_roles": {str(r.site_id): r.role.name for r in user.site_roles},
        "local_password": user.has_local_password,
    }


async def _roles(db: AsyncSession, role_ids: Iterable[int]) -> dict[int, Role]:
    ids = set(role_ids)
    found = {r.id: r for r in (await db.execute(select(Role).where(Role.id.in_(ids)))).scalars()}
    if missing := ids - found.keys():
        raise ValidationFailedError(f"Unknown role ids: {sorted(missing)}")
    return found


# --- Roles -----------------------------------------------------------------------------------

#: created by the migration; ``ensure_builtin_roles`` repairs a database without them
BUILTIN_ROLES: dict[BuiltinRole, tuple[str, str, list[Permission]]] = {
    BuiltinRole.VIEWER: ("Lesen", "Alles ansehen, Abfragen anstoßen", []),
    BuiltinRole.ADMIN: ("Administrator", "Alle Rechte am Standort", list(Permission)),
}


async def ensure_builtin_roles(db: AsyncSession) -> None:
    existing = set((await db.execute(select(Role.builtin))).scalars())
    for key, (name, description, permissions) in BUILTIN_ROLES.items():
        if key.value not in existing:
            db.add(
                Role(
                    name=name,
                    description=description,
                    permissions=[p.value for p in permissions],
                    builtin=key.value,
                )
            )
    await db.flush()


async def list_roles(db: AsyncSession, caller: Caller) -> Sequence[Role]:
    """Every user may read the roles (the UI explains what a role allows)."""
    return (await db.execute(select(Role).order_by(Role.id))).scalars().all()


async def save_role(
    db: AsyncSession,
    caller: Caller,
    values: dict[str, object],
    role_id: int | None = None,
) -> Role:
    require_superadmin(caller.user)
    role = await db.get(Role, role_id) if role_id else Role()
    if role is None:
        raise NotFoundError("Role not found")
    before = _role_snapshot(role) if role_id else {}
    permissions = values.get("permissions", [])
    assert isinstance(permissions, list)
    role.name = str(values["name"]).strip()
    role.description = str(values.get("description", ""))
    role.permissions = sorted({Permission(p).value for p in permissions})
    if role_id is None:
        db.add(role)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("A role with this name already exists") from exc
    old, new = audit.changes(before, _role_snapshot(role))
    if new:
        await audit.record(
            db, caller.actor, "role.save", f"Role {role.name} saved", old=old, new=new
        )
    return role


async def delete_role(db: AsyncSession, caller: Caller, role_id: int) -> None:
    require_superadmin(caller.user)
    role = await db.get(Role, role_id)
    if role is None:
        raise NotFoundError("Role not found")
    if role.builtin:
        raise ValidationFailedError("Built-in roles cannot be deleted")
    in_use = await db.scalar(
        select(func.count()).select_from(UserSiteRole).where(UserSiteRole.role_id == role_id)
    )
    if in_use:
        raise ConflictError(f"The role is still assigned {in_use} time(s)")
    await db.delete(role)
    await audit.record(db, caller.actor, "role.delete", f"Role {role.name} deleted")


def _role_snapshot(role: Role) -> dict[str, object]:
    return {"name": role.name, "description": role.description, "permissions": role.permissions}
