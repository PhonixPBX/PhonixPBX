# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""IVR menus and business hours: services, dialplan, UI, REST and MCP."""

import datetime as dt
import re
from urllib.parse import urlencode

import pytest
from factories import sample_pbx
from fastapi.testclient import TestClient
from test_web import bearer, csrf, login

from phonix.core.db import session_scope
from phonix.core.models import BusinessHours, IvrMenu, IvrOption, ProviderIncomingRoute
from phonix.generators import dialplan
from phonix.generators.base import build_snapshot
from phonix.services import dialplan as dp
from phonix.services import hours, ivr, media, phones, users
from phonix.services.common import NotFound, ServiceError, clear_dirty, dirty_areas


def _menu(**kw) -> ivr.IvrMenuIn:
    data = {"name": "Menu", "prompt_mode": "sound", "prompt_sound": "welcome", **kw}
    return ivr.IvrMenuIn.model_validate(data)


def _hours(**kw) -> hours.BusinessHoursIn:
    data = {"name": "Office", "open_dest_type": "hangup", **kw}
    return hours.BusinessHoursIn.model_validate(data)


@pytest.fixture
def ids(session):
    out = sample_pbx(session)
    session.flush()
    return out


@pytest.fixture
def client(initialized):
    from phonix.web.app import create_app

    with session_scope() as s:
        users.create_user(s, "admin", "adminadmin")
        sample = sample_pbx(s)
    with TestClient(create_app()) as c:
        c.ids = sample  # type: ignore[attr-defined]
        yield c


# --- services ---------------------------------------------------------------------------


def test_menu_validation(session, ids):
    alice, bob = ids["alice"], ids["bob"]
    with pytest.raises(ServiceError) as exc:
        ivr.create_menu(session, _menu(prompt_mode="upload"))
    assert "prompt_media_id" in exc.value.fields
    with pytest.raises(ServiceError) as exc:
        ivr.create_menu(
            session,
            _menu(
                options=[
                    {"key": "1", "dest_type": "phone", "dest_id": alice},
                    {"key": "1", "dest_type": "hangup"},
                ]
            ),
        )
    assert "options.1" in exc.value.fields
    # bob has no voicemail box
    with pytest.raises(ServiceError) as exc:
        ivr.create_menu(session, _menu(options=[{"key": "1", "dest_type": "voicemail", "dest_id": bob}]))
    assert "options.0" in exc.value.fields
    with pytest.raises(ServiceError) as exc:
        ivr.create_menu(session, _menu(extension="101"))
    assert "phone Alice" in exc.value.fields["extension"]
    with pytest.raises(ServiceError) as exc:
        ivr.create_menu(session, _menu(timeout_dest_type="phone", timeout_dest_id=9999))
    assert "timeout_dest" in exc.value.fields
    with pytest.raises(ServiceError, match="Choose a destination"):
        from phonix.services.common import parse

        parse(ivr.IvrMenuIn, {"name": "x", "options": [{"key": "1", "dest_type": ""}]})
    # the menu number is taken for other objects now
    with pytest.raises(ServiceError) as exc:
        dp.create_callgroup(session, dp.CallGroupIn(name="X", extension="600", member_ids=[alice]))
    assert "IVR menu Main menu" in exc.value.fields["extension"]


def test_menu_options_keep_their_order_and_keys_can_swap(session, ids):
    menu = ivr.get_menu(session, ids["main_menu"])
    data = ivr.to_dict(menu)
    options = data["options"]
    # swap the keys of the first two options and move the last one to the front
    options[0]["key"], options[1]["key"] = options[1]["key"], options[0]["key"]
    data["options"] = [options[-1], *options[:-1]]
    ivr.update_menu(session, menu.id, ivr.IvrMenuIn.model_validate(data))
    session.expire_all()
    menu = ivr.get_menu(session, ids["main_menu"])
    assert [(o.key, o.label) for o in menu.options] == [
        ("#", "Repeat"),
        ("2", "Sales"),
        ("1", "Support"),
        ("3", "Conference"),
        ("0", "Reception"),
    ]


def test_timeout_cannot_loop_to_itself(session, ids):
    data = ivr.to_dict(ivr.get_menu(session, ids["main_menu"]))
    data.update(timeout_dest_type="ivr", timeout_dest_id=ids["main_menu"])
    with pytest.raises(ServiceError) as exc:
        ivr.update_menu(session, ids["main_menu"], ivr.IvrMenuIn.model_validate(data))
    assert "timeout_dest" in exc.value.fields


def test_deleting_a_destination_cleans_up_references(session, ids):
    phones.delete_phone(session, ids["alice"])
    session.expire_all()
    main = ivr.get_menu(session, ids["main_menu"])
    assert "0" not in {o.key for o in main.options}  # reception rang alice
    assert (main.timeout_dest_type, main.timeout_dest_id) == ("hangup", None)
    office = hours.get_hours(session, ids["office"])
    assert (office.closed_dest_type, office.closed_dest_id) == ("hangup", None)  # alice's mailbox
    support = ivr.get_menu(session, ids["support_menu"])
    assert "9" not in {o.key for o in support.options}

    ivr.delete_menu(session, ids["main_menu"])
    session.expire_all()
    office = hours.get_hours(session, ids["office"])
    assert office.open_dest_type == "hangup"
    assert not session.query(IvrOption).filter_by(dest_type="ivr", dest_id=ids["main_menu"]).count()

    hours.delete_hours(session, ids["office"])
    assert not session.query(ProviderIncomingRoute).filter_by(dest_type="hours").count()


def test_script(session, ids):
    menu = ivr.get_menu(session, ids["main_menu"])
    options = [ivr.IvrOptionIn.model_validate(o) for o in ivr.to_dict(menu)["options"]]
    assert ivr.script(session, options) == (
        "For Sales, press 1. For Support, press 2. For Conference, press 3. For Reception, press 0. "
        "To hear these options again, press the hash key."
    )


def test_flow_shows_submenus_and_ways_back(session, ids):
    rows = ivr.flow(session, ivr.get_menu(session, ids["main_menu"]))
    assert [(r["depth"], r["key"], r["back"]) for r in rows] == [
        (0, "1", False),
        (0, "2", False),
        (1, "1", False),
        (1, "9", False),
        (1, "*", True),
        (0, "3", False),
        (0, "0", False),
        (0, "#", False),
    ]


def test_hours_validation(session, ids):
    with pytest.raises(ServiceError):
        from phonix.services.common import parse

        parse(
            hours.BusinessHoursIn,
            {"name": "x", "open_dest_type": "hangup", "ranges": [{"weekday": 0, "start": "12:00", "end": "08:00"}]},
        )
    with pytest.raises(ServiceError) as exc:
        hours.create_hours(session, _hours(feature_code="*81"))  # pickup is *8
    assert "pickup" in exc.value.fields["feature_code"]
    with pytest.raises(ServiceError) as exc:
        hours.create_hours(session, _hours(feature_code="*31"))
    assert "Office hours" in exc.value.fields["feature_code"]
    with pytest.raises(ServiceError) as exc:
        hours.create_hours(session, _hours(holidays=[{"date": "2026-01-01"}, {"date": "2026-01-01"}]))
    assert "holidays.1" in exc.value.fields
    # range times are normalised, duplicates dropped and ordered
    h = hours.create_hours(
        session,
        _hours(
            ranges=[
                {"weekday": 2, "start": "9:00", "end": "24:00"},
                {"weekday": 0, "start": "08:00", "end": "12:00"},
                {"weekday": 0, "start": "08:00", "end": "12:00"},
            ]
        ),
    )
    session.expire_all()
    assert [(r.weekday, r.start, r.end) for r in hours.get_hours(session, h.id).ranges] == [
        (0, "08:00", "12:00"),
        (2, "09:00", "24:00"),
    ]


