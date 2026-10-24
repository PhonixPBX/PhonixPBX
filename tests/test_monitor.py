# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import pytest
from factories import sample_pbx

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


@pytest.fixture
def ids(session):
    out = sample_pbx(session)
    session.flush()
    return out


def _hours_with_specials(session):
    from phonix.services import hours

    data = hours.BusinessHoursIn.model_validate(
        {
            "name": "Shop",
            "feature_code": "*45",
            "open_dest_type": "hangup",
            "specials": [
                {"name": "Phone switched", "dest_type": "hangup", "enabled": False},
                {"name": "Other", "dest_type": "hangup", "enabled": True},
            ],
        }
    )
    return hours.create_hours(session, data)


def test_sync_once(session, ids, fake_ami):
    import datetime as dt

    from phonix.services import hours, hours_sync
    from phonix.services.common import clear_dirty, dirty_areas

    office = ids["office"]
    h = _hours_with_specials(session)
    session.flush()
    clear_dirty(session)
    switched, other = h.specials[0].id, h.specials[1].id
    now = dt.datetime(2026, 10, 24, 10, 0)  # Saturday
    db = fake_ami.astdb
    db[("phonix-hours-tmp", str(office))] = "closed:2026-10-23"  # expired: other day
    db[("phonix-hours-tmp", str(h.id))] = "open:2026-10-24"  # still valid (Shop is closed all week)
    db[("phonix-hours-tmp", "888")] = "open:2026-10-24"  # unknown id
    db[("phonix-hours", "888")] = "closed"
    db[("phonix-hours", str(h.id))] = "garbage"
    db[("phonix-special", "999")] = "1"
    db[("phonix-special", str(switched))] = "1"  # switched on by a phone

    hours_sync.sync_once(session, fake_ami(), now)

    assert ("phonix-hours-tmp", str(office)) not in db
    assert ("phonix-hours-tmp", "888") not in db
    assert ("phonix-hours", "888") not in db
    assert ("phonix-hours", str(h.id)) not in db
    assert ("phonix-special", "999") not in db
    assert db[("phonix-hours-tmp", str(h.id))] == "open:2026-10-24"
    assert hours.get_hours(session, h.id).specials[0].enabled is True
    assert db[("phonix-special", str(other))] == "1"
    assert db[("phonix-special", str(switched))] == "1"
    assert not dirty_areas(session)
    assert any(
        a[1].get("Command", "").startswith(f"devstate change Custom:phonix-hours-{h.id}") for a in fake_ami.actions
    )


def test_sync_once_drops_override_equal_to_automatic_state(session, ids, fake_ami):
    import datetime as dt

    from phonix.services import hours_sync

    h = _hours_with_specials(session)
    session.flush()
    fake_ami.astdb[("phonix-hours-tmp", str(h.id))] = "closed:2026-10-24"  # Shop is closed anyway
    hours_sync.sync_once(session, fake_ami(), dt.datetime(2026, 10, 24, 10, 0))
    assert ("phonix-hours-tmp", str(h.id)) not in fake_ami.astdb


def test_run_forever_survives_errors(monkeypatch):
    import threading

    from phonix import ami
    from phonix.services import hours_sync

    class Broken:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            raise ami.AmiError("down")

        def __exit__(self, *exc):
            pass

    monkeypatch.setattr(hours_sync.ami, "AmiClient", Broken)
    stop = threading.Event()
    waits = []

    def wait(timeout=None):
        waits.append(timeout)
        stop.set()
        return True

    monkeypatch.setattr(stop, "wait", wait)
    hours_sync.run_forever(interval=5, stop=stop)
    assert waits == [5]
