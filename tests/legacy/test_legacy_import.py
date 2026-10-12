"""Importing legacy config.xml files into the NG database."""

from __future__ import annotations

from pathlib import Path

import pytest
from legacy_helpers import check_golden, db_snapshot, fixture
from sqlalchemy import select

from askozia import config
from askozia.core import db
from askozia.core import settings as st
from askozia.core.models import Application, AuditLog, Dirty, Phone, Provider
from askozia.generators import build_snapshot, generate_all
from askozia.legacy import importer
from askozia.services import phones as ph
from askozia.services import users
from askozia.services.common import AREAS

GOLDEN_FIXTURES = {
    "generic-pc": "generic-pc.xml",
    "alvispbx": "alvispbx.xml",
    "synthetic": "synthetic-2.1.xml",
    "old-2.0": "old-2.0.xml",
}


def _summary(report: importer.ImportReport) -> dict:
    return {
        "ok": report.ok,
        "source_version": report.source_version,
        "counts": {k: v for k, v in report.counts.items() if any(v.values())},
        "dropped_sections": report.dropped_sections,
        "errors": sorted(f"{i.section}/{i.name}: {i.message}" for i in report.errors),
    }


@pytest.mark.parametrize("name", list(GOLDEN_FIXTURES))
def test_golden_import(initialized: config.RuntimeConfig, name: str) -> None:
    report = importer.import_bytes(fixture(GOLDEN_FIXTURES[name]), mode="replace", user="test")
    assert report.ok, report.to_text()
    with db.session_scope() as session:
        snapshot = db_snapshot(session)
    check_golden(name, {"report": _summary(report), "db": snapshot})


def test_synthetic_import_details(initialized: config.RuntimeConfig) -> None:
    report = importer.import_bytes(fixture("synthetic-2.1.xml"), user="tester")
    assert report.ok
    assert report.counts["phones"] == {"create": 6, "update": 0, "skip": 1}
    assert {"analog", "isdn", "storage", "dyndns", "thirdparty", "interfaces/dahdi-port"} <= set(
        report.dropped_sections
    )
    with db.session_scope() as session:
        snap = db_snapshot(session)
        phones = {p["extension"]: p for p in snap["phones"]}
        alice = phones["101"]
        assert alice["tech"] == "pjsip"
        assert alice["codecs"] == ["ulaw", "alaw", "g722"]
        assert alice["dtmf_mode"] == "rfc4733"
        assert alice["manual_attributes"] == "allow=g729"
        assert alice["blocked_provider_ids"] == ["IAX Trunk"]
        assert alice["provider_callerids"] == {"Sipgate": "Alice <4930111101>"}
        assert alice["vm_enabled"] and alice["vm_pin"] == "1234"
        assert alice["notify_missed"] and alice["public_access"]
        assert phones["102"]["enabled"] is False and phones["102"]["nat"] is False
        assert phones["102"]["language"] == "en_GB"
        assert phones["103"]["callerid"] == "Carol CEO"
        assert phones["103"]["ringlength"] is None and phones["103"]["language"] == "de"
        assert phones["110"]["tech"] == "iax"
        assert phones["201"]["dial_type"] == "provider"
        assert phones["201"]["dial_provider_id"] == "Sipgate"
        assert phones["202"]["dial_type"] == "sip_uri"
        assert "203" not in phones  # dials through ISDN

        providers = {p["name"]: p for p in snap["providers"]}
        sipgate = providers["Sipgate"]
        assert sipgate["dialpatterns"] == ["0|X.", "49+0|1XX."]
        assert sipgate["failover_provider_id"] == "IAX Trunk"
        assert sipgate["incoming_routes"] == [
            {"pattern": "", "dest": "phone:101"},
            {"pattern": "", "dest": "phone:102"},
            {"pattern": "4930111300", "dest": "callgroup:Sales"},
            {"pattern": "49301114XX", "dest": "application:2700"},
        ]
        assert sipgate["callerid_source"] == "string"
        assert sipgate["incoming_cid_override"] == "prepend"
        assert sipgate["language"] == "de" and sipgate["readback_number"] == "4930111000"
        backup = providers["Backup SIP"]
        assert backup["registration"] is False and backup["port"] == 5070
        assert backup["dialpatterns"] == ["00X."]  # 0|X. already used by Sipgate
        assert backup["failover_provider_id"] is None  # ISDN failover dropped
        assert backup["qualify"] == 0 and backup["nat"] is False
        assert providers["IAX Trunk"]["iax_auth"] == "plaintext"
        assert providers["IAX Trunk"]["incoming_routes"] == [{"pattern": "", "dest": "conference:2664"}]

        assert [g["name"] for g in snap["callgroups"]] == ["Sales"]
        assert snap["callgroups"][0]["member_ids"] == ["101", "102"]
        rooms = {r["number"]: r for r in snap["rooms"]}
        assert rooms["2664"]["pin"] == "4711" and rooms["2664"]["admin_pin"] == "0815"

        apps = {a["extension"]: a for a in snap["applications"]}
        assert "2702" not in apps  # PHP
        assert "ConfBridge(2664)" in apps["2700"]["logic"]
        assert "${ASKOZIA_LAN_IP}" in apps["2701"]["logic"]
        assert "CHANNEL(language)=de" in apps["2701"]["logic"]
        assert apps["2701"]["enabled"] is False
        # unmodified factory defaults use NG's built-in logic but keep the uniqid
        assert "@default" in apps["000086"]["logic"]
        assert apps["000086"]["legacy_uniqid"] == "DIALPLAN-APPLICATION-7643526674dde509b64232"
        # a customised default keeps its own logic
        assert apps["000064554"]["logic"].startswith("1,Answer()\n2,Wait(1)")

        ami = {u["username"]: u for u in snap["ami_users"]}
        assert ami["monitor"]["permit"] == ["192.168.1.0/24"]
        assert ami["crm"]["write_perms"] == ["originate"]

        s = snap["settings"]
        assert s["system"]["hostname"] == "pbx-office"
        assert s["system"]["timezone"] == "Europe/Berlin"
        assert s["system"]["ui_language"] == "de"
        assert s["system"]["ntp_servers"] == ["0.pool.ntp.org", "1.pool.ntp.org"]
        assert s["network"]["mode"] == "static" and s["network"]["address"] == "10.0.0.5"
        assert s["network"]["topology"] == "natstatic"
        assert s["network"]["external_address"] == "203.0.113.10"
        assert s["network"]["dns_servers"] == ["10.0.0.1", "9.9.9.9"]
        assert s["sip"]["srv_lookup"] is False and s["sip"]["default_expiry"] == 120
        assert s["iax"]["jitterbuffer"] is True
        assert s["iax"]["manual_attributes"] == "trunktimestamps=yes"
        assert (s["rtp"]["port_start"], s["rtp"]["port_end"]) == (10000, 10500)
        assert s["features"]["attended_transfer"] == "*2"
        assert s["features"]["feature_digit_timeout_ms"] == 1500
        assert (s["features"]["park_ext"], s["features"]["park_start"]) == ("800", 801)
        assert s["voicemail"]["custom_subject"] == "New message in mailbox ${VM_MAILBOX}"
        assert "${VM_DUR} long" in s["voicemail"]["custom_body"]
        assert s["email"]["encryption"] == "starttls" and s["email"]["port"] == 587

        # web admin password is the legacy one
        assert users.authenticate(session, "admin", "Office-2011!") is not None
        assert {d.area for d in session.scalars(select(Dirty))} >= set(AREAS)
        assert session.scalar(select(AuditLog).where(AuditLog.action == "legacy-import"))