@pytest.mark.parametrize(
    "when, mode, expected",
    [
        (dt.datetime(2026, 10, 19, 9, 0), None, (True, "schedule")),  # Monday morning
        (dt.datetime(2026, 10, 19, 12, 0), None, (False, "schedule")),  # lunch (end is exclusive)
        (dt.datetime(2026, 10, 19, 17, 29), "auto", (True, "schedule")),
        (dt.datetime(2026, 10, 19, 17, 30), "auto", (False, "schedule")),
        (dt.datetime(2026, 10, 24, 23, 59), None, (True, "schedule")),  # Saturday until midnight
        (dt.datetime(2026, 10, 25, 10, 0), None, (False, "schedule")),  # Sunday
        (dt.datetime(2027, 12, 25, 10, 0), None, (False, "holiday")),  # yearly
        (dt.datetime(2027, 3, 26, 10, 0), None, (False, "holiday")),  # Good Friday 2027
        (dt.datetime(2028, 3, 26, 10, 0), None, (False, "schedule")),  # a Sunday, not a holiday
        (dt.datetime(2026, 10, 19, 9, 0), "closed", (False, "forced")),
        (dt.datetime(2026, 10, 25, 10, 0), "open", (True, "forced")),
    ],
)
def test_hours_status(session, ids, when, mode, expected):
    office = hours.get_hours(session, ids["office"])
    rt = hours.Runtime(modes={office.id: mode}) if mode in ("open", "closed") else hours.Runtime()
    st = hours.status(office, rt, when, {})
    assert (st["open"], st["reason"]) == expected


def test_override_expires(session, ids):
    office = hours.get_hours(session, ids["office"])
    mon9 = dt.datetime(2026, 10, 19, 9, 0)
    rt = hours.Runtime(overrides={office.id: ("closed", mon9.date())})
    assert (hours.status(office, rt, mon9, {})["open"], hours.status(office, rt, mon9, {})["reason"]) == (
        False,
        "override",
    )
    # automatic reaches the overridden value at 17:30 -> override gone
    assert hours.status(office, rt, mon9.replace(hour=18), {})["reason"] == "schedule"
    # set yesterday -> expired at midnight
    rt = hours.Runtime(overrides={office.id: ("open", dt.date(2026, 10, 18))})
    assert hours.status(office, rt, dt.datetime(2026, 10, 19, 0, 5), {})["reason"] == "schedule"


def test_override_status_fields(session, ids):
    office = hours.get_hours(session, ids["office"])
    mon9 = dt.datetime(2026, 10, 19, 9, 0)
    st = hours.status(office, hours.Runtime(overrides={office.id: ("closed", mon9.date())}), mon9, {})
    assert (st["override"], st["reverts_to"]) == ("closed", True)
    st = hours.status(office, hours.Runtime(), mon9, {})
    assert (st["override"], st["reverts_to"]) == (None, None)
    # the permanent mode sits above the override
    rt = hours.Runtime(modes={office.id: "open"}, overrides={office.id: ("closed", mon9.date())})
    st = hours.status(office, rt, mon9, {})
    assert (st["open"], st["reason"], st["override"]) == (True, "forced", None)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("open:2026-10-24", ("open", dt.date(2026, 10, 24))),
        ("closed:2026-01-02", ("closed", dt.date(2026, 1, 2))),
        ("closed", None),
        ("maybe:2026-10-24", None),
        ("open:2026-13-01", None),
        ("", None),
    ],
)
def test_parse_override(value, expected):
    assert hours.parse_override(value) == expected


@pytest.mark.parametrize(
    "day, applies", [("2026-12-31", True), ("2027-01-01", True), ("2027-01-03", False), ("2026-12-23", False)]
)
def test_yearly_special_crosses_new_year(session, ids, day, applies):
    h = hours.create_hours(
        session,
        _hours(
            specials=[
                {
                    "name": "Xmas",
                    "enabled": True,
                    "start": "2025-12-24",
                    "end": "2026-01-02",
                    "yearly": True,
                    "dest_type": "hangup",
                }
            ]
        ),
    )
    assert hours.special_matches(h.specials[0], dt.date.fromisoformat(day)) is applies


@pytest.mark.parametrize(
    "special, day, applies",
    [
        ({"start": "2027-07-05", "end": "2027-08-06"}, "2027-07-05", True),
        ({"start": "2027-07-05", "end": "2027-08-06"}, "2027-08-06", True),
        ({"start": "2027-07-05", "end": "2027-08-06"}, "2028-07-10", False),
        ({"start": "2026-07-05", "end": "2026-08-06", "yearly": True}, "2030-07-10", True),
        ({"start": "2026-07-05", "end": "2026-08-06", "yearly": True}, "2030-08-07", False),
        ({}, "2031-02-03", True),
    ],
)
def test_special_matches(session, ids, special, day, applies):
    h = hours.create_hours(session, _hours(specials=[{"name": "P", "dest_type": "hangup", **special}]))
    assert hours.special_matches(h.specials[0], dt.date.fromisoformat(day)) is applies


def test_precedence_first_applying_special_wins(session, ids):
    target = hours.create_hours(
        session, _hours(name="Morning", ranges=[{"weekday": d, "start": "09:00", "end": "12:00"} for d in range(7)])
    )
    h = hours.create_hours(
        session,
        _hours(
            specials=[
                {"name": "Emergency", "enabled": False, "dest_type": "hangup"},
                {
                    "name": "Xmas",
                    "enabled": True,
                    "start": "2026-12-24",
                    "end": "2027-01-02",
                    "dest_type": "hours",
                    "dest_id": target.id,
                },
            ]
        ),
    )
    others = {target.id: target}
    xmas10 = dt.datetime(2026, 12, 28, 10, 0)
    st = hours.status(h, hours.Runtime(), xmas10, others)
    assert (st["open"], st["reason"], st["special"]) == (True, "special", "Xmas")
    emergency = h.specials[0].id
    st = hours.status(h, hours.Runtime(active={emergency: True}), xmas10, others)
    assert (st["open"], st["special"]) == (False, "Emergency")
    # the key (override) sits above every special period
    st = hours.status(
        h, hours.Runtime(active={emergency: True}, overrides={h.id: ("open", xmas10.date())}), xmas10, others
    )
    assert (st["open"], st["reason"]) == (True, "override")


def test_special_status_details(session, ids):
    target = hours.create_hours(
        session, _hours(name="Morning", ranges=[{"weekday": d, "start": "09:00", "end": "12:00"} for d in range(7)])
    )
    h = hours.create_hours(
        session,
        _hours(
            specials=[
                {
                    "name": "Xmas",
                    "enabled": True,
                    "start": "2025-12-24",
                    "end": "2026-01-02",
                    "yearly": True,
                    "dest_type": "hours",
                    "dest_id": target.id,
                },
            ]
        ),
    )
    sp = h.specials[0]
    st = hours.status(h, hours.Runtime(), dt.datetime(2026, 12, 28, 14, 0), {target.id: target})
    assert (st["open"], st["special"], st["special_id"], st["until"]) == (False, "Xmas", sp.id, dt.date(2027, 1, 2))
    st = hours.status(h, hours.Runtime(), dt.datetime(2027, 1, 1, 10, 0), {target.id: target})
    assert (st["open"], st["until"]) == (True, dt.date(2027, 1, 2))
    # the target follows its own permanent mode
    rt = hours.Runtime(modes={target.id: "closed"})
    assert hours.status(h, rt, dt.datetime(2027, 1, 1, 10, 0), {target.id: target})["open"] is False
    # unknown target -> closed
    assert hours.status(h, hours.Runtime(), dt.datetime(2027, 1, 1, 10, 0), {})["open"] is False
    # switched off at runtime -> the weekly schedule applies
    st = hours.status(h, hours.Runtime(active={sp.id: False}), dt.datetime(2027, 1, 1, 10, 0), {})
    assert (st["reason"], st["special"], st["until"]) == ("schedule", None, None)


def test_read_runtime(fake_ami):
    fake_ami.astdb = {
        ("phonix-hours", "1"): "closed",
        ("phonix-hours", "3"): "bogus",
        ("phonix-hours-tmp", "2"): "open:2026-10-24",
        ("phonix-hours-tmp", "4"): "garbage",
        ("phonix-special", "5"): "1",
        ("phonix-special", "6"): "0",
    }
    from phonix import ami

    with ami.AmiClient() as c:
        rt = hours.read_runtime(c)
    assert rt == hours.Runtime(
        modes={1: "closed"}, overrides={2: ("open", dt.date(2026, 10, 24))}, active={5: True, 6: False}
    )


def test_load_runtime_without_asterisk():
    assert hours.load_runtime() is None


