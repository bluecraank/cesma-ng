"""Record the SNMP data of a switch into an ``.snmprec`` file (raw input for test fixtures).

The output contains internal data and is never committed; see anonymize_snmprec.py.

Only reads (GETBULK), never writes. Example:

    python scripts/snmp_record.py 10.0.0.2 --name dell-n1548p --community public
    python scripts/snmp_record.py 10.0.0.3 --name hp-2530 --v3-user cesma \
        --auth-protocol SHA --auth-password ... --priv-protocol AES --priv-password ...

Output format, one line per value, sorted by OID:  ``<oid>|<type tag>|<value>``
(4 = string, 4x = hex string, 2 = integer, 6 = OID, 64 = IP, 65/66/67/70 = counter/gauge/ticks).
"""

import argparse
import asyncio
import string
import sys
import time
from pathlib import Path

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    bulk_walk_cmd,
    usmAesCfb128Protocol,
    usmAesCfb256Protocol,
    usmDESPrivProtocol,
    usmHMAC192SHA256AuthProtocol,
    usmHMACMD5AuthProtocol,
    usmHMACSHAAuthProtocol,
)

STANDARD_SUBTREES = {
    "system": "1.3.6.1.2.1.1",
    "interfaces (IF-MIB)": "1.3.6.1.2.1.2",
    "ipNetToMedia (ARP)": "1.3.6.1.2.1.4.22",
    "ipNetToPhysical (ARP)": "1.3.6.1.2.1.4.35",
    "EtherLike-MIB": "1.3.6.1.2.1.10.7",
    "BRIDGE/Q-BRIDGE (FDB, VLANs)": "1.3.6.1.2.1.17",
    "ifXTable (names, alias, 64-bit counters)": "1.3.6.1.2.1.31",
    "ENTITY-MIB (model, serial)": "1.3.6.1.2.1.47.1.1.1",
    "POWER-ETHERNET-MIB (PoE)": "1.3.6.1.2.1.105",
    "LLDP-MIB": "1.0.8802.1.1.2",
    # AOS-CX has no Q-BRIDGE VLAN tables (17.7.1.4); VLANs and PVIDs are only here
    "IEEE8021-BRIDGE (base ports)": "1.3.111.2.802.1.1.2",
    "IEEE8021-Q-BRIDGE (VLANs)": "1.3.111.2.802.1.1.4",
}
VENDOR_SUBTREES = {
    "Dell enterprise": "1.3.6.1.4.1.674",
    "Dell/Force10 enterprise": "1.3.6.1.4.1.6027",
    "HP enterprise": "1.3.6.1.4.1.11",
    "HPE Aruba enterprise (AOS-CX)": "1.3.6.1.4.1.47196",
}

AUTH = {
    "MD5": usmHMACMD5AuthProtocol,
    "SHA": usmHMACSHAAuthProtocol,
    "SHA256": usmHMAC192SHA256AuthProtocol,
}
PRIV = {"DES": usmDESPrivProtocol, "AES": usmAesCfb128Protocol, "AES256": usmAesCfb256Protocol}

TAGS = {
    "Integer": "2",
    "Integer32": "2",
    "OctetString": "4",
    "Bits": "4",
    "Null": "5",
    "ObjectIdentifier": "6",
    "IpAddress": "64",
    "Counter32": "65",
    "Gauge32": "66",
    "Unsigned32": "66",
    "TimeTicks": "67",
    "Opaque": "68",
    "Counter64": "70",
}
PRINTABLE = set(string.printable.encode()) - set(b"|\r\n\t\x0b\x0c")
# Exceptions in a response, not values: skipped on purpose.
NO_VALUE = {"NoSuchObject", "NoSuchInstance", "EndOfMibView"}


def oid_key(oid: str) -> tuple[int, ...]:
    return tuple(int(part) for part in oid.split("."))


