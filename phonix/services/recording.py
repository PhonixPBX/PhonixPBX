# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Record an announcement by phone.

The web interface rings the administrator's phone (AMI Originate) into the
``phonix-record`` context. Asterisk records to ``<media>/incoming/<token>.wav``
and keeps the progress in the Asterisk database (``phonix-rec/<token>``:
``recording``, ``review``, ``saved``, ``cancel`` or ``hangup``). The page polls
``poll()``; once the caller saved the recording it becomes a normal media file
through ``media.add_media()``.

``incoming`` is the only directory Asterisk may write to: mode 2770, owned by
``phonix`` with group ``asterisk`` (the web user is a member of that group and
can read and remove the files Asterisk creates). What a pending recording is
for (kind, name, user) stays in the state directory, out of Asterisk's reach.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import secrets
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from phonix import ami, config
from phonix.core.models import MediaFile
from phonix.i18n import _
from phonix.services import calls, media
from phonix.services.common import NotFound, ServiceError, audit

KINDS = ("ivr_prompt", "vm_greeting")
CONTEXT = "phonix-record"
ASTDB_FAMILY = "phonix-rec"
INCOMING = "incoming"
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
# no state yet after this long: the phone was not answered
ANSWER_TIMEOUT = calls.RING_TIMEOUT_MS / 1000 + 15
# pending recordings older than this are given up
MAX_AGE = 30 * 60


@dataclass
class Status:
    state: str  # ringing, recording, review, saving, saved, cancelled, no-answer, expired, failed
    kind: str
    name: str
    media: MediaFile | None = None
    error: str = ""

    @property
    def done(self) -> bool:
        return self.state not in ("ringing", "recording", "review", "saving")


def incoming_dir() -> Path:
    path = config.get().media_dir / INCOMING
    path.mkdir(parents=True, exist_ok=True)
    # Asterisk (group asterisk) writes here; the setgid bit keeps the group
    with contextlib.suppress(OSError):
        os.chmod(path, 0o2770)  # noqa: S103 - Asterisk writes the recordings here
    return path


def _pending_dir(create: bool = True) -> Path:
    """``<token>.json`` while pending, ``.claimed`` while one poll stores it, ``.done`` (the media id) after."""
    path = config.get().state_dir / "recordings"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _meta_path(token: str, suffix: str = ".json") -> Path:
    if not TOKEN_RE.match(token):
        raise NotFound(_("Recording not found"))
    return _pending_dir() / f"{token}{suffix}"


def _astdb(client: ami.AmiClient, token: str) -> str:
    out = client.command(f"database get {ASTDB_FAMILY} {token}")
    for line in out.splitlines():
        if line.startswith("Value:"):
            return line.split(":", 1)[1].strip()
    return ""


