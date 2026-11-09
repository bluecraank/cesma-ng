"""Golden tests: exactly what each switch family receives for a change."""

import base64
from dataclasses import replace

import pytest

from app.domain.changes import (
    CreateVlan,
    DeleteVlan,
    RenameVlan,
    SetHostname,
    SetPortDescription,
    SetPortEnabled,
    SetPortVlans,
    vlan_list,
)
from app.domain.credentials import DeviceCredentials, LoginCredentials
from app.drivers.writers import (
    ArubaCxRestWriter,
    ArubaOsRestWriter,
    DnosCliWriter,
    Os10CliWriter,
    WriteError,
)
from app.transports.cli import FakeCli
from app.transports.http import FakeHttp

CREDS = DeviceCredentials(
    api=LoginCredentials(username="admin", password="pw"),
    ssh=LoginCredentials(username="admin", password="pw"),
)

TRUNK = SetPortVlans(
    "P",
    untagged=10,
    tagged=frozenset({20, 30}),
    before_untagged=1,
    before_tagged=frozenset({30, 40}),
)


def test_vlan_list_compacts_ranges() -> None:
    assert vlan_list({1, 2, 3, 5, 7, 8}) == "1-3,5,7-8"
    assert vlan_list(set()) == ""


# --- Dell N1500 (DNOS 6) ---------------------------------------------------------------------


def test_dnos_render() -> None:
    w = DnosCliWriter("sw", CREDS)
    assert w.render([SetPortDescription("Gi1/0/5", 'Drucker "EG"')]) == [
        "interface Gi1/0/5",
        "description \"Drucker 'EG'\"",
        "exit",
    ]
    assert w.render([SetPortDescription("Gi1/0/5", "")])[1] == "no description"
    assert w.render([SetPortEnabled("Gi1/0/5", False)])[1] == "shutdown"
    assert w.render([SetPortVlans("Gi1/0/5", untagged=10, tagged=frozenset())]) == [
        "interface Gi1/0/5",
        "switchport mode access",
        "switchport access vlan 10",
        "exit",
    ]
    assert w.render([SetPortVlans("Te1/0/1", untagged=10, tagged=frozenset({20, 21, 22}))]) == [
        "interface Te1/0/1",
        "switchport mode trunk",
        "switchport trunk native vlan 10",
        "switchport trunk allowed vlan 10,20-22",
        "exit",
    ]
    assert w.render([CreateVlan(120, "Office"), DeleteVlan(99)]) == [
        "vlan 120",
        'name "Office"',
        "exit",
        "no vlan 99",
    ]


async def test_dnos_apply_configures_and_saves() -> None:
    cli = FakeCli()
    w = DnosCliWriter("sw", CREDS, cli_factory=lambda: _ready(cli))
    log = await w.apply([SetPortEnabled("Gi1/0/1", True)])
    assert cli.commands == [
        "configure",
        "interface Gi1/0/1",
        "no shutdown",
        "exit",
        "end",
        "write memory",
    ]
    assert log[-1] == "write memory"
    assert cli.closed


async def test_dnos_rejected_command_stops_and_reports() -> None:
    cli = FakeCli({"switchport access vlan 4000": "% Invalid input detected at '^' marker."})
    w = DnosCliWriter("sw", CREDS, cli_factory=lambda: _ready(cli))
    with pytest.raises(WriteError, match="vlan 4000"):
        await w.apply([SetPortVlans("Gi1/0/1", untagged=4000, tagged=frozenset())])
    assert "write memory" not in cli.commands  # never persisted
    assert cli.closed


async def _ready(cli: FakeCli) -> FakeCli:
    return cli


# --- Dell OS10 -------------------------------------------------------------------------------


def test_os10_render_uses_diff_for_trunks() -> None:
    w = Os10CliWriter("sw", CREDS)
    assert w.render([replace(TRUNK, port="ethernet1/1/5")]) == [
        "interface ethernet1/1/5",
        "switchport mode trunk",
        "no switchport trunk allowed vlan 40",
        "switchport trunk allowed vlan 20",
        "switchport access vlan 10",
        "exit",
    ]
    assert w.render([RenameVlan(10, "Office")]) == [
        "interface vlan 10",
        'description "Office"',
        "exit",
    ]
    assert w.render([DeleteVlan(10)]) == ["no interface vlan 10"]


async def test_os10_backup_uses_os10_command() -> None:
    cli = FakeCli({"show running-configuration": "! config\nhostname sw\n"})
    w = Os10CliWriter("sw", CREDS, cli_factory=lambda: _ready(cli))
    assert "hostname sw" in await w.running_config()


# --- HP/Aruba 2530 (ArubaOS-Switch REST) -----------------------------------------------------


def test_arubaos_render_membership_changes() -> None:
    w = ArubaOsRestWriter("sw", CREDS)
    assert w.render([replace(TRUNK, port="5")]) == [
        'POST /vlans-ports {"vlan_id": 10, "port_id": "5", "port_mode": "POM_UNTAGGED"}',
        'POST /vlans-ports {"vlan_id": 20, "port_id": "5", "port_mode": "POM_TAGGED_STATIC"}',
        "DELETE /vlans-ports/40-5",
    ]
    assert w.render([SetPortVlans("5", None, frozenset(), 10, frozenset())]) == [
        "DELETE /vlans-ports/10-5"
    ]
    assert w.render([SetPortDescription("5", "AP")]) == ['PUT /ports/5 {"name": "AP"}']


