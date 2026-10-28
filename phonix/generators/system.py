# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Operating system configuration (network, time, firewall, mail relay)."""

from __future__ import annotations

import ipaddress

from phonix.generators.base import GeneratedFile, Snapshot, render


def _priv(path: str, content: str, component: str, mode: int = 0o644) -> GeneratedFile:
    return GeneratedFile(path=path, content=content, component=component, mode=mode, privileged=True)


def _split_nets(nets: list[str]) -> tuple[list[str], list[str]]:
    v4: list[str] = []
    v6: list[str] = []
    for net in nets:
        parsed = ipaddress.ip_network(net, strict=False)
        (v4 if parsed.version == 4 else v6).append(str(parsed))
    return v4, v6


def nftables(snap: Snapshot) -> str:
    fw = snap.firewall
    admin4, admin6 = _split_nets(fw.admin_allowed_networks)
    sip4, sip6 = _split_nets(fw.sip_allowed_networks)
    admin_ports = "80, 443" + (", 22" if snap.system.ssh_enabled else "")
    sip = snap.sip
    rules = [f"udp dport {sip.udp_port}"]
    used = {p.transport for p in snap.active_providers if p.tech == "pjsip"}
    if sip.tcp_enabled or "tcp" in used:
        rules.append(f"tcp dport {sip.udp_port}")
    if sip.tls_enabled or "tls" in used:
        rules.append(f"tcp dport {sip.tls_port}")
    if snap.iax.enabled:
        rules.append(f"udp dport {snap.iax.port}")
    # manager (AMI) users that may connect from elsewhere (Asterisk binds 0.0.0.0 then, IPv4 only)
    ami4 = sorted(
        {
            str(net)
            for user in snap.ami_users
            for net in (ipaddress.ip_network(n, strict=False) for n in user.permit)
            if net.version == 4 and not net.subnet_of(ipaddress.IPv4Network("127.0.0.0/8"))
        }
    )
    return render(
        "system/nftables.nft.j2",
        fw=fw,
        ssh=snap.system.ssh_enabled,
        mdns=snap.system.mdns_enabled,
        admin4=admin4,
        admin6=admin6,
        sip4=sip4,
        sip6=sip6,
        admin_ports=admin_ports,
        sip_rules=rules,
        ami4=ami4,
        rtp=snap.rtp,
    )


def generate(snap: Snapshot) -> list[GeneratedFile]:
    sysset, net = snap.system, snap.network
    fqdn = f"{sysset.hostname}.{sysset.domain}"
    files = [
        _priv(
            "/etc/network/interfaces",
            render("system/interfaces.j2", net=net, hostname=sysset.hostname),
            "system:network",
        ),
        _priv("/etc/hostname", sysset.hostname + "\n", "system:hostname"),
        _priv("/etc/hosts", render("system/hosts.j2", net=net, fqdn=fqdn, hostname=sysset.hostname), "system:hostname"),
        _priv("/etc/chrony/chrony.conf", render("system/chrony.conf.j2", servers=sysset.ntp_servers), "system:time"),
        _priv("/etc/timezone", sysset.timezone + "\n", "system:time"),
        # root:phonix 0640 - the web process compares it before staging changes
        _priv("/etc/nftables.nft", nftables(snap), "system:firewall", mode=0o640),
        # line 1: on/off, line 2: root password hash (empty = key logins only)
        _priv(
            "/etc/phonix/ssh",
            ("on" if sysset.ssh_enabled else "off") + "\n" + sysset.ssh_password_hash + "\n",
            "system:ssh",
            mode=0o640,
        ),
        _priv(
            "/etc/avahi/avahi-daemon.conf",
            render("system/avahi-daemon.conf.j2", hostname=sysset.hostname),
            "system:mdns",
        ),
        _priv("/etc/avahi/services/phonix.service", render("system/phonix.service.j2"), "system:mdns"),
        # on/off: whether phonix-mdns (avahi-daemon) runs
        _priv("/etc/phonix/mdns", ("on" if sysset.mdns_enabled else "off") + "\n", "system:mdns"),
        GeneratedFile(
            path="/etc/phonix/msmtprc",
            content=render("system/msmtprc.j2", email=snap.email),
            component="email",
            mode=0o640,
        ),
        GeneratedFile(
            path="/etc/phonix/msmtp-password",
            content=snap.email.password if snap.email.configured and snap.email.auth else "",
            component="email",
            mode=0o640,
        ),
    ]
    # with DHCP the resolver is managed by udhcpc unless servers are pinned
    if net.mode == "static" or net.dns_servers:
        servers = net.dns_servers or ([net.gateway] if net.gateway else [])
        files.append(
            _priv(
                "/etc/resolv.conf",
                render("system/resolv.conf.j2", domain=sysset.domain, servers=servers),
                "system:network",
            )
        )
    return files
