# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Asterisk configuration files (everything except extensions.conf)."""

from __future__ import annotations

import ipaddress
import json

from phonix.core.models import Provider
from phonix.generators import dialplan
from phonix.generators.base import DATA, GeneratedFile, Snapshot, render

ETC = "/etc/asterisk"


def manual_lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def net_mask(cidr: str) -> str:
    net = ipaddress.ip_network(cidr, strict=False)
    return f"{net.network_address}/{net.netmask}"


def _file(name: str, content: str, component: str) -> GeneratedFile:
    return GeneratedFile(path=f"{ETC}/{name}", content=content, component=component)


def nat_settings(snap: Snapshot) -> dict[str, object]:
    net = snap.network
    if net.topology == "public":
        return {"enabled": False, "local_net": "", "external": ""}
    external = net.external_address if net.topology == "natstatic" else net.external_hostname
    if net.mode == "static":
        local = str(ipaddress.ip_network(f"{net.address}/{net.prefix}", strict=False))
    else:
        local = snap.facts.lan_network
    return {"enabled": True, "local_net": local, "external": external}


def transports(snap: Snapshot) -> list[dict[str, object]]:
    sip = snap.sip
    used = {p.transport for p in snap.active_providers if p.tech == "pjsip"}
    out: list[dict[str, object]] = [{"protocol": "udp", "port": sip.udp_port}]
    if sip.tcp_enabled or "tcp" in used:
        out.append({"protocol": "tcp", "port": sip.udp_port})
    if sip.tls_enabled or "tls" in used:
        out.append({"protocol": "tls", "port": sip.tls_port})
    return out


# standard port per provider transport (RFC 3263: an explicit port skips the DNS SRV lookup)
SIP_PORTS = {"udp": 5060, "tcp": 5060, "tls": 5061}


def provider_hostport(snap: Snapshot, provider: Provider) -> str:
    """host[:port] of a PJSIP provider; with SRV lookups off the port is always given."""
    port = provider.port or (None if snap.sip.srv_lookup else SIP_PORTS.get(provider.transport, 5060))
    return f"{provider.host}:{port}" if port else provider.host


def pjsip_conf(snap: Snapshot) -> str:
    providers = [p for p in snap.active_providers if p.tech == "pjsip"]
    return render(
        "asterisk/pjsip.conf.j2",
        sip=snap.sip,
        transports=transports(snap),
        nat=nat_settings(snap),
        tls_cert=f"{snap.facts.data_dir}/tls/server.crt",
        tls_key=f"{snap.facts.data_dir}/tls/server.key",
        srtp=snap.sip.srtp == "optional",
        providers=providers,
        hostport={p.id: provider_hostport(snap, p) for p in providers},
        phones=[p for p in snap.active_phones if p.tech == "pjsip"],
        provider_context=dialplan.provider_contexts(snap),
        identify=dialplan.identify_providers(snap),
        manual_lines=manual_lines,
    )


def iax_conf(snap: Snapshot) -> str:
    return render(
        "asterisk/iax.conf.j2",
        iax=snap.iax,
        language=snap.system.prompt_language,
        providers=[p for p in snap.active_providers if p.tech == "iax"],
        phones=[p for p in snap.active_phones if p.tech == "iax"],
        provider_context=dialplan.provider_contexts(snap),
        manual_lines=manual_lines,
    )


def voicemail_conf(snap: Snapshot) -> str:
    email = snap.email
    from_address = (
        snap.voicemail.from_address or email.from_address or (f"voicemail@{snap.system.hostname}.{snap.system.domain}")
    )
    return render(
        "asterisk/voicemail.conf.j2",
        vm=snap.voicemail,
        from_address=from_address,
        email_ok=email.configured,
        phones=[p for p in snap.active_phones if p.vm_enabled],
    )


