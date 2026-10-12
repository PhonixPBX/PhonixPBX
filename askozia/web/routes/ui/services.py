"""Services: e-mail notifications, voicemail, conferencing and media."""

from __future__ import annotations

import subprocess

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.orm import Session

from askozia import config
from askozia.core import settings as st
from askozia.core.models import MediaFile, User
from askozia.services import dialplan as dp
from askozia.services import media as media_svc
from askozia.services.common import NotFound, ServiceError
from askozia.web.deps import get_db, ui_user
from askozia.web.routes.ui.common import dirty_trigger, page, redirect, save_settings_form, service_errors
from askozia.web.routes.ui.dialplan import Kind, register
from askozia.web.templating import render

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
    from askozia.core import validation as v

    try:
        to = v.email(to)
    except ValueError as exc:
        return render(request, "partials/alert.html", {"level": "danger", "message": str(exc)})
    msmtprc = config.get().path("/etc/askozia/msmtprc")
    body = f"To: {to}\nSubject: AskoziaPBX test message\n\nE-mail notifications are working.\n"
    try:
        proc = subprocess.run(
            ["msmtp", "-C", str(msmtprc), "-t"], input=body, text=True, capture_output=True, timeout=60, check=False
        )
        ok, detail = proc.returncode == 0, (proc.stderr or proc.stdout).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        ok, detail = False, str(exc)
    if ok:
        return render(request, "partials/alert.html", {"level": "success", "message": f"Test message sent to {to}."})
    return render(
        request,
        "partials/alert.html",
        {"level": "danger", "message": f"Sending failed (did you apply the settings?): {detail[:300]}"},
    )


# --- voicemail ---------------------------------------------------------------------------


@router.get("/voicemail")
def voicemail(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return page(
        request,
        "pages/voicemail.html",
        values=st.load(db, st.VoicemailSettings).model_dump(),
        email_ok=st.load(db, st.EmailSettings).configured,
    )


@router.post("/voicemail")
async def voicemail_save(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    saved, values, errors = await save_settings_form(request, db, st.VoicemailSettings, ("services",))
    if not saved:
        return page(
            request,
            "pages/voicemail.html",
            status_code=422,
            values=values,
            errors=errors,
            email_ok=st.load(db, st.EmailSettings).configured,
        )
    return redirect(request, "/services/voicemail")


# --- conferencing --------------------------------------------------------------------------

ROOMS = Kind(
    "conference",
    "Conference room",
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
)
register(ROOMS, router, "/services")


# --- media --------------------------------------------------------------------------------


@router.get("/media")
def media(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return page(
        request,
        "pages/media.html",
        files=media_svc.list_media(db),
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
    resp = render(request, "partials/media_table.html", {"files": media_svc.list_media(db), "kinds": media_svc.KINDS})
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
        raise HTTPException(404, "Media file not found")
    return FileResponse(
        media_svc.media_path(media), media_type="audio/wav", filename=f"{media.name.rsplit('.', 1)[0]}.wav"
    )