async def test_arubaos_apply_logs_in_saves_and_logs_out() -> None:
    http = FakeHttp(
        {
            ("GET", "/rest/version"): {"version_element": [{"version": "v3"}, {"version": "v7.0"}]},
            ("POST", "/rest/v7/login-sessions"): {"cookie": "sessionId=abc"},
        }
    )
    w = ArubaOsRestWriter("sw", CREDS, http_factory=lambda base: http)
    await w.apply([CreateVlan(120, "Office")])
    assert [(m, p) for m, p, _ in http.calls] == [
        ("GET", "/rest/version"),
        ("POST", "/rest/v7/login-sessions"),
        ("POST", "/rest/v7/vlans"),
        ("POST", "/rest/v7/cli"),
        ("DELETE", "/rest/v7/login-sessions"),
    ]
    assert http.calls[3][2] == {"cmd": "write memory"}
    assert http.closed


async def test_arubaos_backup_decodes_cli_output() -> None:
    config = "hostname sw\nvlan 1\n"
    http = FakeHttp(
        {
            ("GET", "/rest/version"): {"version_element": [{"version": "v7.0"}]},
            ("POST", "/rest/v7/login-sessions"): {"cookie": "sessionId=abc"},
            ("POST", "/rest/v7/cli"): {
                "result_base64_encoded": base64.b64encode(config.encode()).decode()
            },
        }
    )
    w = ArubaOsRestWriter("sw", CREDS, http_factory=lambda base: http)
    assert await w.running_config() == config


def test_arubaos_uses_http_when_configured() -> None:
    plain = DeviceCredentials(api=CREDS.api, api_https=False)
    assert ArubaOsRestWriter("10.0.0.2", plain).base_url == "http://10.0.0.2"
    assert ArubaOsRestWriter("10.0.0.2", CREDS).base_url == "https://10.0.0.2"


# --- Aruba CX --------------------------------------------------------------------------------


def test_cx_render_uses_url_encoded_ports_and_vlan_references() -> None:
    w = ArubaCxRestWriter("sw", CREDS)
    [call] = w.calls([SetPortVlans("1/1/5", 10, frozenset({20}))], api="/rest/v10.13")
    assert call.method == "PATCH" and call.path == "/system/interfaces/1%2F1%2F5"
    assert call.body == {
        "vlan_mode": "native-untagged",
        "vlan_trunks": ["/rest/v10.13/system/vlans/20"],
        "vlan_tag": "/rest/v10.13/system/vlans/10",
    }
    [access] = w.calls([SetPortVlans("1/1/6", 30, frozenset())], api="/rest/v10.13")
    assert access.body == {"vlan_mode": "access", "vlan_tag": "/rest/v10.13/system/vlans/30"}


async def test_cx_apply_discovers_api_version_and_saves() -> None:
    http = FakeHttp({("GET", "/rest"): {"latest": {"prefix": "/rest/v10.13"}}})
    w = ArubaCxRestWriter("sw", CREDS, http_factory=lambda base: http)
    await w.apply([SetPortEnabled("1/1/1", False)])
    paths = [p for _, p, _ in http.calls]
    assert paths[1] == "/rest/v10.13/login"
    assert "/rest/v10.13/system/interfaces/1%2F1%2F1" in paths
    assert any(p.startswith("/rest/v10.13/fullconfigs/startup-config") for p in paths)
    assert paths[-1] == "/rest/v10.13/logout"


async def test_arubaos_restore_polls_until_success() -> None:
    http = FakeHttp(
        {
            ("GET", "/rest/version"): {"version_element": [{"version": "v7.0"}]},
            ("POST", "/rest/v7/login-sessions"): {"cookie": "sessionId=abc"},
            ("POST", "/rest/v7/system/config/cfg_restore/payload"): {"status": "CRS_IN_PROGRESS"},
            ("GET", "/rest/v7/system/config/cfg_restore/payload/status"): {"status": "CRS_SUCCESS"},
        }
    )
    w = ArubaOsRestWriter("sw", CREDS, http_factory=lambda base: http)
    w.RESTORE_POLL_SECONDS = 0  # type: ignore[misc]
    await w.restore("hostname sw\n")
    body = http.calls[2][2]
    assert base64.b64decode(body["config_base64_encoded"]).decode() == "hostname sw\n"
    assert body["is_forced_reboot_enabled"] is False
    assert http.calls[-1][1] == "/rest/v7/login-sessions"  # logged out


async def test_arubaos_restore_failure_is_reported() -> None:
    http = FakeHttp(
        {
            ("GET", "/rest/version"): {"version_element": [{"version": "v7.0"}]},
            ("POST", "/rest/v7/login-sessions"): {"cookie": "sessionId=abc"},
            ("POST", "/rest/v7/system/config/cfg_restore/payload"): {
                "status": "CRS_FAILED",
                "failure_reason": "invalid config",
            },
        }
    )
    w = ArubaOsRestWriter("sw", CREDS, http_factory=lambda base: http)
    with pytest.raises(WriteError, match="CRS_FAILED invalid config"):
        await w.restore("x")


async def test_dell_has_no_restore() -> None:
    with pytest.raises(WriteError, match="not supported"):
        await DnosCliWriter("sw", CREDS).restore("x")


def test_hostname_on_every_model() -> None:
    op = [SetHostname("sw-eg-01")]
    assert DnosCliWriter("sw", CREDS).render(op) == ['hostname "sw-eg-01"']
    assert Os10CliWriter("sw", CREDS).render(op) == ["hostname sw-eg-01"]
    assert ArubaOsRestWriter("sw", CREDS).render(op) == ['PUT /system {"name": "sw-eg-01"}']
    assert ArubaCxRestWriter("sw", CREDS).render(op) == ['PATCH /system {"hostname": "sw-eg-01"}']