def test_live_mode(session, ids, fake_ami):
    office = ids["office"]
    assert hours.live_status(session, office)["mode"] == "auto"
    hours.set_mode(session, office, "closed", "admin")
    assert fake_ami.astdb == {("phonix-hours", str(office)): "closed"}
    assert hours.live_status(session, office)["mode"] == "closed"
    hours.set_mode(session, office, "auto", "admin")
    assert fake_ami.astdb == {}
    with pytest.raises(ServiceError):
        hours.set_mode(session, office, "maybe", "admin")


def test_live_status_specials(session, ids, fake_ami):
    h = hours.create_hours(
        session,
        _hours(
            feature_code="*95",
            specials=[{"name": "Emergency", "enabled": False, "feature_code": "*96", "dest_type": "hangup"}],
        ),
    )
    sp = h.specials[0]
    live = hours.live_status(session, h.id)
    assert live["override"] is None
    assert live["specials"] == [
        {"id": sp.id, "name": "Emergency", "active": False, "applies": False, "feature_code": "*96"}
    ]
    fake_ami.astdb = {("phonix-special", str(sp.id)): "1"}
    live = hours.live_status(session, h.id)
    assert (live["open"], live["reason"], live["special"]) == (False, "special", "Emergency")
    assert live["specials"][0]["active"] is live["specials"][0]["applies"] is True


def test_reset_runtime(session, ids, fake_ami):
    h = hours.create_hours(
        session,
        _hours(
            feature_code="*95",
            specials=[
                {"name": "Emergency", "enabled": True, "feature_code": "*96", "dest_type": "hangup"},
                {"name": "Xmas", "enabled": False, "dest_type": "hangup"},
            ],
        ),
    )
    emergency, xmas = (sp.id for sp in h.specials)
    office = ids["office"]
    # left over from before the restore: they must not attach to the restored objects
    fake_ami.astdb = {
        ("phonix-hours", str(h.id)): "open",
        ("phonix-hours", str(office)): "closed",
        ("phonix-hours-tmp", str(h.id)): "closed:2026-10-24",
        ("phonix-special", str(emergency)): "0",
        ("phonix-special", str(xmas)): "1",
        ("phonix-special", "999"): "1",
        ("phonix-other", "1"): "kept",
    }
    hours.reset_runtime(session)
    assert fake_ami.astdb == {
        ("phonix-special", str(emergency)): "1",
        ("phonix-special", str(xmas)): "0",
        ("phonix-other", "1"): "kept",
    }
    commands = [a[1].get("Command") for a in fake_ami.actions]
    assert f"devstate change Custom:phonix-special-{emergency} INUSE" in commands
    assert f"devstate change Custom:phonix-hours-{h.id} INUSE" in commands


def test_reset_runtime_without_asterisk(session, ids):
    hours.reset_runtime(session)  # best effort: never fails


def test_delete_forgets_runtime_state(session, ids, fake_ami):
    h = hours.create_hours(
        session,
        _hours(
            specials=[
                {"name": "Emergency", "enabled": True, "dest_type": "hangup"},
                {"name": "Xmas", "enabled": False, "dest_type": "hangup"},
            ],
        ),
    )
    emergency, xmas = (sp.id for sp in h.specials)
    office = ids["office"]
    fake_ami.astdb = {
        ("phonix-hours", str(h.id)): "open",
        ("phonix-hours-tmp", str(h.id)): "closed:2026-10-24",
        ("phonix-special", str(emergency)): "1",
        ("phonix-special", str(xmas)): "0",
        ("phonix-hours", str(office)): "closed",
    }
    # a period removed in a save loses its switch, the others keep theirs
    data = hours.to_dict(h)
    data["specials"] = [sp for sp in data["specials"] if sp["id"] == xmas]
    hours.update_hours(session, h.id, _hours(**data))
    assert ("phonix-special", str(emergency)) not in fake_ami.astdb
    assert fake_ami.astdb[("phonix-special", str(xmas))] == "0"
    assert fake_ami.astdb[("phonix-hours", str(h.id))] == "open"

    hours.delete_hours(session, h.id)
    assert fake_ami.astdb == {("phonix-hours", str(office)): "closed"}


def test_delete_without_asterisk(session, ids):
    h = hours.create_hours(session, _hours(specials=[{"name": "Emergency", "dest_type": "hangup"}]))
    hours.update_hours(session, h.id, _hours(**{**hours.to_dict(h), "specials": []}))
    hours.delete_hours(session, h.id)


def test_live_mode_without_asterisk(session, ids):
    assert hours.live_status(session, ids["office"])["mode"] is None
    with pytest.raises(ServiceError, match="Asterisk is not running"):
        hours.set_mode(session, ids["office"], "closed", "admin")


# --- dialplan ---------------------------------------------------------------------------


def test_last_minute():
    assert dialplan.last_minute("17:30") == "17:29"
    assert dialplan.last_minute("24:00") == "23:59"
    assert dialplan.last_minute("08:01") == "08:00"


def test_dialplan(session, ids):
    out = dialplan.generate(build_snapshot(session))
    main, support, office = ids["main_menu"], ids["support_menu"], ids["office"]
    assert f"exten => 600,1,NoOp(Internal call to IVR menu Main menu)\n same => n,Goto(ivr-{main},s,1)" in out
    # callers from outside: public variant, no transfer feature, public direct dial only
    pub = out.split(f"[ivr-{main}-pub]\n", 1)[1].split("\n\n", 1)[0]
    assert pub.startswith("include => public-direct-dial")
    assert f"Goto(ivr-{support}-pub,s,1)" in pub and ",tT," not in pub
    assert f"[ivr-{support}]\nexten => s," in out  # no direct dial: no include
    assert "exten => #,1,NoOp(IVR menu Main menu: Repeat)\n same => n,Goto(s,prompt)" in out
    assert "exten => 4930123458,1," in out and f"Goto(hours-{office}-pub,s,1)" in out
    assert "GotoIfTime(13:00-17:29,fri,*,*?open)" in out and "GotoIfTime(09:00-23:59,sat,*,*?open)" in out
    assert "exten => *31,1,NoOp(Switch business hours Office hours)" in out

    # disabled menus disappear, references to them hang up
    ivr.set_enabled(session, support, False)
    out = dialplan.generate(build_snapshot(session))
    assert f"[ivr-{support}]" not in out and "exten => 610," not in out
    assert f"NoOp(Destination ivr {support} is not available)" in out


def _block(out: str, context: str) -> str:
    """The lines of one generated context."""
    return out.split(f"[{context}]\n", 1)[1].split("\n\n", 1)[0]


def test_dialplan_hours_subroutines(session, ids):
    office = ids["office"]
    out = dialplan.generate(build_snapshot(session))
    for suffix in ("auto", "state", "lamp"):
        assert f"[hours-{office}-{suffix}]\nexten => s,1," in out
    assert f"exten => *31,hint,Custom:phonix-hours-{office}" in out
    for context in (f"hours-{office}", f"hours-{office}-pub"):
        assert _block(out, context).startswith(f"exten => s,1,Gosub(hours-{office}-state,s,1)")
    auto = _block(out, f"hours-{office}-auto")
    assert "GotoIfTime(13:00-17:29,fri,*,*?open)" in auto and '"${TODAY:5}" = "12-25"' in auto
    assert "Return(open-0)" in auto and "Return(closed-0)" in auto
    lamp = _block(out, f"hours-{office}-lamp")
    assert f"Set(DEVICE_STATE(Custom:phonix-hours-{office})=" in lamp and "INUSE:NOT_INUSE" in lamp
    # the key: permanent mode and override, then the lamp, then the announcement
    key = out.split("exten => *31,1,", 1)[1].split("\n\n", 1)[0].split("\n; ", 1)[0]
    assert f"Gosub(hours-{office}-auto,s,1)" in key and f"Gosub(hours-{office}-state,s,1)" in key
    assert f"DB_DELETE(phonix-hours/{office})" in key and f"DB_DELETE(phonix-hours-tmp/{office})" in key
    assert f"Set(DB(phonix-hours-tmp/{office})=${{HOURS_OPP}}:${{STRFTIME(${{EPOCH}},,%Y-%m-%d)}})" in key
    assert key.index(f"Gosub(hours-{office}-lamp,s,1)") < key.index("Playback(") < key.index("Hangup()")
    # without a feature code: no key, no lamp, no hint
    plain = hours.create_hours(session, _hours(name="Plain"))
    out = dialplan.generate(build_snapshot(session))
    assert f"[hours-{plain.id}-state]" in out and f"[hours-{plain.id}-lamp]" not in out
    assert f"Custom:phonix-hours-{plain.id}" not in out


