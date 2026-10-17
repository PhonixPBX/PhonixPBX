---
title: "IAX"
weight: 20
description: "IAX2 port, firewall access and jitter buffer."
---
*Advanced → IAX* sets the global options of IAX2, the Inter-Asterisk eXchange protocol. IAX is used by some providers and for linking Asterisk systems; it carries signalling and audio over a single UDP port, which makes it easy to pass through NAT. Phones and providers that use IAX are set up under *Accounts* like SIP ones.

Click **Save** and then apply the changes, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

## Settings {#settings}

| Field | Meaning | Default |
|---|---|---|
| Accept IAX connections (firewall) | Open the IAX port in the firewall. Turn it off when you use no IAX phones or providers. Only the firewall rule changes; outgoing IAX connections, for example a registration at a provider, continue to work. | on |
| IAX port | UDP port for IAX, 1–65535. | `4569` |
| Enable jitter buffer | Smooth out uneven packet arrival on IAX calls, at the cost of a little delay. | off |
| Force jitter buffer | Use the jitter buffer even when the other side of the call could handle the jitter itself. | off |
| Additional [general] options | `key=value` lines appended to the `[general]` section of `iax.conf`, for experts. | empty |

If [Advanced → Firewall]({{< relref "/advanced/firewall.md#networks" >}}) restricts the networks allowed to use SIP/IAX, that restriction applies to the IAX port as well.
