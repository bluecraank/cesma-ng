"""Writing configuration and reading backups, one class per switch family.

``render`` is pure (used for the preview / dry run), ``apply`` executes exactly what
``render`` shows. Transports are injected, so tests run against fakes.
"""

import asyncio
import base64
import contextlib
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar
from urllib.parse import quote

import asyncssh

from app.domain.changes import (
    CreateVlan,
    DeleteVlan,
    Operation,
    RenameVlan,
    SetHostname,
    SetPortDescription,
    SetPortEnabled,
    SetPortVlans,
    vlan_list,
)
from app.domain.credentials import DeviceCredentials
from app.transports.cli import Cli, CliError, SshCli
from app.transports.http import Http, HttpError, HttpxClient

CliFactory = Callable[[], Awaitable[Cli]]
HttpFactory = Callable[[str], Http]  # base URL -> client


class WriteError(Exception):
    """A switch rejected a change."""


SftpUpload = Callable[
    [str, DeviceCredentials, str, str], Awaitable[None]
]  # host, creds, path, text


async def sftp_upload(host: str, credentials: DeviceCredentials, path: str, text: str) -> None:
    login = credentials.ssh
    keys = [asyncssh.import_private_key(login.private_key)] if login.private_key else None
    try:
        async with (
            asyncssh.connect(
                host,
                username=login.username,
                password=login.password,
                client_keys=keys,
                known_hosts=None,
            ) as conn,
            conn.start_sftp_client() as sftp,
            sftp.open(path, "w") as remote,
        ):
            await remote.write(text)
    except (OSError, asyncssh.Error) as exc:
        raise WriteError(f"SFTP upload to {host} failed: {exc}") from exc


def rsa_public_key_blob(private_key: str | None) -> str:
    """Base64 part of the RSA public key that belongs to Cesma's own private key."""
    if not private_key:
        raise WriteError(
            "The credential profile has no private SSH key: generate Cesma's key there first"
        )
    try:
        key = asyncssh.import_private_key(private_key)
    except (asyncssh.KeyImportError, ValueError) as exc:
        raise WriteError(
            f"The private SSH key of the credential profile is invalid: {exc}"
        ) from exc
    if key.get_algorithm() != "ssh-rsa":
        raise WriteError("This switch accepts only RSA keys: generate an RSA key for Cesma")
    return key.export_public_key("openssh").decode().split()[1]


class ConfigWriter(ABC):
    #: can upload SSH public keys for the management user
    supports_ssh_keys: ClassVar[bool] = False
    #: the switch gets only Cesma's own key, not the user key list
    ssh_keys_own_only: ClassVar[bool] = False
    #: can load a backup back onto the switch
    supports_restore: ClassVar[bool] = False

    def __init__(self, host: str, credentials: DeviceCredentials) -> None:
        self.host = host
        self.credentials = credentials

    @abstractmethod
    def render(self, operations: Sequence[Operation]) -> list[str]: ...

    @abstractmethod
    async def apply(self, operations: Sequence[Operation]) -> list[str]:
        """Execute and persist (write memory). Returns a log of what was done."""

    @abstractmethod
    async def running_config(self) -> str: ...

    async def push_ssh_keys(self, keys: Sequence[str]) -> int:
        """Put the key list on the switch (replacing what was there); returns how many keys
        the switch now holds from Cesma."""
        raise WriteError("Uploading SSH keys is not supported for this model")

    async def restore(self, config: str) -> None:
        raise WriteError("Restoring a backup is not supported for this model")

    async def run_show(self, command: str) -> str:
        """Run one read-only command (validated by the caller) and return its output."""
        try:
            return await ssh_show(self.host, self.credentials, command, ("terminal length 0",))
        except CliError as exc:
            raise WriteError(str(exc)) from exc


def _quote(text: str) -> str:
    return '"' + text.replace('"', "'") + '"'


# --- CLI based (Dell) ------------------------------------------------------------------------

_CLI_ERROR = re.compile(
    r"^\s*%|Invalid input|Incomplete command|Error:", re.IGNORECASE | re.MULTILINE
)