def test_dialplan_special_periods(session, ids):
    target = hours.create_hours(
        session, _hours(name="Morning", ranges=[{"weekday": d, "start": "09:00", "end": "12:00"} for d in range(7)])
    )
    h = hours.create_hours(
        session,
        _hours(
            name="Shop",
            feature_code="*69",
            closed_dest_type="hangup",
            specials=[
                {"name": "Emergency", "enabled": False, "feature_code": "*70", "dest_type": "hangup"},
                {
                    "name": "Xmas",
                    "enabled": True,
                    "start": "2026-12-24",
                    "end": "2027-01-02",
                    "yearly": True,
                    "dest_type": "hours",
                    "dest_id": target.id,
                },
                {"name": "Summer", "enabled": True, "start": "2027-07-01", "end": "2027-07-31", "dest_type": "hangup"},
            ],
        ),
    )
    emergency, xmas, summer = (sp.id for sp in h.specials)
    out = dialplan.generate(build_snapshot(session))
    auto = _block(out, f"hours-{h.id}-auto")
    # in list order; an empty switch falls back to the configured value
    assert auto.index(f"phonix-special/{emergency}") < auto.index(f"phonix-special/{xmas}")
    assert auto.index(f"phonix-special/{xmas}") < auto.index(f"phonix-special/{summer}")
    assert 'ExecIf($["${ON}" = ""]?Set(LOCAL(ON)=0))' in auto and 'ExecIf($["${ON}" = ""]?Set(LOCAL(ON)=1))' in auto
    assert f"Return(closed-{emergency})" in auto
    # yearly across the new year: 12-24...12-31 or 01-01...01-02
    assert '"${TODAY:5}" >= "12-24" | "${TODAY:5}" <= "01-02"' in auto
    assert '"${TODAY}" >= "2027-07-01" & "${TODAY}" <= "2027-07-31"' in auto
    assert f"Gosub(hours-{target.id}-state,s,1)" in auto and f"-{xmas})" in auto
    # routing: a period pointing to business hours goes there
    pub = _block(out, f"hours-{h.id}-pub")
    assert f"Goto(hours-{target.id}-pub,s,1)" in pub
    assert f"Goto(hours-{target.id},s,1)" in _block(out, f"hours-{h.id}")
    # keys: hint, default 0, the period's lamp and the owner's lamp
    assert f"exten => *70,hint,Custom:phonix-special-{emergency}" in out
    key = out.split("exten => *70,1,", 1)[1].split("\n\n", 1)[0].split("\n; ", 1)[0]
    assert 'ExecIf($["${HOURS_ON}" = ""]?Set(HOURS_ON=0))' in key
    assert f"Set(DB(phonix-special/{emergency})=${{HOURS_ON}})" in key
    assert f"Set(DEVICE_STATE(Custom:phonix-special-{emergency})=" in key and f"Gosub(hours-{h.id}-lamp,s,1)" in key
    assert "activated:de-activated" in key
    # pressing the target's key refreshes the lamps of the business hours pointing to it
    target_key = hours.update_hours(session, target.id, _hours(**{**hours.to_dict(target), "feature_code": "*68"}))
    out = dialplan.generate(build_snapshot(session))
    key = out.split("exten => *68,1,", 1)[1].split("\n\n", 1)[0].split("\n; ", 1)[0]
    assert f"Gosub(hours-{target_key.id}-lamp,s,1)" in key and f"Gosub(hours-{h.id}-lamp,s,1)" in key


def test_dialplan_override_purged_in_dialplan(session, ids):
    office = ids["office"]
    out = dialplan.generate(build_snapshot(session))
    state = _block(out, f"hours-{office}-state")
    valid = 'GotoIf($["${TMP}" = "${OPP}:${STRFTIME(${EPOCH},,%Y-%m-%d)}"]?override)'
    purge = f"Set(LOCAL(GONE)=${{DB_DELETE(phonix-hours-tmp/{office})}})"
    assert valid in state and purge in state
    # only a valid override skips the purge
    assert state.index(valid) < state.index(purge) < state.index("(override)")
    assert f"Set(LOCAL(MODE)=${{DB(phonix-hours/{office})}})" in state
    assert "Return(${MODE}-forced-0)" in state and "Return(${CUT(TMP,:,1)}-override-0)" in state


def test_dialplan_no_gosub_to_deleted_hours(session, ids):
    target = hours.create_hours(session, _hours(name="Morning"))
    h = hours.create_hours(
        session,
        _hours(name="Shop", specials=[{"name": "Xmas", "enabled": True, "dest_type": "hours", "dest_id": target.id}]),
    )
    assert f"hours-{target.id}" in _block(dialplan.generate(build_snapshot(session)), f"hours-{h.id}-auto")
    hours.delete_hours(session, target.id)
    session.expire_all()
    out = dialplan.generate(build_snapshot(session))
    assert f"hours-{target.id}" not in out
    assert f"Return(closed-{h.specials[0].id})" in _block(out, f"hours-{h.id}-auto")


def test_dialplan_special_never_routes_to_itself(session, ids):
    h = hours.create_hours(session, _hours(name="Shop", specials=[{"name": "Loop", "dest_type": "hangup"}]))
    # only possible by editing the database directly
    sp = h.specials[0]
    sp.dest_type, sp.dest_id = "hours", h.id
    session.flush()
    out = dialplan.generate(build_snapshot(session))
    for ctx in (f"hours-{h.id}", f"hours-{h.id}-pub"):
        block = _block(out, ctx)
        assert f"Goto(hours-{h.id}" not in block
        period = block.split("Special period Loop", 1)[1]
        assert "Hangup()" in period.split("\n", 2)[1]


def test_dialplan_uploaded_prompt_and_unsafe_names(session, ids, runtime):
    prompt = media.add_media(session, "ivr_prompt", "Welcome.wav", _wav())
    menu = ivr.create_menu(
        session,
        ivr.IvrMenuIn(name='Odd ${EXTEN} (menu), "x"', prompt_mode="upload", prompt_media_id=prompt.id),
    )
    out = dialplan.generate(build_snapshot(session))
    block = out.split(f"[ivr-{menu.id}]\n", 1)[1].split("\n\n", 1)[0]
    assert "Background(/data/media/ivr_prompt/Welcome)" in block
    assert "NoOp(IVR menu Odd EXTEN menu x)" in block
    # deleting the file leaves the menu without announcement
    media.delete_media(session, prompt.id)
    session.expire_all()
    out = dialplan.generate(build_snapshot(session))
    block = out.split(f"[ivr-{menu.id}]\n", 1)[1].split("\n\n", 1)[0]
    assert "Background" not in block and "(prompt),WaitExten(5)" in block


def _wav() -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0\0" * 800)
    return buf.getvalue()


# --- UI ---------------------------------------------------------------------------------

FORM = {"content-type": "application/x-www-form-urlencoded"}


def _post(client, url, pairs, **kw):
    """POST form fields in the given order (the order of dynamic rows matters)."""
    return client.post(url, content=urlencode(pairs), headers=FORM, **kw)


def test_menu_form(client):
    ids = client.ids
    login(client)
    assert client.get("/dialplan/ivr").status_code == 200
    page = client.get(f"/dialplan/ivr/{ids['main_menu']}").text
    assert "Technical support" in page and "back to IVR menu Main menu" in page
    token = csrf(client, "/dialplan/ivr/new")
    # rows are taken in the order they were submitted, whatever their index
    form = [
        ("csrf_token", token),
        ("name", "Night"),
        ("prompt_mode", "sound"),
        ("prompt_sound", "welcome"),
        ("timeout", "4"),
        ("repeats", "1"),
        ("timeout_dest", "hangup"),
        ("invalid_dest", "repeat"),
        ("opt_key_7", "2"),
        ("opt_label_7", "Bob"),
        ("opt_dest_7", f"phone:{ids['bob']}"),
        ("opt_key_1", "1"),
        ("opt_label_1", "Message"),
        ("opt_dest_1", f"voicemail:{ids['alice']}"),
        ("enabled__present", "1"),
        ("enabled", "true"),
    ]
    r = _post(client, "/dialplan/ivr/new", form, follow_redirects=False)
    assert r.status_code == 303, r.text
    with session_scope() as s:
        menu = s.query(IvrMenu).filter_by(name="Night").one()
        assert [(o.key, o.dest_type) for o in menu.options] == [("2", "phone"), ("1", "voicemail")]
        menu_id = menu.id

    # a row without destination is reported on that row
    bad = [*form[:-2], ("opt_key_9", "3"), ("opt_dest_9", "")]
    bad[1] = ("name", "Night 2")
    r = _post(client, "/dialplan/ivr/new", bad)
    assert r.status_code == 422 and "Choose a destination" in r.text

    headers = {"X-CSRF-Token": csrf(client, "/dialplan/ivr"), "HX-Request": "true"}
    r = client.post(f"/dialplan/ivr/{menu_id}/toggle", headers=headers)
    assert r.status_code == 200 and "disabled" in r.text
    assert client.delete(f"/dialplan/ivr/{menu_id}", headers=headers).status_code == 200
    with session_scope() as s:
        assert s.get(IvrMenu, menu_id) is None


