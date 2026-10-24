# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Backup and restore: a ``.tar.zst`` with ``config.json``, media, TLS and ACME files.

The configuration is a versioned document (``services/configdoc.py``), not a
database snapshot, so a backup restores on newer releases and a restore never
replaces the database file under running processes:

1. extract into a temp dir below the data dir and validate everything,
   including a dry run of the import (nothing changed so far)
2. take a safety backup of the current state
3. import the document in one transaction, swap in the file directories and
   commit; on failure the directories are swapped back
4. apply the configuration (and reload nginx for a restored certificate)

The Asterisk database (``asterisk/``) is runtime state and not included.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import logging
import os
import re
import shutil
import tarfile
import tempfile
from collections.abc import Collection, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import zstandard

from phonix import __version__, config
from phonix.core import db
from phonix.i18n import _
from phonix.services import configdoc, hours, privileged
from phonix.services.common import ServiceError, audit

log = logging.getLogger(__name__)

MANIFEST = "manifest.json"
CONFIG = "config.json"
FORMAT = 2
MAX_RESTORE_BYTES = 2 * 1024**3
# directories below the data dir that are restored as a whole, with the
# directory and file modes phonix-firstboot gives them
FILE_DIRS: dict[str, tuple[int, int]] = {
    "media": (0o2750, 0o640),
    "tls": (0o750, 0o640),
    "acme": (0o700, 0o600),
}
# runtime files that are not backed up
SKIP_FILES = {"acme/lock"}
KEEP_BACKUPS = 10


@dataclass
class Preview:
    manifest: dict[str, Any]
    counts: dict[str, int]
    # file directories contained in the backup
    files: list[str]


@dataclass
class RestoreResult(Preview):
    apply_errors: list[str] = field(default_factory=list)
    # parts of the previous configuration that were kept (configdoc.KEEP_PARTS)
    kept: list[str] = field(default_factory=list)


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o600
    info.mtime = int(dt.datetime.now().timestamp())
    tar.addfile(info, io.BytesIO(data))


