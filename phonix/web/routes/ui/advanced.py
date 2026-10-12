"""Advanced: SIP, IAX, RTP, AMI users, firewall, certificate, administrators, GUI options."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from phonix.core import settings as st
from phonix.core.models import User
from phonix.services import acme as acme_svc
from phonix.services import acme_providers, tls, tokens, users
from phonix.services import manager as ami_svc
from phonix.services.common import AREAS, ServiceError, audit, diff_dicts, errors_from_validation
from phonix.web.deps import form_to_dict, get_db, ui_user
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

ACME_SECRETS = {"eab_hmac", "dns_env"}
LOCAL_SUFFIXES = (".local", ".lan", ".localdomain", ".internal", ".home.arpa", ".localhost")


def _acme_values(acme: st.AcmeSettings) -> dict[str, Any]:
    """Form values for the ACME card; stored secrets are never sent back."""
    values = acme.model_dump()
    values["eab_hmac"] = ""
    provider = acme_providers.get(acme.dns_provider)
    values["dns_provider_choice"] = provider.code if provider else (acme_providers.OTHER if acme.dns_provider else "")
    values["dns_provider_other"] = "" if provider else acme.dns_provider
    for p in acme_providers.PROVIDERS:
        for f in p.fields:
            name = f"env__{p.code}__{f.env}"
            stored = acme.dns_env.get(f.env, "") if p is provider else ""
            values[name] = "" if f.secret else stored
            values[name + "__unset"] = not stored
    values["dns_env_text"] = "" if provider else "\n".join(f"{k}=" for k in acme.dns_env)
    values["dns_env"] = {}
    return values


def _certificate_page(
    request: Request,
    db: Session,
    status_code: int = 200,
    values: dict[str, Any] | None = None,
    errors: dict[str, str] | None = None,
    upload_errors: dict[str, str] | None = None,
) -> Response:
    acme = st.load(db, st.AcmeSettings)
    system = st.load(db, st.SystemSettings)
    default_domain = f"{system.hostname}.{system.domain}"
    return page(
        request,
        "pages/advanced_certificate.html",
        status_code=status_code,
        cert=tls.certificate_info(),
        values=values if values is not None else _acme_values(acme),
        errors=errors or {},
        upload_errors=upload_errors or {},
        status=acme_svc.read_status(),
        providers=acme_providers.choices(),
        provider_list=acme_providers.PROVIDERS,
        default_domain=default_domain,
        local_domain=not acme.domains and ("." + default_domain).endswith(LOCAL_SUFFIXES),
        admin_restricted=bool(st.load(db, st.FirewallSettings).admin_allowed_networks),
    )


def _disable_acme(request: Request, db: Session) -> None:
    acme = st.load(db, st.AcmeSettings)
    if acme.enabled:
        acme.enabled = False
        st.save(db, acme)
        flash(request, "Automatic certificates were turned off.", "info")


def _flash_warnings(request: Request, warnings: list[str]) -> None:
    for message in warnings:
        flash(request, message, "warning")


@router.get("/certificate")
def certificate(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return _certificate_page(request, db)


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
    except ServiceError as exc:
        return _certificate_page(request, db, status_code=422, upload_errors=service_errors(exc))
    audit(db, user.username, "certificate", summary="uploaded certificate")
    _disable_acme(request, db)
    _flash_warnings(request, acme_svc.reload_consumers(db))
    flash(request, "Certificate installed.")
    return redirect(request, "/advanced/certificate")


@router.post("/certificate/regenerate")
def certificate_regenerate(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    system = st.load(db, st.SystemSettings)
    tls.generate_self_signed(f"{system.hostname}.{system.domain}")
    audit(db, user.username, "certificate", summary="regenerated self-signed certificate")
    _disable_acme(request, db)
    _flash_warnings(request, acme_svc.reload_consumers(db))
    flash(request, "A new self-signed certificate was created.")
    return redirect(request, "/advanced/certificate")


def _acme_dns_form(form: Any, current: st.AcmeSettings) -> tuple[str, dict[str, str], dict[str, str]]:
    """DNS provider code and credentials from the form. Empty secrets keep the stored value."""
    choice = str(form.get("dns_provider_choice", "")).strip()
    keep = current.dns_env
    if choice == acme_providers.OTHER:
        code = str(form.get("dns_provider_other", "")).strip()
        keep = current.dns_env if code == current.dns_provider else {}
        env: dict[str, str] = {}
        for line in str(form.get("dns_env_text", "")).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, sep, value = line.partition("=")
            if not sep:
                return code, {}, {"dns_env_text": f"Expected NAME=value: {line}"}
            name, value = name.strip(), value.strip()
            env[name] = value or keep.get(name, "")
        return code, env, {}
    provider = acme_providers.get(choice)
    if provider is None:
        return "", {}, {}
    if provider.code != current.dns_provider:
        keep = {}
    env = {}
    for f in provider.fields:
        value = str(form.get(f"env__{provider.code}__{f.env}", "")).strip()
        if f.secret and not value:
            value = keep.get(f.env, "")
        if value:
            env[f.env] = value
    return provider.code, env, {}


@router.post("/certificate/acme")
async def certificate_acme(
    request: Request, issue: bool = False, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    from pydantic import ValidationError

    form = await request.form()
    current = st.load(db, st.AcmeSettings)
    data = current.model_dump()
    submitted = form_to_dict(form, st.AcmeSettings)
    if not submitted.get("eab_hmac"):
        submitted.pop("eab_hmac", None)
    data.update(submitted)
    code, env, errors = _acme_dns_form(form, current)
    data.update(dns_provider=code, dns_env=env)

    def invalid(errors: dict[str, str]) -> Response:
        values = {**dict(form), "domains": data["domains"], "dns_resolvers": data["dns_resolvers"]}
        values["enabled"] = data["enabled"]
        values.update({k: "" for k in form if k.startswith("env__") or k == "eab_hmac"})
        stored = current.dns_env if current.dns_provider else {}
        for p in acme_providers.PROVIDERS:
            for f in p.fields:
                values[f"env__{p.code}__{f.env}__unset"] = p.code != current.dns_provider or not stored.get(f.env)
        return _certificate_page(request, db, status_code=422, values=values, errors=errors)

    if errors:
        return invalid(errors)
    try:
        new = st.AcmeSettings.model_validate(data)
    except ValidationError as exc:
        errors = errors_from_validation(exc)
        if "dns_env" in errors:
            errors["dns_env_text"] = errors.pop("dns_env")
        return invalid(errors)
    if new.enabled and new.challenge == "dns":
        missing = acme_providers.missing(new.dns_provider, new.dns_env)
        if missing:
            return invalid({"__all__": "Missing DNS provider credentials: " + ", ".join(missing)})
    st.save(db, new)
    diff = diff_dicts(current.model_dump(), new.model_dump(), hide=ACME_SECRETS)
    if diff:
        audit(db, user.username, "update", "settings", "acme", summary="acme", diff=diff)
    if not issue:
        flash(request, "Settings saved.")
        return redirect(request, "/advanced/certificate#acme")
    if not new.enabled:
        flash(request, "Turn on automatic certificates to request one.", "warning")
        return redirect(request, "/advanced/certificate#acme")
    db.commit()  # the background process reads the settings from the database
    try:
        acme_svc.start_background()
    except ServiceError as exc:
        flash(request, str(exc), "warning")
    return redirect(request, "/advanced/certificate#acme")


@router.get("/certificate/acme/status")
def certificate_acme_status(request: Request, was: str = "", user: User = Depends(ui_user)) -> Response:
    status = acme_svc.read_status()
    response = page(request, "partials/acme_status.html", status=status)
    if was == "running" and status.get("state") != "running":
        response.headers["HX-Refresh"] = "true"  # show the new certificate
    return response


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


# --- API tokens ----------------------------------------------------------------------------

TOKEN_DEFAULTS = {"access": "read", "expires_in_days": ""}


def _tokens_page(request: Request, db: Session, status_code: int = 200, **ctx: Any) -> Response:
    ctx.setdefault("values", TOKEN_DEFAULTS)
    return page(
        request,
        "pages/advanced_tokens.html",
        status_code=status_code,
        tokens=tokens.list_tokens(db),
        token_status=tokens.status,
        max_days=tokens.MAX_DAYS,
        **ctx,
    )


@router.get("/tokens")
def api_tokens(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return _tokens_page(request, db)


@router.post("/tokens")
async def api_token_create(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    form = await request.form()
    name = str(form.get("name", ""))
    expires = str(form.get("expires_in_days", "")).strip()
    values: dict[str, Any] = {
        "name": name,
        "access": "write" if form.get("access") == "write" else "read",
        "expires_in_days": expires,
    }
    try:
        # empty = unlimited, like "phonix token create" without --expires-days
        days = None
        if expires:
            if not expires.isdigit():
                raise ServiceError(fields={"expires_in_days": "Enter a number of days"})
            days = int(expires)
        token, plain = tokens.create(
            db, user, name, read_only=values["access"] == "read", expires_in_days=days, actor=user.username
        )
    except ServiceError as exc:
        db.rollback()
        return _tokens_page(request, db, status_code=422, values=values, errors=service_errors(exc))
    # shown once on this response; never redirected through the session/flash
    return _tokens_page(request, db, new_token=token, new_token_plain=plain)


@router.post("/tokens/{token_id}/toggle")
def api_token_toggle(
    token_id: int, request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    try:
        token = tokens.get(db, token_id)
        tokens.set_enabled(db, token_id, not token.enabled, actor=user.username)
    except ServiceError as exc:
        raise HTTPException(404, str(exc)) from None
    return page(request, "partials/token_row.html", t=token, token_status=tokens.status)


@router.delete("/tokens/{token_id}")
def api_token_delete(token_id: int, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    try:
        tokens.delete(db, token_id, actor=user.username)
    except ServiceError as exc:
        raise HTTPException(404, str(exc)) from None
    return Response("")


__all__ = ["AREAS", "router"]
