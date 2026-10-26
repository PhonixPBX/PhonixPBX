# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Ban hosts that repeatedly fail SIP/IAX/AMI authentication (fail2ban equivalent).

Listens to Asterisk security events over AMI and asks the root helper to put
offending addresses into the nftables ``banned4``/``banned6`` sets.
"""

from __future__ import annotations

import ipaddress
import logging
import threading
import time
from collections import defaultdict, deque

from phonix import ami
from phonix.core import settings as st
from phonix.core.db import session_scope
from phonix.services import hours_sync, privileged, recording

log = logging.getLogger(__name__)

FAILURE_EVENTS = {
    "InvalidAccountID",
    "ChallengeResponseFailed",
    "InvalidPassword",
    "FailedACL",
    "UnexpectedAddress",
    "RequestNotAllowed",
}
WINDOW = 600  # seconds in which ban_threshold failures lead to a ban
RELOAD = 60  # seconds after which the firewall settings are read again


def remote_ip(address: str) -> str | None:
    """Parse AMI security addresses like ``IPV4/UDP/203.0.113.5/5060``."""
    parts = address.split("/")
    if len(parts) >= 3:
        try:
            ip = ipaddress.ip_address(parts[2])
        except ValueError:
            return None
        if ip.is_loopback:
            return None
        return str(ip)
    return None


class Banner:
    def __init__(self, threshold: int, seconds: int, whitelist: list[str]) -> None:
        self.configure(threshold, seconds, whitelist)
        self.failures: dict[str, deque[float]] = defaultdict(deque)
        self.banned: dict[str, float] = {}

    def configure(self, threshold: int, seconds: int, whitelist: list[str]) -> None:
        self.threshold = threshold
        self.seconds = seconds
        self.whitelist = [ipaddress.ip_network(n, strict=False) for n in whitelist]

    def whitelisted(self, ip: str) -> bool:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in self.whitelist)

    def record(self, ip: str, now: float | None = None) -> bool:
        """Record a failure; returns True when the address must be banned now."""
        now = time.monotonic() if now is None else now
        if self.whitelisted(ip) or self.banned.get(ip, 0) > now:
            return False
        q = self.failures[ip]
        q.append(now)
        while q and q[0] < now - WINDOW:
            q.popleft()
        if len(q) >= self.threshold:
            q.clear()
            self.banned[ip] = now + self.seconds
            return True
        return False


def _load(previous: Banner | None = None) -> Banner | None:
    """Banner for the current firewall settings (None: banning is off); keeps the
    failure counters and bans of *previous*."""
    with session_scope() as session:
        fw = st.load(session, st.FirewallSettings)
        net = st.load(session, st.NetworkSettings)
    if not (fw.enabled and fw.ban_enabled):
        return None
    whitelist = list(fw.admin_allowed_networks)
    if net.mode == "static":
        whitelist.append(f"{net.address}/{net.prefix}")
    if previous is None:
        return Banner(fw.ban_threshold, fw.ban_seconds, whitelist)
    previous.configure(fw.ban_threshold, fw.ban_seconds, whitelist)
    return previous


def _recording_cleanup(interval: float = 600.0) -> None:
    """Recordings by phone whose page was closed: files, state and AstDB entries."""
    while True:
        try:
            recording.cleanup()
        except Exception:
            log.exception("cleaning up recordings failed")
        time.sleep(interval)


def run_forever() -> None:
    threading.Thread(target=hours_sync.run_forever, name="hours-sync", daemon=True).start()
    threading.Thread(target=_recording_cleanup, name="recording-cleanup", daemon=True).start()
    banner: Banner | None = None
    while True:
        banner = _load(banner)
        if banner is None:
            time.sleep(60)
            continue
        loaded = time.monotonic()
        try:
            with ami.AmiClient() as client:
                log.info("watching Asterisk security events")
                for event in client.events():
                    if event.get("Event") not in FAILURE_EVENTS:
                        continue
                    if time.monotonic() - loaded > RELOAD:
                        # settings changed in the web interface apply without a restart
                        banner, loaded = _load(banner), time.monotonic()
                        if banner is None:
                            break
                    ip = remote_ip(event.get("RemoteAddress", ""))
                    if ip and banner.record(ip):
                        log.warning("banning %s for %ss", ip, banner.seconds)
                        try:
                            privileged.run("ban", ip, str(banner.seconds))
                        except privileged.PrivilegedError as exc:
                            log.error("ban failed: %s", exc)
        except ami.AmiError as exc:
            log.info("AMI unavailable (%s), retrying", exc)
            time.sleep(10)
