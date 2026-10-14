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
    broken["callgroups"][0]["member_ids"] = [9999]
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

    monkeypatch.setattr(configdoc, "CONFIG_VERSION", 2)
    monkeypatch.setitem(configdoc.UPGRADES, 1, upgrade)
    parsed = configdoc.parse_document(doc)
    assert parsed.version == 2 and parsed.phones[0].description == "upgraded"
    assert doc["phones"][0]["description"] == ""  # the input is not modified


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