def test_menu_form_tabs(client):
    ids = client.ids
    login(client)

    def active(page):
        return re.search(r'class="tab-pane active show" id="tab-(\w+)"', page).group(1)

    # a new menu starts on General and has no call flow yet, a saved one starts on Keys
    page = client.get("/dialplan/ivr/new").text
    assert active(page) == "general" and 'id="tab-flow"' not in page
    page = client.get(f"/dialplan/ivr/{ids['main_menu']}").text
    assert active(page) == "keys" and 'id="tab-flow"' in page and 'form="ivr-test"' in page
    # the tab with the error opens
    form = [
        ("csrf_token", csrf(client, "/dialplan/ivr/new")),
        ("name", "Tabs"),
        ("prompt_mode", "sound"),
        ("prompt_sound", "welcome"),
        ("timeout", "4"),
        ("repeats", "1"),
        ("timeout_dest", "hangup"),
        ("invalid_dest", "repeat"),
        ("opt_key_0", "1"),
        ("opt_dest_0", ""),
    ]
    r = _post(client, "/dialplan/ivr/new", form)
    assert r.status_code == 422 and active(r.text) == "keys"
    # "Create and stay" returns to the edit page on the open tab
    form[-1] = ("opt_dest_0", "hangup")
    r = _post(client, "/dialplan/ivr/new", [*form, ("stay", "1"), ("tab", "prompt")], follow_redirects=False)
    assert r.status_code == 303
    with session_scope() as s:
        menu_id = s.query(IvrMenu).filter_by(name="Tabs").one().id
    assert r.headers["location"].endswith(f"/dialplan/ivr/{menu_id}#tab-prompt")


def test_script_and_prompt_upload(client):
    ids = client.ids
    login(client)
    headers = {"X-CSRF-Token": csrf(client, "/dialplan/ivr/new"), "HX-Request": "true"}
    form = {
        "opt_key_a": "1",
        "opt_label_a": "Sales",
        "opt_dest_a": f"callgroup:{ids['group']}",
        "opt_key_b": "*",
        "opt_dest_b": "hangup",
        "opt_key_c": "2",
        "opt_dest_c": "",
    }
    r = client.post("/dialplan/ivr/script", data=form, headers=headers)
    assert r.status_code == 200
    assert "For Sales, press 1. To end the call, press star." in r.text

    r = client.post("/dialplan/ivr/prompts", files={"file": ("greeting.wav", _wav(), "audio/wav")}, headers=headers)
    assert r.status_code == 200 and "greeting.wav" in r.text
    assert re.search(r'<option value="\d+" selected>greeting.wav</option>', r.text)
    r = client.post("/dialplan/ivr/prompts", files={"file": ("empty.wav", b"", "audio/wav")}, headers=headers)
    assert r.status_code == 422


def test_test_call(client, fake_ami):
    ids = client.ids
    login(client)
    headers = {"X-CSRF-Token": csrf(client, "/dialplan/ivr"), "HX-Request": "true"}
    r = client.post(f"/dialplan/ivr/{ids['main_menu']}/test", data={"extension": "102"}, headers=headers)
    assert r.status_code == 200 and "Phone 102 is ringing" in r.text
    name, fields = fake_ami.actions[-1]
    assert name == "Originate" and fields["Channel"] == "PJSIP/102"
    assert fields["Context"] == f"ivr-{ids['main_menu']}" and fields["Exten"] == "s"
    r = client.post(f"/dialplan/ivr/{ids['main_menu']}/test", data={"extension": "201"}, headers=headers)
    assert "only SIP and IAX phones" in r.text


def test_hours_form(client, fake_ami):
    ids = client.ids
    login(client)
    assert "open" in client.get("/dialplan/hours").text
    page = client.get(f"/dialplan/hours/{ids['office']}").text
    assert "Christmas Day" in page and 'value="23:59"' in page and "Switch now" in page
    # year at a glance: twelve months, the yearly holiday marked
    assert "Year at a glance" in page and page.count('<table class="hours-cal">') == 12
    assert re.search(r'class="hours-cal-holiday[^"]*" title="\d{4}-12-25: Christmas Day"', page)
    # new business hours show their year before the first save
    assert client.get("/dialplan/hours/new").text.count('<table class="hours-cal">') == 12
    # ?months=N shows more or fewer months; out of range falls back to twelve
    for query, count in (("?months=24", 24), ("?months=3", 3), ("?months=61", 12), ("?months=x", 12)):
        page = client.get(f"/dialplan/hours/{ids['office']}{query}").text
        assert page.count('<table class="hours-cal">') == count, query
    page = client.get(f"/dialplan/hours/{ids['office']}?months=24").text
    url = f"/dialplan/hours/{ids['office']}/year"
    assert f'hx-post="{url}?months=24" hx-include="closest form" hx-target="#hours-year"' in page
    trigger = "phonix:tab-shown, phonix:special-switched from:body"
    assert f'<div id="hours-year" hx-post="{url}?months=24" hx-trigger="{trigger}"' in page
    assert re.search(r'href="\?months=24#tab-year"[^>]* class="btn active"', page)
    # the buttons reload only the calendars (htmx) with the form, so unsaved entries in the form stay
    headers = {"X-CSRF-Token": csrf(client, "/dialplan/hours"), "HX-Request": "true"}
    part = client.post(f"{url}?months=36", data={"name": "Office"}, headers=headers).text
    assert part.startswith("<div") and 'id="hours-year"' in part and part.count('<table class="hours-cal">') == 36
    assert "<form" not in part and "<html" not in part
    assert client.post("/dialplan/hours/999/year", headers=headers).status_code == 404
    form = [
        ("csrf_token", csrf(client, "/dialplan/hours/new")),
        ("name", "Support line"),
        ("open_dest", f"callgroup:{ids['group']}"),
        ("closed_dest", "hangup"),
        ("range_day_x1", "0"),
        ("range_start_x1", "08:00"),
        ("range_end_x1", "23:59"),
        ("range_day_x2", "6"),
        ("range_start_x2", ""),
        ("range_end_x2", ""),
        ("hol_date_0", "2026-08-01"),
        ("hol_name_0", "National Day"),
        ("hol_yearly_0", "true"),
    ]
    r = _post(client, "/dialplan/hours/new", form, follow_redirects=False)
    assert r.status_code == 303, r.text
    with session_scope() as s:
        h = s.query(BusinessHours).filter_by(name="Support line").one()
        assert [(r.weekday, r.start, r.end) for r in h.ranges] == [(0, "08:00", "24:00")]
        assert [(d.date, d.yearly) for d in h.holidays] == [(dt.date(2026, 8, 1), True)]
    form[6] = ("range_end_x1", "07:00")
    form[1] = ("name", "Broken")
    r = _post(client, "/dialplan/hours/new", form)
    assert r.status_code == 422 and "The end must be after the start" in r.text

    headers = {"X-CSRF-Token": csrf(client, "/dialplan/hours"), "HX-Request": "true"}
    r = client.post(f"/dialplan/hours/{ids['office']}/mode", data={"mode": "closed"}, headers=headers)
    assert r.status_code == 200 and "switched manually" in r.text
    assert fake_ami.astdb == {("phonix-hours", str(ids["office"])): "closed"}


