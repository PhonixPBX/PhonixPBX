"""System: general setup, network, storage, firmware, backup/restore, defaults, reboot."""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import shutil
import tempfile
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.orm import Session

from phonix import __version__, config
from phonix.core import settings as st
from phonix.core import validation as v
from phonix.core.models import User
from phonix.core.shacrypt import sha512_crypt
from phonix.i18n import _
from phonix.services import backup as backup_svc
from phonix.services import privileged, status, update
from phonix.services.common import ServiceError, audit
from phonix.web.deps import form_to_dict, get_db, ui_user
from phonix.web.routes.ui.common import page, redirect, save_settings_form
from phonix.web.templating import flash, render

router = APIRouter(prefix="/system")


def _timezones() -> list[str]:
    zones = sorted(v._timezones()) or ["UTC"]
    return zones if "UTC" in zones else ["UTC", *zones]


def _alert(request: Request, level: str, message: str, status_code: int = 200) -> Response:
    resp = render(request, "partials/alert.html", {"level": level, "message": message})
    resp.status_code = status_code
    return resp


# --- general --------------------------------------------------------------------------


@router.get("/general")
def general(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return page(
        request, "pages/system_general.html", values=st.load(db, st.SystemSettings).model_dump(), timezones=_timezones()
    )


@router.post("/general")
async def general_save(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    form = await request.form()
    password = str(form.get("ssh_password", ""))
    extra: dict[str, str] = {}
    if form.get("ssh_password_clear"):
        extra["ssh_password_hash"] = ""
    elif password:
        if len(password) < 8:
            values = {**st.load(db, st.SystemSettings).model_dump(), **form_to_dict(form, st.SystemSettings)}
            errors = {"ssh_password": _("The password must have at least 8 characters")}
            return page(
                request,
                "pages/system_general.html",
                status_code=422,
                values=values,
                errors=errors,
                timezones=_timezones(),
            )
        extra["ssh_password_hash"] = sha512_crypt(password)
    saved, values, errors = await save_settings_form(
        request,
        db,
        st.SystemSettings,
        ("system", "network", "telephony", "firewall"),
        secret_fields=("ssh_password_hash",),
        extra=extra,
    )
    if not saved:
        return page(
            request, "pages/system_general.html", status_code=422, values=values, errors=errors, timezones=_timezones()
        )
    return redirect(request, "/system/general")


# --- network ----------------------------------------------------------------------------


def _interfaces() -> list[str]:
    try:
        names = sorted(p.name for p in Path("/sys/class/net").iterdir() if p.name != "lo")
    except OSError:
        names = []
    return names or ["eth0"]


@router.get("/network")
def network(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    from phonix.services import facts

    net = st.load(db, st.NetworkSettings)
    return page(
        request,
        "pages/system_network.html",
        values=net.model_dump(),
        interfaces=_interfaces(),
        current=facts.interface_ipv4(net.interface),
    )


@router.post("/network")
async def network_save(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    saved, values, errors = await save_settings_form(request, db, st.NetworkSettings, ("network", "telephony"))
    if not saved:
        return page(
            request,
            "pages/system_network.html",
            status_code=422,
            values=values,
            errors=errors,
            interfaces=_interfaces(),
            current=None,
        )
    return redirect(request, "/system/network")


# --- storage ------------------------------------------------------------------------------


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(root, name)).st_size
    return total


@router.get("/storage")
def storage(request: Request, user: User = Depends(ui_user)) -> Response:
    cfg = config.get()
    areas = [
        (_("Configuration database"), cfg.db_path.parent / "phonix.db"),
        (_("Media (music on hold, greetings)"), cfg.media_dir),
        (_("Backups"), cfg.backup_dir),
        (_("Voicemail"), cfg.path("/var/spool/asterisk/voicemail")),
        (_("Asterisk database"), cfg.data_dir / "asterisk"),
    ]
    usage = []
    for label, path in areas:
        size = path.stat().st_size if path.is_file() else (_dir_size(path) if path.exists() else 0)
        usage.append({"label": label, "path": str(path), "size": size})
    return page(
        request,
        "pages/system_storage.html",
        disk=status.disk(str(cfg.data_dir)),
        usage=usage,
        data_dir=str(cfg.data_dir),
    )


# --- firmware -------------------------------------------------------------------------------


@router.get("/firmware")
def firmware(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    return page(
        request, "pages/system_firmware.html", info=update.status(), values=st.load(db, st.UpdateSettings).model_dump()
    )


@router.post("/firmware/settings")
async def firmware_settings(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    saved, values, errors = await save_settings_form(request, db, st.UpdateSettings, ())
    if not saved:
        return page(
            request, "pages/system_firmware.html", status_code=422, info=update.status(), values=values, errors=errors
        )
    return redirect(request, "/system/firmware")


@router.post("/firmware/check")
def firmware_check(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    url = st.load(db, st.UpdateSettings).check_url
    if not url.startswith("https://"):
        return _alert(request, "warning", _("Configure an https:// update check URL first."))
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310 - https only, admin configured
            data = json.loads(resp.read(65536))
        latest = str(data.get("version", "?"))
    except (OSError, ValueError) as exc:
        return _alert(request, "danger", _("Update check failed: %(error)s", error=exc))
    if latest == __version__:
        return _alert(request, "success", _("You are running the latest version (%(version)s).", version=latest))
    return _alert(
        request,
        "info",
        _(
            "Version %(latest)s is available (running %(version)s). Download: %(url)s",
            latest=latest,
            version=__version__,
            url=data.get("url", ""),
        ),
    )


@router.post("/firmware/upload")
async def firmware_upload(
    request: Request, file: UploadFile, user: User = Depends(ui_user), db: Session = Depends(get_db)
) -> Response:
    cfg = config.get()
    target = cfg.data_dir / "update.bundle"
    with target.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            fh.write(chunk)
            if fh.tell() > update.MAX_BUNDLE:
                break
    try:
        info = update.install(target)
    except (ServiceError, privileged.PrivilegedError) as exc:
        target.unlink(missing_ok=True)
        return _alert(request, "danger", _("Update rejected: %(error)s", error=exc), status_code=422)
    audit(db, user.username, "firmware", summary=f"installed {info.version}")
    target.unlink(missing_ok=True)
    return render(request, "partials/firmware_done.html", {"info": info})


# --- backup / restore / legacy ------------------------------------------------------------


@router.get("/backup")
def backup(request: Request, user: User = Depends(ui_user)) -> Response:
    return page(request, "pages/system_backup.html", backups=backup_svc.list_backups())


@router.post("/backup/create")
def backup_create(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    path = backup_svc.create()
    audit(db, user.username, "backup", summary=path.name)
    flash(request, _("Backup %(name)s created.", name=path.name))
    return redirect(request, "/system/backup")


def _backup_file(name: str) -> Path:
    if "/" in name or not name.startswith("phonix-backup-") or not name.endswith(".tar.zst"):
        raise HTTPException(404, _("Backup not found"))
    path = config.get().backup_dir / name
    if not path.is_file():
        raise HTTPException(404, _("Backup not found"))
    return path


@router.get("/backup/download/{name}")
def backup_download(name: str, user: User = Depends(ui_user)) -> Response:
    return FileResponse(_backup_file(name), media_type="application/zstd", filename=name)


@router.delete("/backup/{name}")
def backup_delete(name: str, user: User = Depends(ui_user)) -> Response:
    _backup_file(name).unlink()
    return Response("")


@router.post("/backup/restore")
async def backup_restore(request: Request, file: UploadFile, user: User = Depends(ui_user)) -> Response:
    cfg = config.get()
    with tempfile.NamedTemporaryFile(dir=cfg.data_dir, suffix=".tar.zst", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        manifest = backup_svc.restore(tmp_path)
    except ServiceError as exc:
        return _alert(request, "danger", str(exc), status_code=422)
    finally:
        tmp_path.unlink(missing_ok=True)
    return _alert(
        request,
        "success",
        _(
            "Backup from %(created)s restored. Review the configuration and apply the changes.",
            created=manifest.get("created", "?"),
        ),
    )


def _legacy_dir() -> Path:
    path = config.get().state_dir / "legacy-uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.post("/legacy/upload")
async def legacy_upload(request: Request, file: UploadFile, user: User = Depends(ui_user)) -> Response:
    from phonix.legacy import importer

    data = await file.read(10 * 1024 * 1024 + 1)
    token = secrets.token_hex(16)
    (_legacy_dir() / f"{token}.xml").write_bytes(data)
    report = importer.import_bytes(data, mode="replace", dry_run=True, user=user.username)
    return render(request, "partials/legacy_report.html", {"report": report, "token": token, "dry_run": True})


@router.post("/legacy/import")
async def legacy_import(request: Request, user: User = Depends(ui_user)) -> Response:
    from phonix.legacy import importer

    form = await request.form()
    token = str(form.get("token", ""))
    mode = "merge" if form.get("mode") == "merge" else "replace"
    if not token.isalnum():
        raise HTTPException(400, _("invalid token"))
    path = _legacy_dir() / f"{token}.xml"
    if not path.exists():
        return _alert(request, "danger", _("The uploaded file expired, please upload it again."))
    report = importer.import_bytes(path.read_bytes(), mode=mode, dry_run=False, user=user.username)
    path.unlink(missing_ok=True)
    resp = render(request, "partials/legacy_report.html", {"report": report, "token": "", "dry_run": False})
    resp.headers["HX-Trigger"] = "phonix:dirty"
    return resp


@router.get("/legacy/export")
def legacy_export(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    from phonix.legacy import exporter

    xml, _report = exporter.export(db, user=user.username)
    return Response(
        xml, media_type="application/xml", headers={"Content-Disposition": 'attachment; filename="config.xml"'}
    )


# --- factory defaults / reboot --------------------------------------------------------------


@router.get("/defaults")
def defaults(request: Request, user: User = Depends(ui_user)) -> Response:
    return page(request, "pages/system_defaults.html")


@router.post("/defaults")
async def defaults_do(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    form = await request.form()
    if form.get("confirm") != "RESET":
        return page(
            request, "pages/system_defaults.html", status_code=422, errors={"confirm": _("Type RESET to confirm.")}
        )
    audit(db, user.username, "factory-reset")
    db.commit()
    try:
        privileged.run("factory-reset")
    except privileged.PrivilegedError as exc:
        flash(request, str(exc), "error")
        return redirect(request, "/system/defaults")
    return page(
        request,
        "pages/system_rebooting.html",
        message=_("The system is being reset to factory defaults and reboots now."),
    )


@router.get("/reboot")
def reboot(request: Request, user: User = Depends(ui_user)) -> Response:
    return page(request, "pages/system_reboot.html")


@router.post("/reboot")
async def reboot_do(request: Request, user: User = Depends(ui_user), db: Session = Depends(get_db)) -> Response:
    form = await request.form()
    action = "shutdown" if form.get("action") == "shutdown" else "reboot"
    audit(db, user.username, action)
    db.commit()
    try:
        privileged.run(action)
    except privileged.PrivilegedError as exc:
        flash(request, str(exc), "error")
        return redirect(request, "/system/reboot")
    msg = (
        _("The system is shutting down.")
        if action == "shutdown"
        else _("The system is rebooting. This page reloads when it is back.")
    )
    return page(request, "pages/system_rebooting.html", message=msg, poll=action == "reboot")


@router.get("/ping")
def ping() -> HTMLResponse:
    return HTMLResponse("ok")
