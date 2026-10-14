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
from sqlalchemy.orm import Session

from phonix.core.models import User
from phonix.services import apply as apply_svc
from phonix.services import settings_api
from phonix.services import status as status_svc
from phonix.services.common import NotFound, ServiceError, dirty_areas
from phonix.services.resources import RESOURCES, Resource
from phonix.web.deps import api_user, get_db

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