def _special_rows(rows):
    """Form fields of special period rows ``(index, id, name, enabled, start, end, yearly, code, dest)``."""
    out = []
    for idx, sid, name, enabled, start, end, yearly, code, dest in rows:
        out += [(f"sp_id_{idx}", sid), (f"sp_name_{idx}", name)]
        if enabled:
            out.append((f"sp_enabled_{idx}", "true"))
        out += [(f"sp_start_{idx}", start), (f"sp_end_{idx}", end)]
        if yearly:
            out.append((f"sp_yearly_{idx}", "true"))
        out += [(f"sp_code_{idx}", code), (f"sp_dest_{idx}", dest)]
    return out


def test_hours_form_special_periods(client, fake_ami):
    ids = client.ids
    login(client)
    token = csrf(client, "/dialplan/hours/new")
    base = [("csrf_token", token), ("name", "Hotline"), ("open_dest", "hangup"), ("closed_dest", "hangup")]
    rows = [
        ("k", "", "Emergency", False, "", "", False, "*70", f"callgroup:{ids['group']}"),
        ("a", "", "Xmas", True, "2026-12-24", "2027-01-02", True, "", f"hours:{ids['office']}"),
    ]
    r = _post(client, "/dialplan/hours/new", base + _special_rows(rows), follow_redirects=False)
    assert r.status_code == 303, r.text
    with session_scope() as s:
        h = s.query(BusinessHours).filter_by(name="Hotline").one()
        got = [(sp.name, sp.enabled, sp.yearly, sp.feature_code, sp.dest_type) for sp in h.specials]
        assert got == [("Emergency", False, False, "*70", "callgroup"), ("Xmas", True, True, None, "hours")]
        hid, (emergency, xmas) = h.id, [sp.id for sp in h.specials]

    page = client.get(f"/dialplan/hours/{hid}").text
    assert 'value="Emergency"' in page and 'value="Xmas"' in page and 'value="2026-12-24"' in page
    assert f'name="sp_id_0" value="{emergency}"' in page and 'data-move="up"' in page
    # the live toggles of the periods
    assert f'hx-post="/dialplan/hours/{hid}/special/{xmas}"' in page
    # the target picker offers neither the object itself nor business hours with periods
    assert f'value="hours:{hid}"' not in page and f'value="hours:{ids["office"]}"' in page

    # reversed on the second save: order follows the form, ids are kept
    rows = [
        ("b", str(xmas), "Xmas", True, "2026-12-24", "2027-01-02", True, "", f"hours:{ids['office']}"),
        ("c", str(emergency), "Emergency", False, "", "", False, "*70", f"callgroup:{ids['group']}"),
    ]
    r = _post(client, f"/dialplan/hours/{hid}", base + _special_rows(rows), follow_redirects=False)
    assert r.status_code == 303, r.text
    with session_scope() as s:
        got = [(sp.id, sp.name) for sp in s.get(BusinessHours, hid).specials]
        assert got == [(xmas, "Xmas"), (emergency, "Emergency")]

    # errors are shown on the row
    bad = [("x", "", "Broken", False, "2026-12-24", "", False, "", "hangup")]
    r = _post(client, f"/dialplan/hours/{hid}", base + _special_rows(bad))
    assert r.status_code == 422 and "Enter both the first and the last day" in r.text


def test_hours_form_keeps_live_switch(client, fake_ami):
    """A form opened before a period was switched does not switch it back; only new rows have the checkbox."""
    login(client)
    with session_scope() as s:
        h = hours.create_hours(s, _hours(name="Hotline", specials=[{"name": "Emergency", "dest_type": "hangup"}]))
        s.flush()
        hid, sid = h.id, h.specials[0].id
    page = client.get(f"/dialplan/hours/{hid}").text
    assert 'name="sp_enabled_0"' not in page and 'name="sp_enabled___INDEX__"' in page
    with session_scope() as s:
        hours.set_special_active(s, hid, sid, True, "admin")
    form = [
        ("csrf_token", csrf(client, "/dialplan/hours")),
        ("name", "Hotline"),
        ("open_dest", "hangup"),
        ("closed_dest", "hangup"),
        *_special_rows([("0", str(sid), "Emergency", False, "", "", False, "", "hangup")]),
        *_special_rows([("n", "", "New", True, "", "", False, "", "hangup")]),
    ]
    r = _post(client, f"/dialplan/hours/{hid}", form, follow_redirects=False)
    assert r.status_code == 303, r.text
    with session_scope() as s:
        assert [(sp.name, sp.enabled) for sp in s.get(BusinessHours, hid).specials] == [
            ("Emergency", True),
            ("New", True),
        ]
    assert fake_ami.astdb[("phonix-special", str(sid))] == "1"


def test_hours_special_toggle(client, fake_ami):
    login(client)
    with session_scope() as s:
        h = hours.create_hours(s, _hours(name="Hotline", specials=[{"name": "Emergency", "dest_type": "hangup"}]))
        s.flush()
        hid, sid = h.id, h.specials[0].id
    url = f"/dialplan/hours/{hid}/special/{sid}"
    assert client.post(url, data={"active": "true"}).status_code == 403
    headers = {"X-CSRF-Token": csrf(client, "/dialplan/hours"), "HX-Request": "true"}
    r = client.post(url, data={"active": "true"}, headers=headers)
    assert r.status_code == 200 and 'id="hours-mode"' in r.text and "Emergency" in r.text
    assert fake_ami.astdb[("phonix-special", str(sid))] == "1"
    with session_scope() as s:
        assert s.get(BusinessHours, hid).specials[0].enabled is True
    # the edit page redraws its year at a glance, which now has the period (without dates: every day)
    assert r.headers["HX-Trigger"] == "phonix:special-switched"
    form = {"sp_id_0": str(sid), "sp_name_0": "Emergency", "sp_dest_0": "hangup"}
    year = client.post(f"/dialplan/hours/{hid}/year?months=1", data=form, headers=headers).text
    assert '<td class="hours-cal-special' in year and '<td class="hours-cal-open' not in year
    # from the list page: the row is returned
    r = client.post(url, data={"active": "false", "view": "row"}, headers=headers)
    assert r.status_code == 200 and f'id="hours-row-{hid}"' in r.text and "HX-Trigger" not in r.headers
    assert fake_ami.astdb[("phonix-special", str(sid))] == "0"
    r = client.post(f"/dialplan/hours/{hid}/special/999999", data={"active": "true"}, headers=headers)
    assert r.status_code == 404


def test_hours_special_toggle_without_asterisk(client):
    login(client)
    with session_scope() as s:
        h = hours.create_hours(s, _hours(name="Hotline", specials=[{"name": "Emergency", "dest_type": "hangup"}]))
        s.flush()
        hid, sid = h.id, h.specials[0].id
    headers = {"X-CSRF-Token": csrf(client, "/dialplan/hours"), "HX-Request": "true"}
    r = client.post(f"/dialplan/hours/{hid}/special/{sid}", data={"active": "true"}, headers=headers)
    assert r.status_code == 200 and "Asterisk is not running" in r.text


def test_hours_list_shows_special_period(client, fake_ami):
    login(client)
    today = dt.date.today()
    with session_scope() as s:
        h = hours.create_hours(
            s,
            _hours(
                name="Hotline",
                specials=[
                    {"name": "Off", "dest_type": "hangup"},
                    {
                        "name": "Xmas",
                        "enabled": True,
                        "start": today.isoformat(),
                        "end": (today + dt.timedelta(days=3)).isoformat(),
                        "dest_type": "hangup",
                    },
                ],
            ),
        )
        s.flush()
        hid, (off, _xmas) = h.id, [sp.id for sp in h.specials]
    page = client.get("/dialplan/hours").text
    row = page.split(f'id="hours-row-{hid}"', 1)[1].split("</tr>", 1)[0]
    assert "Xmas" in row and f"until {(today + dt.timedelta(days=3)).isoformat()}" in row
    assert f'hx-post="/dialplan/hours/{hid}/special/{off}"' in row
    # a key override is explained
    fake_ami.astdb[("phonix-hours-tmp", str(hid))] = f"open:{today}"
    page = client.get("/dialplan/hours").text
    assert "switched by key until the next change" in page


# --- REST and MCP -----------------------------------------------------------------------