class CliWriter(ConfigWriter):
    """Configuration via SSH CLI: configure / commands / end / write memory."""

    setup: ClassVar[tuple[str, ...]] = ("terminal length 0",)
    save_command: ClassVar[str] = "write memory"
    show_config_command: ClassVar[str] = "show running-config"

    def __init__(
        self, host: str, credentials: DeviceCredentials, cli_factory: CliFactory | None = None
    ) -> None:
        super().__init__(host, credentials)
        self._cli_factory = cli_factory or self._ssh

    async def _ssh(self) -> Cli:
        return await SshCli.connect(self.host, self.credentials.ssh, setup=self.setup)

    def render(self, operations: Sequence[Operation]) -> list[str]:
        lines: list[str] = []
        for op in operations:
            lines += self.render_one(op)
        return lines

    @abstractmethod
    def render_one(self, op: Operation) -> list[str]: ...

    async def apply(self, operations: Sequence[Operation]) -> list[str]:
        return await self._configure(self.render(operations))

    async def _configure(self, commands: Sequence[str]) -> list[str]:
        """configure / commands / end / save; stops at the first rejected command."""
        if not commands:
            return []
        log: list[str] = []
        cli = await self._cli_factory()
        try:
            await cli.run("configure")
            for command in commands:
                output = await cli.run(command)
                log.append(f"{command}")
                if _CLI_ERROR.search(output):
                    raise WriteError(f"'{command}' rejected: {output.strip()[:300]}")
            await cli.run("end")
            await cli.run(self.save_command, read_timeout=120)
            log.append(self.save_command)
        except CliError as exc:
            raise WriteError(str(exc)) from exc
        finally:
            await cli.close()
        return log

    async def run_show(self, command: str) -> str:
        cli = await self._cli_factory()
        try:
            return await cli.run(command, read_timeout=120)
        except CliError as exc:
            raise WriteError(str(exc)) from exc
        finally:
            await cli.close()

    async def running_config(self) -> str:
        cli = await self._cli_factory()
        try:
            return await cli.run(self.show_config_command, read_timeout=180)
        except CliError as exc:
            raise WriteError(str(exc)) from exc
        finally:
            await cli.close()


class DnosCliWriter(CliWriter):
    """Dell N1500 / DNOS 6."""

    setup = ("enable", "terminal length 0")
    #: DNOS 6 stores a single RSA key per user, so the user list cannot go there. Instead
    #: Cesma deposits the public part of its own key (from the credential profile).
    supports_ssh_keys = True
    ssh_keys_own_only = True

    def ssh_key_commands(self) -> list[str]:
        login = self.credentials.ssh
        if not login.username:
            raise WriteError("The credential profile has no SSH user")
        return [
            "crypto key pubkey-chain ssh",
            f"user-key {login.username} rsa",
            f'key-string "{rsa_public_key_blob(login.private_key)}"',
            "exit",
            "exit",
            "ip ssh pubkey-auth",
        ]

    async def push_ssh_keys(self, keys: Sequence[str]) -> int:
        await self._configure(self.ssh_key_commands())
        return 1

    def render_one(self, op: Operation) -> list[str]:
        match op:
            case SetPortDescription(port, description):
                cmd = f"description {_quote(description)}" if description else "no description"
                return [f"interface {port}", cmd, "exit"]
            case SetPortEnabled(port, enabled):
                return [f"interface {port}", "no shutdown" if enabled else "shutdown", "exit"]
            case SetPortVlans(port=port, untagged=untagged, tagged=tagged):
                if not tagged:
                    access = (
                        f"switchport access vlan {untagged}"
                        if untagged
                        else "no switchport access vlan"
                    )
                    return [f"interface {port}", "switchport mode access", access, "exit"]
                native = (
                    f"switchport trunk native vlan {untagged}"
                    if untagged
                    else "no switchport trunk native vlan"
                )
                allowed = set(tagged) | ({untagged} if untagged else set())
                return [
                    f"interface {port}",
                    "switchport mode trunk",
                    native,
                    f"switchport trunk allowed vlan {vlan_list(allowed)}",
                    "exit",
                ]
            case CreateVlan(vid, name) | RenameVlan(vid, name):
                return [f"vlan {vid}", f"name {_quote(name)}", "exit"]
            case DeleteVlan(vid):
                return [f"no vlan {vid}"]
            case SetHostname(name):
                return [f"hostname {_quote(name)}"]
        raise WriteError(f"Unsupported operation {op}")


