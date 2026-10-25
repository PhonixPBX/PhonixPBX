---
title: "Providers"
weight: 20
description: "SIP and IAX trunks: registration, dial patterns for outgoing calls, incoming routes, caller ID and failover."
---
A provider is an account at a VoIP provider or a SIP trunk, or another PBX reached over SIP or IAX. It carries the calls between the PBX and the outside world. Providers are managed under *Accounts → Providers*.

Outgoing calls are routed by the provider's [dial patterns](#dial-patterns), incoming calls by its [incoming routes](#incoming-routes). Changes take effect after you apply them, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

## Provider list {#list}

Click **SIP provider** or **IAX provider** above the list to add a provider. The list shows:

| Column | Meaning |
|---|---|
| Name | Your name for the provider. Click it to edit. A *disabled* badge marks disabled providers. |
| Type | SIP or IAX. |
| Status | Whether the provider is registered right now, for example *Registered* or *Rejected*. For a provider without registration it shows whether it can be reached, for an IAX provider the state of the trunk. *not loaded* means the configuration with this provider is not applied yet, *Asterisk down* that Asterisk is not running. The column is updated every 15 seconds; disabled providers show a dash. |
| Host | Host name or address, with the port if one is set. |
| Username | The account user name. |
| Dial patterns | The outgoing patterns, or *none* (then the provider is not used for outgoing calls). |
| Incoming | The number of incoming routes. |

The buttons at the end of each row edit, disable/enable and delete the provider. A disabled provider does not register and is not used for calls. Deleting a provider also disables the [external phones]({{< relref "/accounts/phones.md#types" >}}) that dialled through it.

The same states, together with the phones and the active calls, are shown under [*Status → Calls & Registrations*]({{< relref "/status/calls.md" >}}).

## Add or edit a provider {#edit}

Your provider's documentation or customer portal lists the values you need: the server (host), your user name and password, and sometimes a separate authentication user or a required *From* domain. The form has four tabs.

### Account {#account}

| Field | Meaning | Default |
|---|---|---|
| Name | Your name for the provider, shown in lists and pickers. | – |
| Host | Host name or IP address of the provider's server, for example `sip.provider.example`. | – |
| Port | Port of the server. Empty uses the default: for SIP the host name is looked up via DNS SRV first if *Use DNS SRV lookups* is on under [Advanced → SIP]({{< relref "/advanced/sip.md#timers" >}}), otherwise 5060 (5061 for TLS); 4569 for IAX. | empty |
| Transport | SIP only: UDP, TCP or TLS. Choosing TCP or TLS also enables that transport on the PBX. | UDP |
| Username | Your account user name at the provider. | – |
| Password | The account password. When editing, leave it empty to keep the stored one. | – |
| Register with the provider | The PBX registers with the provider so that incoming calls reach it. Switch it off for providers that authenticate by IP address. | on |
| Authentication user | SIP only. Only if the provider gives you an authentication name that differs from the user name. | the user name |
| From user | SIP only. The user part of the *From* header of outgoing calls. | the user name |
| From domain | SIP only. The domain of the *From* header. | the host |
| Authentication | IAX only: MD5, Plain text or RSA. | MD5 |

### Outgoing calls {#outgoing}

