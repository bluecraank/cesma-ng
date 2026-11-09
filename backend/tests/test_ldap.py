import pytest

from app.auth.authenticators import LdapAuthenticator
from app.core.config import Settings


def _auth(**overrides: object) -> LdapAuthenticator:
    return LdapAuthenticator(Settings(ldap_base_dn="DC=corp,DC=local", **overrides))  # type: ignore[arg-type]


def test_filter_escapes_user_input() -> None:
    flt = _auth()._search_filter("*)(objectClass=*")
    assert "*)(objectClass=*" not in flt
    assert r"\2a\29\28objectClass=\2a" in flt


def test_filter_requires_nested_group_membership() -> None:
    flt = _auth(ldap_required_group="CN=Cesma,OU=Groups,DC=corp,DC=local")._search_filter("bob")
    assert "(memberOf:1.2.840.113556.1.4.1941:=CN=Cesma,OU=Groups,DC=corp,DC=local)" in flt
    assert flt.startswith("(&") and flt.endswith(")")


@pytest.mark.parametrize("password", ["", None])
async def test_empty_password_never_reaches_the_directory(password: str | None) -> None:
    # would be an unauthenticated bind, which AD accepts
    assert (
        await _auth(ldap_url="ldap://unreachable.invalid").authenticate("bob", password or "")
        is None
    )
