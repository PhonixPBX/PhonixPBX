# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Export to config.xml 2.1 and the two round trips required by the spec."""

from __future__ import annotations

import copy

from factories import sample_pbx
from legacy_helpers import db_snapshot, fixture, legacy_view, view_diff
from sqlalchemy import select

from phonix import config
from phonix.core import db
from phonix.core.models import AuditLog
from phonix.legacy import exporter, importer
from phonix.legacy.parse import parse_bytes

# Differences between the synthetic fixture and export(import(fixture)). Each
# one is a documented, reported loss (see the import report), not a bug.
EXPECTED_SYNTHETIC_LOSSES = {
    # an external phone dialing through ISDN, an analog-only call group and a
    # PHP application cannot be imported
    "-/phones/EXTERNAL-PHONE-11003",
    "-/callgroups/CALLGROUP-PARALLEL-50002",
    "-/applications/DIALPLAN-APPLICATION-60004",
    # references to the dropped analog phone / ISDN provider
    "/phones/SIP-PHONE-10001/provider",
    "/providers/SIP-PROVIDER-20001/incomingextensionmap",
    "/providers/SIP-PROVIDER-20002/failover",
    "/callgroups/CALLGROUP-PARALLEL-50001/groupmember",
    # unsupported codec h261 and chan_sip-only manual attributes
    "/phones/SIP-PHONE-10001/codec",
    "/phones/SIP-PHONE-10001/manualattributes",
    # caller id with quotes is cleaned up
    "/phones/SIP-PHONE-10003/callerid",
    # invalid dial pattern, and one already used by another provider
    "/providers/SIP-PROVIDER-20001/dialpattern",
    "/providers/SIP-PROVIDER-20002/dialpattern",
    # factory default applications are replaced by PhonixPBX's Asterisk 22 versions,
    # MeetMe / parseip / language rewrites are intentional
    "/applications/DIALPLAN-APPLICATION-14520268874c62d16c931be/descr",
    "/applications/DIALPLAN-APPLICATION-7643526674dde509b64232/logic",
    "/applications/DIALPLAN-APPLICATION-60001/logic",
    "/applications/DIALPLAN-APPLICATION-60002/logic",
    # PhonixPBX writes every feature/parking value explicitly (legacy left defaults out)
    "+/settings/featuremap/pickupexten",
    "+/settings/featuremap/atxfernoanswertimeout",
    "+/settings/featuremap/transferdigittimeout",
    # unknown AMI permission
    "/manager/crm/write",
}


def test_export_import_side_round_trip(initialized: config.RuntimeConfig) -> None:
    """export(import(xml)) keeps every supported field of the synthetic config."""
    original = fixture("synthetic-2.1.xml")
    report = importer.import_bytes(original)
    assert report.ok
    with db.session_scope() as session:
        xml, export_report = exporter.export(session, user="tester")
    assert export_report.ok
    before = legacy_view(original)
    after = legacy_view(xml)
    assert view_diff(before, after) == EXPECTED_SYNTHETIC_LOSSES

    # spot checks of values that must survive unchanged
    alice = after["phones"]["SIP-PHONE-10001"]
    assert alice["codec"] == ["ulaw", "alaw", "g722"]
    assert alice["manualattributes"] == "allow=g729"
    assert alice["provider"] == ["IAX-PROVIDER-30001"]
    sipgate = after["providers"]["SIP-PROVIDER-20001"]
    assert sipgate["incomingextensionmap"] == sorted(
        e for e in before["providers"]["SIP-PROVIDER-20001"]["incomingextensionmap"] if e[1] != "ANALOG-PHONE-80001"
    )
    assert sipgate["dialpattern"] == ["0|X.", "49+0|1XX."]
    assert after["settings"]["voicemail"] == before["settings"]["voicemail"]
    assert after["settings"]["email"] == before["settings"]["email"]


def test_export_document_shape(initialized: config.RuntimeConfig) -> None:
    importer.import_bytes(fixture("synthetic-2.1.xml"))
    with db.session_scope() as session:
        xml, report = exporter.export(session, user="tester")
    text = xml.decode()
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<askoziapbx>\n\t<version>2.1</version>')
    assert "\t\t<disablesrv/>" in text
    cfg = parse_bytes(xml)
    assert cfg.version == "2.1"
    apps = cfg.root.node("dialplan").nodes("application")
    assert all(a.text("type") == "plaintext" for a in apps)
    assert report.counts["phones"] == 6
    assert any("password" in i.name for i in report.warnings)
    with db.session_scope() as session:
        assert session.scalar(select(AuditLog).where(AuditLog.action == "legacy-export"))


def _ng_subset(snapshot: dict) -> dict:
    """Drop what config.xml cannot carry (listed in the export report)."""
    snap = copy.deepcopy(snapshot)
    for phone in snap["phones"]:
        phone.pop("legacy_uniqid", None)
        phone.pop("max_contacts")
        phone.pop("qualify")
    for provider in snap["providers"]:
        provider.pop("legacy_uniqid", None)
        provider.pop("transport")
    for group in snap["callgroups"]:
        group.pop("legacy_uniqid", None)
        group.pop("strategy")
    for key in ("rooms", "applications", "ami_users"):
        for item in snap[key]:
            item.pop("legacy_uniqid", None)
    for group in ("firewall", "gui", "update", "media"):
        snap["settings"].pop(group)
    return snap


def test_import_export_db_round_trip(initialized: config.RuntimeConfig) -> None:
    """import(export(db)) == db for the supported subset."""
    with db.session_scope() as session:
        sample_pbx(session)
    with db.session_scope() as session:
        before = db_snapshot(session)
        xml, export_report = exporter.export(session)
    omitted = "\n".join(export_report.omitted)
    assert "max_contacts=2" in omitted and "strategy=linear" in omitted

    report = importer.import_bytes(xml, mode="replace")
    assert report.ok, report.to_text()
    assert not report.errors, report.to_text()
    with db.session_scope() as session:
        after = db_snapshot(session)
    assert _ng_subset(after) == _ng_subset(before)
    # objects created in PhonixPBX got generated legacy uniqids on the way
    assert all(p["legacy_uniqid"].startswith("SIP-PHONE-") for p in after["phones"] if p["tech"] == "pjsip")

    # exporting again yields the same uniqids (stable references)
    with db.session_scope() as session:
        xml2, _ = exporter.export(session)
    assert legacy_view(xml2) == legacy_view(xml)
