# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Dialplan: IVR menus and business hours."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from phonix import i18n
from phonix.core import settings as st
from phonix.core.models import User
from phonix.i18n import _
from phonix.services import calls as calls_svc
from phonix.services import destinations as dst
from phonix.services import hours as hours_svc
from phonix.services import ivr as ivr_svc
from phonix.services import media as media_svc
from phonix.services import phones as phone_svc
from phonix.services.common import NotFound, ServiceError, parse
from phonix.web.deps import form_to_dict, get_db, ui_user
from phonix.web.routes.ui.common import dirty_trigger, model_values, page, redirect, service_errors
from phonix.web.templating import flash, render

router = APIRouter(prefix="/dialplan")


def _404(exc: NotFound) -> Response:
    raise HTTPException(404, str(exc))


def _rows(form: FormData, prefix: str) -> list[str]:
    """Indices of the dynamic rows ``<prefix><index>`` in the order they were submitted
    (= the order on the page, after drag and drop)."""
    seen: list[str] = []
    for key, _value in form.multi_items():
        if key.startswith(prefix):
            idx = key[len(prefix) :]
            if idx not in seen:
                seen.append(idx)
    return seen


def _dest(form: FormData, field: str, data: dict[str, Any], prefix: str) -> None:
    """A destination picker ``field`` ("type:id") into ``<prefix>_dest_type`` / ``_dest_id``."""
    parsed = dst.parse_value(str(form.get(field, "")))
    data[f"{prefix}_dest_type"], data[f"{prefix}_dest_id"] = parsed if parsed else ("", None)


def _alert(request: Request, level: str, message: str, status_code: int = 200) -> Response:
    return render(request, "partials/alert.html", {"level": level, "message": message}, status_code=status_code)


# --- IVR menus ----------------------------------------------------------------------------


def _menu_form_data(form: FormData) -> dict[str, Any]:
    data = form_to_dict(form, ivr_svc.IvrMenuIn)
    if data.get("prompt_media_id") in ("", None):
        data["prompt_media_id"] = None
    _dest(form, "timeout_dest", data, "timeout")
    _dest(form, "invalid_dest", data, "invalid")
    options = []
    for idx in _rows(form, "opt_key_"):
        parsed = dst.parse_value(str(form.get(f"opt_dest_{idx}", "")))
        options.append(
            {
                "key": str(form.get(f"opt_key_{idx}", "")),
                "label": str(form.get(f"opt_label_{idx}", "")),
                "dest_type": parsed[0] if parsed else "",
                "dest_id": parsed[1] if parsed else None,
            }
        )
    data["options"] = options
    return data


def _menu_page(
    request: Request,
    db: Session,
    values: dict[str, Any],
    errors: dict[str, str],
    menu_id: int | None,
    status_code: int = 200,
) -> Response:
    menu = db.get(ivr_svc.IvrMenu, menu_id) if menu_id else None
    sounds = list(ivr_svc.SOUNDS)
    if values.get("prompt_sound") and values["prompt_sound"] not in sounds:
        sounds.insert(0, values["prompt_sound"])
    return page(
        request,
        "pages/ivr_form.html",
        status_code=status_code,
        values=values,
        errors=errors,
        menu_id=menu_id,
        is_new=menu_id is None,
        keys=ivr_svc.KEYS,
        option_choices=dst.choices(db, dst.IVR_TYPES),
        timeout_choices=dst.choices(db, dst.IVR_TIMEOUT_TYPES),
        prompts=ivr_svc.list_prompts(db),
        sounds=sounds,
        dest_value=dst.value,
        flow=ivr_svc.flow(db, menu) if menu else [],
        test_phones=[p for p in phone_svc.list_phones(db) if p.enabled and p.tech in calls_svc.CHANNEL_TECH],
        saved=menu,
    )


