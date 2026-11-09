"""SNMP access behind a small interface, so readers can run against live switches or recordings.

Values are converted to plain Python types:
``int`` (integers, counters, gauges, timeticks), ``bytes`` (octet strings),
``str`` (OIDs and IP addresses) or ``None`` (NULL).
"""

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

from app.domain.credentials import SnmpCredentials

Oid = tuple[int, ...]
SnmpValue = int | bytes | str | None


class SnmpError(Exception):
    """Timeout, authentication failure or protocol error."""


def parse_oid(oid: str) -> Oid:
    return tuple(int(part) for part in oid.strip(".").split("."))


def format_oid(oid: Oid) -> str:
    return ".".join(map(str, oid))


class SnmpClient(Protocol):
    async def get(self, oids: Iterable[str]) -> dict[Oid, SnmpValue]:
        """Values of single objects; missing objects are left out."""
        ...

    async def walk(self, oid: str) -> dict[Oid, SnmpValue]:
        """All objects below ``oid``, keyed by full OID."""
        ...


def column(rows: Mapping[Oid, SnmpValue], base: str) -> dict[Oid, SnmpValue]:
    """Strip the column OID from walked rows, leaving the table index as key."""
    prefix = parse_oid(base)
    n = len(prefix)
    return {oid[n:]: value for oid, value in rows.items() if oid[:n] == prefix}


# --- Recorded data (tests, simulator) ----------------------------------------------------------

_SNMPREC_INT_TAGS = {"2", "65", "66", "67", "70"}


def _decode_snmprec(tag: str, value: str) -> SnmpValue:
    if tag in _SNMPREC_INT_TAGS:
        return int(value)
    if tag == "4":
        return value.encode()
    if tag == "4x":
        return bytes.fromhex(value)
    if tag in ("6", "64"):
        return value
    if tag == "5":
        return None
    raise ValueError(f"Unsupported snmprec tag {tag!r}")


def load_snmprec(path: Path) -> dict[Oid, SnmpValue]:
    rows: dict[Oid, SnmpValue] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line := line.rstrip("\n"):
                oid, tag, value = line.split("|", 2)
                rows[parse_oid(oid)] = _decode_snmprec(tag, value)
    return rows


class RecordedSnmpClient:
    """Answers from a recording (``.snmprec``) instead of a live device."""

    def __init__(self, rows: Mapping[Oid, SnmpValue]) -> None:
        self._rows = dict(sorted(rows.items()))

    @classmethod
    def from_file(cls, path: Path) -> "RecordedSnmpClient":
        return cls(load_snmprec(path))

    async def get(self, oids: Iterable[str]) -> dict[Oid, SnmpValue]:
        return {o: self._rows[o] for o in map(parse_oid, oids) if o in self._rows}

    async def walk(self, oid: str) -> dict[Oid, SnmpValue]:
        prefix = parse_oid(oid)
        n = len(prefix)
        return {o: v for o, v in self._rows.items() if o[:n] == prefix}


# --- Live access via pysnmp --------------------------------------------------------------------


