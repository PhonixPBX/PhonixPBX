---
title: "Transfers & Parking"
weight: 50
description: "Feature codes for transferring, picking up and ending calls, the call parking numbers and how numbers with a leading + are dialled."
---
*Dialplan → Transfers & Parking* sets the feature codes that phone users dial during a call to transfer it or end it, the code for picking up a ringing phone, the numbers used to park calls, and what a leading `+` in a dialled number is replaced with. The codes are typed on the phone's keypad, so they work on every phone, independent of its own transfer buttons.

Click **Save** to store the settings. They take effect after you apply them, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}). How users dial the codes is described in [Using your phone]({{< relref "/phone-users/_index.md#transfer" >}}).

## Feature codes {#feature-codes}

Feature codes are 1–8 characters of digits, `*` and `#`.

| Field | Meaning | Default |
|---|---|---|
| Attended transfer | Dialled during a call: puts the other party on hold, dial a number, talk to the person you call, then hang up to hand the call over. | `**` |
| Blind transfer | Dialled during a call: dial a number and the call is handed over at once, without talking first. | `##` |
| Call pickup | Dialled alone, picks up any ringing phone. Followed by a number, for example `*8101`, picks up the call ringing at that phone. | `*8` |
| Disconnect | Dialled during a call: ends the call. | `*0` |
| Feature digit timeout (ms) | How long the PBX waits between the digits of a feature code. | 1000 |
| Transfer digit timeout (s) | How long the PBX waits for the next digit of the transfer destination before it dials. | 3 |
| Attended transfer no-answer timeout (s) | How long the transfer destination rings during an attended transfer before the call returns. | 15 |

The person who answered a call can always transfer it. The caller can transfer only when they are an internal phone; callers from outside cannot use the feature codes. The same applies to *Disconnect*: between two internal phones either side can end the call, in calls with an outside party only the internal phone.

> Feature codes are sent as key presses during the call. If they do not work, check the *DTMF mode* of the [phone]({{< relref "/accounts/phones.md#advanced" >}}).

## Call parking {#parking}

Parking puts a call on hold in a numbered slot, so that it can be picked up from any phone.

| Field | Meaning | Default |
|---|---|---|
| Parking number | Transfer a call to this number to park it. The PBX announces the slot the call was parked in. | `700` |
| First slot | The first parking slot number. | `701` |
| Last slot | The last parking slot number. | `720` |
| Parking time (s) | How long a call stays parked (5–3600). After that, it rings back at the phone that parked it. | 45 |

To park a call, transfer it (for example with **Blind transfer**, `##700`) to the parking number and note the slot the PBX announces. To pick it up, dial the slot number from any phone. The parked caller hears music on hold.

The parking number and the slots are reserved: phones, call groups and other objects cannot use these numbers.

## Numbers with + {#plus}

Phones, address books and call lists often show numbers in the international form, for example `+41 44 123 45 67`. A dial pattern cannot match the `+` (it separates the prefix to add, see [Dial patterns]({{< relref "/accounts/providers.md#dial-patterns" >}})). So the PBX first replaces a leading `+` and then dials the number again: internal numbers first, then the dial patterns. This also applies to click-to-call and to call forwarding to such numbers.

The setting is in the card **Numbers with +**:

| Field | Meaning | Default |
|---|---|---|
| Replace a leading + with | What a leading `+` becomes. Empty: numbers with `+` are not dialled. | `00` |

| Setup | Value | The phone dials | Dialled again as |
|---|---|---|---|
| International prefix `00` (most of Europe) | `00` | `+41441234567` | `0041441234567` |
| With an outside line prefix `0` (patterns like `0\|00X.`) | `000` | `+41441234567` | `00041441234567` |
| North America | `011` | `+41441234567` | `01141441234567` |
