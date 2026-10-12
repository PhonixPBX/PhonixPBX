"""Live status: system resources and Asterisk state (via AMI)."""

from __future__ import annotations

import os
import platform
import re
import shutil
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from phonix import __version__, ami, config


def _read(path: str) -> str:
    try:
        return Path(path).read_text()
    except OSError:
        return ""


def uptime_seconds() -> int:
    raw = _read("/proc/uptime").split()
    return int(float(raw[0])) if raw else 0


def format_duration(seconds: int) -> str:
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def memory() -> dict[str, int]:
    info: dict[str, int] = {}
    for line in _read("/proc/meminfo").splitlines():
        key, _, rest = line.partition(":")
        if key in ("MemTotal", "MemAvailable"):
            info[key] = int(rest.split()[0]) * 1024
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", 0)
    return {"total": total, "used": total - avail}


def disk(path: str) -> dict[str, int]:
    try:
        usage = shutil.disk_usage(path)
        return {"total": usage.total, "used": usage.used}
    except OSError:
        return {"total": 0, "used": 0}


def cpu_model() -> str:
    info: dict[str, str] = {}
    for line in _read("/proc/cpuinfo").splitlines():
        key, _, value = line.partition(":")
        info.setdefault(key.strip().lower(), value.strip())
    # x86: "model name"; Raspberry Pi: "Model" (board) / "Hardware"
    for key in ("model name", "hardware"):
        if info.get(key):
            return info[key]
    model = info.get("model", "")
    return model if model and not model.isdigit() else platform.machine()


def system_info() -> dict[str, Any]:
    cfg = config.get()
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    return {
        "version": __version__,
        "kernel": platform.release(),
        "arch": platform.machine(),
        "cpu": cpu_model(),
        "cpus": os.cpu_count() or 1,
        "uptime": format_duration(uptime_seconds()),
        "load": [round(x, 2) for x in load],
        "memory": memory(),
        "data_disk": disk(str(cfg.data_dir)),
    }


# --- sampled metrics for the graphs (CPU %, network bytes/s) -----------------


@dataclass
class Sample:
    ts: float
    cpu: float
    rx: float
    tx: float


class Sampler:
    """Keeps a short history; sampled lazily whenever the dashboard polls."""

    def __init__(self, size: int = 120) -> None:
        self.history: deque[Sample] = deque(maxlen=size)
        self._last_cpu: tuple[int, int] | None = None
        self._last_net: tuple[float, int, int] | None = None

    @staticmethod
    def _cpu_counters() -> tuple[int, int]:
        stat = _read("/proc/stat")
        values = [int(x) for x in stat.splitlines()[0].split()[1:]] if stat else []
        if not values:
            return 0, 0
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return sum(values), idle

    @staticmethod
    def _net_counters() -> tuple[int, int]:
        rx = tx = 0
        for line in _read("/proc/net/dev").splitlines()[2:]:
            name, _, rest = line.partition(":")
            if name.strip() == "lo":
                continue
            cols = rest.split()
            if len(cols) >= 9:
                rx += int(cols[0])
                tx += int(cols[8])
        return rx, tx

    def sample(self) -> Sample:
        now = time.monotonic()
        # several browsers polling at once must not produce bogus short samples
        if self.history and self._last_net and now - self._last_net[0] < 1.0:
            return self.history[-1]
        total, idle = self._cpu_counters()
        rx, tx = self._net_counters()
        cpu = 0.0
        if self._last_cpu and total > self._last_cpu[0]:
            dt_total = total - self._last_cpu[0]
            cpu = 100.0 * (1 - (idle - self._last_cpu[1]) / dt_total)
        rx_rate = tx_rate = 0.0
        if self._last_net and now > self._last_net[0]:
            dt = now - self._last_net[0]
            rx_rate = max(0.0, (rx - self._last_net[1]) / dt)
            tx_rate = max(0.0, (tx - self._last_net[2]) / dt)
        self._last_cpu = (total, idle)
        self._last_net = (now, rx, tx)
        sample = Sample(time.time(), round(cpu, 1), round(rx_rate), round(tx_rate))
        self.history.append(sample)
        return sample


sampler = Sampler()


# --- Asterisk ------------------------------------------------------------------


def asterisk_status() -> dict[str, Any]:
    """Registrations, trunk state and active channels. Never raises."""
    out: dict[str, Any] = {
        "running": False,
        "version": "",
        "uptime": "",
        "endpoints": {},
        "registrations": {},
        "iax_peers": {},
        "channels": [],
        "current_calls": 0,
        # "YYYY-MM-DD HH:MM:SS" local time
        "started": "",
        "error": "",
    }
    try:
        with ami.AmiClient(timeout=3.0) as client:
            out["running"] = True
            info = client.action("CoreStatus")
            out["uptime"] = info.get("CoreStartupTime", "")
            out["started"] = f"{info.get('CoreStartupDate', '')} {info.get('CoreStartupTime', '')}".strip()
            calls = info.get("CoreCurrentCalls", "")
            out["current_calls"] = int(calls) if calls.isdigit() else 0
            settings = client.action("CoreSettings")
            out["version"] = settings.get("AsteriskVersion", "")
            for ev in client.action_list("PJSIPShowEndpoints"):
                out["endpoints"][ev.get("ObjectName", "")] = {
                    "state": ev.get("DeviceState", ""),
                    "contacts": ev.get("Contacts", ""),
                }
            for ev in client.action_list("PJSIPShowContacts"):
                # ContactList events carry no Aor field; the contact is named
                # "<aor>;@<hash>" ("<aor>@@<hash>" on older Asterisk)
                aor = re.split(r";@|@@", ev.get("ObjectName", ""), maxsplit=1)[0]
                rtt = ev.get("RoundtripUsec", "")
                out["endpoints"].setdefault(aor, {}).setdefault("addresses", []).append(
                    {
                        "uri": ev.get("Uri", ""),
                        "status": ev.get("Status", ""),
                        "rtt": rtt if rtt.isdigit() else "",
                        "agent": ev.get("UserAgent", ""),
                    }
                )
            for ev in client.action_list("PJSIPShowRegistrationsOutbound"):
                out["registrations"][ev.get("ObjectName", "")] = ev.get("Status", "")
            try:
                for ev in client.action_list("IAXpeerlist"):
                    out["iax_peers"][ev.get("ObjectName", "")] = ev.get("Status", "")
            except ami.AmiError:
                pass
            for ev in client.action_list("CoreShowChannels"):
                out["channels"].append(
                    {
                        "channel": ev.get("Channel", ""),
                        "callerid": f"{ev.get('CallerIDName', '')} <{ev.get('CallerIDNum', '')}>",
                        "exten": ev.get("Exten", ""),
                        "state": ev.get("ChannelStateDesc", ""),
                        "app": ev.get("Application", ""),
                        "duration": ev.get("Duration", ""),
                        "bridged": ev.get("BridgeId", ""),
                    }
                )
    except ami.AmiError as exc:
        out["error"] = str(exc)
    return out


def tail(path: Path, lines: int = 200, max_bytes: int = 512 * 1024) -> list[str]:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            data = fh.read().decode("utf-8", "replace")
    except OSError:
        return []
    return data.splitlines()[-lines:]
