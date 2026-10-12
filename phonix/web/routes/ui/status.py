"""Dashboard and status pages."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from markupsafe import escape
from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix import config
from phonix.core import settings as st
from phonix.core.models import AuditLog, User
from phonix.i18n import N_
from phonix.services import firstboot, phones, providers, status, tls, update
from phonix.web.deps import get_db, ui_user
from phonix.web.routes.ui.common import page
from phonix.web.templating import render

router = APIRouter()


@router.get("/")
def dashboard(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    system = st.load(db, st.SystemSettings)
    network = st.load(db, st.NetworkSettings)
    return page(
        request,
        "pages/dashboard.html",
        info=status.system_info(),
        system=system,
        network=network,
        phone_count=len(phones.list_phones(db)),
        provider_count=len(providers.list_providers(db)),
        update=update.status(),
        cert=tls.certificate_info(),
        initial_password=firstboot.initial_password() is not None,
    )


@router.get("/status/asterisk")
def asterisk_fragment(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    """Polled fragment: Asterisk state, registrations and calls."""
    return render(
        request,
        "partials/asterisk_status.html",
        {
            "ast": status.asterisk_status(),
            "phones": phones.list_phones(db),
            "providers": providers.list_providers(db),
            "compact": request.query_params.get("compact") == "1",
        },
    )


@router.get("/status/calls")
def calls(request: Request, user: User = Depends(ui_user)) -> Response:
    return page(request, "pages/status_calls.html")


@router.get("/status/graphs")
def graphs(request: Request, user: User = Depends(ui_user)) -> Response:
    return page(request, "pages/status_graphs.html")


@router.get("/status/metrics.json")
def metrics(user: User = Depends(ui_user)) -> JSONResponse:
    status.sampler.sample()
    data = [s.__dict__ for s in status.sampler.history]
    return JSONResponse(data)


LOGS = {"asterisk": "Asterisk", "system": N_("System")}


@router.get("/status/logs")
def logs(request: Request, log: str = "asterisk", user: User = Depends(ui_user)) -> Response:
    if log not in LOGS:
        log = "asterisk"
    path = config.get().log_files[log]
    return page(request, "pages/status_logs.html", logs=LOGS, current=log, lines=status.tail(path, 300), path=str(path))


@router.get("/status/logs/stream")
async def log_stream(request: Request, log: str = "asterisk", user: User = Depends(ui_user)) -> Response:
    """Server-sent events with new log lines (consumed by the htmx 4 SSE extension)."""
    path = config.get().log_files.get(log)
    if path is None:
        return Response(status_code=404)

    async def events() -> AsyncIterator[str]:
        position = path.stat().st_size if path.exists() else 0
        while not await request.is_disconnected():
            try:
                size = path.stat().st_size
                if size < position:  # rotated
                    position = 0
                if size > position:
                    with path.open("rb") as fh:
                        fh.seek(position)
                        chunk = fh.read(256 * 1024)
                        position += len(chunk)
                    lines = chunk.decode("utf-8", "replace").splitlines()
                    html = "".join(f"<div>{escape(line)}</div>" for line in lines)
                    yield "data: " + html.replace("\n", "") + "\n\n"
            except OSError:
                pass
            await asyncio.sleep(1.0)

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    )


@router.get("/status/audit")
def audit_log(
    request: Request, page_no: int = 1, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    per_page = 50
    page_no = max(page_no, 1)
    rows = list(
        db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).offset((page_no - 1) * per_page).limit(per_page + 1))
    )
    return page(
        request,
        "pages/status_audit.html",
        rows=rows[:per_page],
        page_no=page_no,
        has_more=len(rows) > per_page,
        json=json,
    )
