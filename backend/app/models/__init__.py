"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.audit import AuditEntry, AuditLevel
from app.models.clients import Client, DiscoveredHost, MacType, MacVendor, SnmpGateway
from app.models.config import (
    Backup,
    BackupStatus,
    Job,
    JobStatus,
    PortProfile,
    SiteVlan,
    SshPublicKey,
)
from app.models.device import CredentialProfile, Device, DeviceModel, DeviceStatus, SnmpVersion
from app.models.inventory import (
    ArpEntry,
    DevicePollState,
    DeviceVlan,
    FdbEntry,
    LldpNeighbor,
    PollTask,
    Port,
    PortCounterSample,
    PortVlan,
)
from app.models.notification import Notification, NotificationKind, NotificationSeverity
from app.models.org import Building, Room, Site
from app.models.user import SiteRole, User, UserSession, UserSiteRole

__all__ = [
    "ArpEntry",
    "AuditEntry",
    "AuditLevel",
    "Backup",
    "BackupStatus",
    "Building",
    "Client",
    "CredentialProfile",
    "Device",
    "DeviceModel",
    "DevicePollState",
    "DeviceStatus",
    "DeviceVlan",
    "DiscoveredHost",
    "FdbEntry",
    "Job",
    "JobStatus",
    "LldpNeighbor",
    "MacType",
    "MacVendor",
    "Notification",
    "NotificationKind",
    "NotificationSeverity",
    "PollTask",
    "Port",
    "PortCounterSample",
    "PortProfile",
    "PortVlan",
    "Room",
    "Site",
    "SiteRole",
    "SiteVlan",
    "SnmpGateway",
    "SnmpVersion",
    "SshPublicKey",
    "User",
    "UserSession",
    "UserSiteRole",
]
