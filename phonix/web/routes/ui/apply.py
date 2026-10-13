# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""The "pending changes" banner and the apply action."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from phonix.core.models import User
from phonix.i18n import _
from phonix.services import apply as apply_service
from phonix.services.common import AREAS, dirty_areas
from phonix.web.deps import get_db, ui_user
from phonix.web.routes.ui.common import is_htmx, redirect
from phonix.web.templating import flash, render

router = APIRouter()


def _labels(areas: list[str]) -> list[str]:
    return [AREAS.get(a, a) for a in areas]


@router.get("/apply/banner")
def banner(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return render(request, "partials/apply_banner_wrapper.html", {"dirty": _labels(dirty_areas(db))})


@router.post("/apply")
def apply(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    result = apply_service.apply(db, user=user.username)
    db.flush()
    remaining = _labels(dirty_areas(db))
    if is_htmx(request):
        return render(request, "partials/apply_result.html", {"result": result, "dirty": remaining})
    if result.ok:
        flash(request, _("Configuration applied."))
    else:
        flash(request, _("Applying failed: %(errors)s", errors="; ".join(result.errors)), "error")
    return redirect(request, request.headers.get("referer") or "/")
