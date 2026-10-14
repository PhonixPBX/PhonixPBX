# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Login, logout and password change."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from phonix import i18n
from phonix.core.models import User
from phonix.i18n import _
from phonix.services import firstboot, users
from phonix.services.common import ServiceError
from phonix.web import security
from phonix.web.deps import get_db, require_user
from phonix.web.routes.ui.common import page, service_errors
from phonix.web.templating import flash

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
            error=_("Too many failed attempts. Please wait a few minutes."),
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
            error=_("Invalid username or password."),
        )
    security.login_limiter.reset(key)
    security.login(request, user)
    return RedirectResponse("/password" if user.must_change_pw else target, status_code=303)


@router.post("/logout")
async def logout(request: Request) -> Response:
    await security.verify_csrf(request)
    security.logout(request)
    return RedirectResponse("/login", status_code=303)


def _languages() -> list[tuple[str, str]]:
    return [(code, name) for code, name in i18n.LANGUAGE_NAMES.items() if code != i18n.DEFAULT]


@router.get("/account")
def account_form(request: Request, user: User = Depends(require_user)) -> Response:
    return page(request, "account.html", languages=_languages(), values={"language": user.language or ""})


@router.post("/account")
async def account_save(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)) -> Response:
    await security.verify_csrf(request)
    form = await request.form()
    language = str(form.get("language", ""))
    try:
        users.set_language(db, user, language)
    except ServiceError as exc:
        return page(
            request,
            "account.html",
            status_code=422,
            languages=_languages(),
            values={"language": language},
            errors=service_errors(exc),
        )
    request.session[security.SESSION_LANGUAGE] = i18n.normalize(user.language)
    # flash in the new language
    with i18n.language(user.language):
        flash(request, _("Your preferences have been saved."))
    return RedirectResponse("/account", status_code=303)


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
    # keep this session; the others of this user end
    request.session[security.SESSION_PW_STAMP] = security.password_stamp(user)
    flash(request, _("Your password has been changed."))
    return RedirectResponse("/", status_code=303)
