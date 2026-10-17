---
title: "Applications"
weight: 10
description: "Small dialplan programs reachable by a number, including the built-in test and service numbers."
---
An application is a short piece of Asterisk dialplan that runs when someone dials its number. PhonixPBX ships a set of applications for testing and for phone features, and you can add your own, for example an announcement or a time service. Applications are managed under *Dialplan → Applications*.

Changes take effect after you apply them, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

## Application list {#list}

Click **Application** above the list to add one. The list shows the **Number**, **Name**, **Description** and **Status** (enabled or disabled, and *public* when it is reachable from outside). The buttons at the end of each row edit and delete the application. Deleting an application also removes the incoming routes and IVR keys that led to it.

New installations come with these applications:

| Number | Name | What it does |
|---|---|---|
| `000063` | Read extension number | Reads back the number of the calling phone (0000**ME**). |
| `000047` | Read IP | Reads back the IP address of the PBX (0000**IP**). |
| `00003246` | Echo | Plays back what you say, to test audio and delay (0000**ECHO**). |
| `000064554` | Milliwatt | A constant 1000 Hz tone to test line quality (0000**MILLI**). |
| `000086` | Voicemail system | Opens the voicemail box of the calling phone (0000**VM**). |
| `000023` | Call forwarding | Switches call forwarding of the calling phone on and off (0000**CF**). |
| `00009327357` | Weasels | A test announcement (0000**WEASELS**). |

The numbers spell the name on a phone keypad. You can change or delete them like your own applications. How phone users use them is described in [Using your phone]({{< relref "/phone-users/_index.md#codes" >}}).

## Add or edit an application {#edit}

| Field | Meaning | Default |
|---|---|---|
| Number | The number that starts the application: digits, or an Asterisk pattern such as `_0XX.` (`X`, `N`, `Z`, `[]`, `.`, `!`). It must not be used by anything else. | – |
| Name | A name for lists and destination pickers. | – |
| Description | A note, shown in the list and in the printed overview. | empty |
| Application logic | The dialplan, one step per line (see below). | – |
| Enabled | Disabled applications are left out of the configuration. | on |
| Reachable from outside | Callers from providers may reach the application directly by its number. | off |
| Public name | With *Reachable from outside*: an alternative number or name for callers from outside. | empty |

### Application logic {#logic}

Each line is one dialplan step in the form `priority,Application(arguments)`:

- The priority is a number (`1`, `2`, …) or `n` for "the next one". A label can follow in brackets, for example `3(retry),Playback(beep)`, and `Goto(retry)` jumps there.
- The first step needs priority `1`, otherwise Asterisk does not find the number.
- `include => context` lines include another dialplan context.
- Lines starting with `;` are comments and are ignored.

Example — play an announcement and hang up:

```
1,Answer()
n,Playback(hello-world)
n,Hangup()
```

The dialled number is available as `${EXTEN}`. When the application is reached as the destination of an incoming route, an IVR key or business hours, `${EXTEN}` is `s`. The [Asterisk documentation](https://docs.asterisk.org/) lists the available dialplan applications and functions.

> PhonixPBX checks only the form of each line; the application logic is passed to Asterisk as written. Test the number after applying.