class Os10CliWriter(CliWriter):
    """Dell PowerSwitch OS10. VLAN names are descriptions of 'interface vlan N'."""

    show_config_command = "show running-configuration"
    #: several keys only via a key file in the user's home directory
    supports_ssh_keys = True
    KEY_FILE: ClassVar[str] = "cesma_authorized_keys"

    def __init__(
        self,
        host: str,
        credentials: DeviceCredentials,
        cli_factory: CliFactory | None = None,
        sftp: SftpUpload = sftp_upload,
    ) -> None:
        super().__init__(host, credentials, cli_factory)
        self._sftp = sftp

    async def push_ssh_keys(self, keys: Sequence[str]) -> int:
        user = self.credentials.ssh.username
        if not user:
            raise WriteError("The credential profile has no SSH user")
        path = f"/home/{user}/{self.KEY_FILE}"
        await self._sftp(self.host, self.credentials, path, "".join(f"{k}\n" for k in keys))
        await self._configure([f"username {user} sshkey filename {path}"])
        return len(keys)

    def render_one(self, op: Operation) -> list[str]:
        match op:
            case SetPortDescription(port, description):
                cmd = f"description {_quote(description)}" if description else "no description"
                return [f"interface {port}", cmd, "exit"]
            case SetPortEnabled(port, enabled):
                return [f"interface {port}", "no shutdown" if enabled else "shutdown", "exit"]
            case SetPortVlans(port=port, untagged=untagged, tagged=tagged) as change:
                lines = [f"interface {port}"]
                if not tagged:
                    lines.append("switchport mode access")
                else:
                    lines.append("switchport mode trunk")
                    if change.removed_tagged:
                        lines.append(
                            f"no switchport trunk allowed vlan {vlan_list(change.removed_tagged)}"
                        )
                    if change.added_tagged:
                        lines.append(
                            f"switchport trunk allowed vlan {vlan_list(change.added_tagged)}"
                        )
                lines.append(
                    f"switchport access vlan {untagged}"
                    if untagged
                    else "no switchport access vlan"
                )
                return [*lines, "exit"]
            case CreateVlan(vid, name) | RenameVlan(vid, name):
                return [f"interface vlan {vid}", f"description {_quote(name)}", "exit"]
            case DeleteVlan(vid):
                return [f"no interface vlan {vid}"]
            case SetHostname(name):
                return [f"hostname {name}"]
        raise WriteError(f"Unsupported operation {op}")


# --- REST based (Aruba) ----------------------------------------------------------------------


@dataclass(frozen=True)
class RestCall:
    method: str
    path: str
    body: Any = None

    def __str__(self) -> str:
        return f"{self.method} {self.path}" + (
            f" {json.dumps(self.body)}" if self.body is not None else ""
        )


class RestWriter(ConfigWriter):
    def __init__(
        self, host: str, credentials: DeviceCredentials, http_factory: HttpFactory | None = None
    ) -> None:
        super().__init__(host, credentials)
        self._http_factory = http_factory or (
            lambda base: HttpxClient(base, verify_tls=credentials.verify_tls)
        )

    @property
    def base_url(self) -> str:
        scheme = "https" if self.credentials.api_https else "http"
        return f"{scheme}://{self.host}"

    def render(self, operations: Sequence[Operation]) -> list[str]:
        return [str(c) for c in self.calls(operations)]

    @abstractmethod
    def calls(self, operations: Sequence[Operation], api: str = "") -> list[RestCall]: ...


