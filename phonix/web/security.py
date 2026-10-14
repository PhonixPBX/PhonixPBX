# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Authentication, CSRF protection, login rate limiting and security headers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from phonix import i18n
from phonix.core.models import User

SESSION_USER = "uid"
# the user id alone could name another user after a backup was restored
SESSION_USERNAME = "uname"
# digest of the password hash: a password change (or a restored one) ends the other sessions
SESSION_PW_STAMP = "pw"
SESSION_CSRF = "csrf"
SESSION_LOGIN_AT = "at"
# web interface language of the logged in user (read by LanguageMiddleware)
SESSION_LANGUAGE = "lang"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class LoginRequired(Exception):
    pass


class PasswordChangeRequired(Exception):
    pass


def csrf_token(request: Request) -> str:
    token = request.session.get(SESSION_CSRF)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_CSRF] = token
    return str(token)


async def verify_csrf(request: Request) -> None:
    """Every state changing request must echo the session token (form field or header)."""
    if request.method in SAFE_METHODS:
        return
    expected = request.session.get(SESSION_CSRF)
    sent = request.headers.get("x-csrf-token")
    if sent is None:
        ctype = request.headers.get("content-type", "")
        if ctype.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
            form = await request.form()
            value = form.get("csrf_token")
            sent = value if isinstance(value, str) else None
    if not expected or not sent or not hmac.compare_digest(str(expected), sent):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


def password_stamp(user: User) -> str:
    """Short digest of the password hash; the session cookie is signed, not encrypted."""
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def login(request: Request, user: User) -> None:
    request.session.clear()
    request.session[SESSION_USER] = user.id
    request.session[SESSION_USERNAME] = user.username
    request.session[SESSION_PW_STAMP] = password_stamp(user)
    request.session[SESSION_LOGIN_AT] = int(time.time())
    request.session[SESSION_CSRF] = secrets.token_urlsafe(32)
    request.session[SESSION_LANGUAGE] = i18n.normalize(user.language)


def logout(request: Request) -> None:
    request.session.clear()


def current_user(request: Request, session: Session, max_age_minutes: int) -> User | None:
    uid = request.session.get(SESSION_USER)
    started = request.session.get(SESSION_LOGIN_AT, 0)
    if not uid:
        return None
    if time.time() - started > max_age_minutes * 60:
        request.session.clear()
        return None
    user = session.get(User, uid)
    if (
        user is None
        or user.username != request.session.get(SESSION_USERNAME)
        or not hmac.compare_digest(password_stamp(user), str(request.session.get(SESSION_PW_STAMP, "")))
    ):
        request.session.clear()
        return None
    # sliding expiration
    request.session[SESSION_LOGIN_AT] = int(time.time())
    # language changed by another session: used from the next request on
    request.session[SESSION_LANGUAGE] = i18n.normalize(user.language)
    return user


class RateLimiter:
    """In-memory login throttle per client address (the web app is a single process)."""

    def __init__(self, attempts: int = 5, window: int = 300) -> None:
        self.attempts = attempts
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def blocked(self, key: str) -> bool:
        q = self._hits[key]
        now = time.monotonic()
        while q and q[0] < now - self.window:
            q.popleft()
        return len(q) >= self.attempts

    def hit(self, key: str) -> None:
        self._hits[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


login_limiter = RateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    # Tabler and ApexCharts set inline styles
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers: dict[str, Any] = {
            "Content-Security-Policy": CSP,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        }
        if request.url.path == "/api/docs":
            # Swagger UI is loaded from jsDelivr (needs internet access)
            headers["Content-Security-Policy"] = (
                CSP.replace("script-src 'self'", "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net")
                .replace(
                    "style-src 'self' 'unsafe-inline'", "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
                )
                .replace("img-src 'self' data:", "img-src 'self' data: https://fastapi.tiangolo.com")
            )
        for key, value in headers.items():
            response.headers.setdefault(key, value)
        if request.url.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "public, max-age=3600")
        else:
            response.headers.setdefault("Cache-Control", "no-store")
        return response


class LanguageMiddleware:
    """Set the request's translation language from the session (pure ASGI, inside SessionMiddleware)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        session = scope.get("session") or {}
        with i18n.language(session.get(SESSION_LANGUAGE)):
            await self.app(scope, receive, send)
