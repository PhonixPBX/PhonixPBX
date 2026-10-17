---
title: "Overview (print)"
weight: 60
description: "A printable list of all internal numbers, feature codes and provider routes."
---
*Dialplan → Overview (print)* collects the numbering plan of the PBX on one page, for example to hang up next to the reception or to check for gaps before adding numbers. Click **Print** to print it; the menu bars are left out of the printout.

The page shows the configuration as it is saved, including changes that have not been applied yet.

## Internal numbers {#internal-numbers}

All phones, call groups with a number, conference rooms and applications, sorted by number:

| Column | Meaning |
|---|---|
| Number | The internal number. |
| Type | *Phone (SIP)*, *Phone (IAX)*, *Phone (external)*, *Call group*, *Conference* or *Application*. |
| Name | The caller ID name of a phone, or the name of the object. |
| Details | The description of a phone or application, the member numbers of a call group, or *PIN protected* for a conference room. |
| Public | *yes* (or the public name) when the number is reachable from outside. |

IVR menus and business hours are not part of this list; see [*Dialplan → IVR Menus*]({{< relref "/dialplan/ivr.md#list" >}}) and [*Dialplan → Business Hours*]({{< relref "/dialplan/hours.md#list" >}}).

## Feature codes {#feature-codes}

The codes for attended and blind transfer, call pickup and disconnect, and the call parking number with its slots, as set under [*Dialplan → Transfers & Parking*]({{< relref "/dialplan/transfers.md" >}}).

## Providers {#providers}

For every provider, the outgoing [dial patterns]({{< relref "/accounts/providers.md#dial-patterns" >}}) and the [incoming routes]({{< relref "/accounts/providers.md#incoming-routes" >}}) as *pattern → destination* (*all* for routes without a pattern).
