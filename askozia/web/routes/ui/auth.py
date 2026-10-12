"""Login, logout and password change."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from askozia.core.models import User
from askozia.services import firstboot, users
from askozia.services.common import ServiceError
from askozia.web import security
from askozia.web.deps import get_db, require_user
from askozia.web.routes.ui.common import page, service_errors
from askozia.web.templating import flash

router = APIRouter()


def _safe_next(target: str) -> str:
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target


@router.get("/login")
def login_form(request: Request, next: str = "/") -> Response:
    return page(request, "login.html", next=_safe_next(next), username="", error="")


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)) -> Response:
    await security.verify_csrf(request)
    form = await request.form()
    username = str(form.get("username", "")).strip().lower()
    password = str(form.get("password", ""))
    target = _safe_next(str(form.get("next", "/")))
    key = security.client_ip(request)
    if security.login_limiter.blocked(key):
        return page(
            request,
            "login.html",
            status_code=429,
            next=target,
            username=username,
            error="Too many failed attempts. Please wait a few minutes.",
        )
    user = users.authenticate(db, username, password)
    if user is None:
        security.login_limiter.hit(key)
        return page(
            request,
            "login.html",
            status_code=401,
            next=target,
            username=username,
            error="Invalid username or password.",
        )
    security.login_limiter.reset(key)
    security.login(request, user)
    return RedirectResponse("/password" if user.must_change_pw else target, status_code=303)


@router.post("/logout")
async def logout(request: Request) -> Response:
    await security.verify_csrf(request)
    security.logout(request)
    return RedirectResponse("/login", status_code=303)


@router.get("/password")
def password_form(request: Request, user: User = Depends(require_user)) -> Response:
    return page(request, "password.html")


@router.post("/password")
async def password_change(
    request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> Response:
    await security.verify_csrf(request)
    form = await request.form()
    try:
        users.change_own_password(
            db, user, str(form.get("current", "")), str(form.get("password", "")), str(form.get("confirm", ""))
        )
    except ServiceError as exc:
        return page(request, "password.html", status_code=422, errors=service_errors(exc))
    firstboot.forget_initial_password()
    flash(request, "Your password has been changed.")
    return RedirectResponse("/", status_code=303)
