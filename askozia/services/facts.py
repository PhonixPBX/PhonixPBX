"""Collect runtime facts (current LAN address etc.) for the generators."""

from __future__ import annotations

import ipaddress
import json
import socket
import subprocess

from askozia import config
from askozia.core.settings import NetworkSettings
from askozia.generators.base import Facts


def interface_ipv4(interface: str) -> tuple[str, int] | None:
    try:
        proc = subprocess.run(
            ["ip", "-j", "-4", "addr", "show", "dev", interface],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        data = json.loads(proc.stdout or "[]")
        for iface in data:
            for addr in iface.get("addr_info", []):
                if addr.get("family") == "inet":
                    return addr["local"], int(addr["prefixlen"])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def default_route_ipv4() -> str | None:
    """Address used for outgoing traffic (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            return str(sock.getsockname()[0])
    except OSError:
        return None


def collect(net: NetworkSettings) -> Facts:
    cfg = config.get()
    if net.mode == "static":
        ip, prefix = net.address, net.prefix
    else:
        found = interface_ipv4(net.interface)
        if found:
            ip, prefix = found
        else:
            ip, prefix = default_route_ipv4() or "127.0.0.1", 24
    ipaddress.IPv4Address(ip)
    return Facts(lan_ip=ip, lan_prefix=prefix, data_dir=str(cfg.data_dir))
