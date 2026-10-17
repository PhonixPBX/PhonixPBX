---
title: "Phones"
weight: 10
description: "SIP, IAX and external phones: numbers, passwords, voicemail, outgoing rules and how to register a device."
---
A phone is an internal number that rings a device. Every desk phone, softphone or mobile app that registers with the PBX needs its own phone account, and an *external* phone lets an internal number ring a mobile or another system. Phones are managed under *Accounts → Phones*.

Changes to phones take effect after you apply them, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

## Phone types {#types}

| Type | Use it for |
|---|---|
| SIP phone | Desk phones, softphones and apps that speak SIP. This is the usual choice. |
| IAX phone | Devices or other Asterisk systems that speak IAX2 (port 4569 UDP). |
| External phone | An internal number that forwards to a number outside the PBX: a mobile number dialled through a provider, or a SIP or IAX address (`user@host`). It has no password and does not register. |

The type is chosen with the buttons **SIP phone**, **IAX phone** and **External phone** above the list and cannot be changed later. To change it, create a new phone and delete the old one.

## Phone list {#list}

The list shows every phone, sorted by number:

| Column | Meaning |
|---|---|
| Extension | The internal number. Click it to edit the phone. |
| Name | The caller ID name. |
| Type | SIP, IAX or External. |
| Status | For SIP phones *registered* (with the address of the device) or *not registered*; for IAX phones the peer state; for external phones the number or address they forward to. The column refreshes every 15 seconds. *Asterisk down* means the telephony service is not running. |
| Voicemail | A mail icon when the phone has a voicemail box. |
| Description | Your note. |

The buttons at the end of each row edit, disable/enable and delete the phone. A disabled phone keeps its settings but is left out of the configuration: it cannot register and cannot be called. Deleting a phone also removes the incoming routes and IVR keys that pointed to it or to its voicemail box; the fixed destinations of IVR menus and business hours that pointed to it fall back to *Hang up*.

The currently registered devices and active calls are also shown under [*Status → Calls & Registrations*]({{< relref "/status/calls.md" >}}).

## Add or edit a phone {#edit}

The form has up to four tabs. External phones only have the first two.

### General {#general}

| Field | Meaning | Default |
|---|---|---|
| Number | The internal number (1–20 digits) used to dial this phone. For SIP and IAX phones it is also the user name the device registers with. It must not be used by another phone, call group, conference room, application, IVR menu, business hours feature code or the call parking range. | next free number from 101 |
| Caller ID name | The name shown to the people this phone calls, for example `Anna Meier`. It must not contain `" < > ; \`. | – |
| Password | SIP/IAX only. The password the device registers with, 4–128 characters without spaces, quotes, `;` or `\`. A strong random password is filled in for new phones; **Generate** creates a new one, the eye button shows it. When editing, leave the field empty to keep the stored password. | generated, 16 characters |
| Reach this phone via | External only: *a provider* (the number is dialled through a provider), *SIP URI (user@host)* or *IAX URI (user@host)*. | a provider |
| Number / URI | External only: the phone number to dial (digits, optionally with a leading `+`, `*` and `#`) or the address `user@host`. | – |
| Provider | External only, with *a provider*: the provider that dials the number. If that provider is deleted, the external phone is disabled. | – |
| Language | Language of the announcements this phone hears (voicemail, prompts, numbers read out). | English |
| Ring time (seconds) | How long the phone rings before the call goes to voicemail (5–600). Empty means the phone rings until the caller hangs up. | empty |
| Description | A note for your reference only. | – |
| Reachable from outside (public direct dial) | Callers from providers or SIP addresses may call this phone directly by its number. | off |
| Public name | Shown when the phone is reachable from outside: an alias for the public context, for example `sales` for `sip:sales@pbx`. Letters, digits and `. _ + -`. Empty uses the number. | empty |

### Voicemail & notifications {#voicemail}

