"""Turn real switch recordings into small, anonymised test fixtures.

    python scripts/anonymize_snmprec.py ../mitschnitte/*.snmprec --out tests/fixtures/snmp

Keeps only the columns Cesma reads and replaces, consistently across all input files:
MAC addresses (vendor prefix kept), IPv4 addresses (/24 structure kept), host and system
names, port descriptions, VLAN names and serial numbers. MACs and IPs are also replaced
where they are part of a table index (forwarding database, ARP, LLDP management address).
The salt is random per run, so the mapping cannot be reproduced from the fixtures.
"""

import argparse
import hashlib
import os
import string
from collections.abc import Callable
from pathlib import Path

Oid = tuple[int, ...]

# Columns that are kept (prefix match). Counters, vendor trees etc. are dropped.
KEEP = [
    "1.3.6.1.2.1.1.1",
    "1.3.6.1.2.1.1.2",
    "1.3.6.1.2.1.1.3",
    "1.3.6.1.2.1.1.5",
    # IF-MIB incl. error counters (14, 20) and 32 bit octets (10, 16)
    *(f"1.3.6.1.2.1.2.2.1.{c}" for c in (1, 2, 3, 5, 6, 7, 8, 10, 14, 16, 20)),
    # ifXTable incl. 64 bit octet counters (6, 10)
    *(f"1.3.6.1.2.1.31.1.1.1.{c}" for c in (1, 6, 10, 15, 18)),
    "1.3.6.1.2.1.17.1.1",
    "1.3.6.1.2.1.17.1.4.1.2",
    "1.3.6.1.2.1.17.4.3.1.2",
    "1.3.6.1.2.1.17.4.3.1.3",
    "1.3.6.1.2.1.17.7.1.2.2.1.2",
    "1.3.6.1.2.1.17.7.1.2.2.1.3",
    *(f"1.3.6.1.2.1.17.7.1.4.2.1.{c}" for c in (3, 4, 5)),
    *(f"1.3.6.1.2.1.17.7.1.4.3.1.{c}" for c in (1, 2, 4)),
    "1.3.6.1.2.1.17.7.1.4.5.1.1",
    *(f"1.3.6.1.2.1.47.1.1.1.1.{c}" for c in (2, 4, 5, 7, 10, 11, 13)),
    *(f"1.3.6.1.2.1.105.1.1.1.{c}" for c in (3, 6, 10)),
    *(f"1.3.6.1.2.1.105.1.3.1.1.{c}" for c in (2, 4, 5)),
    "1.0.8802.1.1.2.1.3.1",
    "1.0.8802.1.1.2.1.3.2",
    "1.0.8802.1.1.2.1.3.3",
    *(f"1.0.8802.1.1.2.1.3.7.1.{c}" for c in (2, 3, 4)),
    *(f"1.0.8802.1.1.2.1.4.1.1.{c}" for c in range(4, 13)),
    "1.0.8802.1.1.2.1.4.2.1.3",
    "1.3.6.1.2.1.4.22.1.2",
    "1.3.6.1.2.1.4.35.1.4",
]
KEEP_OIDS = [tuple(map(int, p.split("."))) for p in KEEP]
PRINTABLE = set(string.printable.encode()) - set(b"|\r\n\t\x0b\x0c")
SALT = os.urandom(16)


def oid(text: str) -> Oid:
    return tuple(int(p) for p in text.split("."))


class Pseudonyms:
    def __init__(self) -> None:
        self.names: dict[str, str] = {}
        self.nets: dict[tuple[int, int, int], tuple[int, int]] = {}

    def mac(self, raw: bytes) -> bytes:
        if len(raw) != 6 or raw == bytes(6):
            return raw
        digest = hashlib.sha256(SALT + raw).digest()
        return raw[:3] + digest[:3]

    def ip(self, octets: tuple[int, ...]) -> tuple[int, ...]:
        if len(octets) != 4 or octets[0] in (0, 127, 224, 255):
            return octets
        net = self.nets.setdefault(octets[:3], divmod(len(self.nets) + 1, 256))
        return (10, *net, octets[3])

    def name(self, value: str, kind: str) -> str:
        if not value.strip():
            return value
        key = f"{kind}:{value}"
        if key not in self.names:
            self.names[key] = f"{kind}-{sum(k.startswith(kind + ':') for k in self.names) + 1}"
        return self.names[key]


def starts(o: Oid, prefix: str) -> bool:
    p = oid(prefix)
    return o[: len(p)] == p


def decode(tag: str, value: str) -> bytes | str:
    if tag == "4":
        return value.encode()
    if tag == "4x":
        return bytes.fromhex(value)
    return value


def encode(tag: str, value: bytes | str) -> tuple[str, str]:
    if isinstance(value, bytes):
        return ("4", value.decode()) if all(b in PRINTABLE for b in value) else ("4x", value.hex())
    return tag, value