def encode(value: object) -> tuple[str, str] | None:
    """Return (tag, value) in snmprec notation, ``None`` for noSuchObject/endOfMibView."""
    if type(value).__name__ in NO_VALUE:
        return None
    tag = next((TAGS[c.__name__] for c in type(value).__mro__ if c.__name__ in TAGS), None)
    if tag is None:
        # Never drop data silently: an unknown type means the recording is incomplete.
        raise TypeError(f"Unsupported SNMP value type {type(value).__name__}")
    if tag == "4":
        raw = value.asOctets()  # type: ignore[attr-defined]
        if all(b in PRINTABLE for b in raw):
            return "4", raw.decode()
        return "4x", raw.hex()
    if tag == "64":
        return tag, ".".join(str(b) for b in value.asOctets())  # type: ignore[attr-defined]
    if tag == "5":
        return tag, ""
    return tag, str(value.prettyPrint())  # type: ignore[attr-defined]


async def walk(engine, auth, target, root: str, rows: dict[str, tuple[str, str]]) -> int:  # type: ignore[no-untyped-def]
    count = 0
    prefix = oid_key(root)
    async for error, status, index, var_binds in bulk_walk_cmd(
        engine,
        auth,
        target,
        ContextData(),
        0,
        25,
        ObjectType(ObjectIdentity(root)),
        # lookupMib=False: raw protocol types. With MIB lookup, OID values of known MIBs
        # (e.g. sysObjectID) arrive as ObjectIdentity and would not be recorded.
        lexicographicMode=False,
        ignoreNonIncreasingOid=True,
        lookupMib=False,
    ):
        if error:
            raise RuntimeError(str(error))
        if status:
            raise RuntimeError(f"{status.prettyPrint()} at index {index}")
        for oid, value in var_binds:
            oid_str = str(oid)
            if oid_key(oid_str)[: len(prefix)] != prefix:
                return count
            encoded = encode(value)
            if encoded:
                rows[oid_str] = encoded
                count += 1
    return count


async def record(args: argparse.Namespace) -> None:
    if args.v3_user:
        auth = UsmUserData(
            args.v3_user,
            authKey=args.auth_password,
            privKey=args.priv_password,
            authProtocol=AUTH[args.auth_protocol],
            privProtocol=PRIV[args.priv_protocol],
        )
    else:
        auth = CommunityData(args.community, mpModel=1)  # v2c
    target = await UdpTransportTarget.create(
        (args.host, args.port), timeout=args.timeout, retries=args.retries
    )
    engine = SnmpEngine()

    subtrees = dict(STANDARD_SUBTREES)
    if not args.no_vendor:
        subtrees |= VENDOR_SUBTREES

    rows: dict[str, tuple[str, str]] = {}
    for label, root in subtrees.items():
        started = time.monotonic()
        print(f"  {label:45} {root:24}", end="", flush=True)
        try:
            count = await walk(engine, auth, target, root, rows)
            print(f"{count:7} values  {time.monotonic() - started:5.1f}s")
        except RuntimeError as exc:
            print(f"   FAILED: {exc}")
            if not rows:
                raise SystemExit("No answer - check IP, community/v3 user and SNMP ACL.") from exc
    engine.close_dispatcher()

    out = Path(args.out) / f"{args.name}.snmprec"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for oid in sorted(rows, key=oid_key):
            tag, value = rows[oid]
            fh.write(f"{oid}|{tag}|{value}\n")
    print(f"\n{len(rows)} values written to {out.resolve()}")
    print("Note: the file contains internal data (IPs, MACs, hostnames, port descriptions).")


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("host")
    p.add_argument("--name", required=True, help="file name, e.g. dell-n1548p")
    p.add_argument("--port", type=int, default=161)
    p.add_argument("--community", default="public")
    p.add_argument("--v3-user")
    p.add_argument("--auth-protocol", choices=sorted(AUTH), default="SHA")
    p.add_argument("--auth-password")
    p.add_argument("--priv-protocol", choices=sorted(PRIV), default="AES")
    p.add_argument("--priv-password")
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--no-vendor", action="store_true", help="skip the enterprise subtrees")
    # raw recordings contain internal data: keep them out of the source tree by default
    p.add_argument("--out", default="mitschnitte", help="folder (default: ./mitschnitte)")
    args = p.parse_args()
    print(f"Recording {args.host} ...")
    try:
        asyncio.run(record(args))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
