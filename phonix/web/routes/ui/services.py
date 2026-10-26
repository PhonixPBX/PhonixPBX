# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Services: e-mail notifications, voicemail, conferencing and media."""

from __future__ import annotations

import secrets
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from phonix import config, i18n
from phonix.core import settings as st
from phonix.core.models import MediaFile, User
from phonix.i18n import N_, _
from phonix.notify import VARIABLES
from phonix.services import calls as calls_svc
from phonix.services import dialplan as dp
from phonix.services import ivr as ivr_svc
from phonix.services import media as media_svc
from phonix.services import notifications
from phonix.services import phones as phone_svc
from phonix.services import recording as rec_svc
from phonix.services import tts as tts_svc
from phonix.services.common import NotFound, ServiceError
from phonix.web.deps import get_db, ui_user
from phonix.web.routes.ui.common import dirty_trigger, list_page, page, redirect, save_settings_form, service_errors
from phonix.web.routes.ui.dialplan import Kind, register
from phonix.web.templating import render

router = APIRouter(prefix="/services")


# --- e-mail -------------------------------------------------------------------------


@router.get("/email")
def email(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    values = st.load(db, st.EmailSettings).model_dump()
    values["password"] = ""
    return page(request, "pages/email.html", values=values)


@router.post("/email")
async def email_save(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    saved, values, errors = await save_settings_form(
        request, db, st.EmailSettings, ("email", "dialplan", "services"), secret_fields=("password",)
    )
    if not saved:
        return page(request, "pages/email.html", status_code=422, values=values, errors=errors)
    return redirect(request, "/services/email")


@router.post("/email/test")
async def email_test(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    """Send a test mail with the *applied* msmtp configuration."""
    form = await request.form()
    to = str(form.get("to", "")).strip()
    from phonix.core import validation as v

    try:
        to = v.email(to)
    except ValueError as exc:
        return render(request, "partials/alert.html", {"level": "danger", "message": str(exc)})
    msmtprc = config.get().path("/etc/phonix/msmtprc")
    body = f"To: {to}\nSubject: PhonixPBX test message\n\nE-mail notifications are working.\n"
    try:
        proc = subprocess.run(
            ["msmtp", "-C", str(msmtprc), "-t"], input=body, text=True, capture_output=True, timeout=60, check=False
        )
        ok, detail = proc.returncode == 0, (proc.stderr or proc.stdout).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        ok, detail = False, str(exc)
    if ok:
        return render(
            request, "partials/alert.html", {"level": "success", "message": _("Test message sent to %(to)s.", to=to)}
        )
    return render(
        request,
        "partials/alert.html",
        {
            "level": "danger",
            "message": _("Sending failed (did you apply the settings?): %(detail)s", detail=detail[:300]),
        },
    )


# --- voicemail ---------------------------------------------------------------------------


def _texts_lang(db: Session, lang: str | None) -> str:
    if lang in i18n.LANGUAGE_NAMES:
        return lang
    return i18n.normalize(st.load(db, st.SystemSettings).prompt_language)


def _voicemail_page(
    request: Request,
    db: Session,
    lang: str | None = None,
    values: dict[str, Any] | None = None,
    errors: dict[str, str] | None = None,
    texts: dict[str, str] | None = None,
    text_errors: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    vm = st.load(db, st.VoicemailSettings)
    lang = _texts_lang(db, lang)
    custom = vm.templates.get(lang)
    return page(
        request,
        "pages/voicemail.html",
        status_code=status_code,
        values=values if values is not None else vm.model_dump(),
        errors=errors or {},
        email_ok=st.load(db, st.EmailSettings).configured,
        texts_lang=lang,
        texts=texts if texts is not None else notifications.texts(vm, lang),
        text_errors=text_errors or {},
        customized=[key for key, value in (custom.model_dump() if custom else {}).items() if value],
        preview=notifications.preview(vm, lang),
        variables={kind: ", ".join(f"${{{name}}}" for name in names) for kind, names in VARIABLES.items()},
    )


@router.get("/voicemail")
def voicemail(
    request: Request, lang: str | None = None, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    return _voicemail_page(request, db, lang)


@router.post("/voicemail")
async def voicemail_save(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    saved, values, errors = await save_settings_form(request, db, st.VoicemailSettings, ("services",))
    if not saved:
        return _voicemail_page(request, db, values=values, errors=errors, status_code=422)
    return redirect(request, "/services/voicemail")


@router.post("/voicemail/texts")
async def voicemail_texts_save(
    request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    form = await request.form()
    lang = _texts_lang(db, str(form.get("lang", "")))
    data = {key: str(form.get(key, "")) for key in notifications.FIELDS}
    try:
        notifications.save_texts(db, lang, data, user=user.username)
    except ServiceError as exc:
        return _voicemail_page(request, db, lang, texts=data, text_errors=service_errors(exc), status_code=422)
    return redirect(request, f"/services/voicemail?lang={lang}#texts")


@router.post("/voicemail/texts/reset")
async def voicemail_texts_reset(
    request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    form = await request.form()
    lang = _texts_lang(db, str(form.get("lang", "")))
    notifications.reset_texts(db, lang, user=user.username)
    return redirect(request, f"/services/voicemail?lang={lang}#texts")


# --- conferencing --------------------------------------------------------------------------

ROOMS = Kind(
    "conference",
    N_("Conference room"),
    dp.ConferenceRoomIn,
    dp.list_rooms,
    dp.get_room,
    dp.create_room,
    dp.update_room,
    dp.delete_room,
    dp.room_to_dict,
    "/services/conferencing",
    "pages/conferences.html",
    "pages/conference_form.html",
    dp.room_search_fields,
)
register(ROOMS, router, "/services")


# --- media --------------------------------------------------------------------------------


@router.get("/media")
def media(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return _media_page(request, db)


def _media_page(
    request: Request,
    db: Session,
    tts_values: dict[str, Any] | None = None,
    tts_errors: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    tts = st.load(db, st.TtsSettings)
    if tts_values is None:
        tts_values = {**tts.model_dump(), "token": ""}
    return page(
        request,
        "pages/media.html",
        status_code=status_code,
        tts=tts,
        tts_values=tts_values,
        tts_errors=tts_errors or {},
        tts_kinds=[(k, media_svc.KINDS[k]) for k in tts_svc.KINDS],
        lv=list_page(request, media_svc.list_media(db), media_svc.search_fields),
        kinds=media_svc.KINDS,
        system=st.load(db, st.SystemSettings),
        record_kinds=[(k, media_svc.KINDS[k]) for k in rec_svc.KINDS],
        record_phones=call_phones(db),
    )


def call_phones(db: Session) -> list[Any]:
    """Phones the PBX can ring (test calls, recording by phone)."""
    return [p for p in phone_svc.list_phones(db) if p.enabled and p.tech in calls_svc.CHANNEL_TECH]


# before /media/{kind}, which would take "record" or "tts" as a kind

# --- text to speech ---


@router.post("/media/tts-settings")
async def tts_settings_save(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    form = await request.form()
    current = st.load(db, st.TtsSettings)
    # a kept token belongs to the old server (settings_api.SECRET_BOUND)
    try:
        url_changed = st.TtsSettings(url=str(form.get("url", ""))).url != current.url
    except ValueError:
        url_changed = False  # the form reports the invalid address
    extra = {"token": ""} if url_changed and not form.get("token") else None
    saved, values, errors = await save_settings_form(
        request, db, st.TtsSettings, (), secret_fields=("token",), extra=extra
    )
    if not saved:
        return _media_page(request, db, values, errors, status_code=422)
    return redirect(request, "/services/media#tts")


@router.get("/media/tts/voices")
def tts_voices(
    request: Request,
    field: str = "tts_voice",
    selected: str = "",
    target: str = "",
    user: User = Depends(ui_user),
    db: Session = Depends(get_db),
) -> Response:
    """The voice select, loaded after the page (the server may be slow or down)."""
    field = field if field in ("tts_voice", "voice") else "tts_voice"
    try:
        voices, error = tts_svc.voices(db), ""
    except ServiceError as exc:
        voices, error = [], str(exc)
    context = {"voices": voices, "error": error, "field": field, "selected": selected, "target": target}
    return render(request, "partials/tts_voices.html", context)


def _tts_text(form: Any) -> str:
    # the IVR editor sends its recording script
    return str(form.get("text") or form.get("prompt_text") or "")


def _tts_speed(form: Any) -> float | None:
    try:
        return float(form["tts_speed"]) if form.get("tts_speed") else None
    except ValueError:
        raise ServiceError(fields={"speed": _("Between 0.5 and 2")}) from None


PREVIEW_MAX_AGE = 600
PREVIEW_KEEP = 20


def _preview_dir() -> Path:
    path = config.get().state_dir / "tts-preview"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _store_preview(audio: bytes) -> str:
    """Keep a preview for the audio element: at most ``PREVIEW_KEEP`` files, none older than 10 minutes."""
    folder = _preview_dir()
    files = sorted(folder.glob("*.wav"), key=lambda f: f.stat().st_mtime, reverse=True)
    for i, old in enumerate(files):
        if i >= PREVIEW_KEEP - 1 or time.time() - old.stat().st_mtime > PREVIEW_MAX_AGE:
            old.unlink(missing_ok=True)
    token = secrets.token_hex(16)
    (folder / f"{token}.wav").write_bytes(audio)
    return token


@router.post("/media/tts/player")
async def tts_player(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    """Speak the text without storing it; the page plays it."""
    form = await request.form()
    ctx = _ctx(form.get("ctx"))
    try:
        audio = await run_in_threadpool(
            tts_svc.synthesize, db, _tts_text(form), str(form.get("tts_voice", "")), _tts_speed(form)
        )
    except ServiceError as exc:
        error = "; ".join(service_errors(exc).values()) or str(exc)
        return render(request, "partials/tts_player.html", {"ctx": ctx, "error": error, "src": ""})
    token = await run_in_threadpool(_store_preview, audio)
    src = f"/services/media/tts/preview/{token}"
    return render(request, "partials/tts_player.html", {"ctx": ctx, "error": "", "src": src})


@router.get("/media/tts/preview/{token}")
def tts_preview(token: str, user: User = Depends(ui_user)) -> Response:
    if not rec_svc.TOKEN_RE.match(token):
        raise HTTPException(404)
    path = _preview_dir() / f"{token}.wav"
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/wav")


@router.post("/media/tts")
async def tts_create(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    form = await request.form()
    ctx = _ctx(form.get("ctx"))
    kind = "ivr_prompt" if ctx == "ivr" else str(form.get("kind", ""))
    try:
        item = await run_in_threadpool(
            tts_svc.create,
            db,
            kind,
            str(form.get("name", "")),
            _tts_text(form),
            str(form.get("tts_voice", "")),
            _tts_speed(form),
            user.username,
        )
    except ServiceError as exc:
        db.rollback()
        error = "; ".join(service_errors(exc).values()) or str(exc)
        return render(request, "partials/tts_result.html", {"ctx": ctx, "error": error, "new_media": None})
    context = {"ctx": ctx, "error": "", "new_media": item, **_new_media_context(request, db, ctx, item)}
    resp = render(request, "partials/tts_result.html", context)
    return dirty_trigger(resp) if ctx == "media" else resp


# "ctx": the page that started the recording (media: the file list, ivr: the announcement select)
RECORD_CTX = ("media", "ivr")


def _ctx(value: object) -> str:
    return value if isinstance(value, str) and value in RECORD_CTX else "media"


def _new_media_context(request: Request, db: Session, ctx: str, item: MediaFile) -> dict[str, Any]:
    """What partials/media_oob.html needs to show a new file on the page that created it."""
    if ctx == "ivr":
        return {"values": {"prompt_media_id": item.id}, "errors": {}, "prompts": ivr_svc.list_prompts(db)}
    return {
        "lv": list_page(request, media_svc.list_media(db), media_svc.search_fields),
        "kinds": media_svc.KINDS,
    }


def _record_status(
    request: Request, db: Session, token: str, ctx: str, status: rec_svc.Status | None, error: str = ""
) -> Response:
    context: dict[str, Any] = {"token": token, "ctx": ctx, "status": status, "error": error}
    if status is not None and status.media is not None:
        context.update(new_media=status.media, **_new_media_context(request, db, ctx, status.media))
    resp = render(request, "partials/record_status.html", context)
    return dirty_trigger(resp) if status is not None and status.media is not None and ctx == "media" else resp


@router.post("/media/record")
async def media_record(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    form = await request.form()
    ctx = _ctx(form.get("ctx"))
    try:
        token = rec_svc.start(
            db, str(form.get("extension", "")), str(form.get("kind", "")), str(form.get("name", "")), user.username
        )
    except ServiceError as exc:
        db.rollback()
        return _record_status(request, db, "", ctx, None, "; ".join(service_errors(exc).values()) or str(exc))
    return _record_status(request, db, token, ctx, rec_svc.Status("ringing", "", ""))


@router.post("/media/record/{token}")
def media_record_status(
    request: Request, token: str, ctx: str = "media", user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    ctx = _ctx(ctx)
    try:
        status = rec_svc.poll(db, token, user.username)
    except NotFound as exc:
        return _record_status(request, db, "", ctx, None, str(exc))
    return _record_status(request, db, token, ctx, status)


@router.post("/media/{kind}")
async def media_upload(
    request: Request, kind: str, file: UploadFile, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    data = await file.read(media_svc.MAX_UPLOAD + 1)
    try:
        media_svc.add_media(db, kind, file.filename or "upload.wav", data, user.username)
    except ServiceError as exc:
        db.rollback()
        msg = "; ".join(service_errors(exc).values())
        return HTMLResponse(
            render(request, "partials/alert.html", {"level": "danger", "message": msg}).body, status_code=422
        )
    resp = render(
        request,
        "partials/media_table.html",
        {"lv": list_page(request, media_svc.list_media(db), media_svc.search_fields), "kinds": media_svc.KINDS},
    )
    return dirty_trigger(resp)


@router.delete("/media/file/{media_id}")
def media_delete(
    request: Request, media_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    try:
        media_svc.delete_media(db, media_id, user.username)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from None
    return dirty_trigger(Response(""))


@router.get("/media/file/{media_id}")
def media_download(media_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    media = db.get(MediaFile, media_id)
    if media is None or not media_svc.media_path(media).exists():
        raise HTTPException(404, _("Media file not found"))
    return FileResponse(
        media_svc.media_path(media), media_type="audio/wav", filename=f"{media.name.rsplit('.', 1)[0]}.wav"
    )