class ArubaOsRestWriter(RestWriter):
    """HP/Aruba 2530 (ArubaOS-Switch) REST API /rest/vN."""

    supports_ssh_keys = True
    AUTHORIZED_KEYS = "/ssh/mgr_keys/authorized_keys"

    def __init__(
        self,
        host: str,
        credentials: DeviceCredentials,
        http_factory: HttpFactory | None = None,
        sftp: SftpUpload = sftp_upload,
    ) -> None:
        super().__init__(host, credentials, http_factory)
        self._sftp = sftp

    @staticmethod
    def ssh_auth(current: dict[str, Any]) -> dict[str, str]:
        """Public key first; the previous login method (password, RADIUS, TACACS) stays as
        the second one, so nobody is locked out."""
        primary = current.get("primary_authentication_method") or "PAM_LOCAL"
        secondary = current.get("secondary_authentication_method") or "SAM_NONE"
        if primary != "PAM_PUBLIC_KEY":
            secondary = {"PAM_RADIUS": "SAM_RADIUS", "PAM_TACACS": "SAM_TACACS"}.get(
                primary, "SAM_LOCAL"
            )
        elif secondary == "SAM_NONE":
            secondary = "SAM_LOCAL"
        return {
            "primary_authentication_method": "PAM_PUBLIC_KEY",
            "secondary_authentication_method": secondary,
        }

    async def push_ssh_keys(self, keys: Sequence[str]) -> int:
        """Replace the manager keys (SFTP) and enable public key login (REST)."""
        content = "".join(f"{key}\n" for key in keys)
        await self._sftp(self.host, self.credentials, self.AUTHORIZED_KEYS, content)
        session = await self._session()
        try:
            current = await session.call(RestCall("GET", "/authentication/ssh")) or {}
            await session.call(RestCall("PUT", "/authentication/ssh", self.ssh_auth(current)))
            await session.call(RestCall("POST", "/cli", {"cmd": "write memory"}))
        except HttpError as exc:
            raise WriteError(str(exc)) from exc
        finally:
            await session.logout()
        return len(keys)

    def calls(self, operations: Sequence[Operation], api: str = "") -> list[RestCall]:
        result: list[RestCall] = []
        for op in operations:
            match op:
                case SetPortDescription(port, description):
                    result.append(RestCall("PUT", f"/ports/{port}", {"name": description}))
                case SetPortEnabled(port, enabled):
                    result.append(RestCall("PUT", f"/ports/{port}", {"is_port_enabled": enabled}))
                case SetPortVlans(port=port, untagged=untagged, before_untagged=before) as change:
                    if untagged and untagged != before:
                        result.append(
                            RestCall(
                                "POST",
                                "/vlans-ports",
                                {"vlan_id": untagged, "port_id": port, "port_mode": "POM_UNTAGGED"},
                            )
                        )
                    elif not untagged and before:
                        result.append(RestCall("DELETE", f"/vlans-ports/{before}-{port}"))
                    for vid in change.added_tagged:
                        result.append(
                            RestCall(
                                "POST",
                                "/vlans-ports",
                                {"vlan_id": vid, "port_id": port, "port_mode": "POM_TAGGED_STATIC"},
                            )
                        )
                    for vid in change.removed_tagged:
                        result.append(RestCall("DELETE", f"/vlans-ports/{vid}-{port}"))
                case CreateVlan(vid, name):
                    result.append(RestCall("POST", "/vlans", {"vlan_id": vid, "name": name}))
                case RenameVlan(vid, name):
                    result.append(RestCall("PUT", f"/vlans/{vid}", {"name": name}))
                case DeleteVlan(vid):
                    result.append(RestCall("DELETE", f"/vlans/{vid}"))
                case SetHostname(name):
                    result.append(RestCall("PUT", "/system", {"name": name}))
        return result

    async def _session(self) -> "_ArubaOsSession":
        http = self._http_factory(self.base_url)
        try:
            versions = await http.request("GET", "/rest/version")
            elements = (versions or {}).get("version_element") or [{"version": "v7"}]
            api = f"/rest/{elements[-1]['version'].split('.')[0]}"
            login = await http.request(
                "POST",
                f"{api}/login-sessions",
                json={
                    "userName": self.credentials.api.username,
                    "password": self.credentials.api.password,
                },
            )
            cookie = (login or {}).get("cookie")
            if not cookie:
                raise WriteError("Login failed (no session cookie)")
        except HttpError as exc:
            await http.close()
            raise WriteError(str(exc)) from exc
        return _ArubaOsSession(http, api, {"Cookie": cookie})

    async def apply(self, operations: Sequence[Operation]) -> list[str]:
        calls = self.calls(operations)
        if not calls:
            return []
        session = await self._session()
        log = []
        try:
            for call in calls:
                await session.call(call)
                log.append(str(call))
            await session.call(RestCall("POST", "/cli", {"cmd": "write memory"}))
            log.append("write memory")
        except HttpError as exc:
            raise WriteError(str(exc)) from exc
        finally:
            await session.logout()
        return log

    supports_restore = True
    RESTORE_POLL_SECONDS: ClassVar[float] = 4
    RESTORE_MAX_POLLS: ClassVar[int] = 75  # 5 minutes

    async def restore(self, config: str) -> None:
        """cfg_restore, then poll its status until CRS_SUCCESS (as cesma-on-premise did)."""
        session = await self._session()
        try:
            data = (
                await session.call(
                    RestCall(
                        "POST",
                        "/system/config/cfg_restore/payload",
                        {
                            "config_base64_encoded": base64.b64encode(config.encode()).decode(),
                            "is_forced_reboot_enabled": False,
                            "is_recoverymode_enabled": False,
                        },
                    )
                )
                or {}
            )
            for _ in range(self.RESTORE_MAX_POLLS):
                status = data.get("status")
                if status == "CRS_SUCCESS":
                    return
                if status not in (None, "CRS_IN_PROGRESS"):
                    break
                await asyncio.sleep(self.RESTORE_POLL_SECONDS)
                data = (
                    await session.call(RestCall("GET", "/system/config/cfg_restore/payload/status"))
                    or {}
                )
            reason = f"{data.get('status', 'timeout')} {data.get('failure_reason', '')}".strip()
            raise WriteError(f"Restore failed: {reason}")
        except HttpError as exc:
            raise WriteError(str(exc)) from exc
        finally:
            await session.logout()

    async def run_show(self, command: str) -> str:
        session = await self._session()
        try:
            result = await session.call(RestCall("POST", "/cli", {"cmd": command}))
            encoded = (result or {}).get("result_base64_encoded", "")
            return base64.b64decode(encoded).decode("utf-8", errors="replace")
        except HttpError as exc:
            raise WriteError(str(exc)) from exc
        finally:
            await session.logout()

    async def running_config(self) -> str:
        session = await self._session()
        try:
            result = await session.call(RestCall("POST", "/cli", {"cmd": "show running-config"}))
            encoded = (result or {}).get("result_base64_encoded", "")
            return base64.b64decode(encoded).decode("utf-8", errors="replace")
        except HttpError as exc:
            raise WriteError(str(exc)) from exc
        finally:
            await session.logout()


