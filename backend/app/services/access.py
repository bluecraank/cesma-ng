"""Authorisation rules. Pure functions so they are trivial to test.

Every role on a site allows seeing it; what else a role allows is its list of permissions.
Super administrators may do everything everywhere.
"""

from app.core.errors import ForbiddenError
from app.models import Permission, User


def has_site_access(user: User, site_id: int) -> bool:
    return user.is_superadmin or any(r.site_id == site_id for r in user.site_roles)


def require_site_access(user: User, site_id: int) -> None:
    if not has_site_access(user, site_id):
        raise ForbiddenError("No permission for this site")


def permissions(user: User, site_id: int) -> set[Permission]:
    if user.is_superadmin:
        return set(Permission)
    for r in user.site_roles:
        if r.site_id == site_id:
            return {p for p in Permission if r.role.allows(p)}
    return set()


def has_permission(user: User, site_id: int, permission: Permission) -> bool:
    return permission in permissions(user, site_id)


def require_permission(user: User, site_id: int, permission: Permission) -> None:
    require_site_access(user, site_id)
    if not has_permission(user, site_id, permission):
        raise ForbiddenError(f"Your role on this site does not allow this ({permission.value})")


def require_superadmin(user: User) -> None:
    if not user.is_superadmin:
        raise ForbiddenError("Super administrator required")


def visible_site_ids(user: User) -> set[int] | None:
    """Site ids the user may see; ``None`` means all sites."""
    if user.is_superadmin:
        return None
    return {r.site_id for r in user.site_roles}


def require_permission_anywhere(user: User, permission: Permission) -> None:
    """For actions that are not tied to one site yet (e.g. probing a new switch)."""
    if not user.is_superadmin and not any(r.role.allows(permission) for r in user.site_roles):
        raise ForbiddenError(f"Your roles do not allow this ({permission.value})")