def _skip(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    return None if info.name in SKIP_FILES else info


def create(target: Path | None = None) -> Path:
    cfg = config.get()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if target is None:
        cfg.backup_dir.mkdir(parents=True, exist_ok=True)
        target = cfg.backup_dir / f"phonix-backup-{stamp}.tar.zst"
        counter = 1
        while target.exists():
            counter += 1
            target = cfg.backup_dir / f"phonix-backup-{stamp}-{counter}.tar.zst"
    with db.session_scope() as session:
        doc = configdoc.export(session)
    manifest = {
        "format": FORMAT,
        "version": __version__,
        "created": doc["created"],
        "config_version": doc["version"],
    }
    tmp_target = target.with_name(f".{target.name}.tmp")
    # the archive contains passwords and private keys
    fd = os.open(tmp_target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as raw:
        cctx = zstandard.ZstdCompressor(level=10)
        with cctx.stream_writer(raw) as zfh, tarfile.open(fileobj=zfh, mode="w|") as tar:
            _add_bytes(tar, MANIFEST, json.dumps(manifest, indent=2).encode())
            _add_bytes(tar, CONFIG, json.dumps(doc, indent=2, ensure_ascii=False).encode())
            for m in doc["media"]:
                tar.add(cfg.media_dir / m["path"], arcname=f"media/{m['path']}")
            for name in ("tls", "acme"):
                path = cfg.data_dir / name
                if path.is_dir():
                    tar.add(path, arcname=name, recursive=True, filter=_skip)
    tmp_target.replace(target)
    _prune(cfg.backup_dir)
    return target


_NAME_RE = re.compile(r"phonix-backup-(\d{8}-\d{6})(?:-(\d+))?\.tar\.zst")


def _age_key(path: Path) -> tuple[str, int]:
    """Oldest first; "-2" (second backup in the same second) sorts after the first one."""
    m = _NAME_RE.fullmatch(path.name)
    return (m[1], int(m[2] or 1)) if m else (path.name, 0)


def _prune(directory: Path) -> None:
    backups = sorted(directory.glob("phonix-backup-*.tar.zst"), key=_age_key)
    for old in backups[:-KEEP_BACKUPS]:
        old.unlink()


def list_backups() -> list[Path]:
    return sorted(config.get().backup_dir.glob("phonix-backup-*.tar.zst"), key=_age_key, reverse=True)


# --- restore --------------------------------------------------------------------------


def _safe_members(tar: tarfile.TarFile) -> Iterator[tarfile.TarInfo]:
    """Yield validated members one by one (the stream cannot seek backwards)."""
    total = 0
    for member in tar:
        name = member.name
        if name.startswith("/") or ".." in Path(name).parts:
            raise ServiceError(_("Unsafe path in backup: %(name)s", name=name))
        if not (member.isfile() or member.isdir()):
            continue
        top = Path(name).parts[0]
        if name not in (MANIFEST, CONFIG) and top not in FILE_DIRS:
            continue
        total += member.size
        if total > MAX_RESTORE_BYTES:
            raise ServiceError(_("Backup is too large"))
        yield member


def _extract(source: Path, tmpdir: Path) -> tuple[dict[str, Any], configdoc.ConfigDocument]:
    try:
        with source.open("rb") as raw:
            dctx = zstandard.ZstdDecompressor()
            with dctx.stream_reader(raw) as zfh, tarfile.open(fileobj=zfh, mode="r|") as tar:
                for member in _safe_members(tar):
                    tar.extract(member, tmpdir, set_attrs=False)
    except (tarfile.TarError, zstandard.ZstdError, OSError) as exc:
        raise ServiceError(_("Not a valid PhonixPBX backup: %(error)s", error=exc)) from exc
    try:
        manifest = json.loads((tmpdir / MANIFEST).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError) as exc:
        raise ServiceError(_("Backup manifest is missing")) from exc
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise ServiceError(
            _("This backup was made by an older PhonixPBX release in a format that can no longer be restored.")
        )
    try:
        data = json.loads((tmpdir / CONFIG).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError) as exc:
        raise ServiceError(_("The configuration in the backup is missing or damaged")) from exc
    doc = configdoc.parse_document(data)
    configdoc.check_media(doc, tmpdir / "media")
    return manifest, doc


def _dry_run(doc: configdoc.ConfigDocument, media_root: Path) -> dict[str, int]:
    session = db.session_factory()()
    try:
        return configdoc.import_document(session, doc, media_root)
    finally:
        session.rollback()
        session.close()


def _contained(tmpdir: Path) -> list[str]:
    return [name for name in FILE_DIRS if (tmpdir / name).is_dir()]


def inspect(source: Path) -> Preview:
    """Validate a backup completely, without changing anything."""
    with tempfile.TemporaryDirectory(dir=config.get().data_dir) as tmp:
        tmpdir = Path(tmp)
        manifest, doc = _extract(source, tmpdir)
        counts = _dry_run(doc, tmpdir / "media")
        return Preview(manifest=manifest, counts=counts, files=_contained(tmpdir))


def _prepare(path: Path, live: Path, modes: tuple[int, int]) -> None:
    """Give a staged directory the modes and group of the live one."""
    dir_mode, file_mode = modes
    gid = live.stat().st_gid if live.exists() else -1
    for root, _dirs, files in os.walk(path):
        for name, mode in [(root, dir_mode), *((os.path.join(root, f), file_mode) for f in files)]:
            with contextlib.suppress(OSError):
                os.chown(name, -1, gid)  # the web user is a member of the group
            os.chmod(name, mode)


def _swap(tmpdir: Path, names: list[str]) -> list[tuple[Path, Path | None]]:
    """Move the staged directories into place; returns what ``_unswap`` needs."""
    data = config.get().data_dir
    done: list[tuple[Path, Path | None]] = []
    try:
        for name in names:
            live = data / name
            old: Path | None = None
            if live.exists():
                old = data / f".{name}.old"
                shutil.rmtree(old, ignore_errors=True)
                live.rename(old)
            done.append((live, old))
            (tmpdir / name).rename(live)
    except OSError:
        _unswap(done)
        raise
    return done


def _unswap(done: list[tuple[Path, Path | None]]) -> None:
    for live, old in reversed(done):
        shutil.rmtree(live, ignore_errors=True)
        if old is not None:
            with contextlib.suppress(OSError):
                old.rename(live)


def restore(source: Path, user: str = "", keep: Collection[str] = ()) -> RestoreResult:
    """Replace the configuration and files with the backup and apply it.

    ``keep`` names parts of the current configuration that stay (``configdoc.KEEP_PARTS``)."""
    from phonix.services import apply as apply_mod

    cfg = config.get()
    with tempfile.TemporaryDirectory(dir=cfg.data_dir) as tmp:
        tmpdir = Path(tmp)
        manifest, doc = _extract(source, tmpdir)
        _dry_run(doc, tmpdir / "media")

        create()  # safety net: the current state

        (tmpdir / "media").mkdir(exist_ok=True)  # media is always replaced
        names = _contained(tmpdir)
        if "certificate" in keep:
            names = [name for name in names if name not in ("tls", "acme")]
        for name in names:
            _prepare(tmpdir / name, cfg.data_dir / name, FILE_DIRS[name])
        session = db.session_factory()()
        try:
            counts = configdoc.import_document(session, doc, tmpdir / "media", user=user, keep=keep)
            summary = f"restored backup from {manifest.get('created')}"
            if keep:
                summary += f", kept {', '.join(sorted(keep))}"
            audit(session, user, "restore", summary=summary)
            try:
                swapped = _swap(tmpdir, names)
            except OSError as exc:  # e.g. a full disk; _swap has put the old files back
                raise ServiceError(_("Restoring the files failed, nothing was changed: %(error)s", error=exc)) from exc
            try:
                session.commit()
            except BaseException:
                _unswap(swapped)
                raise
        finally:
            session.close()
        for _live, old in swapped:
            if old is not None:
                shutil.rmtree(old, ignore_errors=True)

    with db.session_scope() as session:
        hours.reset_runtime(session)
    result = RestoreResult(manifest=manifest, counts=counts, files=names, kept=sorted(keep))
    try:
        with db.session_scope() as session:
            result.apply_errors.extend(apply_mod.apply(session, user=user or "restore").errors)
    except Exception as exc:  # the restore itself is done, the user can apply again
        log.exception("apply after restore failed")
        result.apply_errors.append(str(exc))
    if "tls" in names:
        try:
            privileged.run("nginx-reload")
        except privileged.PrivilegedError as exc:
            result.apply_errors.append(str(exc))
    return result
