"""Post-boot health check used to confirm an update slot."""

from __future__ import annotations

import socket
import time

from askozia import ami, config


def _web_up(path: str = "/run/askozia/web.sock") -> bool:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect(path)
            sock.sendall(b"GET /healthz HTTP/1.0\r\nHost: localhost\r\n\r\n")
            return sock.recv(64).startswith(b"HTTP/1.1 200")
    except OSError:
        return False


def check(retries: int = 30, delay: float = 2.0) -> tuple[bool, list[str]]:
    details: list[str] = []
    web = asterisk = False
    for _ in range(retries):
        web = web or _web_up()
        asterisk = asterisk or ami.is_running()
        if web and asterisk:
            break
        time.sleep(delay)
    details.append(f"web interface: {'ok' if web else 'NOT responding'}")
    details.append(f"asterisk: {'ok' if asterisk else 'NOT responding'}")
    db_ok = config.get().db_path.exists()
    details.append(f"database: {'ok' if db_ok else 'missing'}")
    return web and asterisk and db_ok, details
