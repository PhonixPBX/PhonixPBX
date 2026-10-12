"""Bring older ``config.xml`` versions up to 2.1 (port of ``convert_config()``).

Only the steps relevant for the subset NG imports are ported:

* 2.0  -> 2.01: e-mail ``tls=yes`` becomes ``enctype=tls``
* 2.01 -> 2.02: timezone stored as ``id|posix|name`` becomes just ``id``
* 2.02 -> 2.1:  version 1 applications (``app-command[]`` lines) and the
  separately stored ``application2[]`` merge into ``dialplan/application[]``;
  the legacy upgrade also added the voicemail, call forwarding and weasels
  applications, which NG provides as built-ins.

Besides version upgrades, :func:`normalize` fixes structural quirks seen in
real files (e.g. ``<application>`` elements outside ``<dialplan>`` in the
alvispbx factory config).
"""

from __future__ import annotations

import base64
from decimal import Decimal, InvalidOperation
from typing import Any

from askozia.legacy.parse import LegacyConfig, decode_b64
from askozia.legacy.report import ImportReport

LATEST = "2.1"

# applications added by the 2.02 -> 2.1 legacy upgrade (extension -> name)
UPGRADE_ADDED_APPLICATIONS = {
    "000086": ("Voicemail system", "0000VM", "DIALPLAN-APPLICATION-7643526674dde509b64232"),
    "000023": ("Call Forwarding", "0000CF", "DIALPLAN-APPLICATION-14778225794decb30253418"),
    "00009327357": ("Weasels", "0000WEASELS", "DIALPLAN-APPLICATION-13903502574df9cf4ca35a0"),
}

# marker key: create NG's built-in application for this extension
BUILTIN_MARKER = "_ng_builtin"


class UnsupportedVersion(ValueError):
    pass


def parse_version(value: str) -> Decimal:
    try:
        version = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        raise UnsupportedVersion(f"Unrecognised config version {value!r}") from None
    if not version.is_finite() or version <= 0:
        raise UnsupportedVersion(f"Unrecognised config version {value!r}")
    return version


def upgrade(cfg: LegacyConfig, report: ImportReport) -> None:
    """Upgrade ``cfg`` in place to version 2.1. Raises :class:`UnsupportedVersion`."""
    data = cfg.data
    if not cfg.version:
        report.warning("file", "version", f"No <version> element, assuming {LATEST}")
        cfg.version = LATEST
    version = parse_version(cfg.version)
    latest = Decimal(LATEST)
    if version > latest:
        raise UnsupportedVersion(f"config.xml version {cfg.version} is newer than the supported version {LATEST}")
    if version == latest:
        return
    if version < Decimal("2.0"):
        report.warning(
            "file",
            "version",
            f"Version {cfg.version} predates 2.0; it is upgraded like a 2.0 file, please review the result carefully",
        )
    report.info("file", "version", f"Upgrading configuration from version {cfg.version} to {LATEST}")

    if version < Decimal("2.01"):
        notifications = data.get("notifications")
        email = notifications.get("email") if isinstance(notifications, dict) else None
        if isinstance(email, dict) and str(email.get("tls", "")).strip().lower() == "yes":
            email["enctype"] = "tls"
            email.pop("tls", None)

    if version < Decimal("2.02"):
        system = data.get("system")
        if isinstance(system, dict) and isinstance(system.get("timezone"), str):
            system["timezone"] = system["timezone"].split("|", 1)[0].strip()

    if version < Decimal("2.1"):
        _upgrade_applications(data, report)

    data["version"] = LATEST
    cfg.version = LATEST


def _upgrade_applications(data: dict[str, Any], report: ImportReport) -> None:
    dialplan = data.get("dialplan")
    if not isinstance(dialplan, dict):
        dialplan = data["dialplan"] = {}
    v2 = [a for a in dialplan.pop("application2", []) or [] if isinstance(a, dict)]
    converted: list[dict[str, Any]] = []
    for app in dialplan.get("application", []) or []:
        if not isinstance(app, dict):
            continue
        if "app-command" not in app:
            converted.append(app)
            continue
        lines = []
        for raw in app.get("app-command") or []:
            if not isinstance(raw, str) or not raw.strip():
                continue
            line = decode_b64(raw)
            if line is None:
                report.warning("applications", app.get("name", ""), "Undecodable application line dropped")
                continue
            lines.append(line)
        new = {k: v for k, v in app.items() if k != "app-command"}
        new["type"] = "plaintext"
        new["applicationlogic"] = base64.b64encode("\n".join(lines).encode()).decode()
        # the legacy upgrade assigned a new uniqid and rewrote all references;
        # keeping the old one is equivalent and keeps references valid
        converted.append(new)
    apps = v2 + converted
    existing = {a.get("extension") for a in apps}
    for ext, (name, descr, uniqid) in UPGRADE_ADDED_APPLICATIONS.items():
        if ext not in existing:
            apps.append(
                {
                    "name": name,
                    "descr": descr,
                    "extension": ext,
                    "uniqid": uniqid,
                    "type": "plaintext",
                    BUILTIN_MARKER: True,
                }
            )
    dialplan["application"] = apps


def normalize(cfg: LegacyConfig, report: ImportReport) -> None:
    """Repair structural oddities so the mapping code sees the 2.1 layout."""
    data = cfg.data
    stray = data.pop("application", None)
    if stray:
        apps = [a for a in (stray if isinstance(stray, list) else [stray]) if isinstance(a, dict)]
        dialplan = data.get("dialplan")
        if not isinstance(dialplan, dict):
            dialplan = data["dialplan"] = {}
        current = dialplan.get("application")
        if not isinstance(current, list):
            current = dialplan["application"] = []
        current.extend(apps)
        report.info(
            "applications",
            "",
            f"{len(apps)} <application> element(s) found outside <dialplan>, imported as dialplan applications",
        )
    for note in cfg.warnings:
        report.warning("file", "", note)