| Field | Meaning | Default |
|---|---|---|
| Dial patterns | One pattern per line. A phone dialling a number that matches a pattern places the call through this provider. See [Dial patterns](#dial-patterns). | empty |
| Failover provider | Another provider that takes the call when this one is unavailable or congested. See [Failover](#failover). | none |
| Outgoing caller ID | *use the phone's caller ID* or *fixed caller ID*. | use the phone's caller ID |
| Fixed caller ID | With *fixed caller ID*: the caller ID sent on every call through this provider, for example `Company <4930123456>`. | – |

A phone can override the caller ID per provider and can be blocked from using a provider, see [Outgoing calls]({{< relref "/accounts/phones.md#outgoing" >}}) in the phone settings. Many providers only accept or show caller IDs that belong to your account.

### Incoming calls {#incoming}

| Field | Meaning | Default |
|---|---|---|
| Routes | Pairs of an incoming number pattern and a destination. See [Incoming routes](#incoming-routes). | none |
| Public number | Your main number at this provider. Informational only. | empty |
| Incoming caller ID | Changes the caller ID of incoming calls: *unchanged*, *replace name with number*, *replace with text* or *prepend text to name* (for example `Hotline` to see which line was called). | unchanged |
| Caller ID text | The text for *replace with text* and *prepend text to name*. | – |

### Codecs & advanced {#advanced}

| Field | Meaning | Default |
|---|---|---|
| Codecs | Codecs offered to the provider, in order of preference (drag to reorder). Use what the provider supports; G.711 (alaw in Europe, ulaw in North America) works almost everywhere. | alaw, ulaw, g722 |
| Language | Language of the announcements callers from this provider hear. | English |
| DTMF mode | *RFC 4733 (RFC 2833)*, *In-band*, *SIP INFO* or *Auto*. | RFC 4733 |
| Qualify interval (s) | How often the PBX checks that the provider is reachable (0–3600, 0 = off). | 60 |
| Provider is reached through NAT (symmetric RTP) | Sends audio back to the address it came from. | on |
| Additional options | Advanced: one `key=value` per line, appended to the generated endpoint (SIP) or peer (IAX). | empty |

## Dial patterns {#dial-patterns}

A dial pattern decides which numbers dialled on a phone leave the PBX through this provider, and how the number is changed before it is sent. The syntax is:

```
[prefix to add+][prefix to strip|]pattern
```

The pattern itself uses the Asterisk pattern characters:

| Character | Matches |
|---|---|
| `0`–`9`, `*`, `#` | Exactly this character |
| `X` | Any digit 0–9 |
| `Z` | Any digit 1–9 |
| `N` | Any digit 2–9 |
| `[1-5]`, `[13]` | One digit from the range or list |
| `.` | One or more further characters |
| `!` | Zero or more further characters |

The digits before `|` belong to the pattern but are removed before dialling. The digits before `+` are put in front of the number. Each of `|` and `+` may appear only once.

| Pattern | The phone dials | Sent to the provider |
|---|---|---|
| `X.` | `0301234567` | `0301234567` (unchanged) |
| `0\|X.` | `0 0301234567` | `0301234567` (outside line `0` removed) |
| `49+0\|X.` | `0301234567` | `49301234567` (leading `0` replaced with `49`) |
| `112` | `112` | `112` (emergency number only) |
| `0\|[1-9]XXX.` | `0 1701234567` | `1701234567` |
| `0\|00X.` | `0 0041441234567` | `0041441234567` (international calls) |

Tips:

- A typical setup uses an outside line prefix: `0|X.` on the main provider sends everything that starts with `0` there.
- When several patterns (of one or several providers) match a number, the most specific pattern wins, so `0|00X.` for international calls beats `0|X.`.
- The same pattern cannot be used by two providers; the form reports which provider already has it. Use the [failover provider](#failover) for a backup route instead.
- Always add the emergency numbers (for example `112`, `110`, `911`) if phones dial them without a prefix.
- Patterns must not overlap with internal numbers that should stay internal. Internal numbers are checked first when a phone dials.
- Numbers dialled with a leading `+` are matched after the `+` has been replaced, see [*Dialplan → Transfers & Parking*]({{< relref "/dialplan/transfers.md#plus" >}}).

## Incoming routes {#incoming-routes}

Incoming routes decide where a call from this provider goes, based on the number that was called (the DID). Click **Add route** to add a row with a pattern and a destination:

| Pattern | Matches |
|---|---|
| empty (*all numbers*) | Every incoming call. Use it if you have one number, or as a fallback. |
| `4930123456` | Exactly this number. |
| `49301234XX` | A pattern, with the same characters as dial patterns (no `\|` and no `+`). |

The destination can be a phone, a [call group]({{< relref "/dialplan/callgroups.md" >}}), a conference room, an [application]({{< relref "/dialplan/applications.md" >}}), an [IVR menu]({{< relref "/dialplan/ivr.md" >}}) or [business hours]({{< relref "/dialplan/hours.md" >}}), see [Destinations]({{< relref "/dialplan/ivr.md#destinations" >}}).

- Several routes with the same pattern and phones as destinations ring those phones at the same time.
- If no route matches, the called number is looked up among the objects that are *reachable from outside* (public direct dial): if it equals the number or public name of such a phone, call group, application, conference room or IVR menu, the call goes there.
- Some providers always send your account user name instead of the dialled number. A route with an empty pattern catches these calls too.

### Route an incoming number to an IVR menu {#route-to-ivr}

1. Create the menu under [*Dialplan → IVR Menus*]({{< relref "/dialplan/ivr.md#edit" >}}).
2. Open the provider, tab *Incoming calls*, click **Add route**.
3. Enter the number (or leave the pattern empty for all numbers) and choose the menu as destination.
4. Save and apply the changes.

To answer with a different menu outside office hours, route the number to [business hours]({{< relref "/dialplan/hours.md" >}}) instead, with one menu as *When open* and another as *When closed*.

## Failover {#failover}

If a call through this provider fails because the provider is unavailable or congested, the PBX tries the **Failover provider**. The failover provider must be enabled and have a dial pattern that matches the dialled number; its own pattern rules (strip and add prefixes) are applied. A busy line or a call that is not answered is not retried.

## Several accounts at one provider {#multiple-accounts}

You can add several SIP accounts with the same host, for example one per number. The PBX tells incoming calls apart by the account user name, so each account's incoming routes apply to its own calls.
