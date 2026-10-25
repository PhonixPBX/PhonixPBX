# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Services: e-mail notifications, voicemail, conferencing and media."""

from __future__ import annotations

import subprocess
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.orm import Session

from phonix import config, i18n
from phonix.core import settings as st
from phonix.core.models import MediaFile, User
from phonix.i18n import N_, _
from phonix.notify import VARIABLES
from phonix.services import dialplan as dp
from phonix.services import media as media_svc
from phonix.services import notifications
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
    return page(
        request,
        "pages/media.html",
        lv=list_page(request, media_svc.list_media(db), media_svc.search_fields),
        kinds=media_svc.KINDS,
        system=st.load(db, st.SystemSettings),
    )


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
