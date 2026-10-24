# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""config.json: export, validation, version handling and import."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest
from factories import sample_pbx
from legacy.legacy_helpers import db_snapshot

from phonix.core import db
from phonix.core import settings as st
from phonix.core.models import ApiToken, MediaFile, User
from phonix.services import configdoc, tokens, users
from phonix.services.common import ServiceError, dirty_areas

SCHEMA = Path(__file__).parent.parent / "docs" / "config-schema.json"


def _populated(session) -> dict:
    sample_pbx(session)
    users.create_user(session, "admin", "adminadmin")
    users.create_user(session, "ops", "opsopsops", must_change=True)
    tokens.create(session, users.get_by_name(session, "ops"), "monitoring", read_only=True, expires_in_days=30)
    session.commit()
    return configdoc.export(session)


def _import(doc: dict, media_root: Path) -> dict[str, int]:
    with db.session_scope() as s:
        return configdoc.import_document(s, configdoc.parse_document(doc), media_root, user="test")


def test_schema_is_current():
    rendered = json.dumps(configdoc.json_schema(), indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        SCHEMA.write_text(rendered)
    assert SCHEMA.read_text() == rendered, (
        "docs/config-schema.json is outdated: if the document changed incompatibly, bump "
        "configdoc.CONFIG_VERSION and add an upgrade step; then run with UPDATE_GOLDEN=1"
    )


def test_roundtrip(session, initialized):
    doc = _populated(session)
    before = db_snapshot(session)
    session.close()

    # the document survives JSON encoding and replaces whatever is there now
    with db.session_scope() as s:
        users.delete_user(s, "ops")
    counts = _import(json.loads(json.dumps(doc)), initialized.media_dir)
    assert counts["phones"] == 4 and counts["providers"] == 3 and counts["users"] == 2

    with db.session_scope() as s:
        assert db_snapshot(s) == before
        again = configdoc.export(s)
        assert "accounts" in dirty_areas(s)
        ops = users.get_by_name(s, "ops")
        assert ops is not None and ops.must_change_pw
        token = s.query(ApiToken).one()
        assert token.user is ops and token.read_only and token.expires_at is not None
    # objects get new ids (compared above through db_snapshot), the rest is identical
    for key in ("settings", "users", "ami_users", "media"):
        assert again[key] == doc[key]


def test_restored_password_still_works(session, initialized):
    doc = _populated(session)
    session.close()
    with db.session_scope() as s:
        users.set_password(s, "admin", "something-else")
    _import(doc, initialized.media_dir)
    with db.session_scope() as s:
        assert users.authenticate(s, "admin", "adminadmin") is not None


def test_import_is_all_or_nothing(session, initialized):
    doc = _populated(session)
    session.close()
    broken = copy.deepcopy(doc)
    broken["callgroups"][0]["members"] = ["phone:9999"]
    with pytest.raises(ServiceError, match=r"callgroups/.*unknown phone 9999"):
        _import(broken, initialized.media_dir)
    with db.session_scope() as s:
        assert s.query(User).count() == 2
        assert configdoc.export(s)["phones"] == doc["phones"]


def test_service_validation_applies(session, initialized):
    doc = _populated(session)
    session.close()
    doc["phones"][1]["extension"] = doc["phones"][0]["extension"]
    with pytest.raises(ServiceError, match="phones/101"):
        _import(doc, initialized.media_dir)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(format="something"), "not a PhonixPBX configuration"),
        (lambda d: d.update(version=configdoc.CONFIG_VERSION + 1, phonix_version="9.0"), "PhonixPBX 9.0"),
        (lambda d: d.update(version="1"), "Unknown configuration version"),
        (lambda d: d.update(unknown=1), "unknown"),
        (lambda d: d["settings"]["system"].update(hostnmae="typo"), "settings.system.hostnmae"),
        (lambda d: d["phones"][0].update(extension="x"), "phones.0.extension"),
        (lambda d: d.update(users=[]), "users"),
    ],
)
def test_parse_rejects(session, change, message):
    doc = _populated(session)
    change(doc)
    with pytest.raises(ServiceError, match=message):
        configdoc.parse_document(doc)


def test_upgrade_chain(session, monkeypatch):
    doc = _populated(session)

    def upgrade(data):
        data["phones"][0]["description"] = "upgraded"
        return data

    current = configdoc.CONFIG_VERSION
    monkeypatch.setattr(configdoc, "CONFIG_VERSION", current + 1)
    monkeypatch.setitem(configdoc.UPGRADES, current, upgrade)
    parsed = configdoc.parse_document(doc)
    assert parsed.version == current + 1 and parsed.phones[0].description == "upgraded"
    assert doc["phones"][0]["description"] == ""  # the input is not modified


def test_upgrade_1_moves_custom_voicemail_text(session):
    doc = _populated(session)
    doc["version"] = 1
    doc["settings"]["system"]["prompt_language"] = "de"
    doc["settings"]["voicemail"].pop("templates", None)
    doc["settings"]["voicemail"].update(custom_subject="Neue Nachricht", custom_body="Hallo ${VM_NAME}")
    vm = configdoc.parse_document(doc).settings.voicemail
    assert vm.templates["de"].vm_subject == "Neue Nachricht"
    assert vm.templates["de"].vm_body == "Hallo ${VM_NAME}"


def test_missing_settings_groups_keep_current_values(session, initialized):
    doc = _populated(session)
    st.save(session, st.EmailSettings(host="mail.example.com", from_address="pbx@example.com"))
    session.commit()
    session.close()
    del doc["settings"]["email"]
    counts = _import(doc, initialized.media_dir)
    assert counts["settings"] == len(st.ALL_GROUPS) - 1
    with db.session_scope() as s:
        assert st.load(s, st.EmailSettings).host == "mail.example.com"


