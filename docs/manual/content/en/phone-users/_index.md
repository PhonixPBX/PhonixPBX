---
title: "Using your phone"
weight: 20
icon: phone-call
description: "Dial codes for phone users: transfer, pickup, parking, voicemail, call forwarding, conferences and test numbers."
---
This chapter is for everyone who makes calls with a phone connected to PhonixPBX, whether a desk phone or a softphone app. It lists the codes you can dial and what they do. You do not need access to the web interface.

> The codes below are the defaults. Your administrator may have changed them under *Dialplan → Transfers & Parking* and *Dialplan → Applications*, or switched some of them off. If a code does not work, ask your administrator.

To dial an **internal number**, simply dial the extension of the other phone, for example `21`. How you reach outside numbers (for example with a leading `0`) depends on the setup of your PBX.

## Overview of all codes {#codes}

| Code | What it does | When |
|---|---|---|
| `**` + number | Attended transfer: talk to the other person first, then hand over the call | during a call |
| `##` + number | Blind transfer: hand over the call immediately | during a call |
| `*0` | Disconnect: end the call | during a call |
| `*8` | Pick up a call that is ringing at another phone | phone idle |
| `*8` + extension | Pick up a call that is ringing at that extension | phone idle |
| `700` | Park a call (transfer it to `700`) | during a call |
| `701` … `720` | Take back a parked call | phone idle |
| `000086` | Voicemail: listen to your messages, record greetings | phone idle |
| `000023` | Call forwarding on or off | phone idle |
| `2663` | Default conference room | phone idle |
| set by the administrator | Out-of-office key: switch business hours to the opposite state, or back to *Automatic*; switch a special period on or off | phone idle |
| `000063` | Read back your own extension | test |
| `000047` | Read back the IP address of the PBX | test |
| `00003246` | Echo test | test |
| `000064554` | Test tone (1000 Hz) | test |

Many codes spell a word on the phone keypad: `000086` = 0000**VM**, `000023` = 0000**CF**, `2663` = **CONF**, `00003246` = 0000**ECHO**.

## Transferring calls {#transfer}

You can transfer any call that you are in. Callers from outside cannot use these codes; only you, on the internal phone, can.

**Attended transfer (`**`)** – you speak to the new person before handing over the call:

1. During the call, press `**`. The caller is put on hold.
2. Dial the number you want to transfer to. The PBX starts dialling about three seconds after your last digit.
3. Talk to the person who answers.
4. Hang up. The two are now connected.

If the other person does not answer within 15 seconds, you are connected back to the caller.

**Blind transfer (`##`)** – you hand over the call without speaking to the new person:

1. During the call, press `##`.
2. Dial the number. About three seconds after your last digit the call is transferred and you are disconnected.

A short beep confirms the transfer; an error tone means it did not work, for example because the number does not exist.

**Disconnect (`*0`)** – press `*0` during a call to end it, just like hanging up. In a call between two internal phones either side can use it; in a call with an outside party only you, on the internal phone, can.

Most desk phones and softphones also have a *Transfer* key of their own. It works with PhonixPBX as well and is often easier to use.

## Picking up calls for others {#pickup}

When a colleague's phone is ringing and nobody answers, you can take the call at your own phone:

- Dial `*8` to pick up a call that is ringing at any phone.
- Dial `*8` followed by an extension to pick up a call that is ringing at exactly that phone, for example `*821` for extension 21.

## Parking calls {#parking}

Parking puts a call "on hold for everyone": anybody can take it back from any phone. This is useful when the person you want is somewhere else in the building.

1. During the call, transfer it to `700` – preferably with an attended transfer, `**700`. The PBX announces the number of the parking slot, for example "701". Hang up.
2. Tell your colleague the slot number (for example over the loudspeaker).
3. Your colleague dials the slot number, `701` to `720`, from any phone and is connected to the caller.

The caller hears music while waiting. If nobody takes the call back within 45 seconds, it rings again at the phone that parked it.

## Voicemail {#voicemail}

