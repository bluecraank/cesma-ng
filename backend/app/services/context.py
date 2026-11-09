"""The caller of a service operation: authenticated user plus request metadata."""

from dataclasses import dataclass

from app.core.config import Settings
from app.core.crypto import SecretBox
from app.models import User
from app.services.audit import Actor


@dataclass(frozen=True)
class Caller:
    user: User
    ip_address: str | None = None

    @property
    def actor(self) -> Actor:
        return Actor.of(self.user, self.ip_address)


@dataclass(frozen=True)
class Runtime:
    """What services need to talk to switches: settings (simulator, timeouts) and secrets."""

    settings: Settings
    box: SecretBox
