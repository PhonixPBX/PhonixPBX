# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import pytest
from factories import sample_pbx
from sqlalchemy import select

from phonix.core.models import ProviderIncomingRoute
from phonix.services import dialplan, phones, providers
from phonix.services.common import ServiceError, dirty_areas


def test_seed_defaults(session):
    apps = dialplan.list_applications(session)
    assert {a.extension for a in apps} >= {"000063", "00003246", "000086", "000023"}
    assert [r.number for r in dialplan.list_rooms(session)] == ["2663"]


def test_extension_namespace_is_shared(session):
    with pytest.raises(ServiceError) as exc:
        phones.create_phone(session, phones.parse_phone({"extension": "2663", "callerid": "X"}))
    assert "conference room" in exc.value.fields["extension"]
    with pytest.raises(ServiceError):
        phones.create_phone(session, phones.parse_phone({"extension": "705", "callerid": "Park"}))


def test_phone_defaults_and_secret_kept(session):
    phone = phones.create_phone(session, phones.parse_phone({"extension": "101", "callerid": "A"}))
    assert len(phone.secret) == 16
    old = phone.secret
    data = phones.to_dict(phone)
    data["callerid"] = "B"
    phones.update_phone(session, phone.id, phones.parse_phone(data))
    assert phone.secret == old and phone.callerid == "B"
    assert "accounts" in dirty_areas(session)


def test_next_free_extension(session):
    phones.create_phone(session, phones.parse_phone({"extension": "101", "callerid": "A"}))
    assert phones.next_free_extension(session) == "102"


def _provider(name, patterns):
    return providers.parse_provider(
        {"name": name, "host": "h.example", "username": name.lower(), "dialpatterns": patterns}
    )


def _block(session, phone_id, provider_ids):
    phone = phones.get_phone(session, phone_id)
    data = {**phones.to_dict(phone), "blocked_provider_ids": provider_ids}
    return phones.update_phone(session, phone_id, phones.parse_phone(data))


def test_duplicate_dialpattern_rejected_when_a_phone_sees_both(session):
    sample_pbx(session)
    with pytest.raises(ServiceError) as exc:
        providers.create_provider(session, _provider("Dup", ["0|X."]))
    msg = exc.value.fields["dialpatterns"]
    assert "0|X." in msg and "Example Trunk" in msg and "phone 101" in msg
    # same Asterisk pattern with a different prefix rule is just as ambiguous
    with pytest.raises(ServiceError):
        providers.create_provider(session, _provider("Dup", ["0049+0X."]))


def test_same_dialpattern_on_several_trunks(session):
    """Issue #5: one trunk per phone at the same carrier, all with the same dial pattern."""
    from phonix.generators import Facts, Secrets, build_snapshot, generate_all

    ids = sample_pbx(session)
    _block(session, ids["alice"], [ids["second"]])
    _block(session, ids["bob"], [ids["second"], ids["iax_trunk"]])
    _block(session, ids["carol"], [ids["trunk"]])

    second = providers.get_provider(session, ids["second"])
    data = providers.to_dict(second)
    data["dialpatterns"] = ["0|X."]
    providers.update_provider(session, second.id, providers.parse_provider(data))
    assert providers.dialpattern_conflict(session) is None
    conf = {f.path: f for f in generate_all(build_snapshot(session, Facts(), Secrets()))}
    ext = conf["/etc/asterisk/extensions.conf"].content
    alice = ext.split("[phone-101-out]")[1].split("\n[")[0]
    carol = ext.split("[phone-103-out]")[1].split("\n[")[0]
    assert f"Goto(prov-{ids['trunk']}-out" in alice and f"prov-{ids['second']}-out" not in alice
    assert f"Goto(prov-{ids['second']}-out" in carol and f"prov-{ids['trunk']}-out" not in carol

    # unblocking makes it ambiguous again: the phone save is refused
    with pytest.raises(ServiceError) as exc, session.begin_nested():
        _block(session, ids["carol"], [])
    msg = exc.value.fields["blocked_provider_ids"]
    assert "Example Trunk" in msg and "Second Account" in msg and "0|X." in msg

    # so is a new phone that may use every provider
    with pytest.raises(ServiceError) as exc:
        phones.create_phone(session, phones.parse_phone({"extension": "150", "callerid": "New"}))
    assert "blocked_provider_ids" in exc.value.fields


