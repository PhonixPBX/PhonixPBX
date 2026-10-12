import os
from pathlib import Path

import pytest
from factories import sample_pbx

from askozia.core import settings as st
from askozia.generators import Facts, Secrets, build_snapshot, generate_all
from askozia.services import dialplan as dp

GOLDEN = Path(__file__).parent / "golden"


def render(session):
    snap = build_snapshot(
        session,
        Facts(lan_ip="192.168.1.10", lan_prefix=24, data_dir="/data", version="test"),
        Secrets(ami_internal="internal-secret"),
    )
    return {f.path: f for f in generate_all(snap)}


def test_golden_files(session):
    sample_pbx(session)
    files = render(session)
    GOLDEN.mkdir(exist_ok=True)
    for path, f in files.items():
        golden = GOLDEN / path.lstrip("/").replace("/", "__")
        if os.environ.get("UPDATE_GOLDEN") or not golden.exists():
            golden.write_text(f.content)
        assert f.content == golden.read_text(), f"{path} differs from {golden} (UPDATE_GOLDEN=1 to accept)"


def test_dialplan_semantics(session):
    sample_pbx(session)
    ext = render(session)["/etc/asterisk/extensions.conf"].content
    assert "Macro(" not in ext and "MeetMe(" not in ext
    # outgoing: 49+0|1XX. -> strip 1 digit, prepend 49
    assert "Dial(PJSIP/49${EXTEN:1}@prov-1,,T)" in ext
    # Bob blocked the IAX trunk
    bob = ext.split("[phone-102-out]")[1].split("\n\n")[0]
    assert "prov-3-out" not in bob and "Bob <4930123457>" in bob
    # failover from IAX trunk to the SIP trunk
    assert "prov-1-out,${EXTEN},1" in ext.split("[prov-3-out]")[1]
    # public call group from outside: no transfer for the caller (t, not tT)
    assert "Gosub(sub-dial,s,1(PJSIP/101&PJSIP/102,101,t,))" in ext


def test_pjsip(session):
    sample_pbx(session)
    conf = render(session)["/etc/asterisk/pjsip.conf"].content
    assert "[prov-1-reg]" in conf and "line=yes" in conf
    # two accounts on one host: shared inbound context, identify only once
    assert conf.count("match=sip.example.com") == 1
    assert "context=prov-host-0-in" in conf
    assert "mailboxes=101@default" in conf
    assert "max_contacts=2" in conf


def test_nat_settings(session):
    net = st.NetworkSettings(
        mode="static", address="10.0.0.5", prefix=16, topology="natstatic", external_address="203.0.113.7"
    )
    st.save(session, net)
    conf = render(session)["/etc/asterisk/pjsip.conf"].content
    assert "local_net=10.0.0.0/16" in conf and "external_media_address=203.0.113.7" in conf


def test_disabled_objects_are_skipped(session):
    ids = sample_pbx(session)
    from askozia.services import phones

    phones.set_enabled(session, ids["alice"], False)
    files = render(session)
    assert "[101]" not in files["/etc/asterisk/pjsip.conf"].content
    assert "exten => 101,1" not in files["/etc/asterisk/extensions.conf"].content


def test_conference_pins(session):
    dp.create_room(session, dp.ConferenceRoomIn(number="3000", name="R", admin_pin="99"))
    ext = render(session)["/etc/asterisk/extensions.conf"].content
    room = ext.split("conference room R <3000>")[1]
    assert 'GotoIf($["${PIN}" = "99"]?admin)' in room
    assert 'GotoIf($["${PIN}" = ""]?user)' in room


def test_firewall(session):
    st.save(
        session,
        st.FirewallSettings(
            admin_allowed_networks=["192.168.1.0/24", "2001:db8::/32"], sip_allowed_networks=["198.51.100.0/24"]
        ),
    )
    nft = render(session)["/etc/nftables.nft"].content
    assert "ip saddr @admin4 tcp dport { 80, 443 } accept" in nft
    assert "ip6 saddr @admin6" in nft
    assert "ip saddr @sip4 udp dport 5060 accept" in nft
    assert "policy drop" in nft


def test_privileged_flags(session):
    files = render(session)
    assert files["/etc/network/interfaces"].privileged
    assert not files["/etc/asterisk/pjsip.conf"].privileged
    assert not files["/etc/askozia/msmtprc"].privileged


@pytest.mark.parametrize("secret", ['p"w', "back\\slash"])
def test_msmtp_quoting(session, secret):
    st.save(
        session, st.EmailSettings(host="smtp.example.com", from_address="a@example.com", username="u", password=secret)
    )
    rc = render(session)["/etc/askozia/msmtprc"].content
    line = next(x for x in rc.splitlines() if x.startswith("password "))
    assert line.startswith('password "') and line.endswith('"')