def test_media_must_match(session, initialized):
    (initialized.media_dir / "moh").mkdir(parents=True, exist_ok=True)
    path = initialized.media_dir / "moh" / "song.wav"
    path.write_bytes(b"RIFF....WAVE")
    session.add(MediaFile(kind="moh", name="song.wav", path="moh/song.wav", size=12))
    doc = _populated(session)
    session.close()
    assert doc["media"][0]["path"] == "moh/song.wav"
    path.write_bytes(b"changed")
    with pytest.raises(ServiceError, match=r"moh/song\.wav"):
        _import(doc, initialized.media_dir)


def test_media_path_cannot_escape(session):
    doc = _populated(session)
    doc["media"] = [{"kind": "moh", "name": "x", "path": "moh/../../etc.wav", "size": 1, "sha256": "0" * 64}]
    with pytest.raises(ServiceError, match=r"media\.0\.path"):
        configdoc.parse_document(doc)


def test_unknown_keep_part(session, initialized):
    doc = configdoc.parse_document(_populated(session))
    with pytest.raises(ValueError, match="unknown parts"):
        configdoc.import_document(session, doc, initialized.media_dir, keep=["everything"])


def test_upgrade_3_converts_member_ids(session):
    doc = _populated(session)
    doc["version"] = 3
    for group in doc["callgroups"]:
        group["member_ids"] = [int(m.removeprefix("phone:")) for m in group.pop("members") if m.startswith("phone:")]
    parsed = configdoc.parse_document(doc)
    assert all(all(m.startswith("phone:") for m in g.members) for g in parsed.callgroups)
    assert any(g.members for g in parsed.callgroups)


def test_callgroup_loop_in_document(session, initialized):
    doc = _populated(session)
    session.close()
    groups = {g["name"]: g for g in doc["callgroups"]}
    groups["Sales"]["members"].append(f"callgroup:{groups['Everyone']['id']}")
    with pytest.raises(ServiceError, match="contain each other"):
        _import(doc, initialized.media_dir)
    doc["callgroups"][0]["members"] = ["callgroup:9999"]
    with pytest.raises(ServiceError, match="unknown callgroup 9999"):
        _import(doc, initialized.media_dir)


_DESTS = {"open_dest_type": "hangup", "closed_dest_type": "hangup"}


def _hours_with_specials(session) -> dict:
    from phonix.services import hours as hours_svc

    users.create_user(session, "admin", "adminadmin")
    holiday = hours_svc.create_hours(session, hours_svc.BusinessHoursIn(name="Holiday desk", **_DESTS))
    hours_svc.create_hours(
        session,
        hours_svc.BusinessHoursIn(
            name="Shop",
            **_DESTS,
            specials=[
                hours_svc.SpecialIn(
                    name="Inventory",
                    enabled=True,
                    start="2026-12-27",
                    end="2026-12-28",
                    feature_code="*71",
                    dest_type="hangup",
                ),
                hours_svc.SpecialIn(name="Christmas", yearly=True, dest_type="hours", dest_id=holiday.id),
            ],
        ),
    )
    session.commit()
    return configdoc.export(session)


def test_roundtrip_special_periods(session, initialized):
    doc = _hours_with_specials(session)
    session.close()
    assert doc["version"] == 5
    shop = next(h for h in doc["business_hours"] if h["name"] == "Shop")
    holiday_id = next(h["id"] for h in doc["business_hours"] if h["name"] == "Holiday desk")
    assert [sp["dest_id"] for sp in shop["specials"]] == [None, holiday_id]

    # the ids of the document are not the ones of the database
    for h in doc["business_hours"]:
        h["id"] += 100
    for sp in shop["specials"]:
        sp["id"] += 50
        if sp["dest_type"] == "hours":
            sp["dest_id"] += 100
    _import(json.loads(json.dumps(doc)), initialized.media_dir)

    with db.session_scope() as s:
        from phonix.services import hours as hours_svc

        by_name = {h.name: h for h in hours_svc.list_hours(s)}
        specials = by_name["Shop"].specials
        assert [(sp.name, sp.enabled, sp.yearly, sp.feature_code) for sp in specials] == [
            ("Inventory", True, False, "*71"),
            ("Christmas", False, True, None),
        ]
        assert [sp.position for sp in specials] == [0, 1]
        assert specials[1].dest_type == "hours" and specials[1].dest_id == by_name["Holiday desk"].id
        assert str(specials[0].start) == "2026-12-27"


def test_version_4_document_imports(session, initialized):
    doc = _populated(session)
    session.close()
    doc["version"] = 4
    for h in doc["business_hours"]:
        h.pop("specials", None)
    _import(doc, initialized.media_dir)


def test_import_replaces_specials_and_ignores_document_ids(session, initialized):
    from phonix.core.models import BusinessHoursSpecial
    from phonix.services import hours as hours_svc

    doc = _hours_with_specials(session)
    old = {sp.id: sp.name for sp in session.query(BusinessHoursSpecial)}
    assert 1 in old
    session.close()
    # the document's special with id 1 has another name than the one in the database
    shop = next(h for h in doc["business_hours"] if h["name"] == "Shop")
    shop["specials"] = [{**shop["specials"][0], "id": 1, "name": "Renamed", "feature_code": ""}]
    _import(doc, initialized.media_dir)

    with db.session_scope() as s:
        rows = s.query(BusinessHoursSpecial).all()
        # import replaces the configuration: exactly the document's period, none of the old ones
        assert [r.name for r in rows] == ["Renamed"]
        assert old[1] == "Inventory"
        assert {h.name: [sp.name for sp in h.specials] for h in hours_svc.list_hours(s)} == {
            "Holiday desk": [],
            "Shop": ["Renamed"],
        }
