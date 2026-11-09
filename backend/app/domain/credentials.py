"""Decrypted access data handed to drivers. Never serialised to API responses."""

from dataclasses import dataclass, field

SECRET_FIELDS = (
    "snmp_community",
    "snmp_v3_auth_password",
    "snmp_v3_priv_password",
    "api_password",
    "ssh_password",
    "ssh_private_key",
    "enable_password",
)


@dataclass(frozen=True)
class SnmpCredentials:
    version: str = "v2c"
    community: str = "public"
    v3_username: str | None = None
    v3_auth_protocol: str | None = None
    v3_auth_password: str | None = None
    v3_priv_protocol: str | None = None
    v3_priv_password: str | None = None


@dataclass(frozen=True)
class LoginCredentials:
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    private_key: str | None = field(default=None, repr=False)
    enable_password: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class DeviceCredentials:
    snmp: SnmpCredentials = field(default_factory=SnmpCredentials)
    api: LoginCredentials = field(default_factory=LoginCredentials)
    ssh: LoginCredentials = field(default_factory=LoginCredentials)
    verify_tls: bool = False
    api_https: bool = True
