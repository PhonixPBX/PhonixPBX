---
title: "General Setup"
weight: 10
description: "Host name, domain, time zone, time servers, tones, prompt language, mDNS and SSH access."
---
*System → General Setup* holds the basic identity of the system: its name on the network, the time settings, the country specific tones and the default language of the announcements. It also switches the mDNS announcement and SSH access on or off.

Click **Save** to store the settings. They take effect when you apply the changes, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

## Name and domain {#name}

| Field | Meaning | Default |
|---|---|---|
| Hostname | Name of the system, 1–63 letters, digits or `-`, without dots. It is used for the system host name, the TLS certificate, Asterisk and the mDNS name `<hostname>.local`. | `phonix` |
| Domain | DNS domain of the system. Together with the host name it forms the full name (for example `phonix.example.com`). It is also the DNS search domain when PhonixPBX writes the resolver configuration (static address or DNS servers set under *System → Network*). | `local` |

In a container (LXC/Incus or OCI), PhonixPBX does not change the host name of the container itself; that is set on the container host. The host name here is still used by PhonixPBX for the certificate and Asterisk.

## Time {#time}

| Field | Meaning | Default |
|---|---|---|
| Time zone | Time zone of the system, chosen from a searchable list. It sets the local time of the system and Asterisk, for example in logs, voicemail time stamps and the time conditions of [business hours]({{< relref "/dialplan/hours.md" >}}). | `UTC` |
| Time servers | NTP servers the system synchronises its clock with, one per line (host name or IP address). | `pool.ntp.org` |

In a container the time servers are not used: the clock comes from the container host.

## Tones and language {#tones-language}

| Field | Meaning | Default |
|---|---|---|
| Tone zone | Country specific dial, busy and ring tones that callers hear. Choose the country the phones are used in. | United States |
| Default prompt language | Language of the Asterisk announcements (voicemail, conferences and so on) when a phone or provider does not set its own. Available: English, English (UK), German, French, Spanish, Italian, Dutch, Danish, Swedish, Polish, Portuguese (Brazil), Russian, Japanese. | English |

The language of the web interface is not set here: each administrator chooses it for their own account, see [Your account]({{< relref "/getting-started/_index.md#account" >}}).

## mDNS announcement {#mdns}

**Announce on the local network (mDNS)** (default: on) makes the web interface reachable as `https://<hostname>.local/` and lets discovery tools find it as an HTTPS service. This works on macOS, iOS, Windows 10 and newer, Android 12 and newer, and Linux with nss-mdns.

- Give every PhonixPBX on the same LAN its own host name. If two systems use the same name, the second one is announced as `<hostname>-2.local`.
- In an LXC/Incus container mDNS works when the container is attached to a bridge of your LAN.
- The OCI container image does not announce itself, so the option is not shown there.

## SSH access {#ssh}

SSH is off by default. You only need it for troubleshooting; everything else is done in the web interface, the console menu or with the `phonix` command (see [Command line]({{< relref "/reference/cli.md" >}})).

| Field | Meaning | Default |
|---|---|---|
| Enable SSH access (key or password login for root) | Starts the SSH server and opens port 22 in the firewall. You log in as `root`. | off |
| SSH root password | Password for `root` logins over SSH, at least 8 characters. The password is stored only as a hash and never shown again. Leave the field empty to keep a password that is already set. | none |
| Remove the password (key logins only) | Shown when a password is set. Deletes the password, so that only key logins work. | off |

To log in with a key, put your public keys in `/data/ssh/authorized_keys`. Without a password only key logins work.

> Only enable SSH when you need it. You can additionally limit which networks may reach SSH and the web interface under [Advanced → Firewall]({{< relref "/advanced/firewall.md" >}}).

Keep in mind that on the appliance the root filesystem is read-only: changes you make to it over SSH are lost at the next reboot. The configuration lives in the database at `/data/phonix.db` and is changed through the web interface or the `phonix` command.
