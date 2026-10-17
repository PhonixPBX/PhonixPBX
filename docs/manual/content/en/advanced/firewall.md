---
title: "Firewall"
weight: 50
description: "Packet filter, networks allowed to manage the PBX and to use SIP/IAX, and blocking after failed logins."
---
*Advanced → Firewall* controls the packet filter (nftables) of PhonixPBX. When it is enabled, only the services the PBX offers are reachable: the web interface (HTTP and HTTPS), SSH if enabled, SIP and IAX on their configured ports, the RTP port range, and the Asterisk Manager port 5038 for the IPv4 *Permitted networks* of the [manager users]({{< relref "/advanced/manager.md#network" >}}). Everything else from outside is dropped. The rules follow the ports set under *Advanced → SIP*, *IAX* and *RTP* automatically.

Click **Save** and then apply the changes, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

> Make sure the network of your computer is allowed before applying restrictions. If you lock yourself out, use the console menu on the local screen or serial port (see [Console menu]({{< relref "/getting-started/_index.md#console" >}})).

## Allowed networks {#networks}

| Field | Meaning | Default |
|---|---|---|
| Enable the firewall | Filter incoming traffic as described above. When off, all ports are open and the settings below have no effect. | on |
| Networks allowed to manage the PBX | Networks that may reach the web interface (ports 80 and 443) and SSH (port 22). One CIDR per line, e.g. `192.168.1.0/24`; IPv4 and IPv6. Empty: everyone. | empty |
| Networks allowed to use SIP/IAX | Networks that may reach the SIP and IAX ports: your phones and the servers of your providers. Same format. Empty: everyone. | empty |

Recommendations:

- If the PBX is reachable from the internet, restrict *Networks allowed to manage the PBX* to your local network or VPN.
- When all phones are local and your provider publishes its server addresses, restrict *Networks allowed to use SIP/IAX* to your LAN and the provider's networks. Leave it empty only when phones register from changing addresses, and then use strong passwords.
- A single address is written as `/32` (IPv4) or `/128` (IPv6), e.g. `203.0.113.10/32`.

> With *Networks allowed to manage the PBX* restricted, a CA cannot reach port 80 for the HTTP validation of [automatic certificates]({{< relref "/advanced/certificate.md#acme" >}}). Use DNS validation in that case.

## Brute force protection {#ban}

PhonixPBX watches the security events of Asterisk. When an address fails to authenticate too often (wrong SIP or IAX password, unknown account, wrong AMI secret, connection from a network that is not permitted), the address is blocked completely for a while.

| Field | Meaning | Default |
|---|---|---|
| Block addresses after repeated authentication failures | Turn the protection on or off. It only works while the firewall is enabled. | on |
| Failures within 10 minutes | Number of failures within 10 minutes after which an address is blocked, 1–1000. | `10` |
| Block duration (s) | How long the address stays blocked, at least 60 seconds. | `3600` |

Addresses from *Networks allowed to manage the PBX* and, with a static LAN address, from the local network are never blocked. Blocks are written to the system log.

Changes to these settings take effect without a restart: the security monitor picks them up within about a minute, at the next failed authentication, and keeps the failures counted so far.

There is no list of blocked addresses in the web interface and no button to lift a block. A block ends after the block duration, or when a changed firewall configuration is applied, which reloads the rules.

> A phone with a wrong password that keeps retrying blocks its whole address, and behind a NAT router that can be every device of the site. When phones suddenly stop working, check their passwords and the [logs]({{< relref "/status/logs.md" >}}).