@dataclass
class _ArubaOsSession:
    """Logged-in ArubaOS-Switch REST session (the cookie comes in the login response)."""

    http: Http
    api: str
    headers: dict[str, str]

    async def call(self, call: RestCall) -> Any:
        return await self.http.request(
            call.method, f"{self.api}{call.path}", json=call.body, headers=self.headers
        )

    async def logout(self) -> None:
        with contextlib.suppress(HttpError):  # the session expires on its own
            await self.call(RestCall("DELETE", "/login-sessions"))
        await self.http.close()


class ArubaCxRestWriter(RestWriter):
    """HPE Aruba Networking CX (AOS-CX) REST API /rest/v10.x."""

    supports_ssh_keys = True
    DEFAULT_API = "/rest/v10.09"

    @staticmethod
    def _port(name: str) -> str:
        return quote(name, safe="")

    def calls(self, operations: Sequence[Operation], api: str = "") -> list[RestCall]:
        api = api or self.DEFAULT_API

        def vlan_ref(vid: int) -> str:
            return f"{api}/system/vlans/{vid}"

        result: list[RestCall] = []
        for op in operations:
            match op:
                case SetPortDescription(port, description):
                    result.append(
                        RestCall(
                            "PATCH",
                            f"/system/interfaces/{self._port(port)}",
                            {"description": description},
                        )
                    )
                case SetPortEnabled(port, enabled):
                    result.append(
                        RestCall(
                            "PATCH",
                            f"/system/interfaces/{self._port(port)}",
                            {"user_config": {"admin": "up" if enabled else "down"}},
                        )
                    )
                case SetPortVlans(port=port, untagged=untagged, tagged=tagged):
                    if tagged:
                        body: dict[str, Any] = {
                            "vlan_mode": "native-untagged",
                            "vlan_trunks": [vlan_ref(v) for v in sorted(tagged)],
                        }
                        if untagged:
                            body["vlan_tag"] = vlan_ref(untagged)
                    else:
                        body = {"vlan_mode": "access", "vlan_tag": vlan_ref(untagged or 1)}
                    result.append(RestCall("PATCH", f"/system/interfaces/{self._port(port)}", body))
                case CreateVlan(vid, name):
                    result.append(RestCall("POST", "/system/vlans", {"id": vid, "name": name}))
                case RenameVlan(vid, name):
                    result.append(RestCall("PATCH", f"/system/vlans/{vid}", {"name": name}))
                case DeleteVlan(vid):
                    result.append(RestCall("DELETE", f"/system/vlans/{vid}"))
                case SetHostname(name):
                    result.append(RestCall("PATCH", "/system", {"hostname": name}))
        return result

    async def _session(self) -> tuple[Http, str]:
        http = self._http_factory(self.base_url)
        try:
            info = await http.request("GET", "/rest")
            api = (info or {}).get("latest", {}).get("prefix") or self.DEFAULT_API
            await http.request(
                "POST",
                f"{api}/login",
                data={
                    "username": self.credentials.api.username,
                    "password": self.credentials.api.password,
                },
            )
        except HttpError as exc:
            await http.close()
            raise WriteError(str(exc)) from exc
        return http, api

    async def _logout(self, http: Http, api: str) -> None:
        with contextlib.suppress(HttpError):
            await http.request("POST", f"{api}/logout")
        await http.close()

    async def apply(self, operations: Sequence[Operation]) -> list[str]:
        http, api = await self._session()
        calls = self.calls(operations, api)
        log = []
        try:
            for call in calls:
                await http.request(call.method, f"{api}{call.path}", json=call.body)
                log.append(str(call))
            if calls:
                await http.request(
                    "PUT", f"{api}/fullconfigs/startup-config?from={api}/fullconfigs/running-config"
                )
                log.append("copy running-config startup-config")
        except HttpError as exc:
            raise WriteError(str(exc)) from exc
        finally:
            await self._logout(http, api)
        return log

    async def running_config(self) -> str:
        http, api = await self._session()
        try:
            config = await http.request("GET", f"{api}/fullconfigs/running-config")
            return (
                config if isinstance(config, str) else json.dumps(config, indent=2, sort_keys=True)
            )
        except HttpError as exc:
            raise WriteError(str(exc)) from exc
        finally:
            await self._logout(http, api)

    supports_restore = True

    async def restore(self, config: str) -> None:
        """Load the JSON running configuration of a backup and save it as startup config."""
        try:
            body = json.loads(config)
        except ValueError as exc:
            raise WriteError("This backup is not a JSON configuration") from exc
        http, api = await self._session()
        try:
            await http.request("PUT", f"{api}/fullconfigs/running-config", json=body)
            await http.request(
                "PUT", f"{api}/fullconfigs/startup-config?from={api}/fullconfigs/running-config"
            )
        except HttpError as exc:
            raise WriteError(str(exc)) from exc
        finally:
            await self._logout(http, api)

    async def run_show(self, command: str) -> str:
        try:
            return await ssh_show(self.host, self.credentials, command, ("no page",))
        except CliError as exc:
            raise WriteError(str(exc)) from exc

    async def push_ssh_keys(self, keys: Sequence[str]) -> int:
        http, api = await self._session()
        try:
            user = quote(self.credentials.api.username or "admin", safe="")
            await http.request(
                "PATCH", f"{api}/system/users/{user}", json={"authorized_keys": list(keys)}
            )
            await http.request(
                "PUT", f"{api}/fullconfigs/startup-config?from={api}/fullconfigs/running-config"
            )
        except HttpError as exc:
            raise WriteError(str(exc)) from exc
        finally:
            await self._logout(http, api)
        return len(keys)


