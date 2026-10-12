"""FastAPI dependencies: DB session per request, authenticated user, form parsing."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, get_args, get_origin

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from phonix.core import settings as st
from phonix.core.db import session_factory
from phonix.core.models import User
from phonix.services import tokens as tokens_service
from phonix.services.common import dirty_areas
from phonix.web.security import SAFE_METHODS, LoginRequired, PasswordChangeRequired, current_user, verify_csrf


def get_db() -> Iterator[Session]:
    session = session_factory()()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def _session_minutes(db: Session) -> int:
    return st.load(db, st.GuiSettings).session_minutes


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = current_user(request, db, _session_minutes(db))
    if user is None:
        raise LoginRequired()
    if user.must_change_pw and request.url.path not in ("/password", "/logout"):
        raise PasswordChangeRequired()
    request.state.user = user
    request.state.dirty = dirty_areas(db)
    return user


async def ui_user(request: Request, user: User = Depends(require_user)) -> User:
    """Authenticated UI request; state changing methods must carry the CSRF token."""
    await verify_csrf(request)
    return user


BEARER = {"WWW-Authenticate": "Bearer"}


async def api_user(request: Request, db: Session = Depends(get_db)) -> User:
    """API auth: bearer token (scripts) or the UI session cookie + X-CSRF-Token header."""
    auth = request.headers.get("authorization", "")
    if auth:
        scheme, _, credentials = auth.partition(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(401, "use a bearer token (Advanced > API tokens)", headers=BEARER)
        from phonix.web.security import client_ip, login_limiter

        key = f"api:{client_ip(request)}"
        if login_limiter.blocked(key):
            raise HTTPException(429, "too many failed logins")
        token = tokens_service.authenticate(db, credentials.strip())
        if token is None:
            login_limiter.hit(key)
            raise HTTPException(401, "invalid, disabled or expired token", headers=BEARER)
        if token.read_only and request.method not in SAFE_METHODS:
            raise HTTPException(403, "token is read-only")
        request.state.user = token.user
        request.state.api_token = token
        return token.user
    user = current_user(request, db, _session_minutes(db))
    if user is None:
        raise HTTPException(401, "authentication required", headers=BEARER)
    await verify_csrf(request)
    request.state.user = user
    return user


# --- form parsing ------------------------------------------------------------

TRUE = {"1", "true", "on", "yes"}


def _unwrap(annotation: Any) -> tuple[Any, bool]:
    """Return (inner type, optional) for ``X | None``."""
    args = get_args(annotation)
    if args and type(None) in args:
        inner = [a for a in args if a is not type(None)]
        return (inner[0] if inner else Any), True
    return annotation, False


def form_to_dict(form: FormData, model: type[BaseModel], prefix: str = "") -> dict[str, Any]:
    """Convert submitted HTML form fields into a dict suitable for ``model``.

    Checkboxes: unchecked boxes are absent -> False. Lists come from repeated
    fields (multi selects / checkbox groups). Empty optional numbers -> None.
    """
    data: dict[str, Any] = {}
    for name, info in model.model_fields.items():
        key = prefix + name
        annotation, optional = _unwrap(info.annotation)
        origin = get_origin(annotation)
        if annotation is bool:
            if key in form or f"{key}__present" in form:
                data[name] = form.get(key, "").lower() in TRUE  # type: ignore[union-attr]
            continue
        if origin is list:
            values = [str(x) for x in form.getlist(key)]
            if not values and f"{key}__present" not in form:
                continue
            inner = get_args(annotation)[0] if get_args(annotation) else str
            if inner is int:
                data[name] = [int(x) for x in values if x.strip().lstrip("-").isdigit()]
            elif inner is str and len(values) == 1 and "\n" in values[0]:
                data[name] = [x.strip() for x in values[0].splitlines() if x.strip()]
            else:
                data[name] = [x for x in values if x.strip()] if inner is str else values
            continue
        if key not in form:
            continue
        raw = form.get(key)
        if not isinstance(raw, str):
            continue
        if annotation is int:
            raw = raw.strip()
            if raw == "":
                if optional:
                    data[name] = None
                continue
            data[name] = raw
        else:
            data[name] = raw
    return data