def transform(
    o: Oid, tag: str, value: bytes | str, ps: Pseudonyms, lldp_subtypes: dict[Oid, int]
) -> tuple[Oid, bytes | str]:
    def tail_mac(n: int = 6) -> Oid:  # MAC in the last 6 index components
        return o[:-n] + tuple(ps.mac(bytes(o[-n:])))

    def text(fn: Callable[[str], str]) -> bytes | str:
        return fn(value.decode(errors="replace")).encode() if isinstance(value, bytes) else value

    # Values that are MAC addresses
    if any(
        starts(o, p)
        for p in (
            "1.3.6.1.2.1.2.2.1.6",
            "1.3.6.1.2.1.17.1.1",
            "1.3.6.1.2.1.4.22.1.2",
            "1.3.6.1.2.1.4.35.1.4",
            "1.0.8802.1.1.2.1.3.2",
        )
    ) and isinstance(value, bytes):
        value = ps.mac(value)
    # Forwarding database: MAC is part of the index
    if starts(o, "1.3.6.1.2.1.17.7.1.2.2.1") or starts(o, "1.3.6.1.2.1.17.4.3.1"):
        o = tail_mac()
    # ARP: IPv4 in the index
    if starts(o, "1.3.6.1.2.1.4.22.1") and len(o) >= 4:
        o = o[:-4] + ps.ip(o[-4:])
    if starts(o, "1.3.6.1.2.1.4.35.1") and len(o) >= 7 and o[-6:-4] == (1, 4):
        o = o[:-4] + ps.ip(o[-4:])
    # LLDP management address in the index (..., subtype 1 = IPv4, length 4, a.b.c.d)
    if starts(o, "1.0.8802.1.1.2.1.4.2.1") and o[-6:-4] == (1, 4):
        o = o[:-4] + ps.ip(o[-4:])

    # Names and free text
    if starts(o, "1.3.6.1.2.1.1.5") or starts(o, "1.0.8802.1.1.2.1.3.3"):
        value = text(lambda v: ps.name(v, "switch"))
    elif starts(o, "1.3.6.1.2.1.31.1.1.1.18"):
        value = text(lambda v: f"desc-{o[-1]}" if v.strip() else v)
    elif starts(o, "1.3.6.1.2.1.17.7.1.4.3.1.1"):
        value = text(
            lambda v: (
                v
                if v.lower() in ("default", "default_vlan", f"vlan{o[-1]}", f"vlan{o[-1]:04d}")
                else f"VLAN-{o[-1]}"
            )
        )
    elif starts(o, "1.3.6.1.2.1.47.1.1.1.1.11"):
        value = text(lambda v: f"SERIAL{o[-1]}" if v.strip() else v)
    elif starts(o, "1.0.8802.1.1.2.1.4.1.1.9"):
        value = text(lambda v: ps.name(v, "neighbor"))
    elif starts(o, "1.0.8802.1.1.2.1.4.1.1.4"):
        lldp_subtypes[("chassis", *o[-3:])] = int(value)  # type: ignore[arg-type]
    elif starts(o, "1.0.8802.1.1.2.1.4.1.1.6"):
        lldp_subtypes[("port", *o[-3:])] = int(value)  # type: ignore[arg-type]
    elif starts(o, "1.0.8802.1.1.2.1.4.1.1.5") and isinstance(value, bytes):
        subtype = lldp_subtypes.get(("chassis", *o[-3:]))  # type: ignore[arg-type]
        if subtype == 4:
            value = ps.mac(value)
        elif subtype == 5 and len(value) == 5 and value[0] == 1:
            value = b"\x01" + bytes(ps.ip(tuple(value[1:])))
        elif subtype == 7:
            value = text(lambda v: ps.name(v, "neighbor"))
    elif (
        starts(o, "1.0.8802.1.1.2.1.4.1.1.7")
        and isinstance(value, bytes)
        and lldp_subtypes.get(("port", *o[-3:])) == 3  # type: ignore[arg-type]
    ):
        value = ps.mac(value)
    return o, value


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    ps = Pseudonyms()

    for path in args.files:
        rows: list[tuple[Oid, str, str]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            text_oid, tag, value = line.split("|", 2)
            rows.append((oid(text_oid), tag, value))
        rows.sort()  # subtype columns (4, 6) come before the values (5, 7)
        lldp_subtypes: dict[Oid, int] = {}
        result: dict[Oid, tuple[str, str]] = {}
        for o, tag, value in rows:
            if not any(o[: len(k)] == k for k in KEEP_OIDS):
                continue
            new_oid, new_value = transform(o, tag, decode(tag, value), ps, lldp_subtypes)
            result[new_oid] = encode(tag, new_value)
        target = args.out / path.name
        with target.open("w", encoding="utf-8", newline="\n") as fh:
            for o in sorted(result):
                t, v = result[o]
                fh.write(f"{'.'.join(map(str, o))}|{t}|{v}\n")
        print(
            f"{path.name}: {len(rows)} -> {len(result)} values, {target.stat().st_size // 1024} KiB"
        )


if __name__ == "__main__":
    main()