class SimulatedWriter(ConfigWriter):
    """Development/demo: renders like the real writer but never touches the network."""

    def __init__(self, real: ConfigWriter, config: str = "") -> None:
        super().__init__(real.host, real.credentials)
        self._real = real
        self._config = config
        self.supports_ssh_keys = real.supports_ssh_keys  # type: ignore[misc]
        self.ssh_keys_own_only = real.ssh_keys_own_only  # type: ignore[misc]
        self.supports_restore = real.supports_restore  # type: ignore[misc]

    def render(self, operations: Sequence[Operation]) -> list[str]:
        return self._real.render(operations)

    async def apply(self, operations: Sequence[Operation]) -> list[str]:
        return [f"[simulated] {line}" for line in self.render(operations)]

    async def running_config(self) -> str:
        return self._config or f"! simulated configuration of {self.host}\n"

    async def push_ssh_keys(self, keys: Sequence[str]) -> int:
        return len(keys)

    async def restore(self, config: str) -> None:
        if not self._real.supports_restore:
            await self._real.restore(config)  # raises "not supported"

    async def run_show(self, command: str) -> str:
        if command.startswith("show run"):
            return await self.running_config()
        return f"[simulated] output of '{command}' on {self.host}\n"


# --- Read-only commands ("console") ----------------------------------------------------------


async def ssh_show(
    host: str, credentials: DeviceCredentials, command: str, setup: tuple[str, ...]
) -> str:
    cli = await SshCli.connect(host, credentials.ssh, setup=setup)
    try:
        return await cli.run(command, read_timeout=120)
    finally:
        await cli.close()
