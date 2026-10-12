"""Prometheus metrics (text exposition format 0.0.4) for ``GET /api/v1/metrics``.

Written by hand instead of with prometheus_client: everything is computed per
scrape from the database, /proc, the data partition and one AMI connection.
"""

from __future__ import annotations

import datetime as dt
import os
import time
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix import __version__, config
from phonix.core import settings as st
from phonix.core.models import Phone, Provider
from phonix.services import acme, backup, status, tls
from phonix.services.common import dirty_areas

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

Labels = dict[str, str]
Sample = tuple[Labels, float]


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _number(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return repr(float(value))


class Exposition:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, name: str, kind: str, help_text: str, samples: Iterable[Sample] | float) -> None:
        if isinstance(samples, (int, float)):
            samples = [({}, samples)]
        self.lines.append(f"# HELP {name} {help_text}")
        self.lines.append(f"# TYPE {name} {kind}")
        for labels, value in samples:
            label_text = ",".join(f'{k}="{_escape(v)}"' for k, v in labels.items())
            self.lines.append(f"{name}{{{label_text}}} {_number(value)}" if labels else f"{name} {_number(value)}")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


# --- helpers --------------------------------------------------------------------


def _network_counters() -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for line in status._read("/proc/net/dev").splitlines()[2:]:
        name, _, rest = line.partition(":")
        cols = rest.split()
        if name.strip() and name.strip() != "lo" and len(cols) >= 9:
            out[name.strip()] = (int(cols[0]), int(cols[8]))
    return out


def _voicemail_counts() -> list[Sample]:
    """Messages per mailbox and folder (INBOX = new, Old = heard)."""
    base = config.get().path("/var/spool/asterisk/voicemail")
    samples: list[Sample] = []
    try:
        contexts = sorted(p for p in base.iterdir() if p.is_dir())
    except OSError:
        return samples
    for context in contexts:
        for mailbox in sorted(p for p in context.iterdir() if p.is_dir()):
            for folder in ("INBOX", "Old"):
                try:
                    count = sum(1 for _ in (mailbox / folder).glob("msg*.txt"))
                except OSError:
                    continue
                samples.append(({"context": context.name, "mailbox": mailbox.name, "folder": folder}, count))
    return samples


