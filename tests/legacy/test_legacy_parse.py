"""Parsing, hostile input and version upgrades of legacy config.xml files."""

from __future__ import annotations

import base64

import pytest
from legacy_helpers import fixture

from phonix.legacy import mapping, upgrade
from phonix.legacy.parse import MAX_BYTES, LegacyParseError, parse_bytes
from phonix.legacy.report import ImportReport


def test_list_tags_become_lists_and_flags() -> None:
    cfg = parse_bytes(fixture("synthetic-2.1.xml"))
    assert cfg.version == "2.1"
    root = cfg.root
    assert root.node("system").texts("dnsserver") == ["10.0.0.1", "9.9.9.9"]
    phones = root.node("sip").nodes("phone")
    assert [p.text("extension") for p in phones] == ["101", "102", "103"]
    assert phones[0].texts("codec") == ["ulaw", "alaw", "g722", "h261"]
    assert phones[1].flag("disabled") and not phones[0].flag("disabled")
    # single list entries are still lists
    assert root.node("iax").nodes("provider")[0].texts("dialpattern") == ["9|X."]
    assert root.node("services", "sip").flag("disablesrv")
    assert not root.node("interfaces", "lan").has("dhcp")


@pytest.mark.parametrize("name", ["hostile-billion-laughs.xml", "hostile-xxe.xml"], ids=["entity-bomb", "xxe"])
def test_hostile_xml_is_rejected(name: str) -> None:
    with pytest.raises(LegacyParseError, match="DTD"):
        parse_bytes(fixture(name))


def test_wrong_root_rejected() -> None:
    with pytest.raises(LegacyParseError, match="root element is <pfsense>"):
        parse_bytes(fixture("wrong-root.xml"))


def test_broken_xml_rejected() -> None:
    with pytest.raises(LegacyParseError, match="Invalid XML"):
        parse_bytes(fixture("broken.xml"))


def test_size_limit() -> None:
    data = b"<askoziapbx>" + b" " * MAX_BYTES + b"</askoziapbx>"
    with pytest.raises(LegacyParseError, match="too large"):
        parse_bytes(data)


def test_empty_file() -> None:
    with pytest.raises(LegacyParseError, match="empty"):
        parse_bytes(b"  \n")


def test_latin1_file_is_decoded() -> None:
    data = (
        '<?xml version="1.0"?><askoziapbx><system><hostname>x</hostname>'
        "<notes>M\xfcller</notes></system></askoziapbx>".encode("latin-1")
    )
    cfg = parse_bytes(data)
    assert cfg.root.node("system").text("notes") == "Müller"
    assert any("ISO-8859-1" in w for w in cfg.warnings)


def test_alvispbx_stray_closing_tag_is_repaired() -> None:
    cfg = parse_bytes(fixture("alvispbx.xml"))
    assert any("</dialplan>" in w for w in cfg.warnings)
    report = ImportReport()
    upgrade.normalize(cfg, report)
    apps = cfg.root.node("dialplan").nodes("application")
    assert len(apps) == 7
    assert "application" not in cfg.data


def test_duplicate_single_element_keeps_first() -> None:
    cfg = parse_bytes(b"<askoziapbx><system><hostname>a</hostname><hostname>b</hostname></system></askoziapbx>")
    assert cfg.root.node("system").text("hostname") == "a"
    assert cfg.warnings


def test_upgrade_from_2_0() -> None:
    cfg = parse_bytes(fixture("old-2.0.xml"))
    report = ImportReport()
    upgrade.upgrade(cfg, report)
    assert cfg.version == "2.1"
    root = cfg.root
    email = root.node("notifications", "email")
    assert email.text("enctype") == "tls" and not email.has("tls")
    assert root.node("system").text("timezone") == "1800"
    apps = {a.text("extension"): a for a in root.node("dialplan").nodes("application")}
    # application2 (v2) + converted v1 + the three apps added by the legacy upgrade
    assert set(apps) == {"00003246", "500", "000086", "000023", "00009327357"}
    hello = apps["500"]
    assert hello.text("uniqid") == "APPLICATION-MAPPING-1"
    assert base64.b64decode(hello.text("applicationlogic")).decode() == (
        "1,Answer()\n2,Playback(hello-world)\n3,Hangup()"
    )
    assert apps["000086"].flag(upgrade.BUILTIN_MARKER)
    assert not root.node("dialplan").has("application2")


