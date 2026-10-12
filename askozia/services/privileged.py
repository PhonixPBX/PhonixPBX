"""Calls into the root helper ``/usr/libexec/askozia/priv`` via doas.

The web process runs as the unprivileged ``askozia`` user. Everything that
needs root goes through this single entry point; the helper accepts a fixed
set of actions (see ``system/libexec/priv``). In ``dry-run`` mode (dev/tests)
calls are only recorded, and staged files are copied below ``ASKOZIA_ROOT`` so
the result can still be inspected.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field

from askozia import config

log = logging.getLogger(__name__)

ACTIONS = {
    "install-staged": 1,  # component
    "asterisk-restart": 0,
    "asterisk-start": 0,
    "nginx-reload": 0,
    "time-sync": 0,
    "reboot": 0,
    "shutdown": 0,
    "factory-reset": 0,
    "install-update": 1,  # bundle path
    "mark-good": 0,
    "ban": 2,  # ip, seconds
    "unban": 1,  # ip
}

# what the helper installs for each component (must match system/libexec/priv)
STAGED_FILES = {
    "system:network": ["/etc/network/interfaces", "/etc/resolv.conf"],
    "system:hostname": ["/etc/hostname", "/etc/hosts"],
    "system:time": ["/etc/chrony/chrony.conf", "/etc/timezone"],
    "system:firewall": ["/etc/nftables.nft"],
    "system:ssh": ["/etc/askozia/ssh"],
}

_ARG = re.compile(r"^[A-Za-z0-9_.:/\-]{1,255}$")


class PrivilegedError(Exception):
    pass


@dataclass
class Recorder:
    calls: list[tuple[str, ...]] = field(default_factory=list)


recorder = Recorder()


def run(action: str, *args: str, timeout: int = 120) -> str:
    if action not in ACTIONS or len(args) != ACTIONS[action]:
        raise PrivilegedError(f"invalid privileged action {action!r}")
    for arg in args:
        if not _ARG.match(arg):
            raise PrivilegedError(f"invalid argument {arg!r}")
    cfg = config.get()
    if cfg.privileged_mode == "dry-run":
        recorder.calls.append((action, *args))
        log.info("dry-run privileged action: %s %s", action, " ".join(args))
        if action == "install-staged":
            _dry_install(args[0])
        return ""
    helper = str(cfg.libexec_dir / "priv")
    try:
        proc = subprocess.run(
            ["doas", "-n", helper, action, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PrivilegedError(f"{action} failed: {exc}") from exc
    if proc.returncode != 0:
        raise PrivilegedError(f"{action} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def _dry_install(component: str) -> None:
    cfg = config.get()
    for target in STAGED_FILES.get(component, []):
        src = cfg.staged_dir / target.lstrip("/")
        if src.exists():
            dst = cfg.path(target)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