If your administrator has enabled voicemail for your phone, callers can leave a message when you do not answer, are busy or your phone is not reachable.

**Listening to messages:** dial `000086` from your own phone and enter your **voicemail PIN**, followed by `#`. Your administrator gives you the PIN. The voice menu then guides you; the most important keys are:

| Key | Function |
|---|---|
| `1` | Listen to new messages |
| `5` / `4` / `6` | Repeat the message / previous / next message |
| `7` | Delete the message |
| `9` | Save the message to a folder |
| `0` | Mailbox options: record greetings, change the PIN |
| `*` | Help |
| `#` | Exit |

**Greetings:** under the mailbox options (`0`) you can record your own greetings:

- `1` – the **unavailable** greeting, played when you do not answer or your phone is not reachable,
- `2` – the **busy** greeting, played when you are on the phone,
- `3` – your name,
- `5` – change your PIN.

Without your own recording, callers hear a standard greeting with your extension number. If your administrator has uploaded a common greeting for the whole company, it replaces your unavailable greeting.

**Voicemail by e-mail:** your administrator can have each new message sent to your e-mail address, usually with the recording attached. Depending on the setup, messages that were e-mailed are also kept on the PBX or deleted from it. You may also receive an e-mail for calls you missed.

## Call forwarding {#forwarding}

Call forwarding sends all calls for your extension to another number, for example to your mobile phone.

**Switch on:** dial `000023`. After the announcement and the beep, dial the number you want to forward to – internal or external, exactly as you would dial it from your phone. The PBX reads the number back and says "thank you". Calls to your extension now go straight to that number.

**Switch off:** dial `000023` again. Three short tones confirm that forwarding is off.

If you dial nothing after the beep, you hear "invalid" and nothing changes.

## Conferences {#conference}

In a conference room several people talk together. Every participant dials the number of the room; callers from outside can join too if your administrator has made the room reachable from outside.

- The default room is `2663`. Your administrator may have set up more rooms with other numbers.
- If the room has a **PIN**, you are asked for it when you join. Enter it and press `#`. After three wrong attempts the call ends.
- Some rooms have an **admin PIN**. With it you join as moderator and get additional keys.
- While you are alone in the room, you hear music. The PBX announces how many people are in the room when you join.

Keys during the conference (press `*` first to hear the menu, or press the key directly):

| Key | Function | Who |
|---|---|---|
| `1` | Mute / unmute your microphone | everyone |
| `4` / `6` | Listen more quietly / louder | everyone |
| `7` / `9` | Talk more quietly / louder | everyone |
| `8` | Leave the conference | everyone |
| `2` | Lock / unlock the room (nobody else can join) | moderator |
| `3` | Remove the participant who joined last | moderator |

## Business hours {#business-hours}

Your administrator can define business hours: during opening hours calls go, for example, to the reception; outside them to an announcement or voicemail. For each set of business hours, the administrator can also define a **feature code**, usually set up as an **out-of-office key** on your phone. Its lamp is lit while the office is closed and dark while it is open.

- Press the key (or dial the code): the business hours switch to the opposite state – for example closed when you leave early, or open when you are in the office during the company holidays. You hear "disabled" (now closed) or "enabled" (now open).
- Press it again: they return to **Automatic** and follow the schedule again. You hear "cancelled".
- If you forget, the switch ends by itself at the next scheduled change, at midnight at the latest.

Your administrator may also set up keys for **special periods**, for example an emergency routing. Such a key switches the period on ("activated") or off ("de-activated"); its lamp is lit while the period is on.

The change takes effect immediately for all callers and all phones. Ask your administrator for the codes.

## Test numbers {#tests}

These numbers help to check a phone and the connection:

| Number | What you hear |
|---|---|
| `000063` | Your own extension number, read back repeatedly. Shows that the phone is registered with the right account. |
| `000047` | The IP address of the PBX, read back digit group by digit group. |
| `00003246` | Echo test: everything you say is played back to you. Use it to judge delay and audio quality. |
| `000064554` | A constant 1000 Hz tone. Use it to check the audio path for dropouts. |

Hang up to end the test.
