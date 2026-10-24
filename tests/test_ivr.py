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
