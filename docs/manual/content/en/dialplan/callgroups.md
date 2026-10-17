---
title: "Call Groups"
weight: 20
description: "Ring several phones at once or one after another under one number."
---
A call group rings several phones for one call, either all at the same time or one after another. Use it for a team number, a hotline or a reception that several people answer. Call groups are managed under *Dialplan → Call Groups*.

Changes take effect after you apply them, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

## Call group list {#list}

Click **Call group** above the list to add one. The list shows the **Number** (or `–` for groups without a number), the **Name** (with a *public* badge when the group is reachable from outside), the **Members** and the **Strategy** (*ring all* or *one after another*). The buttons at the end of each row edit and delete the group. Deleting a group also removes the incoming routes and IVR keys that led to it.

## Add or edit a call group {#edit}

| Field | Meaning | Default |
|---|---|---|
| Name | A name for lists and destination pickers, for example `Sales`. | – |
| Number | The internal number of the group (1–20 digits). Optional: a group without a number can still be the destination of an incoming route or an IVR key. | empty |
| Members | The phones in the group, at least one. For *One after another*, the phones ring in the order shown here. | – |
| Ring strategy | *Ring all at once*: all members ring together, the first to answer takes the call. *One after another*: the members ring in turn. | Ring all at once |
| Ring time (seconds) | *Ring all at once*: how long the group rings (5–600); empty rings until the caller hangs up. *One after another*: how long each phone rings before the next one; empty uses each phone's own ring time, or 20 seconds if the phone has none. | empty |
| Description | A note for your reference. | empty |
| Reachable from outside | Callers from providers may reach the group directly by its number. | off |
| Public name | With *Reachable from outside*: an alternative number or name for callers from outside. | empty |

Calls that nobody answers go to the voicemail box of the **first member**, if that phone has voicemail enabled; otherwise the call ends. The missed call e-mail of the first member is used for the group as well. Disabled phones are skipped.

### Set up a team number {#team-number}

1. Make sure every team member has a [phone]({{< relref "/accounts/phones.md" >}}).
2. Click **Call group**, enter a **Name** and a **Number**, and select the **Members**.
3. To have unanswered calls recorded, put a phone with voicemail first, and set a **Ring time** so the call reaches the mailbox.
4. Click **Create** and apply the changes.
5. To route an outside number to the team, add an [incoming route]({{< relref "/accounts/providers.md#incoming-routes" >}}) with the group as destination.

> Instead of a call group, you can also add several incoming routes with the same number and different phones on a provider; those phones then ring at the same time.
