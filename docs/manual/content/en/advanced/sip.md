---
title: "SIP"
weight: 10
description: "SIP ports and transports (UDP, TCP, TLS), SRTP media encryption and registration timers."
---
*Advanced → SIP* sets the global SIP parameters of Asterisk (PJSIP): the ports and transports phones and providers use, media encryption, and the registration intervals. Phone and provider settings themselves are on their own pages under *Accounts*.

Click **Save** and then apply the changes, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}). The firewall rules follow the ports and transports set here automatically.

> Changing the SIP port or transports affects every phone and provider. Phones configured with the old port can no longer register until you change them too.

## Ports and transports {#transports}

| Field | Meaning | Default |
|---|---|---|
| SIP port (UDP/TCP) | Port for SIP over UDP, and over TCP when TCP is enabled. | `5060` |
| Enable TCP | Accept SIP over TCP on the same port. Enabled automatically when a provider uses the TCP transport. | off |
| Enable TLS | Accept SIP over TLS (encrypted signalling). Enabled automatically when a provider uses the TLS transport. | off |
| TLS port | Port for SIP over TLS. Only shown with *Enable TLS*. | `5061` |

UDP is always active and is what most phones use.

## TLS {#tls}

SIP over TLS encrypts the signalling, including the authentication and the SRTP keys. Asterisk uses the certificate from [Advanced → Certificate]({{< relref "/advanced/certificate.md" >}}) and TLS 1.2. With the self-signed default certificate, phones must be set to accept it or to skip certificate verification; with a certificate from a public CA (for example by [ACME]({{< relref "/advanced/certificate.md#acme" >}})) they usually work as is, if they connect using the certificate's name.

When the certificate changes, Asterisk is restarted to load it once no call is active.

## Media encryption (SRTP) {#srtp}

| Option | Meaning |
|---|---|
| off | Audio is sent unencrypted (RTP). |
| offer SRTP (SDES), fall back to RTP | PhonixPBX offers encrypted audio (SRTP with SDES key exchange) to phones and providers and falls back to plain RTP when the other side does not support it. |

SDES transmits the keys inside the SIP messages, so SRTP only protects the audio when the signalling is encrypted as well. Use it together with TLS.

## Registration timers {#timers}

| Field | Meaning | Default |
|---|---|---|
| Default expiry (s) | How long a registration of PhonixPBX at a provider is valid before it is renewed. At least 60. | `3600` |
| Minimum expiry (s) | Shortest registration interval a phone may request. Shorter requests are raised to this value. At least 10. | `60` |
| Maximum expiry (s) | Longest registration interval a phone may request. Longer requests are lowered to this value. At least 60. | `7200` |
| Use DNS SRV lookups | For providers without a port: look up the host name via DNS SRV first (RFC 3263). When off, the standard port is used directly (5060 for UDP and TCP, 5061 for TLS). | on |

*Default expiry* also applies to phones that do not request an interval of their own when they register.

## NAT {#nat}

Whether the PBX sits behind a NAT router, and its public address, is set under [System → Network]({{< relref "/system/network.md#nat" >}}). With NAT, forward the SIP port (and the TLS port, if used) and the [RTP port range]({{< relref "/advanced/rtp.md" >}}) on the router to the PBX.

## Additional options {#manual}

**Additional [global] options** takes `key=value` lines that are appended to the `[global]` section of the generated `pjsip.conf`. This is meant for experts and for options that the web interface does not offer. Wrong options can stop SIP from working; check the [Asterisk log]({{< relref "/status/logs.md" >}}) after applying.
