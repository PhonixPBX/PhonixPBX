---
title: "Calls & Registrations"
weight: 20
description: "Live state of Asterisk, provider and phone registrations, and the calls in progress."
---
*Status → Calls & Registrations* shows the live state of the telephone system. The page refreshes itself every 5 seconds, so you can leave it open while you test a phone or a provider.

## Asterisk {#asterisk}

The first line shows the Asterisk version, the number of *Active channels* (every call leg counts as one channel, so a call between two phones usually has two) and *SIP phones registered*: how many of the SIP phones currently have a registered device, out of all SIP phones.

If the page shows *Asterisk is not reachable* with an error, the telephony engine is not running or does not answer. Look at the Asterisk log under [Status → Logs]({{< relref "/status/logs.md" >}}); applying the configuration again or a [reboot]({{< relref "/system/reboot.md" >}}) usually brings it back.

## Providers {#providers}

| Column | Meaning |
|---|---|
| Name | Name of the provider. |
| Type | `SIP` or `IAX`. |
| Registration / state | For SIP providers that register: the registration state. For SIP providers without registration and for IAX providers: whether the provider is reachable. Disabled providers show *disabled*. |

*not loaded* means the provider exists in the configuration but is not active in Asterisk yet; apply the pending changes.

## Phones {#phones}

| Column | Meaning |
|---|---|
| Extension | Internal number of the phone. |
| Name | Caller ID name of the phone. |
| State | Device state reported by Asterisk, or *disabled*. |
| Contact | For each registered device: its address (SIP URI), the qualify state and the round-trip time in milliseconds. Empty when no device is registered. |
| User agent | Make and firmware the device reports, for example the softphone name and version. |

External phones (numbers that are dialled through a provider or a SIP URI) are not listed, as they never register.

## Active calls {#active-calls}

Every channel of a running call is one row:

| Column | Meaning |
|---|---|
| Channel | Technical name of the channel, for example `PJSIP/21-00000004`. |
| Caller | Caller ID of the channel. |
| Dialed | The number that was dialled. |
| State | Channel state, for example *Up* (connected) or *Ringing*. |
| Application | What Asterisk is doing with the channel, for example `Dial`, `VoiceMail` or `ConfBridge`. |
| Duration | Duration of the channel. |

*No active calls.* means nobody is on the phone.

## States {#states}

The coloured dot next to a state shows its meaning at a glance:

- **Green:** *Registered*, *Reachable*, *Not in use*, *In use* – the phone or provider works.
- **Grey:** unknown – Asterisk has no information yet, for example right after a start.
- **Red:** every other state, such as *Unregistered*, *Rejected*, *Unreachable*, *Unavailable* or *not loaded*.

A red state for a phone usually means that the device is switched off, not configured, or cannot reach the PBX. For help see [Troubleshooting]({{< relref "/reference/troubleshooting.md#phone-registration" >}}).
