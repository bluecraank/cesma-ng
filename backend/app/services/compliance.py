"""Configuration rules: every switch's latest backup is checked against them."""

import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import SecretBox
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import (
    Backup,
    BackupStatus,
    ComplianceMode,
    ComplianceRule,
    Device,
    DeviceModel,
    DeviceStatus,
    Permission,
)
from app.services import audit
from app.services.access import has_permission, require_site_access, require_superadmin
from app.services.context import Caller

MAX_LINE = 200  # matched lines are cut to this length in the result


def compile_pattern(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    except re.error as exc:
        raise ValidationFailedError(f"Invalid regular expression: {exc}") from exc


def check(rule: ComplianceRule, config: str) -> tuple[bool, list[str]]:
    """(passed, matching lines). REQUIRE passes with a match, FORBID without one."""
    lines = [m.group(0).strip()[:MAX_LINE] for m in _line_matches(rule.pattern, config)]
    passed = bool(lines) if rule.mode is ComplianceMode.REQUIRE else not lines
    return passed, lines[:5]


def _line_matches(pattern: str, config: str) -> list[re.Match[str]]:
    # Match whole lines so the result shows the offending line, not only the fragment.
    regex = compile_pattern(rf"^.*(?:{pattern}).*$")
    return list(regex.finditer(config))


# --- Rules (super administrators) -------------------------------------------------------------


async def list_rules(db: AsyncSession, caller: Caller) -> Sequence[ComplianceRule]:
    return (await db.execute(select(ComplianceRule).order_by(ComplianceRule.name))).scalars().all()


async def save_rule(
    db: AsyncSession, caller: Caller, values: dict[str, Any], rule_id: int | None = None
) -> ComplianceRule:
    require_superadmin(caller.user)
    compile_pattern(values["pattern"])
    rule = await db.get(ComplianceRule, rule_id) if rule_id else ComplianceRule()
    if rule is None:
        raise NotFoundError("Rule not found")
    rule.name = values["name"].strip()
    rule.description = values.get("description", "")
    rule.mode = ComplianceMode(values["mode"])
    rule.pattern = values["pattern"]
    rule.models = [DeviceModel(m).value for m in values.get("models", [])]
    rule.enabled = values.get("enabled", True)
    if rule_id is None:
        db.add(rule)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("A rule with this name already exists") from exc
    await audit.record(db, caller.actor, "compliance.save", f"Configuration rule {rule.name} saved")
    return rule


async def delete_rule(db: AsyncSession, caller: Caller, rule_id: int) -> None:
    require_superadmin(caller.user)
    rule = await db.get(ComplianceRule, rule_id)
    if rule is None:
        raise NotFoundError("Rule not found")
    await db.delete(rule)
    await audit.record(
        db, caller.actor, "compliance.delete", f"Configuration rule {rule.name} deleted"
    )


# --- Evaluation ------------------------------------------------------------------------------


async def site_compliance(
    db: AsyncSession, caller: Caller, box: SecretBox, site_id: int
) -> dict[str, Any]:
    """Result per switch and rule, from the latest successful backup of each switch.

    The matching lines come from the configuration, so only users who may read backups
    get them.
    """
    require_site_access(caller.user, site_id)
    show_lines = has_permission(caller.user, site_id, Permission.BACKUPS_READ)
    rules = [r for r in await list_rules(db, caller) if r.enabled]
    latest = (
        select(Backup.device_id, func.max(Backup.created_at).label("at"))
        .where(Backup.status == BackupStatus.OK)
        .group_by(Backup.device_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(Device, Backup)
            .outerjoin(latest, latest.c.device_id == Device.id)
            .outerjoin(Backup, (Backup.device_id == Device.id) & (Backup.created_at == latest.c.at))
            .where(Device.site_id == site_id, Device.status != DeviceStatus.UNCONFIRMED)
            .order_by(Device.name)
        )
    ).tuples()
    devices: list[dict[str, Any]] = []
    for device, backup in rows:
        results: list[dict[str, Any]] = []
        config = (
            box.decrypt(backup.config_encrypted) if backup and backup.config_encrypted else None
        )
        for rule in rules:
            if rule.models and device.model.value not in rule.models:
                continue
            if config is None:
                results.append({"rule_id": rule.id, "passed": None, "lines": []})
                continue
            passed, lines = check(rule, config)
            results.append(
                {"rule_id": rule.id, "passed": passed, "lines": lines if show_lines else []}
            )
        devices.append(
            {
                "device_id": device.id,
                "device_name": device.name,
                "backup_at": backup.created_at if backup else None,
                "results": results,
            }
        )
    return {"rules": rules, "devices": devices}
