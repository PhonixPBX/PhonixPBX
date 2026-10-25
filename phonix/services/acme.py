# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Certificates from an ACME CA (Let's Encrypt, ZeroSSL, ...) obtained with lego.

lego does the ACME protocol, HTTP-01 (webroot served by nginx) and DNS-01
(about 180 DNS provider APIs, credentials in environment variables). Its state
(account key, issued certificates) lives in ``<data>/acme``; a fresh
certificate is copied to the regular TLS paths and the consumers are reloaded.
``phonix cert renew`` runs daily from cron and renews 30 days before expiry;
PhonixPBX decides when, lego always renews when it is called. lego v5 changed
the layout of its state; data written by lego v4 is converted with
``lego migrate`` before the first run.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix import ami, config
from phonix.core import settings as st
from phonix.core.models import Provider
from phonix.i18n import _
from phonix.services import privileged, tls
from phonix.services.common import ServiceError, audit

log = logging.getLogger(__name__)

LEGO = "lego"
RENEW_DAYS = 30
TIMEOUT = 600
LOG_LINES = 40


def domains(session: Session, acme: st.AcmeSettings | None = None) -> list[str]:
    acme = acme or st.load(session, st.AcmeSettings)
    if acme.domains:
        return list(acme.domains)
    system = st.load(session, st.SystemSettings)
    return [f"{system.hostname}.{system.domain}"]


def build_command(acme: st.AcmeSettings, names: list[str]) -> tuple[list[str], dict[str, str]]:
    """lego command line and environment for obtaining a certificate for ``names``."""
    cfg = config.get()
    argv = [
        LEGO, "run",
        "--accept-tos",
        "--email", acme.email,
        "--server", acme.directory_url,
        "--path", str(cfg.acme_dir),
        "--key-type", "EC256",
        # renew now, for exactly these names (default: only when lego thinks
        # it is due, after a random sleep, merged with the stored names)
        "--renew-force", "--no-random-sleep", "--force-cert-domains",
    ]  # fmt: skip
    for name in names:
        argv += ["--domains", name]
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "HOME": str(cfg.acme_dir)}
    if acme.eab_kid and acme.eab_hmac:
        # environment instead of flags: keeps the HMAC key out of the process list
        env.update({"LEGO_EAB": "true", "LEGO_EAB_KID": acme.eab_kid, "LEGO_EAB_HMAC": acme.eab_hmac})
    if acme.challenge == "http":
        argv += ["--http", "--http.webroot", str(cfg.acme_webroot)]
    else:
        argv += ["--dns", acme.dns_provider]
        for resolver in acme.dns_resolvers:
            argv += ["--dns.resolvers", resolver]
        env.update(acme.dns_env)
    return argv, env


def issued_files(names: list[str]) -> tuple[Path, Path]:
    """Where lego stores the certificate (with chain) and key for ``names``."""
    name = names[0].replace(":", "-").replace("*", "_").encode("idna").decode("ascii")
    base = config.get().acme_dir / "certificates" / name
    return base.with_name(base.name + ".crt"), base.with_name(base.name + ".key")


def needs_migration() -> bool:
    """Whether ``<data>/acme`` holds accounts or certificates in the lego v4 layout.

    Like ``lego migrate`` itself: account and certificate JSON files written by
    lego v4 lack the ``origin`` that v5 adds. A v5 run on that state would
    register a new account and fail to read the certificates.
    """
    base = config.get().acme_dir
    for path in [*base.glob("accounts/*/*/account.json"), *base.glob("certificates/*.json")]:
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and "origin" not in data:
            return True
    return False


def migrate() -> None:
    """Convert lego v4 state with ``lego migrate`` (idempotent)."""
    cfg = config.get()
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "HOME": str(cfg.acme_dir)}
    # lego migrate fails if one of them is missing (v4 account, no certificate yet)
    for name in ("accounts", "certificates"):
        (cfg.acme_dir / name).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        # the confirmation prompt is answered on stdin; the suggested
        # configuration file it writes into the working directory is not needed
        try:
            proc = subprocess.run(
                [LEGO, "migrate", "--path", str(cfg.acme_dir)],
                env=env,
                cwd=tmp,
                input="y\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=60,
                check=False,
            )
        except FileNotFoundError:
            raise ServiceError(_("The lego ACME client is not installed.")) from None
        except subprocess.TimeoutExpired as exc:
            output = exc.output if isinstance(exc.output, str) else ""
            raise LegoError("lego migrate did not finish within 60 seconds.", output) from None
    output = proc.stdout or ""
    if proc.returncode != 0:
        raise LegoError(_lego_error(output) or f"lego migrate failed (exit code {proc.returncode}).", output)
    log.info("migrated %s to the lego v5 layout", cfg.acme_dir)


def renewal_reason(names: list[str], days: int = RENEW_DAYS) -> str:
    """Why the installed certificate has to be replaced; empty if it is fine."""
    cert = tls.current_certificate()
    if cert is None:
        return "no certificate installed"
    if cert.subject == cert.issuer:
        return "self-signed certificate installed"
    if sorted(tls.dns_names(cert)) != sorted(names):
        return "domain names changed"
    left = cert.not_valid_after_utc - dt.datetime.now(dt.timezone.utc)
    if left < dt.timedelta(days=days):
        return f"expires in {max(left.days, 0)} days"
    return ""


# --- status (shown in the web UI, written by the CLI) -------------------------


def _status_path() -> Path:
    return config.get().acme_dir / "status.json"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class LegoError(ServiceError):
    def __init__(self, message: str, output: str = "") -> None:
        super().__init__(message)
        self.output = output


