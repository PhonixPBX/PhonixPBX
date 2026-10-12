"""Backup and restore: a ``.tar.zst`` with a consistent DB snapshot, media and TLS."""

from __future__ import annotations

import datetime as dt
import io
import json
import shutil
import sqlite3
import tarfile
import tempfile
from collections.abc import Iterator
from pathlib import Path

import zstandard

from askozia import __version__, config
from askozia.core import db, migrate
from askozia.services.common import ServiceError

MANIFEST = "manifest.json"
FORMAT = 1
MAX_RESTORE_BYTES = 2 * 1024**3
# directories below the data dir that are included as-is
INCLUDE_DIRS = ("media", "tls", "asterisk")
KEEP_BACKUPS = 10


def _db_snapshot(target: Path) -> None:
    src = sqlite3.connect(config.get().db_path)
    try:
        dst = sqlite3.connect(target)
        with dst:
            src.backup(dst)
        dst.close()
    finally:
        src.close()


def _add_dir(tar: tarfile.TarFile, base: Path, name: str) -> None:
    path = base / name
    if path.is_dir():
        tar.add(path, arcname=name, recursive=True)


def create(target: Path | None = None) -> Path:
    cfg = config.get()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if target is None:
        cfg.backup_dir.mkdir(parents=True, exist_ok=True)
        target = cfg.backup_dir / f"askozia-backup-{stamp}.tar.zst"
        counter = 1
        while target.exists():
            counter += 1
            target = cfg.backup_dir / f"askozia-backup-{stamp}-{counter}.tar.zst"
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "askozia.db"
        _db_snapshot(snap)
        manifest = {
            "format": FORMAT,
            "version": __version__,
            "created": dt.datetime.now(dt.timezone.utc).isoformat(),
            "schema": migrate.current_revision(),
        }
        tmp_target = target.with_name(f".{target.name}.tmp")
        with tmp_target.open("wb") as raw:
            cctx = zstandard.ZstdCompressor(level=10)
            with cctx.stream_writer(raw) as zfh, tarfile.open(fileobj=zfh, mode="w|") as tar:
                data = json.dumps(manifest, indent=2).encode()
                info = tarfile.TarInfo(MANIFEST)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
                tar.add(snap, arcname="askozia.db")
                for name in INCLUDE_DIRS:
                    _add_dir(tar, cfg.data_dir, name)
        tmp_target.replace(target)
    _prune(cfg.backup_dir)
    return target


def _prune(directory: Path) -> None:
    backups = sorted(directory.glob("askozia-backup-*.tar.zst"))
    for old in backups[:-KEEP_BACKUPS]:
        old.unlink()


def list_backups() -> list[Path]:
    return sorted(config.get().backup_dir.glob("askozia-backup-*.tar.zst"), reverse=True)


def _safe_members(tar: tarfile.TarFile) -> Iterator[tarfile.TarInfo]:
    """Yield validated members one by one (the stream cannot seek backwards)."""
    total = 0
    for member in tar:
        name = member.name
        if name.startswith("/") or ".." in Path(name).parts:
            raise ServiceError(f"Unsafe path in backup: {name}")
        if not (member.isfile() or member.isdir()):
            continue
        top = Path(name).parts[0]
        if name not in (MANIFEST, "askozia.db") and top not in INCLUDE_DIRS:
            continue
        total += member.size
        if total > MAX_RESTORE_BYTES:
            raise ServiceError("Backup is too large")
        yield member


def restore(source: Path) -> dict[str, object]:
    cfg = config.get()
    with tempfile.TemporaryDirectory(dir=cfg.data_dir) as tmp:
        tmpdir = Path(tmp)
        try:
            with source.open("rb") as raw:
                dctx = zstandard.ZstdDecompressor()
                with dctx.stream_reader(raw) as zfh, tarfile.open(fileobj=zfh, mode="r|") as tar:
                    for member in _safe_members(tar):
                        tar.extract(member, tmpdir, set_attrs=False)
        except (tarfile.TarError, zstandard.ZstdError, OSError) as exc:
            raise ServiceError(f"Not a valid AskoziaPBX backup: {exc}") from exc
        try:
            manifest = json.loads((tmpdir / MANIFEST).read_text())
        except (FileNotFoundError, ValueError) as exc:
            raise ServiceError("Backup manifest is missing") from exc
        if manifest.get("format") != FORMAT or not (tmpdir / "askozia.db").is_file():
            raise ServiceError("Unsupported backup format")
        try:
            check = sqlite3.connect(tmpdir / "askozia.db")
            check.execute("PRAGMA integrity_check").fetchone()
            check.close()
        except sqlite3.DatabaseError as exc:
            raise ServiceError("Database in backup is corrupt") from exc

        # safety net: keep the current state
        if cfg.db_path.exists():
            create()
        db.dispose()
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(cfg.db_path) + suffix)
            if p.exists():
                p.unlink()
        shutil.move(str(tmpdir / "askozia.db"), cfg.db_path)
        for name in INCLUDE_DIRS:
            src = tmpdir / name
            if src.is_dir():
                dst = cfg.data_dir / name
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.move(str(src), dst)
    migrate.upgrade()
    from askozia.core.db import session_scope
    from askozia.services.common import AREAS, audit, mark_dirty

    with session_scope() as session:
        mark_dirty(session, *AREAS)
        audit(session, "", "restore", summary=f"restored backup from {manifest.get('created')}")
    return manifest