def test_imported_config_generates(initialized: config.RuntimeConfig) -> None:
    for name in GOLDEN_FIXTURES.values():
        report = importer.import_bytes(fixture(name))
        assert report.ok, name
        with db.session_scope() as session:
            files = generate_all(build_snapshot(session))
        assert files
        content = {f.path.rsplit("/", 1)[-1]: f.content for f in files}
        if name == "synthetic-2.1.xml":
            assert "ConfBridge(2664)" in content["extensions.conf"]


def test_dry_run_changes_nothing(initialized: config.RuntimeConfig) -> None:
    with db.session_scope() as session:
        before = db_snapshot(session)
        audit_rows = len(list(session.scalars(select(AuditLog))))
    report = importer.import_bytes(fixture("synthetic-2.1.xml"), dry_run=True)
    assert report.ok and report.dry_run
    assert report.counts["phones"]["create"] == 6
    assert any(i.section == "phones" and i.level == "error" for i in report.items)
    with db.session_scope() as session:
        assert db_snapshot(session) == before
        assert len(list(session.scalars(select(AuditLog)))) == audit_rows
        assert users.authenticate(session, "admin", "Office-2011!") is None
    # the merge dry run uses savepoints before any write: still nothing changes
    report = importer.import_bytes(fixture("synthetic-2.1.xml"), mode="merge", dry_run=True)
    assert report.ok
    with db.session_scope() as session:
        assert db_snapshot(session) == before


def test_replace_keeps_web_users(initialized: config.RuntimeConfig) -> None:
    with db.session_scope() as session:
        users.create_user(session, "operator", "operator-pass-1")
    importer.import_bytes(fixture("generic-pc.xml"))
    with db.session_scope() as session:
        assert users.authenticate(session, "operator", "operator-pass-1") is not None
        # legacy password 'askozia' is too short: not imported
        assert users.authenticate(session, "admin", "askozia") is None


def test_replace_removes_existing_objects(initialized: config.RuntimeConfig) -> None:
    with db.session_scope() as session:
        ph.create_phone(session, ph.parse_phone({"extension": "999", "callerid": "Old"}))
    report = importer.import_bytes(fixture("synthetic-2.1.xml"))
    assert report.ok
    with db.session_scope() as session:
        assert session.scalar(select(Phone).where(Phone.extension == "999")) is None