def write_status(state: str, message: str = "", output: str = "", pid: int | None = None) -> None:
    path = _status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "state": state,
        "message": message,
        "log": output.splitlines()[-LOG_LINES:],
        "time": _now(),
        "pid": (pid or os.getpid()) if state == "running" else None,
        "id": secrets.token_hex(8),
    }
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def _read_raw() -> dict[str, Any]:
    try:
        data = json.loads(_status_path().read_text())
    except (OSError, ValueError):
        return {"state": "none"}
    return data if isinstance(data, dict) else {"state": "none"}


def read_status() -> dict[str, Any]:
    data = _read_raw()
    if data.get("state") == "running" and not _alive(data.get("pid")):
        data["state"] = "error"
        data["message"] = "The certificate request was interrupted."
    return data


def _alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextmanager
def _locked() -> Iterator[None]:
    path = config.get().acme_dir / "lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ServiceError(_("A certificate request is already running.")) from None
        yield


# --- issue / renew ------------------------------------------------------------------


def tls_transport_used(session: Session) -> bool:
    """Whether Asterisk has a SIP-TLS transport (see generators/asterisk.transports)."""
    if st.load(session, st.SipSettings).tls_enabled:
        return True
    rows = session.scalars(select(Provider).where(Provider.enabled.is_(True), Provider.tech == "pjsip"))
    return any(p.transport == "tls" for p in rows)


def reload_consumers(session: Session) -> list[str]:
    """Make nginx and Asterisk (SIP-TLS) use the installed certificate. Returns warnings."""
    warnings = []
    try:
        privileged.run("nginx-reload")
    except privileged.PrivilegedError as exc:
        warnings.append(_("Reloading the web server failed: %(error)s", error=exc))
    # PJSIP transports only read the certificate when they are created; restart
    # once no call is active instead of dropping calls
    if tls_transport_used(session) and ami.is_running():
        try:
            ami.run_commands(["core restart when convenient"])
        except ami.AmiError as exc:
            warnings.append(_("Restarting Asterisk for SIP-TLS failed: %(error)s", error=exc))
    return warnings


def issue(session: Session, force: bool = False, user: str = "acme") -> str:
    """Obtain a certificate if one is due (or ``force``). Returns a summary message."""
    acme = st.load(session, st.AcmeSettings)
    if not acme.enabled:
        if force:
            write_status("error", "Automatic certificates are disabled.")
        return "ACME is disabled."
    names = domains(session, acme)
    with _locked():
        reason = "requested" if force else renewal_reason(names)
        if not reason:
            return "The certificate is still valid, nothing to do."
        write_status("running", f"Requesting a certificate for {', '.join(names)} ({reason}).")
        try:
            message = _obtain(session, acme, names, user)
        except LegoError as exc:
            write_status("error", str(exc), exc.output)
            raise
        except ServiceError as exc:
            write_status("error", str(exc))
            raise
        except Exception as exc:
            write_status("error", f"Unexpected error: {exc}")
            raise
        return message


def _obtain(session: Session, acme: st.AcmeSettings, names: list[str], user: str) -> str:
    cfg = config.get()
    argv, env = build_command(acme, names)
    if acme.challenge == "http":
        cfg.acme_webroot.mkdir(parents=True, exist_ok=True)
    if needs_migration():
        migrate()
    try:
        proc = subprocess.run(
            argv,
            env=env,
            cwd=cfg.acme_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        raise ServiceError(_("The lego ACME client is not installed.")) from None
    except subprocess.TimeoutExpired as exc:
        output = exc.output if isinstance(exc.output, str) else ""
        raise LegoError(f"lego did not finish within {TIMEOUT} seconds.", output) from None
    output = proc.stdout or ""
    if proc.returncode != 0:
        raise LegoError(_lego_error(output) or f"lego failed (exit code {proc.returncode}).", output)
    crt, key = issued_files(names)
    try:
        tls.install_certificate(crt.read_bytes(), key.read_bytes())
    except OSError as exc:
        raise ServiceError(f"lego succeeded but the certificate files are missing: {exc}") from None
    warnings = reload_consumers(session)
    audit(session, user, "certificate", summary=f"obtained ACME certificate for {', '.join(names)}")
    session.commit()
    cert = tls.current_certificate()
    until = cert.not_valid_after_utc.strftime("%Y-%m-%d") if cert else "?"
    message = f"Certificate for {', '.join(names)} installed, valid until {until}."
    if warnings:
        message += " " + " ".join(warnings)
    write_status("ok", message, output)
    return message


def _lego_error(output: str) -> str:
    """lego's fatal message: its last log line, without timestamp and level.

    lego v5 ends with ``<time> ERROR Error error="<message>"``.
    """
    for line in reversed(output.splitlines()):
        line = re.sub(r"^\d{4}-\d\d-\d\dT\S+\s+(?:[A-Z]+\s+)?", "", line.strip())
        if m := re.fullmatch(r'Error error="(.*)"', line):
            line = m.group(1).replace('\\"', '"').replace("\\\\", "\\")
        if line:
            return line[:500]
    return ""


def start_background() -> None:
    """Run ``phonix cert renew --force`` detached, so the web request returns at once."""
    if read_status().get("state") == "running":
        raise ServiceError(_("A certificate request is already running."))
    before = _read_raw().get("id")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "phonix.cli", "cert", "renew", "--force"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            cwd="/",
        )
    except OSError as exc:
        write_status("error", f"Could not start the certificate request: {exc}")
        raise ServiceError(_("Could not start the certificate request: %(error)s", error=exc)) from exc
    # reap the child when it exits (a zombie would look alive to read_status)
    threading.Thread(target=proc.wait, daemon=True).start()
    # show "running" right away unless the child already wrote its own status
    if _read_raw().get("id") == before:
        write_status("running", "Starting the certificate request.", pid=proc.pid)
