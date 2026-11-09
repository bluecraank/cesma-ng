"""Authorisation rules. Pure functions so they are trivial to test."""

from app.core.errors import ForbiddenError
from app.models import SiteRole, User

_RANK = {SiteRole.VIEWER: 1, SiteRole.ADMIN: 2}


def site_role(user: User, site_id: int) -> SiteRole | None:
    if user.is_superadmin:
        return SiteRole.ADMIN
    return next((r.role for r in user.site_roles if r.site_id == site_id), None)


def has_site_role(user: User, site_id: int, required: SiteRole) -> bool:
    role = site_role(user, site_id)
    return role is not None and _RANK[role] >= _RANK[required]


def require_site_role(user: User, site_id: int, required: SiteRole) -> None:
    if not has_site_role(user, site_id, required):
        raise ForbiddenError("No permission for this site")


def require_superadmin(user: User) -> None:
    if not user.is_superadmin:
        raise ForbiddenError("Super administrator required")


def visible_site_ids(user: User) -> set[int] | None:
    """Site ids the user may see; ``None`` means all sites."""
    if user.is_superadmin:
        return None
    return {r.site_id for r in user.site_roles}


def require_any_site_admin(user: User) -> None:
    """For actions that are not tied to one site yet (e.g. probing a new switch)."""
    if not user.is_superadmin and not any(r.role is SiteRole.ADMIN for r in user.site_roles):
        raise ForbiddenError("Administrator role required")