def test_merge_mode(initialized: config.RuntimeConfig) -> None:
    with db.session_scope() as session:
        # same extension as a legacy phone without uniqid: updated
        ph.create_phone(
            session,
            ph.parse_phone({"extension": "101", "callerid": "Old Alice", "secret": "x1234"}),
        )
        # an NG-only phone stays untouched
        ph.create_phone(session, ph.parse_phone({"extension": "555", "callerid": "Keep me"}))
        # extension of the legacy call group (300) is taken by another kind: conflict
        ph.create_phone(session, ph.parse_phone({"extension": "300", "callerid": "Blocker"}))
        hostname = st.load(session, st.SystemSettings).hostname
    report = importer.import_bytes(fixture("synthetic-2.1.xml"), mode="merge")
    assert report.ok
    assert report.counts["phones"]["update"] == 1
    assert report.counts["callgroups"]["skip"] == 2
    assert any(i.section == "callgroups" and i.name == "Sales" and "already used" in i.message for i in report.errors)
    # the built-in applications are matched by extension and only get the uniqid
    assert report.counts["applications"]["update"] >= 2
    with db.session_scope() as session:
        snap = db_snapshot(session)
        phones = {p["extension"]: p for p in snap["phones"]}
        assert phones["101"]["callerid"] == "Alice"
        assert phones["101"]["legacy_uniqid"] == "SIP-PHONE-10001"
        assert phones["555"]["callerid"] == "Keep me"
        assert phones["300"]["callerid"] == "Blocker"
        # settings are not touched in merge mode
        assert st.load(session, st.SystemSettings).hostname == hostname
        echo = session.scalar(select(Application).where(Application.extension == "00003246"))
        assert echo is not None
        assert echo.legacy_uniqid == "DIALPLAN-APPLICATION-14520268874c62d16c931be"

    # importing the same file again matches everything by uniqid
    again = importer.import_bytes(fixture("synthetic-2.1.xml"), mode="merge")
    assert again.ok
    assert again.counts["phones"]["create"] == 0
    assert again.counts["phones"]["update"] == 6
    assert again.counts["providers"]["update"] == 3
    with db.session_scope() as session:
        assert len(list(session.scalars(select(Provider)))) == 3


def test_merge_conflicting_uniqid(initialized: config.RuntimeConfig) -> None:
    with db.session_scope() as session:
        phone = ph.create_phone(session, ph.parse_phone({"extension": "101", "callerid": "Someone else"}))
        phone.legacy_uniqid = "SIP-PHONE-OTHER"
    report = importer.import_bytes(fixture("synthetic-2.1.xml"), mode="merge")
    assert any(i.name == "Alice <101>" and "Conflict" in i.message for i in report.errors)


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("hostile-billion-laughs.xml", "DTD"),
        ("hostile-xxe.xml", "DTD"),
        ("wrong-root.xml", "root element"),
        ("future-3.0.xml", "newer than the supported version"),
        ("broken.xml", "Invalid XML"),
    ],
)
def test_rejected_files(initialized: config.RuntimeConfig, name: str, message: str) -> None:
    with db.session_scope() as session:
        before = db_snapshot(session)
    report = importer.import_bytes(fixture(name))
    assert not report.ok
    assert message in report.errors[0].message
    assert "FAILED" in report.to_text()
    with db.session_scope() as session:
        assert db_snapshot(session) == before


def test_unknown_mode(initialized: config.RuntimeConfig) -> None:
    assert not importer.import_bytes(fixture("generic-pc.xml"), mode="wipe").ok


def test_import_file(initialized: config.RuntimeConfig, tmp_path: Path) -> None:
    path = tmp_path / "config.xml"
    path.write_bytes(fixture("old-2.0.xml"))
    report = importer.import_file(path, user="firstboot")
    assert report.ok and report.source_version == "2.0"
    assert '"source_version": "2.0"' in report.to_json()
    assert not importer.import_file(tmp_path / "missing.xml").ok
    with db.session_scope() as session:
        snap = db_snapshot(session)
    apps = {a["extension"]: a for a in snap["applications"]}
    assert apps["500"]["logic"] == "1,Answer()\n2,Playback(hello-world)\n3,Hangup()"
    assert set(apps) == {"500", "00003246", "000086", "000023", "00009327357"}
    provider = snap["providers"][0]
    assert provider["incoming_routes"] == [
        {"pattern": "500", "dest": "application:500"},
        {"pattern": "", "dest": "phone:101"},
    ]
    assert snap["settings"]["email"]["encryption"] == "starttls"
    assert snap["settings"]["system"]["timezone"] == "Europe/Berlin"


def test_report_rendering(initialized: config.RuntimeConfig) -> None:
    report = importer.import_bytes(fixture("synthetic-2.1.xml"), dry_run=True)
    text = report.to_text()
    assert "dry run" in text and "phones" in text and "[ERROR  ]" in text
    data = report.to_dict()
    assert data["summary"]["error"] == len(report.errors)
    assert data["counts"]["phones"]["skip"] == 1