class PysnmpClient:
    """SNMP v2c/v3 client (GET and GETBULK walks)."""

    def __init__(
        self,
        host: str,
        credentials: SnmpCredentials,
        *,
        port: int = 161,
        timeout: float = 3.0,
        retries: int = 1,
        max_repetitions: int = 25,
    ) -> None:
        self._host = host
        self._port = port
        self._credentials = credentials
        self._timeout = timeout
        self._retries = retries
        self._max_repetitions = max_repetitions

    def _auth(self) -> Any:
        from pysnmp.hlapi.v3arch.asyncio import CommunityData, UsmUserData

        c = self._credentials
        if c.version == "v3":
            from pysnmp.hlapi.v3arch import asyncio as hl

            auth = {
                None: hl.usmNoAuthProtocol,
                "MD5": hl.usmHMACMD5AuthProtocol,
                "SHA": hl.usmHMACSHAAuthProtocol,
                "SHA256": hl.usmHMAC192SHA256AuthProtocol,
                "SHA512": hl.usmHMAC384SHA512AuthProtocol,
            }
            priv = {
                None: hl.usmNoPrivProtocol,
                "DES": hl.usmDESPrivProtocol,
                "AES": hl.usmAesCfb128Protocol,
                "AES256": hl.usmAesCfb256Protocol,
            }
            return UsmUserData(
                c.v3_username or "",
                authKey=c.v3_auth_password,
                privKey=c.v3_priv_password,
                authProtocol=auth[(c.v3_auth_protocol or "").upper() or None],
                privProtocol=priv[(c.v3_priv_protocol or "").upper() or None],
            )
        return CommunityData(c.community, mpModel=1)

    async def _target(self) -> Any:
        from pysnmp.hlapi.v3arch.asyncio import UdpTransportTarget

        return await UdpTransportTarget.create(
            (self._host, self._port), timeout=self._timeout, retries=self._retries
        )

    async def get(self, oids: Iterable[str]) -> dict[Oid, SnmpValue]:
        from pysnmp.hlapi.v3arch.asyncio import (
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            get_cmd,
        )

        engine = SnmpEngine()
        try:
            error, status, _, var_binds = await get_cmd(
                engine,
                self._auth(),
                await self._target(),
                ContextData(),
                *(ObjectType(ObjectIdentity(o)) for o in oids),
                lookupMib=False,
            )
            if error:
                raise SnmpError(f"{self._host}: {error}")
            if status:
                raise SnmpError(f"{self._host}: {status.prettyPrint()}")
            return {
                parse_oid(str(oid)): _convert(value)
                for oid, value in var_binds
                if not _is_exception(value)
            }
        finally:
            engine.close_dispatcher()

    async def walk(self, oid: str) -> dict[Oid, SnmpValue]:
        from pysnmp.hlapi.v3arch.asyncio import (
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            bulk_walk_cmd,
        )

        prefix = parse_oid(oid)
        n = len(prefix)
        rows: dict[Oid, SnmpValue] = {}
        engine = SnmpEngine()
        try:
            async for error, status, _, var_binds in bulk_walk_cmd(
                engine,
                self._auth(),
                await self._target(),
                ContextData(),
                0,
                self._max_repetitions,
                ObjectType(ObjectIdentity(oid)),
                lexicographicMode=False,
                ignoreNonIncreasingOid=True,
                lookupMib=False,
            ):
                if error:
                    raise SnmpError(f"{self._host}: {error}")
                if status:
                    raise SnmpError(f"{self._host}: {status.prettyPrint()}")
                for name, value in var_binds:
                    key = parse_oid(str(name))
                    if key[:n] != prefix:
                        return rows
                    if not _is_exception(value):
                        rows[key] = _convert(value)
            return rows
        finally:
            engine.close_dispatcher()


_EXCEPTIONS = {"NoSuchObject", "NoSuchInstance", "EndOfMibView"}
_INT_TYPES = {
    "Integer",
    "Integer32",
    "Counter32",
    "Gauge32",
    "Unsigned32",
    "TimeTicks",
    "Counter64",
}


def _type_names(value: object) -> set[str]:
    return {cls.__name__ for cls in type(value).__mro__}


def _is_exception(value: object) -> bool:
    """noSuchObject / noSuchInstance / endOfMibView: markers, not values."""
    return bool(_type_names(value) & _EXCEPTIONS)


def _convert(value: Any) -> SnmpValue:
    names = _type_names(value)
    if names & _INT_TYPES:
        return int(value)
    if "IpAddress" in names:
        return ".".join(str(b) for b in value.asOctets())
    if "OctetString" in names:
        return bytes(value.asOctets())
    if "ObjectIdentifier" in names:
        return str(value)
    if "Null" in names:
        return None
    raise SnmpError(f"Unsupported SNMP value type {type(value).__name__}")