@router.get("/ivr")
def ivr_list(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return page(
        request, "pages/ivr_menus.html", items=ivr_svc.list_menus(db), dest_label=lambda t, i: dst.label(db, t, i)
    )


@router.get("/ivr/new")
def ivr_new(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    values = model_values(ivr_svc.IvrMenuIn, {})
    return _menu_page(request, db, values, {}, None)


@router.get("/ivr/{menu_id}")
def ivr_edit(request: Request, menu_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    try:
        menu = ivr_svc.get_menu(db, menu_id)
    except NotFound as exc:
        return _404(exc)
    return _menu_page(request, db, ivr_svc.to_dict(menu), {}, menu_id)


async def _save_menu(request: Request, db: Session, user: User, menu_id: int | None) -> Response:
    form = await request.form()
    data = _menu_form_data(form)
    try:
        parsed = parse(ivr_svc.IvrMenuIn, data)
        if menu_id is None:
            menu = ivr_svc.create_menu(db, parsed, user.username)
        else:
            menu = ivr_svc.update_menu(db, menu_id, parsed, user.username)
    except NotFound as exc:
        return _404(exc)
    except ServiceError as exc:
        db.rollback()
        values = model_values(ivr_svc.IvrMenuIn, data)
        return _menu_page(request, db, values, service_errors(exc), menu_id, status_code=422)
    flash(request, _("IVR menu %(name)s saved.", name=menu.name))
    return redirect(request, "/dialplan/ivr")


@router.post("/ivr/new")
async def ivr_create(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return await _save_menu(request, db, user, None)


@router.post("/ivr/script")
async def ivr_script(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    """The recording script for the options on the page (in the prompt language)."""
    data = _menu_form_data(await request.form())
    options = []
    for o in data["options"]:
        try:
            options.append(parse(ivr_svc.IvrOptionIn, o))
        except ServiceError:
            continue  # rows without a destination yet
    with i18n.language(st.load(db, st.SystemSettings).prompt_language):
        text = ivr_svc.script(db, options)
    return render(request, "partials/ivr_script.html", {"values": {"prompt_text": text}, "errors": {}})


@router.post("/ivr/prompts")
async def ivr_prompt_upload(
    request: Request, file: UploadFile, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    data = await file.read(media_svc.MAX_UPLOAD + 1)
    try:
        media = media_svc.add_media(db, ivr_svc.PROMPT_KIND, file.filename or "announcement.wav", data, user.username)
    except ServiceError as exc:
        db.rollback()
        return _alert(request, "danger", "; ".join(service_errors(exc).values()), status_code=422)
    return render(
        request,
        "partials/ivr_prompt_select.html",
        {"values": {"prompt_media_id": media.id}, "errors": {}, "prompts": ivr_svc.list_prompts(db)},
    )


@router.post("/ivr/{menu_id}")
async def ivr_update(
    request: Request, menu_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    return await _save_menu(request, db, user, menu_id)


@router.delete("/ivr/{menu_id}")
def ivr_delete(
    request: Request, menu_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    try:
        ivr_svc.delete_menu(db, menu_id, user.username)
    except NotFound as exc:
        return _404(exc)
    return dirty_trigger(Response(""))


@router.post("/ivr/{menu_id}/toggle")
def ivr_toggle(
    request: Request, menu_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    try:
        menu = ivr_svc.get_menu(db, menu_id)
        menu = ivr_svc.set_enabled(db, menu_id, not menu.enabled, user.username)
    except NotFound as exc:
        return _404(exc)
    return dirty_trigger(
        render(request, "partials/ivr_row.html", {"m": menu, "dest_label": lambda t, i: dst.label(db, t, i)})
    )


@router.post("/ivr/{menu_id}/test")
async def ivr_test(
    request: Request, menu_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    form = await request.form()
    try:
        menu = ivr_svc.get_menu(db, menu_id)
        calls_svc.test_menu(db, str(form.get("extension", "")), menu, user.username)
    except NotFound as exc:
        return _alert(request, "danger", str(exc))
    except ServiceError as exc:
        db.rollback()
        return _alert(request, "danger", "; ".join(service_errors(exc).values()))
    return _alert(
        request,
        "success",
        _(
            "Phone %(extension)s is ringing. Answer it to hear the menu as it was last applied.",
            extension=form.get("extension"),
        ),
    )


# --- business hours ----------------------------------------------------------------------


def _hours_form_data(form: FormData, db: Session, hours_id: int | None) -> dict[str, Any]:
    """The submitted form; saved special periods keep their switch (it is changed by the live toggles only)."""
    data = form_to_dict(form, hours_svc.BusinessHoursIn)
    _dest(form, "open_dest", data, "open")
    _dest(form, "closed_dest", data, "closed")
    data["ranges"] = [
        {
            "weekday": str(form.get(f"range_day_{idx}", "")),
            "start": str(form.get(f"range_start_{idx}", "")),
            # a time input cannot say 24:00: "until 23:59" means until midnight
            "end": "24:00" if form.get(f"range_end_{idx}") == "23:59" else str(form.get(f"range_end_{idx}", "")),
        }
        for idx in _rows(form, "range_day_")
        if form.get(f"range_start_{idx}") or form.get(f"range_end_{idx}")
    ]
    data["holidays"] = [
        {
            "date": str(form.get(f"hol_date_{idx}", "")),
            "name": str(form.get(f"hol_name_{idx}", "")),
            "yearly": form.get(f"hol_yearly_{idx}") == "true",
        }
        for idx in _rows(form, "hol_date_")
        if form.get(f"hol_date_{idx}") or form.get(f"hol_name_{idx}")
    ]
    saved = {sp.id: sp.enabled for sp in hours_svc.get_hours(db, hours_id).specials} if hours_id else {}
    specials = []
    for idx in _rows(form, "sp_id_"):
        name, start, end, code = (str(form.get(f"sp_{k}_{idx}", "")).strip() for k in ("name", "start", "end", "code"))
        sid = str(form.get(f"sp_id_{idx}", ""))
        if not (sid or name or start or end or code):
            continue  # an empty new row
        parsed = dst.parse_value(str(form.get(f"sp_dest_{idx}", "")))
        special_id = int(sid) if sid.isdigit() else None
        enabled = saved[special_id] if special_id in saved else form.get(f"sp_enabled_{idx}") == "true"
        specials.append(
            {
                "id": special_id,
                "name": name,
                "enabled": enabled,
                "start": start or None,
                "end": end or None,
                "yearly": form.get(f"sp_yearly_{idx}") == "true",
                "feature_code": code,
                "dest_type": parsed[0] if parsed else "",
                "dest_id": parsed[1] if parsed else None,
            }
        )
    data["specials"] = specials
    return data


def _week(values: dict[str, Any]) -> list[dict[str, Any]]:
    """Per weekday: its ranges with the submitted row index, and bars for the week chart."""
    days: list[dict[str, Any]] = [{"ranges": [], "bars": []} for _day in range(7)]
    for idx, r in enumerate(values.get("ranges") or []):
        try:
            day = int(r["weekday"])
        except (TypeError, ValueError, KeyError):
            continue
        if not 0 <= day <= 6:
            continue
        days[day]["ranges"].append({**r, "idx": idx})
        try:
            start = hours_svc._minutes(str(r["start"]))
            end = hours_svc._minutes(str(r["end"]))
        except (ValueError, IndexError):
            continue
        if start < end:
            days[day]["bars"].append({"left": round(start / 14.4, 2), "width": round((end - start) / 14.4, 2)})
    return days


def _hours_page(
    request: Request,
    db: Session,
    values: dict[str, Any],
    errors: dict[str, str],
    hours_id: int | None,
    status_code: int = 200,
) -> Response:
    live = hours_svc.live_status(db, hours_id) if hours_id else None
    # special periods may point to business hours, one level deep: not to themselves or to ones with periods
    excluded = {f"hours:{h.id}" for h in hours_svc.list_hours(db) if h.id == hours_id or h.specials}
    special_choices = [
        (title, [(value, text) for value, text in options if value not in excluded])
        for title, options in dst.choices(db, dst.SPECIAL_TYPES)
    ]
    return page(
        request,
        "pages/hours_form.html",
        status_code=status_code,
        values=values,
        errors=errors,
        hours_id=hours_id,
        is_new=hours_id is None,
        week=_week(values),
        weekdays=hours_svc.WEEKDAYS,
        today=dt.date.today().weekday(),
        now_pct=round((dt.datetime.now().hour * 60 + dt.datetime.now().minute) / 14.4, 2),
        choices=dst.choices(db, dst.HOURS_TYPES),
        special_choices=[(title, options) for title, options in special_choices if options],
        dest_value=dst.value,
        live=live,
    )


def _status_rows(db: Session, only: int | None = None) -> list[tuple[Any, dict[str, Any]]]:
    """The list rows: business hours with their status, mode and special period switches."""
    now = dt.datetime.now()
    loaded = hours_svc.load_runtime()
    rt = loaded or hours_svc.Runtime()
    items = hours_svc.list_hours(db)
    others = {h.id: h for h in items}
    return [
        (
            h,
            {
                **hours_svc.status(h, rt, now, others),
                "mode": None if loaded is None else rt.modes.get(h.id, "auto"),
                "specials": hours_svc.special_states(h, rt, now.date()),
            },
        )
        for h in items
        if only is None or h.id == only
    ]


@router.get("/hours")
def hours_list(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return page(request, "pages/hours.html", items=_status_rows(db), dest_label=lambda t, i: dst.label(db, t, i))


@router.get("/hours/new")
def hours_new(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    values = model_values(hours_svc.BusinessHoursIn, hours_svc.defaults())
    return _hours_page(request, db, values, {}, None)


@router.get("/hours/{hours_id}")
def hours_edit(
    request: Request, hours_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    try:
        hours = hours_svc.get_hours(db, hours_id)
    except NotFound as exc:
        return _404(exc)
    return _hours_page(request, db, hours_svc.to_dict(hours), {}, hours_id)


async def _save_hours(request: Request, db: Session, user: User, hours_id: int | None) -> Response:
    form = await request.form()
    try:
        data = _hours_form_data(form, db, hours_id)
    except NotFound as exc:
        return _404(exc)
    try:
        parsed = parse(hours_svc.BusinessHoursIn, data)
        if hours_id is None:
            hours = hours_svc.create_hours(db, parsed, user.username)
        else:
            hours = hours_svc.update_hours(db, hours_id, parsed, user.username)
    except NotFound as exc:
        return _404(exc)
    except ServiceError as exc:
        db.rollback()
        values = model_values(hours_svc.BusinessHoursIn, data)
        return _hours_page(request, db, values, service_errors(exc), hours_id, status_code=422)
    flash(request, _("Business hours %(name)s saved.", name=hours.name))
    return redirect(request, "/dialplan/hours")


@router.post("/hours/new")
async def hours_create(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return await _save_hours(request, db, user, None)


@router.post("/hours/{hours_id}")
async def hours_update(
    request: Request, hours_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    return await _save_hours(request, db, user, hours_id)


@router.delete("/hours/{hours_id}")
def hours_delete(
    request: Request, hours_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    try:
        hours_svc.delete_hours(db, hours_id, user.username)
    except NotFound as exc:
        return _404(exc)
    return dirty_trigger(Response(""))


@router.post("/hours/{hours_id}/mode")
async def hours_mode(
    request: Request, hours_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    form = await request.form()
    error = ""
    try:
        hours_svc.set_mode(db, hours_id, str(form.get("mode", "")), user.username)
    except NotFound as exc:
        return _404(exc)
    except ServiceError as exc:
        db.rollback()
        error = "; ".join(service_errors(exc).values())
    live = hours_svc.live_status(db, hours_id)
    resp = render(request, "partials/hours_mode.html", {"live": live, "hours_id": hours_id, "mode_error": error})
    return HTMLResponse(resp.body)


@router.post("/hours/{hours_id}/special/{special_id}")
async def hours_special(
    request: Request, hours_id: int, special_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    """Switch a special period on or off; answers with the status card, or the list row (``view=row``)."""
    form = await request.form()
    error = ""
    try:
        hours_svc.set_special_active(db, hours_id, special_id, form.get("active") == "true", user.username)
    except NotFound as exc:
        return _404(exc)
    except ServiceError as exc:
        db.rollback()
        error = "; ".join(service_errors(exc).values())
    if form.get("view") == "row":
        [(h, st)] = _status_rows(db, only=hours_id)
        ctx = {"h": h, "st": st, "row_error": error, "dest_label": lambda t, i: dst.label(db, t, i)}
        resp = render(request, "partials/hours_row.html", ctx)
    else:
        live = hours_svc.live_status(db, hours_id)
        resp = render(request, "partials/hours_mode.html", {"live": live, "hours_id": hours_id, "special_error": error})
    return HTMLResponse(resp.body)
