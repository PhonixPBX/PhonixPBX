# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Apply the database configuration to the running system.

1. build a snapshot and run all generators (pure)
2. write every changed file atomically (privileged ones are staged)
3. trigger the minimal set of reloads for the components that changed

This replaces the legacy rc.bootup / pbx_configure() / *.dirty machinery.
"""

from __future__ import annotations

import contextlib
import grp
import logging
import os
import pwd
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from phonix import ami, config
from phonix.core import settings as st
from phonix.generators import GeneratedFile, Secrets, build_snapshot, generate_all
from phonix.services import facts as facts_mod
from phonix.services import platform, privileged, secrets
from phonix.services.common import audit, clear_dirty

log = logging.getLogger(__name__)

# component -> Asterisk CLI commands executed over AMI
RELOAD_COMMANDS: dict[str, list[str]] = {
    "asterisk:pjsip": [
        "module reload res_pjsip.so",
        "module reload res_pjsip_outbound_registration.so",
        "module reload res_pjsip_notify.so",
    ],
    "asterisk:iax": ["iax2 reload"],
    "asterisk:dialplan": ["dialplan reload"],
    "asterisk:voicemail": ["voicemail reload"],
    "asterisk:confbridge": ["module reload app_confbridge.so"],
    "asterisk:moh": ["moh reload"],
    "asterisk:features": ["module reload features"],
    "asterisk:parking": ["module reload res_parking.so"],
    "asterisk:rtp": ["module reload res_rtp_asterisk.so"],
    "asterisk:manager": ["manager reload"],
    "asterisk:logger": ["logger reload"],
    "asterisk:indications": ["module reload indications"],
    "asterisk:cdr": ["module reload cdr"],
}

# order in which components are applied
ORDER = [
    "system:hostname",
    "system:network",
    "system:time",
    "system:firewall",
    "system:ssh",
    "system:mdns",
    "email",
    "asterisk:restart",
    *RELOAD_COMMANDS,
]


@dataclass
class ApplyResult:
    changed_files: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _write_atomic(path: Path, content: str, mode: int, group: str | None = None, hand_over: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as fh:
        fh.write(content)
    os.chmod(tmp, mode)
    if group:
        # files Asterisk must read get group "asterisk" (the phonix user is a
        # member, so this also works unprivileged); as root also hand them over
        uid = gid = -1
        with contextlib.suppress(KeyError):
            gid = grp.getgrnam(group).gr_gid
        if os.geteuid() == 0 and hand_over:
            with contextlib.suppress(KeyError):
                uid = pwd.getpwnam("phonix").pw_uid
        with contextlib.suppress(PermissionError):
            os.chown(tmp, uid, gid)
    os.replace(tmp, path)


def _read(path: Path) -> str | None:
    try:
        return path.read_text()
    except (FileNotFoundError, PermissionError, UnicodeDecodeError):
        return None


def write_files(files: list[GeneratedFile], direct_privileged: bool, force: bool = False) -> list[GeneratedFile]:
    """Write changed files; returns the list of files that changed."""
    cfg = config.get()
    changed: list[GeneratedFile] = []
    for f in files:
        target = cfg.path(f.path)
        if not force and _read(target) == f.content:
            continue
        changed.append(f)
        if f.privileged and not direct_privileged:
            _write_atomic(cfg.staged_dir / f.path.lstrip("/"), f.content, 0o640)
        elif f.path.startswith(("/etc/asterisk/", "/etc/phonix/msmtprc")):
            _write_atomic(target, f.content, f.mode, "asterisk")
        else:
            # system files written as root at boot: root keeps them, the web
            # process (group phonix) may read them to detect changes
            _write_atomic(target, f.content, f.mode, "phonix" if f.privileged else None, hand_over=False)
    return changed


def generate(session: Session) -> list[GeneratedFile]:
    snap = build_snapshot(
        session,
        facts=facts_mod.collect(st.load(session, st.NetworkSettings)),
        secrets=Secrets(ami_internal=secrets.get("ami_internal")),
    )
    files = generate_all(snap)
    if platform.is_container():
        # the container host owns the network configuration and the host name
        # (/etc/hostname, /etc/hosts and /etc/resolv.conf are often bind mounts)
        files = [f for f in files if f.component not in platform.HOST_MANAGED_COMPONENTS]
    return files


def preview(session: Session) -> list[GeneratedFile]:
    """Files an apply would change; nothing is written."""
    cfg = config.get()
    return [f for f in generate(session) if _read(cfg.path(f.path)) != f.content]


def apply(session: Session, user: str = "", boot: bool = False, force: bool = False) -> ApplyResult:
    """Generate and activate the configuration.

    ``boot``: called by the init script as root before services start - files
    are written directly and nothing is reloaded.
    ``force``: rewrite and reload everything even if unchanged.
    """
    result = ApplyResult()
    files = generate(session)
    direct = boot or (os.geteuid() == 0 and config.get().privileged_mode != "dry-run")
    changed = write_files(files, direct_privileged=direct, force=force)
    result.changed_files = [f.path for f in changed]
    components = {f.component for f in changed}
    result.components = [c for c in ORDER if c in components]

    if not boot:
        _activate(result)

    if result.ok:
        clear_dirty(session)
    audit(session, user, "apply", summary=", ".join(result.components) or "no changes")
    return result


def _activate(result: ApplyResult) -> None:
    components = result.components
    for comp in components:
        if comp.startswith("system:"):
            try:
                privileged.run("install-staged", comp)
                result.actions.append(f"install {comp}")
            except privileged.PrivilegedError as exc:
                result.errors.append(str(exc))

    asterisk = [c for c in components if c.startswith("asterisk:")]
    if not asterisk:
        return
    if "asterisk:restart" in asterisk or not ami.is_running():
        try:
            privileged.run("asterisk-restart")
            result.actions.append("restart asterisk")
        except privileged.PrivilegedError as exc:
            result.errors.append(str(exc))
        return
    commands = [cmd for comp in asterisk for cmd in RELOAD_COMMANDS.get(comp, [])]
    try:
        with ami.AmiClient() as client:
            for cmd in commands:
                client.command(cmd)
                result.actions.append(cmd)
    except ami.AmiError as exc:
        result.errors.append(f"Asterisk reload failed: {exc}")
