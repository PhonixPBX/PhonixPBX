"""JSON REST API (``/api/v1``) - same service layer as the UI.

Authentication: HTTP Basic with an administrator account, or the UI session
cookie plus the ``X-CSRF-Token`` header.
"""

# NOTE: no "from __future__ import annotations" here - FastAPI must see the real
# pydantic classes of the generated CRUD endpoints (closure locals).

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from askozia.core import settings as st
from askozia.core.models import User
from askozia.services import apply as apply_svc
from askozia.services import dialplan as dp
from askozia.services import manager as ami_svc
from askozia.services import phones as phone_svc
from askozia.services import providers as provider_svc
from askozia.services import status as status_svc
from askozia.services.common import NotFound, ServiceError, dirty_areas, parse
from askozia.web.deps import api_user, get_db

router = APIRouter(prefix="/api/v1", tags=["api"])


def _error(exc: ServiceError) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, str(exc))
    return HTTPException(422, {"message": exc.message, "fields": exc.fields})


def crud(
    path: str,
    tag: str,
    schema: type[BaseModel],
    list_fn: Callable[..., Any],
    get_fn: Callable[..., Any],
    create_fn: Callable[..., Any],
    update_fn: Callable[..., Any],
    delete_fn: Callable[..., Any],
    to_dict: Callable[..., dict[str, Any]],
    parse_fn: Callable[[dict[str, Any]], Any] | None = None,
) -> None:
    parser = parse_fn or (lambda data: parse(schema, data))

    @router.get(path, tags=[tag], summary=f"List {tag}")
    def list_items(user: User = Depends(api_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
        return [to_dict(o) for o in list_fn(db)]

    @router.get(path + "/{item_id}", tags=[tag], summary=f"Get one of {tag}")
    def get_item(item_id: int, user: User = Depends(api_user), db: Session = Depends(get_db)) -> dict[str, Any]:
        try:
            return to_dict(get_fn(db, item_id))
        except ServiceError as exc:
            raise _error(exc) from None

    @router.post(path, tags=[tag], status_code=201, summary=f"Create {tag}")
    def create_item(body: schema, user: User = Depends(api_user), db: Session = Depends(get_db)) -> dict[str, Any]:  # type: ignore[valid-type]
        try:
            obj = create_fn(db, parser(body.model_dump()), user.username)  # type: ignore[attr-defined]
        except ServiceError as exc:
            db.rollback()
            raise _error(exc) from None
        return to_dict(obj)

    @router.put(path + "/{item_id}", tags=[tag], summary=f"Replace {tag}")
    def update_item(
        item_id: int, body: schema, user: User = Depends(api_user), db: Session = Depends(get_db)
    ) -> dict[str, Any]:  # type: ignore[valid-type]
        try:
            obj = update_fn(db, item_id, parser(body.model_dump()), user.username)  # type: ignore[attr-defined]
        except ServiceError as exc:
            db.rollback()
            raise _error(exc) from None
        return to_dict(obj)

    @router.delete(path + "/{item_id}", tags=[tag], status_code=204, summary=f"Delete {tag}")
    def delete_item(item_id: int, user: User = Depends(api_user), db: Session = Depends(get_db)) -> Response:
        try:
            delete_fn(db, item_id, user.username)
        except ServiceError as exc:
            raise _error(exc) from None
        return Response(status_code=204)


crud(
    "/phones",
    "phones",
    phone_svc.PhoneIn,
    phone_svc.list_phones,
    phone_svc.get_phone,
    phone_svc.create_phone,
    phone_svc.update_phone,
    phone_svc.delete_phone,
    phone_svc.to_dict,
    phone_svc.parse_phone,
)
crud(
    "/providers",
    "providers",
    provider_svc.ProviderIn,
    provider_svc.list_providers,
    provider_svc.get_provider,
    provider_svc.create_provider,
    provider_svc.update_provider,
    provider_svc.delete_provider,
    provider_svc.to_dict,
    provider_svc.parse_provider,
)
crud(
    "/callgroups",
    "call groups",
    dp.CallGroupIn,
    dp.list_callgroups,
    dp.get_callgroup,
    dp.create_callgroup,
    dp.update_callgroup,
    dp.delete_callgroup,
    dp.callgroup_to_dict,
)
crud(
    "/conferences",
    "conference rooms",
    dp.ConferenceRoomIn,
    dp.list_rooms,
    dp.get_room,
    dp.create_room,
    dp.update_room,
    dp.delete_room,
    dp.room_to_dict,
)
crud(
    "/applications",
    "applications",
    dp.ApplicationIn,
    dp.list_applications,
    dp.get_application,
    dp.create_application,
    dp.update_application,
    dp.delete_application,
    dp.application_to_dict,
)
crud(
    "/ami-users",
    "manager users",
    ami_svc.AmiUserIn,
    ami_svc.list_ami_users,
    ami_svc.get_ami_user,
    ami_svc.create_ami_user,
    ami_svc.update_ami_user,
    ami_svc.delete_ami_user,
    ami_svc.to_dict,
)


SETTINGS = {st.group_name(m): m for m in st.ALL_GROUPS}
SECRET_SETTINGS = {"email": ("password",)}
SETTINGS_AREAS = {
    "system": ("system", "network", "telephony", "firewall"),
    "network": ("network", "telephony"),
    "rtp": ("telephony", "firewall"),
    "sip": ("telephony", "firewall"),
    "iax": ("telephony", "firewall"),
    "voicemail": ("services",),
    "email": ("email", "dialplan", "services"),
    "features": ("dialplan",),
    "media": ("services",),
    "firewall": ("firewall",),
}


@router.get("/settings/{group}", tags=["settings"])
def get_settings(group: str, user: User = Depends(api_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    model = SETTINGS.get(group)
    if model is None:
        raise HTTPException(404, "unknown settings group")
    data = st.load(db, model).model_dump()
    for name in SECRET_SETTINGS.get(group, ()):
        data[name] = ""
    return data


@router.patch("/settings/{group}", tags=["settings"])
async def patch_settings(
    group: str, request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    from pydantic import ValidationError

    from askozia.services.common import audit, errors_from_validation, mark_dirty

    model = SETTINGS.get(group)
    if model is None:
        raise HTTPException(404, "unknown settings group")
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(422, "expected a JSON object")
    current = st.load(db, model).model_dump()
    current.update(body)
    try:
        new = model.model_validate(current)
    except ValidationError as exc:
        raise HTTPException(422, {"fields": errors_from_validation(exc)}) from None
    st.save(db, new)
    audit(db, user.username, "update", "settings", group, summary=f"{group} (API)")
    if SETTINGS_AREAS.get(group):
        mark_dirty(db, *SETTINGS_AREAS[group])
    return get_settings(group, user, db)


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


@router.get("/status", tags=["status"])
def status(user: User = Depends(api_user)) -> dict[str, Any]:
    return {"system": status_svc.system_info(), "asterisk": status_svc.asterisk_status()}
