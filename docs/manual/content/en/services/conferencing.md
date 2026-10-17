---
title: "Conferencing"
weight: 30
description: "Conference rooms with optional PIN and admin PIN, reachable internally and from outside."
---
*Services → Conferencing* manages the conference rooms. A conference room is a number that several callers dial to talk together. Rooms can be protected with a PIN, and an admin PIN lets a moderator join with extra rights. A new installation has one room with the number `2663` ("CONF" on the keypad).

Changes to rooms become active after you apply them, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}). How callers use a conference is described for phone users under [Conferences]({{< relref "/phone-users/_index.md#conference" >}}).

## Room list {#list}

The list shows every room with its **Number**, **Name** and **Protection**:

- **PIN**: callers must enter a PIN.
- **admin PIN**: a moderator PIN is set.
- **open**: anyone who dials the number joins directly.
- The badge **public** next to the name means the room is reachable from outside.

Click **Conference room** above the list to add a room, the number or the pencil icon to edit one, and the trash icon to delete it. Deleting a room also removes incoming routes and IVR keys that led to it.

## Room settings {#edit}

| Field | Meaning | Default |
|---|---|---|
| Number | The internal number callers dial, 1–20 digits. It must not be used by a phone, call group or other object. | — |
| Name | Name of the room, shown in lists and destination selections. | — |
| PIN | Optional, digits only (up to 16). Callers must enter it to join. | empty |
| Admin PIN | Optional, digits only (up to 16). Entering it instead of the PIN joins as moderator. | empty |
| Reachable from outside | Callers from providers can reach the room directly by its number or public name (for example with a direct dial-in number). Without it, external callers only reach the room through an incoming route or IVR menu that points to it. | off |
| Public name | Optional alias used from outside instead of the number, e.g. `meeting` for `sip:meeting@pbx`. Letters, digits and `. _ + -`. Only shown with *Reachable from outside*. Empty: the room number. | empty |

How the PINs work when a caller joins:

- **Neither PIN set**: the caller joins at once.
- **PIN set**: the caller is asked for a PIN and finishes with `#`. The PIN joins as participant, the admin PIN as moderator.
- **Only the admin PIN set**: participants just press `#` without a PIN; the admin PIN joins as moderator.

After three wrong entries the call ends.

> A room without a PIN that is reachable from outside can be used by anyone who knows the number. Set a PIN for public rooms.

## In-call menu {#in-call-menu}

During a conference callers use the keypad:

| Key | Function |
|---|---|
| `*` | Play the menu announcement |
| `1` | Mute / unmute yourself |
| `4` / `6` | Listen quieter / louder |
| `7` / `9` | Speak quieter / louder |
| `8` | Leave the conference |
| `2` | Moderators only: lock / unlock the room |
| `3` | Moderators only: remove the last caller who joined |

A caller who is alone in a room hears music on hold and the number of participants is announced on joining. A room holds up to 50 participants.
