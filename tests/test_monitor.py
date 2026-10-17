# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
from phonix.services.monitor import Banner, remote_ip


def test_remote_ip():
    assert remote_ip("IPV4/UDP/203.0.113.5/5060") == "203.0.113.5"
    assert remote_ip("IPV4/UDP/127.0.0.1/5060") is None
    assert remote_ip("garbage") is None


def test_banner_threshold_and_whitelist():
    b = Banner(threshold=3, seconds=60, whitelist=["192.168.1.0/24"])
    assert not b.record("203.0.113.5", now=1)
    assert not b.record("203.0.113.5", now=2)
    assert b.record("203.0.113.5", now=3)
    assert not b.record("203.0.113.5", now=4)  # already banned
    assert not any(b.record("192.168.1.20", now=t) for t in range(10))
    # failures outside the window do not count
    b2 = Banner(threshold=2, seconds=60, whitelist=[])
    assert not b2.record("198.51.100.1", now=0)
    assert not b2.record("198.51.100.1", now=10_000)


def test_load_keeps_state_and_follows_settings(initialized):
    from phonix.core import settings as st
    from phonix.core.db import session_scope
    from phonix.services.monitor import _load

    with session_scope() as s:
        st.save(s, st.FirewallSettings(enabled=True, ban_enabled=True, ban_threshold=2, ban_seconds=60))
    banner = _load()
    assert banner is not None and not banner.record("203.0.113.5", now=1)
    with session_scope() as s:
        st.save(s, st.FirewallSettings(enabled=True, ban_enabled=True, ban_threshold=5, ban_seconds=300))
    assert _load(banner) is banner and (banner.threshold, banner.seconds) == (5, 300)
    assert len(banner.failures["203.0.113.5"]) == 1
    with session_scope() as s:
        st.save(s, st.FirewallSettings(enabled=True, ban_enabled=False))
    assert _load(banner) is None