def test_api(client, fake_ami):
    ids = client.ids
    auth = bearer()
    menus = client.get("/api/v1/ivr-menus", headers=auth).json()
    assert {m["name"] for m in menus} == {"Main menu", "Support"}
    body = {
        "name": "API menu",
        "prompt_mode": "sound",
        "prompt_sound": "welcome",
        "options": [{"key": "5", "dest_type": "hours", "dest_id": ids["office"]}],
    }
    r = client.post("/api/v1/ivr-menus", json=body, headers=auth)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/ivr-menus", json={**body, "options": [{"key": "x", "dest_type": "hangup"}]}, headers=auth)
    assert r.status_code == 422

    r = client.get(f"/api/v1/business-hours/{ids['office']}/status", headers=bearer(read_only=True))
    assert r.status_code == 200 and r.json()["mode"] == "auto"
    assert (
        client.put(
            f"/api/v1/business-hours/{ids['office']}/mode", json={"mode": "open"}, headers=bearer(read_only=True)
        ).status_code
        == 403
    )
    r = client.put(f"/api/v1/business-hours/{ids['office']}/mode", json={"mode": "open"}, headers=auth)
    assert r.status_code == 200 and r.json()["open"] is True and r.json()["reason"] == "forced"
    assert (
        client.put(f"/api/v1/business-hours/{ids['office']}/mode", json={"mode": "x"}, headers=auth).status_code == 422
    )
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/business-hours/{hours_id}/mode" in paths and "/api/v1/ivr-menus/{item_id}" in paths


def test_mcp(client, fake_ami):
    from test_mcp import call, rpc

    ids = client.ids
    names = {t["name"] for t in rpc(client, "tools/list").json()["result"]["tools"]}
    assert {"list_ivr_menus", "create_ivr_menu", "set_ivr_menu_enabled", "list_business_hours"} <= names
    assert {"get_business_hours", "set_business_hours_mode", "get_business_hours_status"} <= names
    ro = {t["name"] for t in rpc(client, "tools/list", headers=bearer(read_only=True)).json()["result"]["tools"]}
    assert "get_business_hours_status" in ro and "set_business_hours_mode" not in ro

    result = call(client, "set_business_hours_mode", id=ids["office"], mode="closed")
    assert result["structuredContent"]["open"] is False
    result = call(client, "update_ivr_menu", id=ids["support_menu"], repeats=4)
    assert result["structuredContent"]["repeats"] == 4
    result = call(client, "set_business_hours_mode", id=ids["office"], mode="later")
    assert result["isError"] is True


def _two_hours_with_specials():
    from phonix.core.db import session_scope as scope

    out = []
    with scope() as s:
        for name in ("Sp A", "Sp B"):
            h = hours.create_hours(s, _hours(name=name, specials=[{"name": "P", "dest_type": "hangup"}]))
            s.flush()
            out.append((h.id, h.specials[0].id))
    return out


def test_api_special(client, fake_ami):
    (a, pa), (_b, pb) = _two_hours_with_specials()
    url = f"/api/v1/business-hours/{a}/special/{pa}"
    assert client.put(url, json={"active": True}, headers=bearer(read_only=True)).status_code == 403
    r = client.put(url, json={"active": True}, headers=bearer())
    assert r.status_code == 200, r.text
    assert any("database put" in str(x) and f" {pa} 1" in str(x) for x in fake_ami.actions)
    assert (
        client.put(f"/api/v1/business-hours/{a}/special/{pb}", json={"active": True}, headers=bearer()).status_code
        == 404
    )
    assert client.put(url, json={"active": "yes"}, headers=bearer()).status_code == 422
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/business-hours/{hours_id}/special/{special_id}" in paths


def test_mcp_special(client, fake_ami):
    from test_mcp import call, rpc

    (a, pa), (_b, pb) = _two_hours_with_specials()
    names = {t["name"] for t in rpc(client, "tools/list").json()["result"]["tools"]}
    assert "set_business_hours_special" in names
    ro = {t["name"] for t in rpc(client, "tools/list", headers=bearer(read_only=True)).json()["result"]["tools"]}
    assert "set_business_hours_special" not in ro
    result = call(client, "set_business_hours_special", id=a, special_id=pa, active=True)
    assert "isError" not in result or not result["isError"]
    assert call(client, "set_business_hours_special", id=a, special_id=pb, active=True)["isError"] is True
    assert call(client, "set_business_hours_special", id=a, special_id=pa, active="yes")["isError"] is True


def test_hours_form_opens_tab_with_error(client):
    login(client)
    page = client.get("/dialplan/hours/new").text
    assert 'href="#tab-general" class="nav-link active"' in page
    form = {
        "csrf_token": csrf(client, "/dialplan/hours/new"),
        "name": "Support",
        "open_dest": "hangup",
        "closed_dest": "hangup",
        "hol_date_0": "2026-08-01",
        "hol_date_1": "2026-08-01",
    }
    r = client.post("/dialplan/hours/new", data=form)
    assert r.status_code == 422
    assert 'href="#tab-holidays" class="nav-link active"' in r.text
    assert 'id="tab-holidays" role="tabpanel"' in r.text and 'tab-pane active show" id="tab-holidays"' in r.text
    assert 'href="#tab-general" class="nav-link active"' not in r.text


def test_hours_save_and_stay(client, fake_ami):
    """Save and stay returns to the edit page, on the open tab and with the months shown."""
    ids = client.ids
    login(client)
    page = client.get(f"/dialplan/hours/{ids['office']}").text
    assert 'name="stay" value="1"' in page and "Save and stay" in page and "data-active-tab" in page
    assert "Create and stay" in client.get("/dialplan/hours/new").text
    base = [
        ("csrf_token", csrf(client, "/dialplan/hours")),
        ("name", "Stay"),
        ("open_dest", "hangup"),
        ("closed_dest", "hangup"),
        ("stay", "1"),
        ("year_months", "24"),
    ]
    r = _post(client, "/dialplan/hours/new", [*base, ("tab", "year")], follow_redirects=False)
    assert r.status_code == 303, r.text
    with session_scope() as s:
        hid = s.query(BusinessHours).filter_by(name="Stay").one().id
    assert r.headers["location"] == f"/dialplan/hours/{hid}?months=24#tab-year"
    # an unknown tab or number of months is dropped
    r = _post(client, f"/dialplan/hours/{hid}", [*base[:5], ("tab", "x<y"), ("year_months", "99")])
    assert r.status_code == 200 and r.url.path == f"/dialplan/hours/{hid}" and r.url.fragment == ""
    assert "Business hours Stay saved." in r.text and r.text.count('<table class="hours-cal">') == 12
    # without "stay": back to the list
    r = _post(client, f"/dialplan/hours/{hid}", base[:4], follow_redirects=False)
    assert r.headers["location"] == "/dialplan/hours"


def test_hours_year_preview(client, fake_ami):
    """The year at a glance shows the entries of the form before they are saved, without saving them."""
    ids = client.ids
    login(client)
    with session_scope() as s:
        before = hours.to_dict(hours.get_hours(s, ids["office"]))
    year = dt.date.today().year + 1
    # names, destinations and feature codes do not matter for the calendar: a new row may still be incomplete
    form = [
        ("csrf_token", csrf(client, "/dialplan/hours")),
        ("name", ""),
        ("range_day_0", "0"),
        ("range_start_0", "08:00"),
        ("range_end_0", "17:00"),
        ("hol_date_0", f"{year}-08-01"),
        ("hol_name_0", "National Day"),
        *_special_rows([("n", "", "", True, f"{year}-03-02", f"{year}-03-03", False, "1", "")]),
    ]
    for url in (f"/dialplan/hours/{ids['office']}/year?months=24", "/dialplan/hours/new/year?months=24"):
        r = _post(client, url, form)
        assert r.status_code == 200, r.text
        assert f'title="{year}-08-01: National Day"' in r.text
        assert re.search(rf'class="hours-cal-special hours-cal-sp0[^"]*" title="{year}-03-02: -"', r.text)
        assert "Christmas Day" not in r.text  # the saved holiday was removed in the form
    with session_scope() as s:
        assert hours.to_dict(hours.get_hours(s, ids["office"])) == before
        assert not hours.get_hours(s, ids["office"]).specials
    # invalid dates or times: a hint instead of the calendars
    form[4] = ("range_end_0", "07:00")
    r = _post(client, f"/dialplan/hours/{ids['office']}/year", form)
    assert r.status_code == 200 and "cannot be shown" in r.text and "hours-cal" not in r.text


