"""Configuration changes as data.

Services compute a list of operations from "current" and "wanted" state; a writer renders
them for review (dry run) and applies them. This keeps the diff logic in one place.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SetPortDescription:
    port: str
    description: str


@dataclass(frozen=True)
class SetPortEnabled:
    port: str
    enabled: bool


@dataclass(frozen=True)
class SetPortVlans:
    """Wanted VLAN membership of a port, with the current one for add/remove style APIs."""

    port: str
    untagged: int | None
    tagged: frozenset[int]
    before_untagged: int | None = None
    before_tagged: frozenset[int] = frozenset()

    @property
    def added_tagged(self) -> list[int]:
        return sorted(self.tagged - self.before_tagged)

    @property
    def removed_tagged(self) -> list[int]:
        return sorted(self.before_tagged - self.tagged)


@dataclass(frozen=True)
class CreateVlan:
    vid: int
    name: str


@dataclass(frozen=True)
class RenameVlan:
    vid: int
    name: str


@dataclass(frozen=True)
class DeleteVlan:
    vid: int


Operation = (
    SetPortDescription | SetPortEnabled | SetPortVlans | CreateVlan | RenameVlan | DeleteVlan
)


@dataclass
class ChangePlan:
    """What would be sent to one switch."""

    device_id: int
    device_name: str
    operations: list[Operation]
    commands: list[str] = field(default_factory=list)  # rendered CLI lines / REST calls
    warnings: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.operations


def vlan_list(vids: frozenset[int] | set[int] | list[int]) -> str:
    """Compact VLAN list for CLIs: [1, 2, 3, 5] -> '1-3,5'."""
    ordered = sorted(set(vids))
    ranges: list[str] = []
    start = prev = None
    for vid in ordered:
        if start is None:
            start = prev = vid
        elif vid == prev + 1:  # type: ignore[operator]
            prev = vid
        else:
            ranges.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = vid
    if start is not None:
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(ranges)
