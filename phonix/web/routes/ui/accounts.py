"""Accounts: phones and providers."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from phonix.core.models import User
from phonix.i18n import N_, _
from phonix.services import phones as phone_svc
from phonix.services import providers as provider_svc
from phonix.services import status as status_svc
from phonix.services.common import NotFound, ServiceError
from phonix.web.deps import form_to_dict, get_db, ui_user
from phonix.web.routes.ui.common import dirty_trigger, model_values, page, redirect, service_errors
from phonix.web.templating import flash, render

router = APIRouter(prefix="/accounts")

TECH_LABELS = {"pjsip": "SIP", "iax": "IAX", "external": N_("External")}


def _not_found(exc: NotFound) -> Response:
    from fastapi import HTTPException

    raise HTTPException(404, str(exc))


# --- phones ---------------------------------------------------------------------


@router.get("/phones")
def phone_list(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return page(
        request,
        "pages/phones.html",
        phones=phone_svc.list_phones(db),
        providers={p.id: p for p in provider_svc.list_providers(db)},
        techs=TECH_LABELS,
    )


@router.get("/phones/status")
def phone_status(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    """htmx 4 partials: one <hx-partial> per phone status cell."""
    return render(
        request,
        "partials/phone_status.html",
        {"phones": phone_svc.list_phones(db), "ast": status_svc.asterisk_status()},
    )


def _phone_form(
    request: Request,
    db: Session,
    values: dict[str, Any],
    errors: dict[str, str],
    phone_id: int | None,
    status_code: int = 200,
) -> Response:
    providers = provider_svc.list_providers(db)
    return page(
        request,
        "pages/phone_form.html",
        status_code=status_code,
        values=values,
        errors=errors,
        phone_id=phone_id,
        is_new=phone_id is None,
        providers=providers,
        techs=TECH_LABELS,
    )


@router.get("/phones/new")
def phone_new(
    request: Request, tech: str = "pjsip", user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    if tech not in TECH_LABELS:
        tech = "pjsip"
    values = model_values(phone_svc.PhoneIn, phone_svc.defaults(db, tech))
    return _phone_form(request, db, values, {}, None)


@router.get("/phones/{phone_id}")
def phone_edit(
    request: Request, phone_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    try:
        phone = phone_svc.get_phone(db, phone_id)
    except NotFound as exc:
        return _not_found(exc)
    return _phone_form(request, db, phone_svc.to_dict(phone), {}, phone_id)


def _provider_callerids(form: FormData) -> dict[int, str]:
    out: dict[int, str] = {}
    for key in form:
        m = re.fullmatch(r"cid_(\d+)", key)
        value = form.get(key)
        if m and isinstance(value, str) and value.strip():
            out[int(m.group(1))] = value.strip()
    return out


async def _save_phone(request: Request, db: Session, user: User, phone_id: int | None) -> Response:
    form = await request.form()
    data = form_to_dict(form, phone_svc.PhoneIn)
    data["provider_callerids"] = _provider_callerids(form)
    try:
        parsed = phone_svc.parse_phone(data)
        if phone_id is None:
            phone = phone_svc.create_phone(db, parsed, user.username)
            flash(request, _("Phone %(extension)s created.", extension=phone.extension))
        else:
            phone = phone_svc.update_phone(db, phone_id, parsed, user.username)
            flash(request, _("Phone %(extension)s saved.", extension=phone.extension))
    except NotFound as exc:
        return _not_found(exc)
    except ServiceError as exc:
        db.rollback()
        values = model_values(phone_svc.PhoneIn, data)
        return _phone_form(request, db, values, service_errors(exc), phone_id, status_code=422)
    return redirect(request, "/accounts/phones")


@router.post("/phones/new")
async def phone_create(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return await _save_phone(request, db, user, None)


@router.post("/phones/{phone_id}")
async def phone_update(
    request: Request, phone_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    return await _save_phone(request, db, user, phone_id)


@router.delete("/phones/{phone_id}")
def phone_delete(
    request: Request, phone_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    try:
        phone_svc.delete_phone(db, phone_id, user.username)
    except NotFound as exc:
        return _not_found(exc)
    return dirty_trigger(Response(""))


@router.post("/phones/{phone_id}/toggle")
def phone_toggle(
    request: Request, phone_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    try:
        phone = phone_svc.get_phone(db, phone_id)
        phone = phone_svc.set_enabled(db, phone_id, not phone.enabled, user.username)
    except NotFound as exc:
        return _not_found(exc)
    resp = render(
        request,
        "partials/phone_row.html",
        {"p": phone, "providers": {p.id: p for p in provider_svc.list_providers(db)}, "techs": TECH_LABELS},
    )
    return dirty_trigger(resp)


# --- providers ------------------------------------------------------------------


@router.get("/providers")
def provider_list(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return page(request, "pages/providers.html", providers=provider_svc.list_providers(db), techs=TECH_LABELS)


def _provider_form(
    request: Request,
    db: Session,
    values: dict[str, Any],
    errors: dict[str, str],
    provider_id: int | None,
    status_code: int = 200,
) -> Response:
    others = [p for p in provider_svc.list_providers(db) if p.id != provider_id]
    return page(
        request,
        "pages/provider_form.html",
        status_code=status_code,
        values=values,
        errors=errors,
        provider_id=provider_id,
        is_new=provider_id is None,
        others=others,
        destinations=provider_svc.destinations(db),
        techs=TECH_LABELS,
    )


@router.get("/providers/new")
def provider_new(
    request: Request, tech: str = "pjsip", user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    values = model_values(
        provider_svc.ProviderIn, {**provider_svc.defaults(), "tech": "iax" if tech == "iax" else "pjsip"}
    )
    return _provider_form(request, db, values, {}, None)


@router.get("/providers/{provider_id}")
def provider_edit(
    request: Request, provider_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    try:
        provider = provider_svc.get_provider(db, provider_id)
    except NotFound as exc:
        return _not_found(exc)
    return _provider_form(request, db, provider_svc.to_dict(provider), {}, provider_id)


def _incoming_routes(form: FormData) -> list[dict[str, Any]]:
    """Rows are submitted as route_pattern_<i> + route_dest_<i> ("type:id")."""
    rows = []
    keys = sorted({k.rsplit("_", 1)[1] for k in form if k.startswith("route_dest_")})
    for idx in keys:
        dest = str(form.get(f"route_dest_{idx}", ""))
        if ":" not in dest:
            continue
        dest_type, dest_id = dest.split(":", 1)
        if not dest_id.isdigit():
            continue
        rows.append(
            {
                "pattern": str(form.get(f"route_pattern_{idx}", "")),
                "dest_type": dest_type,
                "dest_id": int(dest_id),
            }
        )
    return rows


async def _save_provider(request: Request, db: Session, user: User, provider_id: int | None) -> Response:
    form = await request.form()
    data = form_to_dict(form, provider_svc.ProviderIn)
    data["incoming_routes"] = _incoming_routes(form)
    if data.get("failover_provider_id") in ("", None):
        data["failover_provider_id"] = None
    try:
        parsed = provider_svc.parse_provider(data)
        if provider_id is None:
            provider = provider_svc.create_provider(db, parsed, user.username)
            flash(request, _("Provider %(name)s created.", name=provider.name))
        else:
            provider = provider_svc.update_provider(db, provider_id, parsed, user.username)
            flash(request, _("Provider %(name)s saved.", name=provider.name))
    except NotFound as exc:
        return _not_found(exc)
    except ServiceError as exc:
        db.rollback()
        values = model_values(provider_svc.ProviderIn, data)
        return _provider_form(request, db, values, service_errors(exc), provider_id, status_code=422)
    return redirect(request, "/accounts/providers")


@router.post("/providers/new")
async def provider_create(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return await _save_provider(request, db, user, None)


@router.post("/providers/{provider_id}")
async def provider_update(
    request: Request, provider_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    return await _save_provider(request, db, user, provider_id)


@router.delete("/providers/{provider_id}")
def provider_delete(
    request: Request, provider_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    try:
        provider_svc.delete_provider(db, provider_id, user.username)
    except NotFound as exc:
        return _not_found(exc)
    return dirty_trigger(Response(""))


@router.post("/providers/{provider_id}/toggle")
def provider_toggle(
    request: Request, provider_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    try:
        provider = provider_svc.get_provider(db, provider_id)
        provider = provider_svc.set_enabled(db, provider_id, not provider.enabled, user.username)
    except NotFound as exc:
        return _not_found(exc)
    return dirty_trigger(render(request, "partials/provider_row.html", {"p": provider, "techs": TECH_LABELS}))
