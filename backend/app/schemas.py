"""Pydantic request/response models of the HTTP API."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.core.db import ensure_utc
from app.domain.switch import PoeStatus, PortKind
from app.models import (
    AuditLevel,
    ComplianceMode,
    DeviceModel,
    DeviceStatus,
    NotificationKind,
    NotificationSeverity,
    Permission,
    PollTask,
    SnmpVersion,
)

Name = Field(min_length=1, max_length=100)

# SQLite returns naive timestamps; the API always answers with explicit UTC.
UtcDatetime = Annotated[datetime, AfterValidator(ensure_utc)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth / users ----------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class SiteRoleOut(ORM):
    site_id: int
    role_id: int
    role_name: str
    permissions: list[str]


class UserOut(ORM):
    id: int
    username: str
    display_name: str
    email: str | None
    is_superadmin: bool
    is_active: bool
    locale: str
    last_login_at: UtcDatetime | None
    has_local_password: bool
    site_roles: list[SiteRoleOut]


class UserUpdate(BaseModel):
    is_superadmin: bool | None = None
    is_active: bool | None = None
    #: site id -> role id
    site_roles: dict[int, int] | None = None
    #: emergency password for logins while LDAP is unreachable; "" removes it
    local_password: str | None = Field(default=None, max_length=1024)


class RoleIn(BaseModel):
    name: str = Name
    description: str = Field(default="", max_length=255)
    permissions: list[Permission] = []


class RoleOut(ORM):
    id: int
    name: str
    description: str
    permissions: list[str]
    builtin: str | None


class LocaleUpdate(BaseModel):
    locale: str


# --- Org -------------------------------------------------------------------------------------


class NameIn(BaseModel):
    name: str = Name


class RoomOut(ORM):
    id: int
    building_id: int
    name: str


class BuildingOut(ORM):
    id: int
    site_id: int
    name: str
    rooms: list[RoomOut]


class SiteOut(ORM):
    id: int
    name: str
    buildings: list[BuildingOut]


# --- Credentials -----------------------------------------------------------------------------


class CredentialProfileIn(BaseModel):
    """Secrets: omit to keep the stored value, send an empty string to clear it."""

    name: str = Name
    snmp_version: SnmpVersion = SnmpVersion.V2C
    snmp_v3_username: str | None = None
    snmp_v3_auth_protocol: str | None = None
    snmp_v3_priv_protocol: str | None = None
    api_username: str | None = None
    ssh_username: str | None = None
    verify_tls: bool = False
    api_https: bool = True

    snmp_community: str | None = None
    snmp_v3_auth_password: str | None = None
    snmp_v3_priv_password: str | None = None
    api_password: str | None = None
    ssh_password: str | None = None
    ssh_private_key: str | None = None
    enable_password: str | None = None


class CredentialProfileOut(ORM):
    id: int
    name: str
    snmp_version: SnmpVersion
    snmp_v3_username: str | None
    snmp_v3_auth_protocol: str | None
    snmp_v3_priv_protocol: str | None
    api_username: str | None
    ssh_username: str | None
    verify_tls: bool
    api_https: bool
    secrets_set: list[str] = []


# --- Devices ---------------------------------------------------------------------------------


class DeviceIn(BaseModel):
    name: str = Name
    hostname: str = Field(min_length=1, max_length=255)
    model: DeviceModel
    site_id: int
    room_id: int | None = None
    credential_profile_id: int | None = None
    location_note: str = Field(default="", max_length=255)


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    model: DeviceModel | None = None
    site_id: int | None = None
    room_id: int | None = None
    credential_profile_id: int | None = None
    location_note: str | None = Field(default=None, max_length=255)


class DeviceOut(ORM):
    id: int
    name: str
    hostname: str
    model: DeviceModel
    site_id: int
    room_id: int | None
    credential_profile_id: int | None
    location_note: str
    status: DeviceStatus
    sys_name: str | None
    model_name: str | None
    serial_number: str | None
    firmware: str | None
    mac_address: str | None
    uptime_seconds: int | None
    last_seen_at: UtcDatetime | None
    ip_address: str | None
    dns_name: str | None
    #: the model supports uploading SSH keys
    supports_ssh_keys: bool


# --- Audit -----------------------------------------------------------------------------------


class AuditEntryOut(ORM):
    id: int
    created_at: UtcDatetime
    level: AuditLevel
    action: str
    message: str
    actor_name: str
    ip_address: str | None
    site_id: int | None
    device_id: int | None
    old_values: dict[str, Any] | None
    new_values: dict[str, Any] | None


class Page[T](BaseModel):
    items: list[T]
    total: int


# --- Inventory (read from switches) ----------------------------------------------------------


class PortOut(ORM):
    id: int
    if_index: int
    name: str
    kind: PortKind
    description: str
    admin_up: bool
    oper_up: bool
    speed_mbps: int | None
    mac_address: str | None
    pvid: int | None
    poe: PoeStatus | None
    last_change_at: UtcDatetime | None
    untagged_vlans: list[int] = []
    tagged_vlans: list[int] = []
    is_uplink: bool = False
    neighbor: str | None = None
    neighbor_device_id: int | None = None
    mac_count: int = 0


class DeviceVlanOut(ORM):
    vid: int
    name: str
    untagged_ports: int = 0
    tagged_ports: int = 0


class FdbEntryOut(BaseModel):
    mac_address: str
    vid: int | None
    port_id: int | None
    port_name: str | None
    vendor: str | None = None
    ip_addresses: list[str] = []
    seen_at: UtcDatetime


class LldpNeighborOut(ORM):
    id: int
    port_id: int | None
    local_port_name: str
    chassis_id: str
    remote_port: str
    remote_port_description: str
    system_name: str
    system_description: str
    management_address: str | None
    remote_device_id: int | None


class PollStateOut(ORM):
    task: PollTask
    next_due_at: UtcDatetime
    last_run_at: UtcDatetime | None
    last_success_at: UtcDatetime | None
    failures: int
    last_error: str | None
    last_duration_ms: int | None


class DetectRequest(BaseModel):
    hostname: str = Field(min_length=1, max_length=255)
    credential_profile_id: int | None = None


class DetectResult(BaseModel):
    model: DeviceModel | None
    sys_name: str
    sys_descr: str
    sys_object_id: str
    model_name: str | None


class NotificationOut(ORM):
    id: int
    created_at: UtcDatetime
    kind: NotificationKind
    severity: NotificationSeverity
    site_id: int | None
    device_id: int | None
    port_name: str | None
    message: str
    acknowledged_at: UtcDatetime | None
    acknowledged_by: str | None


# --- Clients ---------------------------------------------------------------------------------


class ClientOut(BaseModel):
    id: int
    mac_address: str
    ip_address: str | None
    hostname: str | None
    vid: int | None
    site_id: int | None
    device_id: int | None
    device_name: str | None
    port_id: int | None
    port_name: str | None
    vendor: str | None
    type_name: str | None
    type_icon: str | None
    first_seen_at: UtcDatetime
    last_seen_at: UtcDatetime
    active: bool


class MacTypeIn(BaseModel):
    prefix: str = Field(min_length=2, max_length=17)
    name: str = Field(min_length=1, max_length=64)
    icon: str = "device"


class MacTypeOut(ORM):
    id: int
    prefix: str
    name: str
    icon: str


class GatewayIn(BaseModel):
    name: str = Name
    hostname: str = Field(min_length=1, max_length=255)
    credential_profile_id: int | None = None
    enabled: bool = True


class GatewayOut(ORM):
    id: int
    name: str
    hostname: str
    credential_profile_id: int | None
    enabled: bool
    last_polled_at: UtcDatetime | None
    last_error: str | None
    entries: int


class SearchHit(BaseModel):
    kind: str  # device | port | client | vlan
    title: str
    subtitle: str = ""
    device_id: int | None = None
    port_id: int | None = None
    site_id: int | None = None
    query: str | None = None  # for "client": the value to search in the clients view


class SearchResult(BaseModel):
    hits: list[SearchHit]


# --- Configuration changes -------------------------------------------------------------------


class PortChangeIn(BaseModel):
    port_ids: list[int] = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None
    untagged: int | None = Field(default=None, ge=1, le=4094)
    tagged: list[int] | None = None
    clear_untagged: bool = False
    #: tag / untag single VLANs, keeping the port's other tagged VLANs
    add_tagged: list[Annotated[int, Field(ge=1, le=4094)]] = []
    remove_tagged: list[Annotated[int, Field(ge=1, le=4094)]] = []
    profile_id: int | None = None  # apply a port profile (overrides VLAN/description fields)


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=63)


class DeviceHintOut(ORM):
    device_id: int
    code: str
    level: str
    detail: str


class ChangePlanOut(BaseModel):
    device_id: int
    device_name: str
    operations: int
    commands: list[str]
    warnings: list[str]


class ApplyResult(BaseModel):
    plan: ChangePlanOut
    log: list[str]


class SiteVlanIn(BaseModel):
    vid: int = Field(ge=1, le=4094)
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)
    ip_range: str | None = None
    is_client_vlan: bool = True
    scan_enabled: bool = False
    sync_enabled: bool = True


class SiteVlanOut(SiteVlanIn):
    id: int
    site_id: int
    devices_with_vlan: int = 0
    devices_name_mismatch: int = 0
    device_count: int = 0


class VlanSyncIn(BaseModel):
    device_ids: list[int] | None = None
    delete_extra: bool = False
    tag_uplinks: bool = False


class PortProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    untagged_vid: int | None = Field(default=None, ge=1, le=4094)
    tagged_vids: list[int] = []
    description: str | None = Field(default=None, max_length=200)


class PortProfileOut(ORM):
    id: int
    site_id: int
    name: str
    untagged_vid: int | None
    tagged_vids: list[int]
    description: str | None


class BackupOut(BaseModel):
    id: int
    device_id: int
    device_name: str
    site_id: int
    created_at: UtcDatetime
    status: str
    sha256: str | None
    size: int
    changed: bool
    error: str | None
    created_by: str


class JobIn(BaseModel):
    kind: str
    site_id: int
    device_ids: list[int] | None = None
    delete_extra: bool = False
    tag_uplinks: bool = False
    cidr: str | None = None  # discover: network to scan
    credential_profile_id: int | None = None  # discover: credentials to try
    backup_id: int | None = None  # restore


class JobOut(ORM):
    id: int
    kind: str
    status: str
    site_id: int | None
    created_by: str
    created_at: UtcDatetime
    started_at: UtcDatetime | None
    finished_at: UtcDatetime | None
    progress: int
    log: str
    error: str | None


class SshKeyIn(BaseModel):
    description: str = Field(min_length=1, max_length=100)
    key: str = Field(min_length=20, max_length=16384)


class SshKeyOut(ORM):
    id: int
    user_id: int | None
    owner: str | None
    description: str
    key: str
    fingerprint: str
    created_at: UtcDatetime


class TopologyNode(BaseModel):
    id: str
    device_id: int | None
    label: str
    kind: str  # switch | external
    status: str
    model: str


class TopologyEdge(BaseModel):
    id: str
    source: str
    target: str
    source_port: str
    target_port: str
    up: bool
    speed_mbps: int | None


class TopologyOut(BaseModel):
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


class PortStatPoint(BaseModel):
    at: UtcDatetime
    in_bps: int
    out_bps: int
    in_errors: int
    out_errors: int


class PortEventOut(BaseModel):
    at: UtcDatetime
    kind: str  # link_up | link_down | speed | configured | changed
    actor: str | None
    old: Any = None
    new: Any = None


class PortDeviceOut(BaseModel):
    mac_address: str
    vid: int | None
    first_seen_at: UtcDatetime
    last_seen_at: UtcDatetime
    vendor: str | None
    ip_address: str | None
    hostname: str | None


class PortHistoryOut(BaseModel):
    events: list[PortEventOut]
    devices: list[PortDeviceOut]


class ConnectedDeviceOut(BaseModel):
    mac_address: str
    vendor: str | None
    ip_address: str | None
    hostname: str | None


class SwitchPortOut(BaseModel):
    id: int
    name: str
    if_index: int
    description: str
    admin_up: bool
    oper_up: bool
    speed_mbps: int | None
    uplink: bool
    free: bool
    down_since: UtcDatetime | None
    last_device_at: UtcDatetime | None
    untagged_vlans: list[int]
    tagged_count: int
    poe: bool
    #: LLDP neighbour on this port ("name (port)"), e.g. another switch or an access point
    neighbor: str | None
    #: devices currently in the MAC table (the first few) and their total number
    connected: list[ConnectedDeviceOut]
    mac_count: int


class SwitchPortsDeviceOut(BaseModel):
    device_id: int
    device_name: str
    model: DeviceModel
    model_name: str | None
    status: DeviceStatus
    room: str | None
    building: str | None
    ports: list[SwitchPortOut]


class ComplianceRuleIn(BaseModel):
    name: str = Name
    description: str = Field(default="", max_length=255)
    mode: ComplianceMode
    pattern: str = Field(min_length=1, max_length=500)
    models: list[DeviceModel] = []
    enabled: bool = True


class ComplianceRuleOut(ORM):
    id: int
    name: str
    description: str
    mode: ComplianceMode
    pattern: str
    models: list[str]
    enabled: bool


class ComplianceResultOut(BaseModel):
    rule_id: int
    #: None: no backup to check yet
    passed: bool | None
    #: matching lines (only for users who may read backups)
    lines: list[str]


class ComplianceDeviceOut(BaseModel):
    device_id: int
    device_name: str
    backup_at: UtcDatetime | None
    results: list[ComplianceResultOut]


class ComplianceOut(BaseModel):
    rules: list[ComplianceRuleOut]
    devices: list[ComplianceDeviceOut]


class PortStatsOut(BaseModel):
    port_id: int
    speed_mbps: int | None
    points: list[PortStatPoint]


class ConsoleIn(BaseModel):
    command: str = Field(min_length=1, max_length=200)


class ConsoleOut(BaseModel):
    output: str
