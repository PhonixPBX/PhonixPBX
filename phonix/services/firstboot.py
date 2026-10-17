# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""First boot initialisation of the data partition (idempotent)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from phonix import config
from phonix.core import settings as st
from phonix.core.db import session_scope
from phonix.services import secrets, setup, tls, users

log = logging.getLogger(__name__)

PASSWORD_FILE = "initial-admin-password"  # noqa: S105 - a file name


@dataclass
class FirstbootResult:
    admin_password: str | None = None
    certificate_created: bool = False
    legacy_import: str | None = None
    messages: list[str] = field(default_factory=list)


def legacy_config_candidates() -> list[Path]:
    boot = config.get().boot_dir
    return [boot / "config.xml", boot / "conf" / "config.xml"]


# report of the config.xml imported at first boot, shown on the dashboard until dismissed
LEGACY_REPORT = "legacy-import-report.json"


def legacy_import_report() -> dict[str, Any] | None:
    try:
        data = json.loads((config.get().state_dir / LEGACY_REPORT).read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def dismiss_legacy_import_report() -> None:
    (config.get().state_dir / LEGACY_REPORT).unlink(missing_ok=True)


def run() -> FirstbootResult:
    cfg = config.get()
    result = FirstbootResult()
    for sub in ("", "media/moh", "media/vm_greeting", "media/prompt", "backups", "state", "asterisk", "tls"):
        (cfg.data_dir / sub).mkdir(parents=True, exist_ok=True)
    secrets.load()
    setup.initialize()

    for candidate in legacy_config_candidates():
        if candidate.is_file():
            try:
                from phonix.legacy import importer

                report = importer.import_file(candidate, mode="replace", user="firstboot")
                result.legacy_import = str(candidate)
                (cfg.state_dir / LEGACY_REPORT).write_text(report.to_json())
                candidate.rename(candidate.with_name("config.xml.imported"))
                result.messages.append(f"imported legacy configuration {candidate}")
            except Exception as exc:  # report but never block booting
                log.exception("legacy import failed")
                result.messages.append(f"legacy import of {candidate} failed: {exc}")
            break

    with session_scope() as session:
        password = users.ensure_admin(session)
        hostname = st.load(session, st.SystemSettings).hostname
    if password:
        result.admin_password = password
        path = cfg.state_dir / PASSWORD_FILE
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(password + "\n")
        result.messages.append("created user 'admin' with a random password")

    result.certificate_created = tls.ensure_certificate(hostname)
    return result


def initial_password() -> str | None:
    """Initial admin password while it has not been changed yet (console banner)."""
    path = config.get().state_dir / PASSWORD_FILE
    try:
        return path.read_text().strip() or None
    except FileNotFoundError:
        return None


def forget_initial_password() -> None:
    path = config.get().state_dir / PASSWORD_FILE
    if path.exists():
        path.unlink()
