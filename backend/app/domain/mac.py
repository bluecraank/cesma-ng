"""MAC address normalisation. Canonical form everywhere: lower case, colon separated."""

import re

_NON_HEX = re.compile(r"[^0-9a-fA-F]")


def normalize_mac(value: str) -> str | None:
    """'AABB.CCDD.EEFF', 'aa-bb-cc-dd-ee-ff', ... -> 'aa:bb:cc:dd:ee:ff' (None if invalid)."""
    digits = _NON_HEX.sub("", value).lower()
    if len(digits) != 12 or len(value) > 17:
        return None
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))


def normalize_prefix(value: str) -> str | None:
    """A MAC prefix of 1 to 6 whole bytes in canonical form, e.g. '000B82' -> '00:0b:82'."""
    digits = _NON_HEX.sub("", value).lower()
    if not digits or len(digits) % 2 or len(digits) > 12:
        return None
    return ":".join(digits[i : i + 2] for i in range(0, len(digits), 2))


def mac_search_fragment(query: str) -> str | None:
    """Turn a typed MAC fragment into a LIKE fragment for canonical MACs.

    Only for queries that look like a MAC (hex with optional separators, >= 4 digits).
    The fragment may start mid-byte, so it is matched against both alignments by the caller.
    """
    stripped = query.strip()
    if not re.fullmatch(r"[0-9a-fA-F:.\-]{4,17}", stripped):
        return None
    digits = _NON_HEX.sub("", stripped).lower()
    if len(digits) < 4:
        return None
    if re.search(r"[:.\-]", stripped):
        # separators given: keep the user's byte alignment
        return ":".join(digits[i : i + 2] for i in range(0, len(digits), 2))
    return digits


def mac_like_patterns(query: str) -> list[str]:
    """SQL LIKE patterns that find canonical MACs containing the typed fragment."""
    fragment = mac_search_fragment(query)
    if fragment is None:
        return []
    if ":" in fragment:
        return [f"%{fragment}%"]
    # no separators: the fragment can start at an even or odd hex digit
    even = ":".join(fragment[i : i + 2] for i in range(0, len(fragment), 2))
    odd = fragment[0] + ":" + ":".join(fragment[i : i + 2] for i in range(1, len(fragment), 2))
    return [f"%{even}%", f"%{odd.rstrip(':')}%"]


def vendor_prefix(mac: str) -> str:
    return mac[:8]