| Field | Meaning | Default |
|---|---|---|
| Enable voicemail | Gives the phone a voicemail box. Calls that are not answered within the ring time, or that find the phone busy, go to the box. Users listen to their messages by dialling `000086`. | off |
| Voicemail PIN | The digits the user enters to open the box. A random 4-digit PIN is suggested for new phones. | generated |
| Send voicemail to e-mail | New messages are sent to this address (with the recording attached, depending on the settings under [*Services → Voicemail*]({{< relref "/services/voicemail.md" >}})). Requires working e-mail, see [*Services → Notifications*]({{< relref "/services/email.md" >}}). | empty |
| E-mail notification on missed calls | Sends an e-mail for every call this phone did not answer. | off |
| Notification address | Where missed call e-mails go. Required when the option above is on. | – |
| E-mail language | Language of the voicemail and missed call e-mails. The texts can be changed under [*Services → Voicemail*]({{< relref "/services/voicemail.md" >}}). | Same as phone language |

### Outgoing calls {#outgoing}

SIP and IAX phones only. This tab lists the configured providers.

| Field | Meaning | Default |
|---|---|---|
| Block providers | The phone cannot place outgoing calls through the selected providers, for example to keep a lobby phone internal. | none |
| Outgoing caller ID per provider | One field per provider. A caller ID such as `Sales <4930123456>` (or just a number) sent when this phone calls through that provider. It overrides the provider's *Outgoing caller ID* setting. Empty uses the provider setting. | empty |

Which numbers go to which provider is set by the provider's [dial patterns]({{< relref "/accounts/providers.md#dial-patterns" >}}).

### Codecs & advanced {#advanced}

SIP and IAX phones only. The defaults suit most devices.

| Field | Meaning | Default |
|---|---|---|
| Codecs | The audio and video codecs offered to the device, in order of preference (drag to reorder). Audio: ulaw, alaw, g722, opus, gsm, g726, g729, ilbc, speex, slin. Video: h264, vp8, vp9, h263. At least one is required. | g722, alaw, ulaw, opus |
| DTMF mode | SIP only. How key presses are transmitted: *RFC 4733 (RFC 2833)*, *In-band*, *SIP INFO* or *Auto*. Change it only if key presses in menus or voicemail are not recognised. | RFC 4733 |
| Qualify interval (s) | How often the PBX checks that the device is reachable (0–3600). 0 disables the check. For IAX phones any value other than 0 just turns the check on. | 60 |
| Max. registered devices | SIP only. How many devices may register with this account at the same time (1–10), for example a desk phone and a softphone. When the limit is reached, a new registration replaces the oldest one. | 1 |
| Busy level | SIP only. With this many concurrent calls the phone is reported busy (1–100), so further callers get the busy treatment (voicemail, if enabled). Empty means no limit. | empty |
| Phone is behind NAT (symmetric RTP, rewrite contact) | SIP only. Sends audio and signalling back to the address the packets came from. Keep it on unless the phone is on the same network and you know it is not needed. | on |
| Additional PJSIP endpoint options / Additional IAX peer options | Advanced: one `key=value` per line, appended to the generated endpoint or peer section. Lines starting with `;` are ignored. | empty |

### Add a SIP phone {#add-sip-phone}

1. Open *Accounts → Phones* and click **SIP phone**.
2. Keep the suggested **Number** or enter your own, and type the **Caller ID name**.
3. Copy the generated **Password** (eye button) before you save.
4. Optionally switch on **Enable voicemail** on the *Voicemail & notifications* tab.
5. Click **Create phone**, then apply the changes.
6. Configure the device as described below.

## Configure a SIP phone or softphone {#configure-device}

Enter these values in the account settings of the phone or softphone:

| Setting on the device | Value |
|---|---|
| Server, registrar, domain or proxy | The IP address (or host name) of the PBX. |
| User name, user ID, authentication user | The phone's **Number**, for example `101`. |
| Password | The phone's **Password**. |
| Display name | Anything; the PBX uses the **Caller ID name**. |
| Transport and port | UDP on port 5060. TCP (also port 5060) and TLS (port 5061) work when they are enabled under [*Advanced → SIP*]({{< relref "/advanced/sip.md" >}}). |
| Voicemail number | `000086` |

After the device registers, its status in the list changes to *registered*. Dial `00003246` (the echo test) to check audio in both directions.

> If the phone does not register, check the user name and password first, then the firewall: the SIP port may be limited to certain networks under [*Advanced → Firewall*]({{< relref "/advanced/firewall.md" >}}), and repeated wrong passwords can get a device's address banned for a while.

IAX phones are set up the same way: server = the PBX address, user name = the number, the password, port 4569 UDP.
