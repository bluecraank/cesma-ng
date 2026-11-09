"""Application settings, loaded from environment variables (prefix ``CESMA_``)."""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"


class AuthBackend(StrEnum):
    LDAP = "ldap"
    DEV = "dev"  # static users from CESMA_DEV_USERS, never allowed in production


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CESMA_", env_file=".env", extra="ignore")

    environment: Environment = Environment.DEVELOPMENT
    database_url: str = "sqlite+aiosqlite:///./cesma.db"
    secret_key: SecretStr = Field(
        default=SecretStr("dev-insecure-secret-change-me"),
        description="Used to derive the encryption key for stored credentials.",
    )

    # Sessions
    session_ttl_hours: int = 12
    session_cookie_name: str = "cesma_session"
    cookie_secure: bool = True

    # Authentication
    auth_backend: AuthBackend = AuthBackend.LDAP
    dev_users: str = Field(default="", description="Comma separated user:password pairs")

    ldap_url: str = "ldaps://dc1.domain.local:636"
    ldap_bind_dn: str = ""
    ldap_bind_password: SecretStr = SecretStr("")
    ldap_base_dn: str = ""
    ldap_required_group: str = Field(
        default="", description="DN of a group (nested membership) required to log in"
    )
    ldap_timeout: int = 10
    ldap_verify_tls: bool = True
    ldap_ca_file: str | None = None

    # Polling (seconds)
    poll_inventory_interval: int = 120
    poll_fdb_interval: int = 300
    poll_arp_interval: int = 300
    poll_lldp_interval: int = 3600
    poll_counters_interval: int = 300
    poll_concurrency: int = 20
    poll_timeout: int = 120
    #: consecutive failed inventory polls before a device is marked offline
    offline_after_failures: int = 2
    #: development/demo only: answer devices from <dir>/<hostname>.snmprec recordings
    snmp_simulator_dir: str | None = None

    # Retention (days)
    retention_audit_days: int = 56
    retention_notification_days: int = 42
    retention_client_days: int = 56
    retention_backup_days: int = 28
    retention_port_stats_days: int = 14
    retention_port_history_days: int = 90

    # Backups
    backup_time: str = "22:30"  # daily, local time HH:MM

    # Mail (weekly backup report)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_starttls: bool = True
    smtp_username: str | None = None
    smtp_password: SecretStr = SecretStr("")
    mail_from: str = "cesma-ng@localhost"
    backup_mail_to: str | None = None

    # Clients
    #: weekly download of the IEEE OUI list (MAC vendors); disable on offline systems
    oui_auto_update: bool = True
    oui_url: str = "https://standards-oui.ieee.org/oui/oui.csv"
    dns_lookup_enabled: bool = True

    # SSO via trusted reverse proxy header (optional)
    #: HTTP header with the user name set by the proxy, e.g. "X-Authentik-Username"
    sso_header: str | None = None
    #: only requests from these addresses/networks may use the header (the proxy itself)
    sso_trusted_proxies: list[str] = Field(default_factory=list)
    #: accept "user@domain" / "DOMAIN\user" and use only the user part
    sso_strip_domain: bool = True

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        if self.environment is Environment.PRODUCTION:
            if self.auth_backend is AuthBackend.DEV:
                raise ValueError("The dev auth backend must not be used in production")
            if self.secret_key.get_secret_value().startswith("dev-insecure"):
                raise ValueError("CESMA_SECRET_KEY must be set in production")
            if self.snmp_simulator_dir:
                raise ValueError("The SNMP simulator must not be used in production")
        return self

    def dev_user_map(self) -> dict[str, str]:
        pairs = (item.split(":", 1) for item in self.dev_users.split(",") if ":" in item)
        return {user.strip(): password for user, password in pairs}


@lru_cache
def get_settings() -> Settings:
    return Settings()