def test_newer_version_rejected() -> None:
    cfg = parse_bytes(fixture("future-3.0.xml"))
    with pytest.raises(upgrade.UnsupportedVersion, match="newer"):
        upgrade.upgrade(cfg, ImportReport())


def test_missing_version_assumes_latest() -> None:
    cfg = parse_bytes(b"<askoziapbx><system><hostname>x</hostname></system></askoziapbx>")
    report = ImportReport()
    upgrade.upgrade(cfg, report)
    assert cfg.version == "2.1"
    assert any("assuming 2.1" in i.message for i in report.warnings)


def test_garbage_version_rejected() -> None:
    cfg = parse_bytes(b"<askoziapbx><version>banana</version></askoziapbx>")
    with pytest.raises(upgrade.UnsupportedVersion):
        upgrade.upgrade(cfg, ImportReport())


# --- mapping details ---------------------------------------------------------------


def test_rewrite_meetme_and_friends() -> None:
    logic, notes = mapping.rewrite_logic(
        "1,Answer()\n2,MeetMe(${EXTEN},dM,${CALLERID(num)})\n"
        "3,Set(X=${SHELL(/etc/scripts/parseip.sh)})\n4,Macro(foo)\n5,Dial(SIP/101&IAX2/x)"
    )
    assert logic.split("\n") == [
        "1,Answer()",
        "2,ConfBridge(${EXTEN})",
        "3,Set(X=${PHONIX_LAN_IP})",
        "4,Macro(foo)",
        "5,Dial(PJSIP/101&IAX2/x)",
    ]
    levels = [lvl for lvl, _ in notes]
    assert levels.count("warning") == 3  # dropped MeetMe options, Macro, SIP/
    assert any("Gosub" in msg for _, msg in notes)


def test_default_application_detection() -> None:
    legacy_echo = "1,Answer()\n2,Echo()\n3,Hangup()\n"
    assert mapping.is_default_application("00003246", legacy_echo)
    assert not mapping.is_default_application("00003246", "1,Answer()\n2,Echo()")
    assert not mapping.is_default_application("2700", legacy_echo)


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [("en-us", "en"), ("en-gb", "en_GB"), ("de-de", "de"), ("pt-br", "pt_BR"), ("se", "sv")],
)
def test_language_mapping(legacy: str, expected: str) -> None:
    ctx = mapping.Context(report=ImportReport())
    assert mapping.language_in(legacy, ctx, "phones", "x") == expected
    assert mapping.LANGUAGE_IN[mapping.LANGUAGE_OUT[expected]] == expected


def test_unknown_language_falls_back() -> None:
    report = ImportReport()
    ctx = mapping.Context(report=report)
    assert mapping.language_in("tlh", ctx, "phones", "x") == "en"
    assert report.warnings


def test_timezones() -> None:
    assert mapping.timezone_in("1800") == "Europe/Berlin"
    assert mapping.timezone_in("Europe/Zurich") == "Europe/Zurich"
    assert mapping.timezone_in("9999") is None
    for tz_id, name in mapping.TIMEZONES_IN.items():
        assert mapping.timezone_in(tz_id) == name, tz_id
        assert mapping.TIMEZONES_IN[mapping.TIMEZONES_OUT[name]] == name


def test_ringlength_and_codecs() -> None:
    report = ImportReport()
    ctx = mapping.Context(report=report)
    assert mapping.ringlength_in("indefinitely", ctx, "phones", "x") is None
    assert mapping.ringlength_in("2", ctx, "phones", "x") == 5
    assert mapping.ringlength_in("900", ctx, "phones", "x") == 600
    assert mapping.codecs_in(["ULAW", "h261", "g729a"], ["alaw"], ctx, "phones", "x") == [
        "ulaw",
        "g729",
    ]
    assert mapping.codecs_in(["jpeg"], ["alaw"], ctx, "phones", "x") == ["alaw"]
