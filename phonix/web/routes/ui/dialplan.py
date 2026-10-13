# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Dialplan: applications, call groups, transfers/parking and the printable overview."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from phonix.core import settings as st
from phonix.core.models import User
from phonix.i18n import N_, _
from phonix.services import dialplan as dp
from phonix.services import phones as phone_svc
from phonix.services import providers as provider_svc
from phonix.services.common import NotFound, ServiceError, parse
from phonix.web.deps import form_to_dict, get_db, ui_user
from phonix.web.routes.ui.common import (
    dirty_trigger,
    model_values,
    page,
    redirect,
    save_settings_form,
    service_errors,
)
from phonix.web.templating import flash

router = APIRouter(prefix="/dialplan")


def _404(exc: NotFound) -> Response:
    raise HTTPException(404, str(exc))


# --- generic CRUD for the three simple object types ----------------------------------


@dataclass(frozen=True)
class Kind:
    """Describes one simple object type for the generic CRUD routes."""

    name: str
    title: str
    schema: type[BaseModel]
    list_fn: Callable[..., Any]
    get_fn: Callable[..., Any]
    create_fn: Callable[..., Any]
    update_fn: Callable[..., Any]
    delete_fn: Callable[..., Any]
    to_dict: Callable[..., dict[str, Any]]
    base: str
    list_tpl: str
    form_tpl: str


APPS = Kind(
    "application",
    N_("Application"),
    dp.ApplicationIn,
    dp.list_applications,
    dp.get_application,
    dp.create_application,
    dp.update_application,
    dp.delete_application,
    dp.application_to_dict,
    "/dialplan/applications",
    "pages/applications.html",
    "pages/application_form.html",
)
GROUPS = Kind(
    "callgroup",
    N_("Call group"),
    dp.CallGroupIn,
    dp.list_callgroups,
    dp.get_callgroup,
    dp.create_callgroup,
    dp.update_callgroup,
    dp.delete_callgroup,
    dp.callgroup_to_dict,
    "/dialplan/callgroups",
    "pages/callgroups.html",
    "pages/callgroup_form.html",
)


def _form_ctx(db: Session, kind: Kind) -> dict[str, Any]:
    if kind is GROUPS:
        return {"phones": phone_svc.list_phones(db)}
    return {}


def register(kind: Kind, target: APIRouter = router, prefix: str = "/dialplan") -> None:
    """Add list/new/edit/save/delete routes for ``kind`` to ``target``."""
    base = kind.base.removeprefix(prefix)

    def form_page(
        request: Request,
        db: Session,
        values: dict[str, Any],
        errors: dict[str, str],
        obj_id: int | None,
        status_code: int = 200,
    ) -> Response:
        return page(
            request,
            kind.form_tpl,
            status_code=status_code,
            values=values,
            errors=errors,
            obj_id=obj_id,
            is_new=obj_id is None,
            kind=kind,
            **_form_ctx(db, kind),
        )

    @target.get(base, name=f"{kind.name}_list")
    def list_view(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
        return page(
            request,
            kind.list_tpl,
            items=kind.list_fn(db),
            kind=kind,
            phones={p.id: p for p in phone_svc.list_phones(db)},
        )

    @target.get(base + "/new", name=f"{kind.name}_new")
    def new_view(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
        return form_page(request, db, model_values(kind.schema, {}), {}, None)

    @target.get(base + "/{obj_id}", name=f"{kind.name}_edit")
    def edit_view(
        request: Request, obj_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
    ) -> Response:
        try:
            obj = kind.get_fn(db, obj_id)
        except NotFound as exc:
            return _404(exc)
        return form_page(request, db, kind.to_dict(obj), {}, obj_id)

    async def save(request: Request, db: Session, user: User, obj_id: int | None) -> Response:
        form = await request.form()
        data = form_to_dict(form, kind.schema)
        try:
            parsed = parse(kind.schema, data)
            if obj_id is None:
                obj = kind.create_fn(db, parsed, user.username)
            else:
                obj = kind.update_fn(db, obj_id, parsed, user.username)
        except NotFound as exc:
            return _404(exc)
        except ServiceError as exc:
            db.rollback()
            return form_page(request, db, model_values(kind.schema, data), service_errors(exc), obj_id, 422)
        name = getattr(obj, "name", None) or getattr(obj, "username", "")
        flash(request, _("Changes saved: %(kind)s %(name)s.", kind=_(kind.title), name=name))
        return redirect(request, kind.base)

    @target.post(base + "/new", name=f"{kind.name}_create")
    async def create_view(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
        return await save(request, db, user, None)

    @target.post(base + "/{obj_id}", name=f"{kind.name}_update")
    async def update_view(
        request: Request, obj_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
    ) -> Response:
        return await save(request, db, user, obj_id)

    @target.delete(base + "/{obj_id}", name=f"{kind.name}_delete")
    def delete_view(
        request: Request, obj_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)
    ) -> Response:
        try:
            kind.delete_fn(db, obj_id, user.username)
        except NotFound as exc:
            return _404(exc)
        return dirty_trigger(Response(""))


register(APPS)
register(GROUPS)


# --- transfers & parking ----------------------------------------------------------------


@router.get("/transfers")
def transfers(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return page(request, "pages/transfers.html", values=st.load(db, st.FeatureSettings).model_dump())


@router.post("/transfers")
async def transfers_save(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    saved, values, errors = await save_settings_form(request, db, st.FeatureSettings, ("dialplan",))
    if not saved:
        return page(request, "pages/transfers.html", status_code=422, values=values, errors=errors)
    return redirect(request, "/dialplan/transfers")


# --- printable overview (legacy printable_dialplan.php) -----------------------------------


@router.get("/print")
def overview(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    rows: list[dict[str, str]] = []
    for p in phone_svc.list_phones(db):
        rows.append(
            {
                "number": p.extension,
                "type": _("Phone (%(tech)s)", tech={"pjsip": "SIP", "iax": "IAX", "external": _("external")}[p.tech]),
                "name": p.callerid,
                "info": p.description,
                "public": p.public_name if p.public_access and p.public_name else (_("yes") if p.public_access else ""),
            }
        )
    for g in dp.list_callgroups(db):
        if g.extension:
            rows.append(
                {
                    "number": g.extension,
                    "type": _("Call group"),
                    "name": g.name,
                    "info": ", ".join(m.phone.extension for m in g.members),
                    "public": g.public_name or (_("yes") if g.public_access else ""),
                }
            )
    for r in dp.list_rooms(db):
        rows.append(
            {
                "number": r.number,
                "type": _("Conference"),
                "name": r.name,
                "info": _("PIN protected") if r.pin else "",
                "public": _("yes") if r.public_access else "",
            }
        )
    for a in dp.list_applications(db):
        rows.append(
            {
                "number": a.extension,
                "type": _("Application"),
                "name": a.name,
                "info": a.description,
                "public": _("yes") if a.public_access else "",
            }
        )
    rows.sort(key=lambda r: (len(r["number"]), r["number"]))
    features = st.load(db, st.FeatureSettings)
    return page(
        request,
        "pages/dialplan_print.html",
        rows=rows,
        features=features,
        providers=provider_svc.list_providers(db),
        destination_label=lambda t, i: provider_svc.destination_label(db, t, i),
    )
