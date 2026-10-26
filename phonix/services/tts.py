# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Announcements from text: a text-to-speech server with the RestfulTTS API.

- ``GET  {url}/api/v1/voices`` lists the voices (``id``, ``language``, ``label``, ...).
- ``POST {url}/api/v1/synthesize`` with ``{"text", "voice" | "language", "speed", "format"}``
  returns the audio. Phonix asks for ``wav8`` (8 kHz mono WAV, what Asterisk plays); the
  result still goes through ``media.add_media()`` like an upload.

The text leaves the PBX: the server is configured by the administrator (*Services → Media*).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, NoReturn

from sqlalchemy.orm import Session

from phonix.core import settings as st
from phonix.core.models import MediaFile
from phonix.i18n import _
from phonix.services import media
from phonix.services.common import ServiceError

KINDS = ("ivr_prompt", "vm_greeting")
MAX_TEXT = 2000
FORMAT = "wav8"
# 2000 characters of 8 kHz speech are a few MB
MAX_AUDIO = 16 * 1024 * 1024
# voices are listed on every page view: answer quickly or not at all
VOICES_TIMEOUT = 5.0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the bearer token to wherever ``Location`` points."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> NoReturn:
        raise urllib.error.HTTPError(newurl, code, f"redirect to {newurl} refused", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


def _settings(session: Session) -> st.TtsSettings:
    tts = st.load(session, st.TtsSettings)
    if not tts.configured:
        raise ServiceError(_("No text-to-speech server is configured (Services > Media)."))
    return tts


def _release(session: Session) -> None:
    """End the transaction before waiting for the server: a pending write (e.g. a token's last use)
    would otherwise hold the SQLite write lock for the whole request."""
    session.commit()


def _request(
    tts: st.TtsSettings, path: str, body: dict[str, Any] | None = None, timeout: float | None = None
) -> tuple[bytes, str]:
    headers = {"Accept": "application/json" if body is None else "audio/wav"}
    if tts.token:
        headers["Authorization"] = f"Bearer {tts.token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(tts.url + path, data=data, headers=headers, method="POST" if body else "GET")  # noqa: S310 - http(s) only (TtsSettings)
    limit = timeout or tts.timeout
    # the socket timeout applies per read: a trickling answer must not exceed the limit in total
    deadline = time.monotonic() + limit
    try:
        with _OPENER.open(req, timeout=limit) as resp:
            content_type = resp.headers.get("Content-Type", "")
            chunks: list[bytes] = []
            size = 0
            while chunk := resp.read(65536):
                size += len(chunk)
                if size > MAX_AUDIO:
                    raise ServiceError(_("The text-to-speech server sent more than 16 MB"))
                if time.monotonic() > deadline:
                    raise TimeoutError("timed out")
                chunks.append(chunk)
    except urllib.error.HTTPError as exc:
        raise ServiceError(_("The text-to-speech server refused: %(error)s", error=_detail(exc))) from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        raise ServiceError(_("The text-to-speech server is not reachable: %(error)s", error=reason)) from exc
    return b"".join(chunks), content_type


def _detail(exc: urllib.error.HTTPError) -> str:
    """The FastAPI error text (``{"detail": ...}``), else the HTTP status."""
    if 300 <= exc.code < 400:
        return str(exc.msg)
    try:
        detail = json.loads(exc.read(4096)).get("detail")
    except (OSError, ValueError, AttributeError):
        detail = None
    if isinstance(detail, list):  # validation errors
        detail = "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in detail)
    return str(detail)[:200] if detail else f"HTTP {exc.code}"


def voices(session: Session) -> list[dict[str, Any]]:
    """The server's voices: ``id``, ``language`` and ``label`` at least."""
    tts = _settings(session)
    _release(session)
    payload, _type = _request(tts, "/api/v1/voices", timeout=VOICES_TIMEOUT)
    try:
        items = json.loads(payload)
    except ValueError as exc:
        raise ServiceError(_("The text-to-speech server sent an invalid answer")) from exc
    if not isinstance(items, list):
        raise ServiceError(_("The text-to-speech server sent an invalid answer"))
    out = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            out.append(
                {
                    "id": item["id"],
                    "language": str(item.get("language", "")),
                    "label": str(item.get("label") or item["id"]),
                }
            )
    return out


def synthesize(session: Session, text: str, voice: str = "", speed: float | None = None) -> bytes:
    """The text as 8 kHz mono WAV. Without a voice: the default voice, else the prompt language."""
    tts = _settings(session)
    text = text.strip()
    if not text:
        raise ServiceError(fields={"text": _("Enter the text to speak")})
    if len(text) > MAX_TEXT:
        raise ServiceError(fields={"text": _("At most %(max)s characters allowed", max=MAX_TEXT)})
    voice = voice.strip() or tts.voice
    speed = tts.speed if speed is None else speed
    if not 0.5 <= speed <= 2.0:
        raise ServiceError(fields={"speed": _("Between 0.5 and 2")})
    body: dict[str, Any] = {"text": text, "speed": speed, "format": FORMAT}
    if voice:
        body["voice"] = voice
    else:
        body["language"] = st.load(session, st.SystemSettings).prompt_language
    _release(session)
    payload, content_type = _request(tts, "/api/v1/synthesize", body)
    if not content_type.startswith("audio/") or not payload:
        raise ServiceError(_("The text-to-speech server sent no audio"))
    return payload


def create(
    session: Session, kind: str, name: str, text: str, voice: str = "", speed: float | None = None, user: str = ""
) -> MediaFile:
    """Speak ``text`` and store it as an announcement (``ivr_prompt``) or the voicemail greeting."""
    if kind not in KINDS:
        raise ServiceError(fields={"kind": _("Unknown media type")})
    name = name.strip()
    if kind == "ivr_prompt" and not name:
        raise ServiceError(fields={"name": _("Enter a name for the announcement")})
    audio = synthesize(session, text, voice, speed)
    return media.add_media(session, kind, f"{name or 'greeting'}.wav", audio, user)