def _read_recording(path: Path) -> bytes:
    """A regular file written by Asterisk: never follow a link planted in ``incoming``."""
    # O_NONBLOCK: opening a FIFO put in its place must not hang the request
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as fh:
        info = os.fstat(fh.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > media.MAX_UPLOAD:
            raise OSError("not a regular file of acceptable size")
        return fh.read()


def _discard(token: str, keep_done: bool = False) -> None:
    with contextlib.suppress(OSError):
        (config.get().media_dir / INCOMING / f"{token}.wav").unlink()
    for suffix in (".json", ".claimed") if keep_done else (".json", ".claimed", ".done"):
        with contextlib.suppress(OSError):
            _meta_path(token, suffix).unlink()
    try:
        with ami.AmiClient(timeout=3.0) as client:
            client.command(f"database del {ASTDB_FAMILY} {token}")
    except (ami.AmiError, OSError):
        pass


def cleanup(now: float | None = None) -> None:
    """Give up pending recordings older than ``MAX_AGE`` and remove stray files in ``incoming``."""
    now = time.time() if now is None else now
    pending = set()
    states = _pending_dir(create=False)
    for meta in states.glob("*") if states.is_dir() else ():
        token = meta.name.split(".", 1)[0]
        try:
            old = now - meta.lstat().st_mtime > MAX_AGE
        except OSError:
            continue
        if not TOKEN_RE.match(token):
            continue
        if old:
            _discard(token)
        else:
            pending.add(token)
    incoming = config.get().media_dir / INCOMING
    if incoming.is_dir():
        for path in incoming.iterdir():
            with contextlib.suppress(OSError):
                if path.name.split(".", 1)[0] not in pending and now - path.lstat().st_mtime > MAX_AGE:
                    path.unlink()


def start(session: Session, extension: str, kind: str, name: str, user: str = "") -> str:
    """Ring the phone; returns the token to poll."""
    if kind not in KINDS:
        raise ServiceError(fields={"kind": _("Unknown media type")})
    name = name.strip()
    if kind == "ivr_prompt" and not name:
        raise ServiceError(fields={"name": _("Enter a name for the announcement")})
    phone = calls.phone_for_call(session, extension)
    cleanup()
    incoming_dir()
    token = secrets.token_hex(16)
    meta = {"kind": kind, "name": name or "greeting", "user": user, "started": time.time()}
    _meta_path(token).write_text(json.dumps(meta))
    try:
        calls.originate_into(phone, CONTEXT, "s", '"Record announcement" <record>', {"PHX_REC": token})
    except ServiceError:
        _discard(token)
        raise
    audit(session, user, "originate", "phone", phone.id, f"{phone.extension} -> record {media.KINDS[kind]}")
    return token


def poll(session: Session, token: str, user: str = "", now: float | None = None) -> Status:
    """The state of a recording; a saved one is stored as a media file (once)."""
    meta_path = _meta_path(token)
    try:
        meta = json.loads(meta_path.read_text())
    except FileNotFoundError:
        return _finished(session, token)
    except (OSError, ValueError) as exc:
        raise NotFound(_("Recording not found")) from exc
    kind, name = str(meta["kind"]), str(meta["name"])
    age = (time.time() if now is None else now) - float(meta["started"])
    try:
        with ami.AmiClient(timeout=3.0) as client:
            state = _astdb(client, token)
    except (ami.AmiError, OSError) as exc:
        return Status("failed", kind, name, error=str(exc))
    if state in ("recording", "review"):
        if age > MAX_AGE:
            _discard(token)
            return Status("expired", kind, name)
        return Status(state, kind, name)
    if state == "":
        if age > ANSWER_TIMEOUT:
            _discard(token)
            return Status("no-answer", kind, name)
        return Status("ringing", kind, name)
    if state != "saved":
        _discard(token)
        return Status("cancelled", kind, name)
    # only one poll stores the recording (two tabs, or a slow conversion and the next poll)
    try:
        os.rename(meta_path, _meta_path(token, ".claimed"))
    except FileNotFoundError:
        return _finished(session, token)
    try:
        data = _read_recording(config.get().media_dir / INCOMING / f"{token}.wav")
    except OSError:
        _discard(token)
        return Status("failed", kind, name, error=_("The recording is missing"))
    try:
        item = media.add_media(session, kind, f"{name}.wav", data, user or str(meta.get("user", "")))
    except ServiceError as exc:
        _discard(token)
        return Status("failed", kind, name, error="; ".join([exc.message, *exc.fields.values()]).strip("; "))
    _meta_path(token, ".done").write_text(json.dumps({**meta, "media_id": item.id}))
    _discard(token, keep_done=True)
    return Status("saved", kind, name, media=item)


def _finished(session: Session, token: str) -> Status:
    """A poll after another one claimed the recording: still storing it, or the stored file."""
    try:
        done = json.loads(_meta_path(token, ".done").read_text())
    except FileNotFoundError:
        if _meta_path(token, ".claimed").exists():
            return Status("saving", "", "")
        raise NotFound(_("Recording not found")) from None
    except (OSError, ValueError) as exc:
        raise NotFound(_("Recording not found")) from exc
    item = session.get(MediaFile, int(done["media_id"]))
    if item is None:  # the other request has not committed yet
        return Status("saving", str(done["kind"]), str(done["name"]))
    return Status("saved", str(done["kind"]), str(done["name"]), media=item)
