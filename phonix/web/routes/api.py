# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""JSON REST API (``/api/v1``) - same service layer as the UI.

Authentication: a bearer token (Advanced > API tokens), or the UI session
cookie plus the ``X-CSRF-Token`` header.
"""

# NOTE: no "from __future__ import annotations" here - FastAPI must see the real
# pydantic classes of the generated CRUD endpoints (closure locals).

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from phonix.core.models import User
from phonix.services import apply as apply_svc
from phonix.services import calls as calls_svc
from phonix.services import hours as hours_svc
from phonix.services import settings_api
from phonix.services import status as status_svc
from phonix.services.common import NotFound, ServiceError, dirty_areas
from phonix.services.resources import RESOURCES, Resource
from phonix.web.deps import api_caller, api_user, get_db

router = APIRouter(prefix="/api/v1", tags=["api"])


def _error(exc: ServiceError) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, str(exc))
    return HTTPException(422, {"message": exc.message, "fields": exc.fields})


def _read_only(request: Request) -> bool:
    token = getattr(request.state, "api_token", None)
    return bool(token and token.read_only)


def crud(res: Resource) -> None:
    path, tag, schema, to_dict = res.path, res.tag, res.schema, res.to_dict

    @router.get(path, tags=[tag], summary=f"List {tag}")
    def list_items(
        request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)
    ) -> list[dict[str, Any]]:
        return [res.public(o, _read_only(request)) for o in res.list_fn(db)]

    @router.get(path + "/{item_id}", tags=[tag], summary=f"Get one of {tag}")
    def get_item(
        item_id: int, request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)
    ) -> dict[str, Any]:
        try:
            return res.public(res.get_fn(db, item_id), _read_only(request))
        except ServiceError as exc:
            raise _error(exc) from None

    # FastAPI needs the real schema class in the annotation (runtime value)
    @router.post(path, tags=[tag], status_code=201, summary=f"Create {tag}")
    def create_item(
        body: schema,  # type: ignore[valid-type]
        user: User = Depends(api_user),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:  # type: ignore[valid-type]
        try:
            obj = res.create_fn(db, res.parse(body.model_dump()), user.username)  # type: ignore[attr-defined]
        except ServiceError as exc:
            db.rollback()
            raise _error(exc) from None
        return to_dict(obj)

    @router.put(path + "/{item_id}", tags=[tag], summary=f"Replace {tag}")
    def update_item(
        item_id: int,
        body: schema,  # type: ignore[valid-type]
        user: User = Depends(api_user),
        db: Session = Depends(get_db),
    ) -> dict[str, Any]:
        try:
            obj = res.update_fn(db, item_id, res.parse(body.model_dump()), user.username)  # type: ignore[attr-defined]
        except ServiceError as exc:
            db.rollback()
            raise _error(exc) from None
        return to_dict(obj)

    @router.delete(path + "/{item_id}", tags=[tag], status_code=204, summary=f"Delete {tag}")
    def delete_item(item_id: int, user: User = Depends(api_user), db: Session = Depends(get_db)) -> Response:
        try:
            res.delete_fn(db, item_id, user.username)
        except ServiceError as exc:
            raise _error(exc) from None
        return Response(status_code=204)


for _res in RESOURCES:
    crud(_res)


class HoursMode(BaseModel):
    mode: hours_svc.Mode = Field(description="auto: follow the schedule; open or closed: until switched back")


@router.get("/business-hours/{hours_id}/status", tags=["business hours"], summary="Open right now, and the live mode")
def business_hours_status(hours_id: int, user: User = Depends(api_user), db: Session = Depends(get_db)) -> Any:
    try:
        return hours_svc.live_status(db, hours_id)
    except ServiceError as exc:
        raise _error(exc) from None


@router.put(
    "/business-hours/{hours_id}/mode",
    tags=["business hours"],
    summary="Switch the live mode (takes effect immediately, no apply needed)",
)
def business_hours_mode(
    hours_id: int, body: HoursMode, user: User = Depends(api_user), db: Session = Depends(get_db)
) -> Any:
    try:
        hours_svc.set_mode(db, hours_id, body.mode, user.username)
        return hours_svc.live_status(db, hours_id)
    except ServiceError as exc:
        db.rollback()
        raise _error(exc) from None


@router.get("/settings/{group}", tags=["settings"])
def get_settings(group: str, user: User = Depends(api_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return settings_api.read_group(db, group)
    except ServiceError as exc:
        raise _error(exc) from None


@router.patch("/settings/{group}", tags=["settings"])
async def patch_settings(
    group: str, request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(422, "expected a JSON object")
    try:
        return settings_api.patch_group(db, group, body, user.username)
    except ServiceError as exc:
        db.rollback()
        raise _error(exc) from None


@router.get("/pending", tags=["apply"], summary="Areas with changes that are not applied yet")
def pending(user: User = Depends(api_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"pending": dirty_areas(db)}


@router.post("/apply", tags=["apply"], summary="Generate and activate the configuration")
def apply(user: User = Depends(api_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    result = apply_svc.apply(db, user=user.username)
    return {
        "ok": result.ok,
        "changed_files": result.changed_files,
        "components": result.components,
        "actions": result.actions,
        "errors": result.errors,
    }


@router.get(
    "/metrics",
    tags=["status"],
    summary="Prometheus metrics",
    response_class=PlainTextResponse,
    responses={200: {"content": {"text/plain": {}}}},
)
def metrics(user: User = Depends(api_user), db: Session = Depends(get_db)) -> Response:
    """Prometheus text format; scrape with a read-only bearer token."""
    from phonix.services import metrics as metrics_svc

    return Response(metrics_svc.collect(db), media_type=metrics_svc.CONTENT_TYPE)


@router.get("/status", tags=["status"])
def status(user: User = Depends(api_user)) -> dict[str, Any]:
    return {"system": status_svc.system_info(), "asterisk": status_svc.asterisk_status()}


class CallRequest(BaseModel):
    extension: str = Field(description="Extension of the SIP or IAX phone to ring first", examples=["100"])
    number: str = Field(description="Number to dial from that phone: digits, *, # and +", examples=["0441234567"])


class CallResult(BaseModel):
    extension: str
    number: str
    status: str = Field(description="'ringing': the phone rings; the number is dialled when it is answered")


@router.post(
    "/calls",
    tags=["calls"],
    status_code=202,
    response_model=CallResult,
    summary="Ring a phone, then dial a number from it",
)
def originate_call(body: CallRequest, user: User = Depends(api_caller), db: Session = Depends(get_db)) -> Any:
    """Click-to-call. The number is dialled with the phone's own outgoing rules and caller ID.
    Bearer tokens need "may place calls"; read-only tokens with it are accepted."""
    try:
        return calls_svc.originate(db, body.extension, body.number, user.username, via="API")
    except ServiceError as exc:
        db.rollback()
        raise _error(exc) from None
