# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from phonix import __version__, config
from phonix.core import migrate
from phonix.services import secrets, setup
from phonix.web.routes import api, mcp, ui
from phonix.web.security import LanguageMiddleware, LoginRequired, PasswordChangeRequired, SecurityHeaders
from phonix.web.templating import render

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # on the appliance "phonix firstboot" already did this; dev/test convenience
    if migrate.needs_upgrade():
        setup.initialize()
    yield


def _is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


def _redirect(request: Request, url: str) -> Response:
    if _is_htmx(request):
        return Response(status_code=204, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


def create_app() -> FastAPI:
    cfg = config.get()
    app = FastAPI(
        title="PhonixPBX",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.add_middleware(SecurityHeaders)
    # inside the session middleware (added later = outer), reads the session
    app.add_middleware(LanguageMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=secrets.get("session_key"),
        session_cookie="phonix_session",
        same_site="strict",
        https_only=not cfg.dev,
        max_age=None,
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    # user manual (docs/manual, built by scripts/help-build.sh); nginx serves it directly on the appliance
    app.mount("/help", StaticFiles(directory=str(STATIC_DIR / "help"), html=True, check_dir=False), name="help")
    app.include_router(ui.router)
    app.include_router(api.router)
    app.include_router(mcp.router)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> PlainTextResponse:
        return PlainTextResponse("ok")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> RedirectResponse:
        return RedirectResponse("/static/img/favicon.svg", status_code=301)

    @app.exception_handler(LoginRequired)
    async def login_required(request: Request, exc: LoginRequired) -> Response:
        target = request.url.path if request.method == "GET" and not _is_htmx(request) else "/"
        return _redirect(request, f"/login?next={target}")

    @app.exception_handler(PasswordChangeRequired)
    async def pw_required(request: Request, exc: PasswordChangeRequired) -> Response:
        return _redirect(request, "/password")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
        return render(
            request,
            "error.html",
            {"status": exc.status_code, "detail": exc.detail},
            status_code=exc.status_code,
        )

    return app
