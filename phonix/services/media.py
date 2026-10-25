# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Uploaded audio: music on hold and the custom voicemail greeting.

Asterisk plays 8 kHz mono 16-bit WAV directly. Uploads are converted with
``sox`` when available (any common format), otherwise a pure Python converter
handles PCM WAV files (Python 3.13+ no longer ships ``audioop``).
"""

from __future__ import annotations

import array
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix import config
from phonix.core import settings as st
from phonix.core.models import IvrMenu, MediaFile
from phonix.i18n import N_, _
from phonix.services.common import NotFound, ServiceError, audit, mark_dirty

MAX_UPLOAD = 64 * 1024 * 1024
TARGET_RATE = 8000
KINDS = {"moh": N_("Music on hold"), "vm_greeting": N_("Voicemail greeting"), "ivr_prompt": N_("IVR announcement")}
SINGLE = {"vm_greeting"}  # kinds with only one file


def _safe_name(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")[:60] or "audio"
    return stem


def _convert_sox(src: Path, dst: Path) -> None:
    proc = subprocess.run(
        ["sox", str(src), "-r", str(TARGET_RATE), "-c", "1", "-b", "16", "-e", "signed-integer", str(dst)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if proc.returncode != 0:
        raise ServiceError(fields={"file": _("Could not convert audio: %(error)s", error=proc.stderr.strip()[:200])})


def _convert_wav(src: Path, dst: Path) -> None:
    """Mix down to mono and resample to 8 kHz (box filter) - PCM WAV only."""
    try:
        with wave.open(str(src), "rb") as wf:
            channels, width, rate, frames = wf.getnchannels(), wf.getsampwidth(), wf.getframerate(), wf.getnframes()
            raw = wf.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise ServiceError(
            fields={
                "file": _(
                    "Only PCM WAV files can be uploaded on this system (convert with: sox in.mp3 -r 8000 -c 1 out.wav)"
                )
            }
        ) from exc
    if width == 2:
        samples = array.array("h")
        samples.frombytes(raw)
        if sys.byteorder == "big":
            samples.byteswap()
    elif width == 1:
        samples = array.array("h", ((b - 128) << 8 for b in raw))
    else:
        raise ServiceError(fields={"file": _("Only 8 or 16 bit WAV files are supported")})
    if channels > 1:
        samples = array.array(
            "h", (sum(samples[i : i + channels]) // channels for i in range(0, len(samples), channels))
        )
    if rate != TARGET_RATE:
        step = rate / TARGET_RATE
        out = array.array("h")
        n = len(samples)
        pos = 0.0
        while pos < n:
            start = int(pos)
            end = min(n, max(start + 1, int(pos + step)))
            chunk = samples[start:end]
            out.append(sum(chunk) // len(chunk))
            pos += step
        samples = out
    if sys.byteorder == "big":
        samples.byteswap()
    with wave.open(str(dst), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(TARGET_RATE)
        wf.writeframes(samples.tobytes())


def convert(src: Path, dst: Path) -> None:
    if shutil.which("sox"):
        _convert_sox(src, dst)
    else:
        _convert_wav(src, dst)


def search_fields(f: MediaFile) -> tuple[object, ...]:
    return (f.name, f.kind, _(KINDS[f.kind]) if f.kind in KINDS else "")


def list_media(session: Session, kind: str | None = None) -> list[MediaFile]:
    stmt = select(MediaFile).order_by(MediaFile.kind, MediaFile.name)
    if kind:
        stmt = stmt.where(MediaFile.kind == kind)
    return list(session.scalars(stmt))


def add_media(session: Session, kind: str, filename: str, data: bytes, user: str = "") -> MediaFile:
    if kind not in KINDS:
        raise ServiceError(fields={"kind": _("Unknown media type")})
    if not data:
        raise ServiceError(fields={"file": _("The file is empty")})
    if len(data) > MAX_UPLOAD:
        raise ServiceError(fields={"file": _("The file is too large (max. 64 MB)")})
    cfg = config.get()
    target_dir = cfg.media_dir / kind
    target_dir.mkdir(parents=True, exist_ok=True)
    name = _safe_name(filename)
    if kind in SINGLE:
        name = "greeting"
    target = target_dir / f"{name}.wav"
    counter = 1
    while kind not in SINGLE and target.exists():
        counter += 1
        target = target_dir / f"{name}-{counter}.wav"
    with tempfile.NamedTemporaryFile(dir=cfg.data_dir, suffix=Path(filename).suffix) as tmp:
        tmp.write(data)
        tmp.flush()
        out = target.with_suffix(".tmp.wav")
        convert(Path(tmp.name), out)
        out.replace(target)
    if kind in SINGLE:
        for old in list_media(session, kind):
            session.delete(old)
    rel = str(target.relative_to(cfg.media_dir))
    media = MediaFile(kind=kind, name=Path(filename).name[:128], path=rel, size=target.stat().st_size)
    session.add(media)
    if kind in ("moh", "vm_greeting"):
        media_settings = st.load(session, st.MediaSettings)
        if kind == "moh":
            media_settings.custom_moh = True
        else:
            media_settings.custom_vm_greeting = True
        st.save(session, media_settings)
    session.flush()
    audit(session, user, "upload", "media", media.id, f"{KINDS[kind]}: {media.name}")
    # IVR announcements only matter once a menu uses them (that marks the dialplan)
    if kind != "ivr_prompt":
        mark_dirty(session, "services")
    return media


def delete_media(session: Session, media_id: int, user: str = "") -> None:
    media = session.get(MediaFile, media_id)
    if media is None:
        raise NotFound(_("Media file not found"))
    path = config.get().media_dir / media.path
    if path.exists():
        path.unlink()
    kind = media.kind
    audit(session, user, "delete", "media", media.id, media.name)
    used = session.scalars(select(IvrMenu).where(IvrMenu.prompt_media_id == media.id)).first() is not None
    session.delete(media)
    session.flush()
    if used:
        mark_dirty(session, "dialplan")
    if kind in ("moh", "vm_greeting") and not list_media(session, kind):
        media_settings = st.load(session, st.MediaSettings)
        if kind == "moh":
            media_settings.custom_moh = False
        else:
            media_settings.custom_vm_greeting = False
        st.save(session, media_settings)
    mark_dirty(session, "services")


def media_path(media: MediaFile) -> Path:
    return config.get().media_dir / media.path
