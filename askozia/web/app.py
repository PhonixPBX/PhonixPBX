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

from askozia import __version__, config
from askozia.core import migrate
from askozia.services import secrets, setup
from askozia.web.routes import api, ui
from askozia.web.security import LoginRequired, PasswordChangeRequired, SecurityHeaders
from askozia.web.templating import render

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # on the appliance "askozia firstboot" already did this; dev/test convenience
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
        title="AskoziaPBX",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.add_middleware(SecurityHeaders)
    app.add_middleware(
        SessionMiddleware,
        secret_key=secrets.get("session_key"),
        session_cookie="askozia_session",
        same_site="strict",
        https_only=not cfg.dev,
        max_age=None,
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(ui.router)
    app.include_router(api.router)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> PlainTextResponse:
        return PlainTextResponse("ok")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> RedirectResponse:
        return RedirectResponse("/static/img/favicon.ico", status_code=301)

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