def test_year_plan(session, ids):
    office = hours.get_hours(session, ids["office"])
    data = hours.to_dict(office)
    data["specials"] = [
        {"name": "Emergency", "dest_type": "hangup"},  # off: not planned
        {
            "name": "Xmas",
            "enabled": True,
            "start": "2026-12-24",
            "end": "2027-01-02",
            "yearly": True,
            "dest_type": "hangup",
        },
    ]
    office = hours.update_hours(session, office.id, hours.BusinessHoursIn.model_validate(data))
    months = hours.year_plan(office, hours.Runtime(), dt.date(2026, 10, 24))
    assert [(m["year"], m["month"]) for m in months][:3] == [(2026, 10), (2026, 11), (2026, 12)]
    assert (months[-1]["year"], months[-1]["month"]) == (2027, 9)
    longer = hours.year_plan(office, hours.Runtime(), dt.date(2026, 10, 24), 36)
    assert len(longer) == 36 and (longer[-1]["year"], longer[-1]["month"]) == (2029, 9)
    days = {d["date"]: d for m in months for w in m["weeks"] for d in w if d}
    assert len(days) == 365 and min(days) == dt.date(2026, 10, 1)
    assert days[dt.date(2026, 10, 19)]["kind"] == "open"  # Monday
    assert days[dt.date(2026, 10, 25)]["kind"] == "closed"  # Sunday
    assert (days[dt.date(2027, 3, 26)]["kind"], days[dt.date(2027, 3, 26)]["name"]) == ("holiday", "Good Friday")
    # the special period wins over the Christmas Day holiday, across the new year
    xmas = [days[dt.date(2026, 12, 25)], days[dt.date(2027, 1, 2)]]
    assert [(d["kind"], d["name"], d["special"]) for d in xmas] == [("special", "Xmas", 1)] * 2
    assert days[dt.date(2027, 1, 4)]["kind"] == "open"
    # the runtime switch decides, as for calls
    emergency = office.specials[0].id
    switched = hours.year_plan(office, hours.Runtime(active={emergency: True}), dt.date(2026, 10, 24))
    assert {d["name"] for m in switched for w in m["weeks"] for d in w if d} == {"Emergency"}


def test_special_yearly_needs_dates():
    assert hours.SpecialIn.model_validate({"name": "x", "yearly": True, "dest_type": "hangup"}).yearly is False
    dated = {"name": "x", "yearly": True, "start": "2026-12-24", "end": "2027-01-02", "dest_type": "hangup"}
    assert hours.SpecialIn.model_validate(dated).yearly is True


def test_special_periods_validation(session, ids):
    from phonix.services.common import parse

    target = hours.create_hours(session, _hours(name="Christmas"))
    # start and end both or neither
    with pytest.raises(ServiceError) as exc:
        parse(
            hours.BusinessHoursIn,
            {
                "name": "x",
                "open_dest_type": "hangup",
                "specials": [{"name": "x", "start": "2026-12-24", "dest_type": "hangup"}],
            },
        )
    assert any(key.startswith("specials.0") for key in exc.value.fields)
    # one level: a target must not have special periods, and not be itself
    xmas = {"name": "xmas", "dest_type": "hours", "dest_id": target.id}
    a = hours.create_hours(session, _hours(name="A", specials=[xmas]))
    with pytest.raises(ServiceError) as exc:
        hours.update_hours(
            session, target.id, _hours(name="Christmas", specials=[{"name": "y", "dest_type": "hangup"}])
        )
    assert "specials" in exc.value.fields
    with pytest.raises(ServiceError):
        hours.create_hours(session, _hours(name="B", specials=[{"name": "z", "dest_type": "hours", "dest_id": a.id}]))
    with pytest.raises(ServiceError):
        hours.update_hours(
            session, a.id, _hours(name="A", specials=[{"name": "me", "dest_type": "hours", "dest_id": a.id}])
        )
    # feature codes are unique across extensions and other feature codes
    with pytest.raises(ServiceError) as exc:
        hours.update_hours(
            session,
            a.id,
            _hours(name="A", specials=[{"name": "e", "dest_type": "hangup", "feature_code": "*31"}]),
        )
    assert "specials.0.feature_code" in exc.value.fields


def test_special_periods_keep_ids_and_order(session, ids):
    h = hours.create_hours(
        session,
        _hours(
            specials=[
                {"name": "Emergency", "dest_type": "hangup", "feature_code": "*70"},
                {
                    "name": "Xmas",
                    "start": "2026-12-24",
                    "end": "2027-01-02",
                    "yearly": True,
                    "dest_type": "hangup",
                },
            ]
        ),
    )
    first, second = [s.id for s in h.specials]
    data = hours.to_dict(h)
    data["specials"].reverse()
    hours.update_hours(session, h.id, hours.BusinessHoursIn.model_validate(data))
    session.expire_all()
    assert [(s.id, s.position) for s in hours.get_hours(session, h.id).specials] == [(second, 0), (first, 1)]


def test_deleting_target_hours_falls_back_to_hangup(session, ids):
    target = hours.create_hours(session, _hours(name="Christmas"))
    special = {"name": "x", "dest_type": "hours", "dest_id": target.id}
    a = hours.create_hours(session, _hours(name="A", specials=[special]))
    hours.delete_hours(session, target.id)
    session.expire_all()
    period = hours.get_hours(session, a.id).specials[0]
    assert (period.dest_type, period.dest_id) == ("hangup", None)


def test_set_mode_clears_override_and_sets_lamp(session, ids, fake_ami):
    office = ids["office"]
    fake_ami.astdb[("phonix-hours-tmp", str(office))] = f"open:{dt.date.today()}"
    hours.set_mode(session, office, "closed", "admin")
    assert ("phonix-hours-tmp", str(office)) not in fake_ami.astdb
    assert ("Command", {"Command": f"devstate change Custom:phonix-hours-{office} INUSE"}) in fake_ami.actions


def test_set_special_active(session, ids, fake_ami):
    h = hours.create_hours(
        session, _hours(specials=[{"name": "Emergency", "dest_type": "hangup", "feature_code": "*70"}])
    )
    sid = h.specials[0].id
    clear_dirty(session)
    hours.set_special_active(session, h.id, sid, True, "admin")
    assert fake_ami.astdb[("phonix-special", str(sid))] == "1"
    assert hours.get_hours(session, h.id).specials[0].enabled is True
    assert ("Command", {"Command": f"devstate change Custom:phonix-special-{sid} INUSE"}) in fake_ami.actions
    assert dirty_areas(session) == []
    with pytest.raises(NotFound):
        hours.set_special_active(session, ids["office"], sid, False, "admin")


def test_set_special_active_without_asterisk(session, ids):
    h = hours.create_hours(session, _hours(specials=[{"name": "E", "dest_type": "hangup"}]))
    with pytest.raises(ServiceError, match="Asterisk is not running"):
        hours.set_special_active(session, h.id, h.specials[0].id, True, "admin")


def test_update_hours_pushes_special_state(session, ids, fake_ami):
    h = hours.create_hours(session, _hours(specials=[{"name": "E", "dest_type": "hangup"}]))
    data = hours.BusinessHoursIn.model_validate(
        {**hours.to_dict(h), "specials": [{**hours.to_dict(h)["specials"][0], "enabled": True}]}
    )
    hours.update_hours(session, h.id, data, "admin")
    assert fake_ami.astdb[("phonix-special", str(h.specials[0].id))] == "1"


def test_update_hours_keeps_switches_made_by_phones(session, ids, fake_ami):
    h = hours.create_hours(session, _hours(specials=[{"name": "E", "dest_type": "hangup", "feature_code": "*70"}]))
    sid = h.specials[0].id
    # a phone switched the period on after the form was opened (not yet copied to SQLite)
    fake_ami.astdb[("phonix-special", str(sid))] = "1"
    form = hours.to_dict(h)
    form["specials"].append({"name": "New", "dest_type": "hangup"})
    hours.update_hours(session, h.id, hours.BusinessHoursIn.model_validate(form), "admin")
    new = hours.get_hours(session, h.id).specials[1].id
    # unchanged switch: the phone's value stays; new period: written
    assert fake_ami.astdb[("phonix-special", str(sid))] == "1"
    assert fake_ami.astdb[("phonix-special", str(new))] == "0"
    assert ("Command", {"Command": f"devstate change Custom:phonix-special-{sid} INUSE"}) in fake_ami.actions