def notify_json(snap: Snapshot) -> str:
    """Language, name and texts for the e-mail sender (phonix.notify): per mailbox or
    missed call target, and per language in use."""
    from phonix.services import notifications as nt

    targets: dict[str, dict[str, str]] = {}
    for p in snap.active_phones:
        if (p.vm_enabled and p.vm_email) or (p.notify_missed and p.notify_email):
            targets[p.extension] = {"lang": nt.effective_language(p), "name": p.callerid, "extension": p.extension}
    for group in snap.callgroups:
        members = dialplan.group_members(group, snap)
        # the first member gets the group's missed call mails (dialplan.callgroup_steps)
        if members and members[0].notify_missed and members[0].notify_email:
            targets[dialplan.group_notify_target(group)] = {
                "lang": nt.effective_language(members[0]),
                "name": group.name,
                "extension": group.extension or "",
            }
    langs = sorted({t["lang"] for t in targets.values()})
    data = {"targets": targets, "languages": {lang: nt.runtime_texts(snap.voicemail, lang) for lang in langs}}
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def manager_conf(snap: Snapshot) -> str:
    loopback = ipaddress.IPv4Network("127.0.0.0/8")
    remote = False
    for user in snap.ami_users:
        for net in user.permit:
            parsed = ipaddress.ip_network(net, strict=False)
            if not (isinstance(parsed, ipaddress.IPv4Network) and parsed.subnet_of(loopback)):
                remote = True
    return render(
        "asterisk/manager.conf.j2",
        bindaddr="0.0.0.0" if remote else "127.0.0.1",  # noqa: S104 - only with remote users
        internal_secret=snap.secrets.ami_internal,
        users=snap.ami_users,
        net_mask=net_mask,
    )


def moh_dir(snap: Snapshot) -> str:
    if snap.media.custom_moh and any(m.kind == "moh" for m in snap.media_files):
        return f"{snap.facts.data_dir}/media/moh"
    return "/usr/share/asterisk/moh"


def generate(snap: Snapshot) -> list[GeneratedFile]:
    zones = (DATA / "indications_zones.conf").read_text()
    return [
        _file(
            "asterisk.conf",
            render(
                "asterisk/asterisk.conf.j2",
                language=snap.system.prompt_language,
                hostname=snap.system.hostname,
                astdb_dir=f"{snap.facts.data_dir}/asterisk",
            ),
            "asterisk:restart",
        ),
        _file("modules.conf", render("asterisk/modules.conf.j2"), "asterisk:restart"),
        _file("logger.conf", render("asterisk/logger.conf.j2", platform=snap.facts.platform), "asterisk:logger"),
        _file(
            "indications.conf",
            render("asterisk/indications.conf.j2", country=snap.system.tonezone, zones=zones),
            "asterisk:indications",
        ),
        _file("pjsip.conf", pjsip_conf(snap), "asterisk:pjsip"),
        _file("iax.conf", iax_conf(snap), "asterisk:iax"),
        _file("extensions.conf", dialplan.generate(snap), "asterisk:dialplan"),
        _file("voicemail.conf", voicemail_conf(snap), "asterisk:voicemail"),
        # read by /usr/libexec/phonix/notify (user asterisk) at send time, no reload needed
        _file("phonix-notify.json", notify_json(snap), "asterisk:voicemail"),
        _file("confbridge.conf", render("asterisk/confbridge.conf.j2"), "asterisk:confbridge"),
        _file("musiconhold.conf", render("asterisk/musiconhold.conf.j2", moh_dir=moh_dir(snap)), "asterisk:moh"),
        _file("features.conf", render("asterisk/features.conf.j2", f=snap.features), "asterisk:features"),
        _file("res_parking.conf", render("asterisk/res_parking.conf.j2", f=snap.features), "asterisk:parking"),
        _file("rtp.conf", render("asterisk/rtp.conf.j2", rtp=snap.rtp), "asterisk:rtp"),
        _file("manager.conf", manager_conf(snap), "asterisk:manager"),
        _file("cdr.conf", render("asterisk/cdr.conf.j2"), "asterisk:cdr"),
        _file("cel.conf", render("asterisk/cel.conf.j2"), "asterisk:restart"),
        _file("http.conf", render("asterisk/http.conf.j2"), "asterisk:restart"),
        _file("udptl.conf", render("asterisk/udptl.conf.j2"), "asterisk:restart"),
        _file("pjsip_notify.conf", render("asterisk/pjsip_notify.conf.j2"), "asterisk:pjsip"),
        _file("acl.conf", render("asterisk/empty.conf.j2"), "asterisk:restart"),
        *(_file(name, render("asterisk/stub.conf.j2"), "asterisk:restart") for name in ("ccss.conf", "pjproject.conf")),
    ]
