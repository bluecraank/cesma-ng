"""User provisioning on login and user administration."""

from collections.abc import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.authenticators import Identity
from app.core.db import utcnow
from app.core.errors import NotFoundError, ValidationFailedError
from app.models import Site, SiteRole, User, UserSiteRole
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
    site_roles: dict[int, SiteRole] | None = None,
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
        user.site_roles = [UserSiteRole(site_id=s, role=r) for s, r in site_roles.items()]
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
        "site_roles": {str(r.site_id): r.role.value for r in user.site_roles},
    }
