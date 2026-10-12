"""Keep /data owned by the unprivileged web user after root-run CLI commands.

``askozia firstboot``, ``apply --boot`` and the console menu run as root and may
create the database (and its -wal/-shm files), secrets or media. The web
process (user ``askozia``) must keep full access, and Asterisk (group
``asterisk``) needs to read media and the TLS certificate.
"""

from __future__ import annotations

import contextlib
import grp
import os
import pwd
from pathlib import Path

from askozia import config

APP_USER = "askozia"
# sub directories of the data dir that Asterisk reads
ASTERISK_READABLE = ("media", "tls")
# owned by Asterisk itself (astdb) - never touched here
SKIP = ("asterisk",)


def _ids() -> tuple[int, int, int] | None:
    try:
        user = pwd.getpwnam(APP_USER)
        asterisk_gid = grp.getgrnam("asterisk").gr_gid
    except KeyError:
        return None
    return user.pw_uid, user.pw_gid, asterisk_gid


def _chown_tree(path: Path, uid: int, gid: int) -> None:
    with contextlib.suppress(OSError):
        os.chown(path, uid, gid, follow_symlinks=False)
    if path.is_dir() and not path.is_symlink():
        for root, dirs, files in os.walk(path):
            for name in dirs + files:
                with contextlib.suppress(OSError):
                    os.chown(os.path.join(root, name), uid, gid, follow_symlinks=False)


def fix_data_ownership() -> None:
    if os.geteuid() != 0:
        return
    ids = _ids()
    data = config.get().data_dir
    if ids is None or not data.is_dir():
        return
    uid, gid, asterisk_gid = ids
    for entry in data.iterdir():
        if entry.name in SKIP or entry.name == "lost+found":
            continue
        _chown_tree(entry, uid, asterisk_gid if entry.name in ASTERISK_READABLE else gid)
