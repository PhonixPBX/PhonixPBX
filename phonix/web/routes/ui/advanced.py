"""Advanced: SIP, IAX, RTP, AMI users, firewall, certificate, administrators, GUI options."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from phonix.core import settings as st
from phonix.core.models import User
from phonix.services import manager as ami_svc
from phonix.services import privileged, tls, users
from phonix.services.common import AREAS, ServiceError, audit, mark_dirty
from phonix.web.deps import get_db, ui_user
from phonix.web.routes.ui.common import page, redirect, save_settings_form, service_errors
from phonix.web.routes.ui.dialplan import Kind, register
from phonix.web.templating import flash

router = APIRouter(prefix="/advanced")

# settings pages: url -> (model, template, areas, secret fields)
SETTINGS_PAGES: dict[str, tuple[type[st.SettingsGroup], str, tuple[str, ...]]] = {
    "sip": (st.SipSettings, "pages/advanced_sip.html", ("telephony", "firewall")),
    "iax": (st.IaxSettings, "pages/advanced_iax.html", ("telephony", "firewall")),
    "rtp": (st.RtpSettings, "pages/advanced_rtp.html", ("telephony", "firewall")),
    "firewall": (st.FirewallSettings, "pages/advanced_firewall.html", ("firewall",)),
    "gui": (st.GuiSettings, "pages/advanced_gui.html", ()),
}


def _settings_routes(slug: str, model: type[st.SettingsGroup], template: str, areas: tuple[str, ...]) -> None:
    @router.get(f"/{slug}", name=f"advanced_{slug}")
    def show(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
        return page(request, template, values=st.load(db, model).model_dump())

    @router.post(f"/{slug}", name=f"advanced_{slug}_save")
    async def save(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
        if model is st.RtpSettings:
            form = await request.form()
            try:
                if int(str(form.get("port_start", 0))) >= int(str(form.get("port_end", 0))):
                    return page(
                        request,
                        template,
                        status_code=422,
                        values=dict(form),
                        errors={"port_end": "The end port must be greater than the start port."},
                    )
            except ValueError:
                pass
        saved, values, errors = await save_settings_form(request, db, model, areas)
        if not saved:
            return page(request, template, status_code=422, values=values, errors=errors)
        return redirect(request, f"/advanced/{slug}")


for _slug, (_model, _template, _areas) in SETTINGS_PAGES.items():
    _settings_routes(_slug, _model, _template, _areas)


# --- AMI users --------------------------------------------------------------------------

AMI = Kind(
    "ami_user",
    "Manager user",
    ami_svc.AmiUserIn,
    ami_svc.list_ami_users,
    ami_svc.get_ami_user,
    ami_svc.create_ami_user,
    ami_svc.update_ami_user,
    ami_svc.delete_ami_user,
    ami_svc.to_dict,
    "/advanced/manager",
    "pages/ami_users.html",
    "pages/ami_user_form.html",
)
register(AMI, router, "/advanced")


# --- certificate -------------------------------------------------------------------------


@router.get("/certificate")
def certificate(request: Request, user: User = Depends(ui_user)) -> Response:
    return page(request, "pages/advanced_certificate.html", cert=tls.certificate_info())


@router.post("/certificate")
async def certificate_upload(
    request: Request,
    certificate: UploadFile,
    private_key: UploadFile,
    user: User = Depends(ui_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        tls.install_certificate(await certificate.read(1024 * 1024), await private_key.read(1024 * 1024))
        privileged.run("nginx-reload")
    except ServiceError as exc:
        return page(
            request,
            "pages/advanced_certificate.html",
            status_code=422,
            cert=tls.certificate_info(),
            errors=service_errors(exc),
        )
    except privileged.PrivilegedError as exc:
        flash(request, f"Certificate installed, but reloading the web server failed: {exc}", "warning")
    audit(db, user.username, "certificate", summary="uploaded certificate")
    mark_dirty(db, "telephony")
    flash(request, "Certificate installed.")
    return redirect(request, "/advanced/certificate")


@router.post("/certificate/regenerate")
def certificate_regenerate(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    system = st.load(db, st.SystemSettings)
    tls.generate_self_signed(f"{system.hostname}.{system.domain}")
    try:
        privileged.run("nginx-reload")
    except privileged.PrivilegedError as exc:
        flash(request, f"Reloading the web server failed: {exc}", "warning")
    audit(db, user.username, "certificate", summary="regenerated self-signed certificate")
    flash(request, "A new self-signed certificate was created.")
    return redirect(request, "/advanced/certificate")


# --- administrators ------------------------------------------------------------------------


@router.get("/users")
def admin_users(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return page(request, "pages/advanced_users.html", admins=users.list_users(db))


@router.post("/users")
async def admin_add(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    form = await request.form()
    try:
        users.create_user(
            db,
            str(form.get("username", "")),
            str(form.get("password", "")),
            must_change=form.get("must_change") == "true",
            actor=user.username,
        )
    except ServiceError as exc:
        db.rollback()
        return page(
            request,
            "pages/advanced_users.html",
            status_code=422,
            admins=users.list_users(db),
            errors=service_errors(exc),
            values=dict(form),
        )
    flash(request, "Administrator created.")
    return redirect(request, "/advanced/users")


@router.delete("/users/{username}")
def admin_delete(username: str, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    if username == user.username:
        raise HTTPException(400, "You cannot delete yourself")
    try:
        users.delete_user(db, username, actor=user.username)
    except ServiceError as exc:
        raise HTTPException(400, str(exc)) from None
    return Response("")


__all__ = ["AREAS", "router"]
