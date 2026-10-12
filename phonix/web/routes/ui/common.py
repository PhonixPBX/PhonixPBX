"""Helpers shared by the HTML route modules."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from phonix.core import settings as st
from phonix.services.common import ServiceError, audit, diff_dicts, errors_from_validation, mark_dirty
from phonix.web.deps import form_to_dict
from phonix.web.templating import flash, render


def is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


def redirect(request: Request, url: str) -> Response:
    """Redirect that also works for htmx requests (full navigation)."""
    if is_htmx(request):
        return Response(status_code=204, headers={"HX-Location": url})
    return RedirectResponse(url, status_code=303)


def dirty_trigger(response: Response) -> Response:
    """Ask the page to refresh the pending changes banner."""
    response.headers["HX-Trigger"] = "phonix:dirty"
    return response


def user_name(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.username if user else ""


def settings_values(model: st.SettingsGroup) -> dict[str, Any]:
    return model.model_dump()


async def save_settings_form(
    request: Request,
    db: Session,
    model: type[st.SettingsGroup],
    areas: tuple[str, ...],
    secret_fields: tuple[str, ...] = (),
) -> tuple[bool, dict[str, Any], dict[str, str]]:
    """Validate and store a settings form. Returns (saved, values, errors)."""
    from pydantic import ValidationError

    form = await request.form()
    current = st.load(db, model)
    data = current.model_dump()
    submitted = form_to_dict(form, model)
    for name in secret_fields:
        if not submitted.get(name):
            submitted.pop(name, None)  # keep the stored secret
    data.update(submitted)
    try:
        new = model.model_validate(data)
    except ValidationError as exc:
        values = {**data, **{k: "" for k in secret_fields}}
        return False, values, errors_from_validation(exc)
    before = current.model_dump()
    st.save(db, new)
    diff = diff_dicts(before, new.model_dump(), hide=set(secret_fields))
    if diff:
        audit(
            db, user_name(request), "update", "settings", st.group_name(model), summary=st.group_name(model), diff=diff
        )
        if areas:
            mark_dirty(db, *areas)
    flash(request, "Settings saved." + (" Apply the changes to activate them." if diff and areas else ""))
    return True, new.model_dump(), {}


def service_errors(exc: ServiceError) -> dict[str, str]:
    errors = dict(exc.fields)
    if exc.message and not errors:
        errors["__all__"] = exc.message
    return errors


def page(request: Request, template: str, status_code: int = 200, **ctx: Any) -> Response:
    return render(request, template, ctx, status_code=status_code)


def model_values(schema: type[BaseModel], data: dict[str, Any]) -> dict[str, Any]:
    out = {name: info.default for name, info in schema.model_fields.items() if not info.is_required()}
    for name, info in schema.model_fields.items():
        if info.default_factory is not None:
            out[name] = info.default_factory()  # type: ignore[call-arg]
    out.update(data)
    return out
