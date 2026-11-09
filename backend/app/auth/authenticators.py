"""Pluggable password authenticators (LDAP / Active Directory and a static dev backend)."""

import asyncio
import hmac
import logging
import ssl
from dataclasses import dataclass
from typing import Any, Protocol

from ldap3 import NONE, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from app.core.config import AuthBackend, Settings

log = logging.getLogger(__name__)

# Active Directory "LDAP_MATCHING_RULE_IN_CHAIN": resolves nested group membership.
_AD_IN_CHAIN = "1.2.840.113556.1.4.1941"


@dataclass(frozen=True)
class Identity:
    username: str
    display_name: str
    email: str | None


class AuthBackendError(Exception):
    """The directory could not be reached or answered unexpectedly."""


class Authenticator(Protocol):
    async def authenticate(self, username: str, password: str) -> Identity | None:
        """Return the identity for valid credentials, ``None`` for invalid ones."""
        ...

    async def lookup(self, username: str) -> Identity | None:
        """Identity of an allowed user without checking a password (SSO behind a proxy)."""
        ...


class StaticAuthenticator:
    """Development backend with users from configuration. Refused in production."""

    def __init__(self, users: dict[str, str]) -> None:
        self._users = users

    async def authenticate(self, username: str, password: str) -> Identity | None:
        expected = self._users.get(username)
        if expected is None or not password:
            return None
        if not hmac.compare_digest(expected.encode(), password.encode()):
            return None
        return Identity(username=username.lower(), display_name=username, email=None)

    async def lookup(self, username: str) -> Identity | None:
        if username not in self._users:
            return None
        return Identity(username=username.lower(), display_name=username, email=None)


class LdapAuthenticator:
    """Active Directory login by sAMAccountName, userPrincipalName or mail."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def authenticate(self, username: str, password: str) -> Identity | None:
        # An empty password would be an anonymous ("unauthenticated") bind that succeeds.
        if not username or not password:
            return None
        return await asyncio.to_thread(self._authenticate_sync, username, password)

    def _server(self) -> Server:
        s = self._settings
        tls = Tls(
            validate=ssl.CERT_REQUIRED if s.ldap_verify_tls else ssl.CERT_NONE,
            ca_certs_file=s.ldap_ca_file,
        )
        return Server(s.ldap_url, get_info=NONE, connect_timeout=s.ldap_timeout, tls=tls)

    def _search_filter(self, username: str) -> str:
        u = escape_filter_chars(username)
        flt = f"(&(objectClass=user)(|(sAMAccountName={u})(userPrincipalName={u})(mail={u}))"
        group = self._settings.ldap_required_group
        if group:
            flt += f"(memberOf:{_AD_IN_CHAIN}:={escape_filter_chars(group)})"
        return flt + ")"

    async def lookup(self, username: str) -> Identity | None:
        if not username:
            return None
        entry = await asyncio.to_thread(self._find, username)
        return _identity(entry, username) if entry is not None else None

    def _find(self, username: str) -> Any:
        """The single directory entry for the user (respecting the required group), or None."""
        s = self._settings
        try:
            with Connection(
                self._server(),
                user=s.ldap_bind_dn,
                password=s.ldap_bind_password.get_secret_value(),
                auto_bind=True,
                receive_timeout=s.ldap_timeout,
            ) as service:
                service.search(
                    s.ldap_base_dn,
                    self._search_filter(username),
                    search_scope=SUBTREE,
                    attributes=["sAMAccountName", "displayName", "mail"],
                    size_limit=2,
                )
                entries = list(service.entries)
        except LDAPException as exc:
            log.error("LDAP search failed: %s", exc)
            raise AuthBackendError("Directory not reachable") from exc
        if len(entries) != 1:
            log.info("LDAP login rejected for %r: %d matching entries", username, len(entries))
            return None
        return entries[0]

    def _authenticate_sync(self, username: str, password: str) -> Identity | None:
        entry = self._find(username)
        if entry is None:
            return None
        try:
            user_conn = Connection(self._server(), user=entry.entry_dn, password=password)
            bound = user_conn.bind()
            user_conn.unbind()
        except LDAPException as exc:
            log.error("LDAP user bind failed: %s", exc)
            raise AuthBackendError("Directory not reachable") from exc
        return _identity(entry, username) if bound else None


def _identity(entry: Any, username: str) -> Identity:
    def attr(name: str) -> str | None:
        value = entry[name].value if name in entry else None
        return str(value) if value else None

    return Identity(
        username=(attr("sAMAccountName") or username).lower(),
        display_name=attr("displayName") or username,
        email=attr("mail"),
    )


def build_authenticator(settings: Settings) -> Authenticator:
    if settings.auth_backend is AuthBackend.DEV:
        return StaticAuthenticator(settings.dev_user_map())
    return LdapAuthenticator(settings)
