"""Interactive switch CLI over SSH, behind a small interface (tests use a fake).

Handles prompts, pagers ("--More--"), y/n confirmations and enable mode.
"""

import asyncio
import re
from typing import Any, Protocol

from app.domain.credentials import LoginCredentials

#: "switch#", "switch(config-if)#", "switch>" and the like
DEFAULT_PROMPT = re.compile(r"(?m)^[\w.\-/:()@]+(\(config[^)]*\))?[#>]\s*$")
_PAGER = re.compile(r"--\s*More\s*--|<--- More --->|Press any key to continue", re.IGNORECASE)
_CONFIRM = re.compile(r"\(y/n\)\s*\??\s*$|\[y/n\]\s*\??\s*$|\(yes/no\)\s*\??\s*$", re.IGNORECASE)
_PASSWORD = re.compile(r"[Pp]assword:\s*$")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[=>]|\r")


class CliError(Exception):
    """Connection, authentication or command failure."""


class Cli(Protocol):
    async def run(self, command: str, read_timeout: float = 30) -> str:
        """Send one command and return its output (without echo and prompt)."""
        ...

    async def close(self) -> None: ...


def clean(text: str) -> str:
    return _ANSI.sub("", text)


class SshCli:
    """A real SSH shell session (asyncssh)."""

    def __init__(self, process, prompt: re.Pattern[str]) -> None:  # type: ignore[no-untyped-def]
        self._process = process
        self._prompt = prompt
        self._conn: Any = None

    @classmethod
    async def connect(
        cls,
        host: str,
        credentials: LoginCredentials,
        *,
        prompt: re.Pattern[str] = DEFAULT_PROMPT,
        connect_timeout: float = 15,
        setup: tuple[str, ...] = (),
    ) -> "SshCli":
        import asyncssh

        keys = (
            [asyncssh.import_private_key(credentials.private_key)]
            if credentials.private_key
            else None
        )
        try:
            conn = await asyncio.wait_for(
                asyncssh.connect(
                    host,
                    username=credentials.username,
                    password=credentials.password,
                    client_keys=keys,
                    known_hosts=None,  # switches are identified by address; see README
                    preferred_auth="publickey,keyboard-interactive,password",
                ),
                connect_timeout,
            )
            process = await conn.create_process(term_type="vt100", term_size=(200, 1000))
        except (OSError, asyncssh.Error, TimeoutError) as exc:
            raise CliError(f"SSH to {host} failed: {exc}") from exc
        cli = cls(process, prompt)
        cli._conn = conn
        await cli._read_until_prompt(
            read_timeout=connect_timeout, answer_password=credentials.password
        )
        if credentials.enable_password is not None or "enable" in setup:
            await cli._enable(credentials.enable_password)
        for command in setup:
            if command != "enable":
                await cli.run(command)
        return cli

    async def _enable(self, password: str | None) -> None:
        self._process.stdin.write("enable\n")
        await self._read_until_prompt(answer_password=password or "")

    async def _read_until_prompt(
        self, read_timeout: float = 30, answer_password: str | None = None
    ) -> str:
        buffer = ""
        try:
            async with asyncio.timeout(read_timeout):
                while True:
                    chunk = await self._process.stdout.read(4096)
                    if not chunk:
                        raise CliError("Connection closed by switch")
                    buffer += clean(chunk)
                    tail = buffer[-200:]
                    if _PAGER.search(tail):
                        buffer = _PAGER.sub("", buffer)
                        self._process.stdin.write(" ")
                    elif _CONFIRM.search(tail):
                        self._process.stdin.write("y\n")
                    elif answer_password is not None and _PASSWORD.search(tail):
                        self._process.stdin.write(answer_password + "\n")
                        answer_password = None
                    elif self._prompt.search(tail):
                        return buffer
        except TimeoutError as exc:
            raise CliError(
                f"No prompt after {read_timeout}s; last output: {buffer[-200:]!r}"
            ) from exc

    async def run(self, command: str, read_timeout: float = 30) -> str:
        self._process.stdin.write(command + "\n")
        output = await self._read_until_prompt(read_timeout)
        lines = output.split("\n")
        if lines and command.strip() and lines[0].strip().endswith(command.strip()):
            lines = lines[1:]  # echo
        if lines and self._prompt.search(lines[-1]):
            lines = lines[:-1]  # prompt
        return "\n".join(lines).strip("\n")

    async def close(self) -> None:
        try:
            self._process.stdin.write("exit\n")
            self._process.close()
        finally:
            if self._conn is not None:
                self._conn.close()


class FakeCli:
    """Test double: records commands, answers from a dict (default: empty output)."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = responses or {}
        self.commands: list[str] = []
        self.closed = False

    async def run(self, command: str, read_timeout: float = 30) -> str:
        self.commands.append(command)
        return self.responses.get(command, "")

    async def close(self) -> None:
        self.closed = True
