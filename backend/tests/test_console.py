import pytest
from httpx import AsyncClient

from app.core.errors import ValidationFailedError
from app.services.console import validate


@pytest.mark.parametrize(
    "command",
    [
        "show vlan",
        "show interfaces status",
        "show run | include vlan 10",
        "ping 10.0.0.1",
        "show mac address-table address aa:bb:cc:dd:ee:ff",
    ],
)
def test_read_only_commands_are_allowed(command: str) -> None:
    assert validate(command) == command


@pytest.mark.parametrize(
    "command",
    [
        "configure",
        "conf t",
        "write memory",
        "copy running-config tftp",
        "reload",
        "show vlan; reload",
        "show vlan\nconfigure",
        "delete flash:x",
        "erase startup-config",
        "no vlan 10",
        "",
    ],
)
def test_changing_commands_are_refused(command: str) -> None:
    with pytest.raises(ValidationFailedError):
        validate(command)


async def test_console_is_admin_only_and_audited(alice: AsyncClient, bob: AsyncClient) -> None:
    site = (await alice.post("/sites", json={"name": "HQ"})).json()["id"]
    device = (
        await alice.post(
            "/devices",
            json={"name": "sw", "hostname": "192.0.2.1", "model": "dell_os10", "site_id": site},
        )
    ).json()
    from tests.conftest import grant

    await grant(alice, "bob", {site: "viewer"})
    assert (
        await bob.post(f"/devices/{device['id']}/console", json={"command": "show vlan"})
    ).status_code == 403
    refused = await alice.post(f"/devices/{device['id']}/console", json={"command": "configure"})
    assert refused.status_code == 422
