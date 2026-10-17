---
title: "RTP"
weight: 30
description: "The UDP port range for call audio and video."
---
*Advanced → RTP* sets the UDP port range that Asterisk uses for the audio and video of calls (RTP). The firewall of PhonixPBX opens this range automatically.

Click **Save** and then apply the changes, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

## Port range {#ports}

| Field | Meaning | Default |
|---|---|---|
| First port | First UDP port of the range, 1024–65535. | `10000` |
| Last port | Last UDP port of the range, 1024–65535. It must be greater than the first port. | `20000` |

Each call uses two ports per call leg; a call between a phone and a provider has two legs. The default range of 10 000 ports is enough for any realistic load. Make the range smaller only when a router or firewall in front of the PBX requires it, and keep at least a few hundred ports.

> Behind a NAT router, forward exactly this UDP range to the PBX, together with the SIP port (see [NAT]({{< relref "/system/network.md#nat" >}})). A missing forward typically results in calls without audio or with audio in one direction only.