def _asterisk_start(started: str) -> float | None:
    try:
        return time.mktime(time.strptime(started, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return None


def _iso_timestamp(value: Any) -> float | None:
    try:
        return dt.datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return None


def _state_up(state: str) -> bool:
    s = state.lower()
    return bool(s) and not s.startswith(("unavailable", "invalid", "unknown", "unreachable", "lagged", "rejected"))


def _registered(state: str) -> bool:
    return state.lower().startswith("registered")


# --- collection -------------------------------------------------------------------


def collect(session: Session) -> str:
    started = time.monotonic()
    out = Exposition()
    info = status.system_info()
    ast = status.asterisk_status()

    out.add(
        "phonix_build_info",
        "gauge",
        "PhonixPBX and Asterisk version",
        [({"version": __version__, "asterisk_version": ast["version"]}, 1)],
    )

    # system ------------------------------------------------------------------
    out.add("phonix_uptime_seconds", "gauge", "Seconds since the system booted", status.uptime_seconds())
    out.add("phonix_cpus", "gauge", "Number of CPUs", info["cpus"])
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    out.add(
        "phonix_load_average",
        "gauge",
        "System load average",
        [({"period": p}, v) for p, v in zip(("1m", "5m", "15m"), load, strict=True)],
    )
    out.add("phonix_memory_total_bytes", "gauge", "Total memory", info["memory"]["total"])
    out.add("phonix_memory_used_bytes", "gauge", "Memory in use (total minus available)", info["memory"]["used"])
    out.add("phonix_data_disk_total_bytes", "gauge", "Size of the data partition", info["data_disk"]["total"])
    out.add("phonix_data_disk_used_bytes", "gauge", "Used space on the data partition", info["data_disk"]["used"])
    net = _network_counters()
    out.add(
        "phonix_network_receive_bytes_total",
        "counter",
        "Bytes received per network interface",
        [({"interface": name}, rx) for name, (rx, _) in sorted(net.items())],
    )
    out.add(
        "phonix_network_transmit_bytes_total",
        "counter",
        "Bytes sent per network interface",
        [({"interface": name}, tx) for name, (_, tx) in sorted(net.items())],
    )

    # asterisk ----------------------------------------------------------------
    out.add("phonix_asterisk_up", "gauge", "Whether Asterisk answers on the manager interface", int(ast["running"]))
    start = _asterisk_start(ast["started"]) if ast["running"] else None
    if start is not None:
        out.add("phonix_asterisk_start_time_seconds", "gauge", "Unix time Asterisk was started", start)
    out.add("phonix_asterisk_active_calls", "gauge", "Calls in progress", ast["current_calls"])
    out.add("phonix_asterisk_active_channels", "gauge", "Active channels", len(ast["channels"]))

    # phones and providers ----------------------------------------------------
    phones = list(session.scalars(select(Phone).order_by(Phone.extension)))
    counts = Counter((p.tech, p.enabled) for p in phones)
    out.add(
        "phonix_phones",
        "gauge",
        "Configured phones",
        [({"tech": tech, "enabled": str(enabled).lower()}, n) for (tech, enabled), n in sorted(counts.items())],
    )
    registered: list[Sample] = []
    for p in phones:
        if not p.enabled or p.tech == "external":
            continue
        if p.tech == "iax":
            up = _state_up(ast["iax_peers"].get(p.extension, ""))
        else:
            up = bool(ast["endpoints"].get(p.extension, {}).get("addresses"))
        registered.append(({"extension": p.extension, "tech": p.tech}, int(up)))
    if ast["running"]:
        out.add("phonix_phone_registered", "gauge", "Whether an enabled phone is registered", registered)

    providers = [prov for prov in session.scalars(select(Provider).order_by(Provider.id)) if prov.enabled]
    provider_up: list[Sample] = []
    for prov in providers:
        key = f"prov-{prov.id}"
        if prov.tech == "iax":
            up = _state_up(ast["iax_peers"].get(key, ""))
        elif prov.registration:
            up = _registered(ast["registrations"].get(f"{key}-reg", ""))
        else:
            up = _state_up(ast["endpoints"].get(key, {}).get("state", ""))
        provider_up.append(({"provider": key, "name": prov.name, "tech": prov.tech}, int(up)))
    out.add("phonix_providers", "gauge", "Enabled providers", len(providers))
    if ast["running"]:
        out.add(
            "phonix_provider_up",
            "gauge",
            "Whether an enabled provider is registered (or reachable without registration)",
            provider_up,
        )

    out.add("phonix_voicemail_messages", "gauge", "Voicemail messages per mailbox and folder", _voicemail_counts())

    # configuration, certificate, backups ----------------------------------------
    out.add("phonix_pending_changes", "gauge", "Areas with changes that are not applied yet", len(dirty_areas(session)))
    cert = tls.current_certificate()
    if cert is not None:
        out.add(
            "phonix_tls_certificate_expiry_seconds",
            "gauge",
            "Unix time the HTTPS/SIP-TLS certificate expires",
            cert.not_valid_after_utc.timestamp(),
        )
        out.add(
            "phonix_tls_certificate_self_signed",
            "gauge",
            "Whether the certificate is self-signed",
            int(cert.subject == cert.issuer),
        )
    out.add(
        "phonix_acme_enabled",
        "gauge",
        "Whether ACME certificates are enabled",
        int(st.load(session, st.AcmeSettings).enabled),
    )
    acme_status = acme.read_status()
    if acme_status.get("state") in ("ok", "error"):
        out.add(
            "phonix_acme_last_request_success",
            "gauge",
            "Whether the last ACME certificate request succeeded",
            int(acme_status["state"] == "ok"),
        )
        ts = _iso_timestamp(acme_status.get("time"))
        if ts is not None:
            out.add("phonix_acme_last_request_timestamp_seconds", "gauge", "Unix time of the last ACME request", ts)
    backups = backup.list_backups()
    out.add("phonix_backups", "gauge", "Backups stored on the data partition", len(backups))
    if backups:
        out.add(
            "phonix_backup_last_timestamp_seconds",
            "gauge",
            "Unix time of the newest backup",
            _mtime(backups[0]),
        )

    out.add(
        "phonix_scrape_duration_seconds", "gauge", "Time taken to collect these metrics", time.monotonic() - started
    )
    return out.text()


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