def test_delete_phone_removes_routes(session):
    ids = sample_pbx(session)
    phones.delete_phone(session, ids["alice"])
    routes = session.scalars(select(ProviderIncomingRoute)).all()
    assert all(not (r.dest_type == "phone" and r.dest_id == ids["alice"]) for r in routes)
    group = dialplan.get_callgroup(session, ids["group"])
    assert [m.phone_id for m in group.members] == [ids["bob"]]


def test_update_callgroup_keeps_and_reorders_members(session):
    ids = sample_pbx(session)
    data = dialplan.callgroup_to_dict(dialplan.get_callgroup(session, ids["group"]))
    data["member_ids"] = [ids["carol"], *reversed(data["member_ids"])]
    dialplan.update_callgroup(session, ids["group"], dialplan.CallGroupIn.model_validate(data))
    group = dialplan.get_callgroup(session, ids["group"])
    assert [m.phone_id for m in group.members] == data["member_ids"]
    assert [m.position for m in group.members] == [0, 1, 2]


def test_failover_cannot_be_self(session):
    ids = sample_pbx(session)
    data = providers.to_dict(providers.get_provider(session, ids["trunk"]))
    data["failover_provider_id"] = ids["trunk"]
    with pytest.raises(ServiceError):
        providers.update_provider(session, ids["trunk"], providers.parse_provider(data))


def test_external_phone_requires_provider(session):
    with pytest.raises(ServiceError) as exc:
        phones.parse_phone({"tech": "external", "extension": "200", "callerid": "M", "dial_string": "0170"})
    assert "dial_provider_id" in exc.value.fields


def test_nested_callgroup_members(session):
    ids = sample_pbx(session)
    group = dialplan.get_callgroup(session, ids["nested"])
    assert [m.ref for m in group.members] == [
        f"phone:{ids['carol']}",
        f"callgroup:{ids['group']}",
        f"phone:{ids['alice']}",
    ]
    data = dialplan.callgroup_to_dict(group)
    assert data["member_ids"] == [ids["carol"], ids["alice"]]
    # deleting the contained group drops the membership
    dialplan.delete_callgroup(session, ids["group"])
    session.expire_all()
    assert [m.ref for m in dialplan.get_callgroup(session, ids["nested"]).members] == [
        f"phone:{ids['carol']}",
        f"phone:{ids['alice']}",
    ]


def test_callgroup_member_ids_still_accepted(session):
    ids = sample_pbx(session)
    data = dialplan.callgroup_to_dict(dialplan.get_callgroup(session, ids["nested"]))
    # a pre-1.9 client edits member_ids of a fetched copy: the phones change, the group stays
    data["member_ids"] = [ids["bob"]]
    dialplan.update_callgroup(session, ids["nested"], dialplan.CallGroupIn.model_validate(data))
    group = dialplan.get_callgroup(session, ids["nested"])
    assert [m.ref for m in group.members] == [f"phone:{ids['bob']}", f"callgroup:{ids['group']}"]


@pytest.mark.parametrize("members", [["phone:9999"], ["callgroup:9999"]])
def test_callgroup_unknown_member(session, members):
    sample_pbx(session)
    with pytest.raises(ServiceError) as exc:
        dialplan.create_callgroup(session, dialplan.CallGroupIn(name="X", members=members))
    assert "Unknown" in exc.value.fields["members"]


@pytest.mark.parametrize("members", [[], ["ivr:1"], ["phone:x"]])
def test_callgroup_invalid_members(members):
    with pytest.raises(ValueError, match="member"):
        dialplan.CallGroupIn(name="X", members=members)


def test_callgroup_loops_rejected(session):
    ids = sample_pbx(session)
    sales = dialplan.callgroup_to_dict(dialplan.get_callgroup(session, ids["group"]))
    for loop in (ids["group"], ids["nested"]):  # itself, and Everyone, which contains Sales
        data = {**sales, "members": [*sales["members"], f"callgroup:{loop}"]}
        data.pop("member_ids")
        with pytest.raises(ServiceError) as exc:
            dialplan.update_callgroup(session, ids["group"], dialplan.CallGroupIn.model_validate(data))
        assert "cannot contain itself" in exc.value.fields["members"]
    # the form offers neither
    choices = dict(dialplan.member_choices(session, ids["group"]))
    offered = {value for value, _label in choices["Call groups"]}
    assert offered == {f"callgroup:{ids['linear']}"}
