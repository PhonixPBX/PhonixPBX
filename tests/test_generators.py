# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path

import pytest
from factories import sample_pbx

from phonix.core import settings as st
from phonix.generators import Facts, Secrets, build_snapshot, generate_all
from phonix.services import dialplan as dp

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


def test_logger_oci_logs_to_syslog(session):
    """OCI: no log files, Asterisk logs through syslogd to the container output."""
    sample_pbx(session)
    snap = build_snapshot(session, Facts(platform="oci"), Secrets())
    conf = {f.path: f for f in generate_all(snap)}["/etc/asterisk/logger.conf"].content
    assert "syslog.local0 => notice,warning,error,verbose(2)" in conf
    assert "syslog.local1 => security" in conf
    assert "messages =>" not in conf and "security =>" not in conf
    default = render(session)["/etc/asterisk/logger.conf"].content
    assert "messages => notice,warning,error,verbose(2)" in default and "syslog" not in default


def test_dialplan_semantics(session):
    sample_pbx(session)
    ext = render(session)["/etc/asterisk/extensions.conf"].content
    assert "Macro(" not in ext and "MeetMe(" not in ext
    # outgoing: 49+0|1XX. -> strip 1 digit, prepend 49
    # the internal caller may disconnect with *0 (H)
    assert "Dial(PJSIP/49${EXTEN:1}@prov-1,,TH)" in ext
    # Bob blocked the IAX trunk
    bob = ext.split("[phone-102-out]")[1].split("\n\n")[0]
    assert "prov-3-out" not in bob and "Bob <4930123457>" in bob
    # failover from IAX trunk to the SIP trunk
    assert "prov-1-out,${EXTEN},1" in ext.split("[prov-3-out]")[1]
    # public call group from outside: no transfer or disconnect for the caller (th, not tThH)
    assert "Gosub(sub-dial,s,1(PJSIP/101&PJSIP/102,101,th,))" in ext
    assert ",tThH," in ext


def test_pjsip(session):
    sample_pbx(session)
    conf = render(session)["/etc/asterisk/pjsip.conf"].content
    assert "[prov-1-reg]" in conf and "line=yes" in conf
    # two accounts on one host: shared inbound context, identify only once
    assert conf.count("match=sip.example.com") == 1
    assert "context=prov-host-0-in" in conf
    assert "mailboxes=101@default" in conf
    assert "max_contacts=2" in conf
    assert "minimum_expiration=60" in conf and "maximum_expiration=7200" in conf


def test_nat_settings(session):
    net = st.NetworkSettings(
        mode="static", address="10.0.0.5", prefix=16, topology="natstatic", external_address="203.0.113.7"
    )
    st.save(session, net)
    conf = render(session)["/etc/asterisk/pjsip.conf"].content
    assert "local_net=10.0.0.0/16" in conf and "external_media_address=203.0.113.7" in conf


def test_disabled_objects_are_skipped(session):
    ids = sample_pbx(session)
    from phonix.services import phones

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
    assert "5038" not in nft


def test_firewall_ami(session):
    # the sample "monitor" manager user may connect from 192.168.1.0/24
    sample_pbx(session)
    nft = render(session)["/etc/nftables.nft"].content
    assert "elements = { 192.168.1.0/24 }" in nft.split("set ami4")[1]
    assert "ip saddr @ami4 tcp dport 5038 accept" in nft


def test_privileged_flags(session):
    files = render(session)
    assert files["/etc/network/interfaces"].privileged
    assert not files["/etc/asterisk/pjsip.conf"].privileged
    assert not files["/etc/phonix/msmtprc"].privileged


@pytest.mark.parametrize("secret", ['p"w', "back\\slash"])
def test_msmtp_quoting(session, secret):
    st.save(
        session, st.EmailSettings(host="smtp.example.com", from_address="a@example.com", username="u", password=secret)
    )
    rc = render(session)["/etc/phonix/msmtprc"].content
    line = next(x for x in rc.splitlines() if x.startswith("password "))
    assert line.startswith('password "') and line.endswith('"')


def test_ssh_root_password_line(session):
    from phonix.core.shacrypt import sha512_crypt

    assert render(session)["/etc/phonix/ssh"].content == "off\n\n"
    pw = sha512_crypt("geheim123")
    st.save(session, st.SystemSettings(ssh_enabled=True, ssh_password_hash=pw))
    f = render(session)["/etc/phonix/ssh"]
    assert f.content == f"on\n{pw}\n" and f.mode == 0o640 and f.privileged


def test_mdns(session):
    files = render(session)
    assert files["/etc/phonix/mdns"].content == "on\n"
    assert files["/etc/phonix/mdns"].component == "system:mdns" and files["/etc/phonix/mdns"].privileged
    assert "host-name=phonix\n" in files["/etc/avahi/avahi-daemon.conf"].content
    assert "enable-dbus=no" in files["/etc/avahi/avahi-daemon.conf"].content
    assert "<type>_https._tcp</type>" in files["/etc/avahi/services/phonix.service"].content
    st.save(session, st.FirewallSettings(enabled=True))
    assert "udp dport 5353 accept" in render(session)["/etc/nftables.nft"].content
    st.save(session, st.SystemSettings(mdns_enabled=False))
    files = render(session)
    assert files["/etc/phonix/mdns"].content == "off\n"
    assert "5353" not in files["/etc/nftables.nft"].content


def test_notification_languages(session):
    import json

    from phonix.services import phones as ph

    ids = sample_pbx(session)
    phone = ph.get_phone(session, ids["alice"])
    data = ph.to_dict(phone)
    data["notify_language"] = "de"
    ph.update_phone(session, phone.id, ph.parse_phone(data))
    notify = json.loads(render(session)["/etc/asterisk/phonix-notify.json"].content)
    # Alice and the call group she gets the missed calls of
    assert notify["targets"]["101"] == {"extension": "101", "lang": "de", "name": "Alice"}
    assert notify["targets"][f"group-{ids['group']}"]["lang"] == "de"
    assert set(notify["languages"]) == {"de"}
    assert notify["languages"]["de"]["missed_subject"] == "Verpasster Anruf von ${CALLERID}"
    assert notify["languages"]["de"]["reasons"]["busy"] == "Besetzt"
    vm = st.load(session, st.VoicemailSettings)
    st.save(session, vm.model_copy(update={"templates": {"de": st.NotificationTexts(vm_subject="VM ${VM_MAILBOX}")}}))
    notify = json.loads(render(session)["/etc/asterisk/phonix-notify.json"].content)
    assert notify["languages"]["de"]["vm_subject"] == "VM ${VM_MAILBOX}"


def test_pjsip_srv_lookup(session):
    sample_pbx(session)
    assert "server_uri=sip:sip.example.com\n" in render(session)["/etc/asterisk/pjsip.conf"].content
    sip = st.load(session, st.SipSettings)
    sip.srv_lookup = False
    st.save(session, sip)
    conf = render(session)["/etc/asterisk/pjsip.conf"].content
    # an explicit port skips the DNS SRV lookup (RFC 3263)
    assert "server_uri=sip:sip.example.com:5060\n" in conf and "contact=sip:sip.example.com:5060\n" in conf
    assert "match=sip.example.com\n" in conf
