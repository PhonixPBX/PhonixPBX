---
title: "IVR Menus"
weight: 30
description: "Auto attendant menus: an announcement, then one destination per key."
---
An IVR menu (auto attendant) answers a call, plays an announcement such as "For sales, press 1. For support, press 2." and sends the caller wherever the pressed key leads. Menus can lead to other menus, so you can build a menu tree. IVR menus are managed under *Dialplan → IVR Menus*.

A menu is reached by its internal number, as the destination of a provider's [incoming route]({{< relref "/accounts/providers.md#incoming-routes" >}}), from an IVR key of another menu or from [business hours]({{< relref "/dialplan/hours.md" >}}). Changes take effect after you apply them, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

## IVR menu list {#list}

Click **IVR menu** above the list to add one. The list shows:

| Column | Meaning |
|---|---|
| Number | The internal number, or `–` for menus that are only used as a destination. |
| Name | The name, a *public* badge when the menu is reachable from outside, and the description. |
| Keys | The keys that have an option. Point at a key to see its label or destination. |
| No key pressed | Where the call goes when the caller presses nothing. |
| Status | Enabled or disabled. |

The buttons at the end of each row edit, disable/enable and delete the menu. A disabled menu is left out of the configuration; calls that would reach it end. Deleting a menu removes the incoming routes and IVR keys that led to it; other menus and business hours that used it for *no key* or *closed* fall back to *Hang up*.

## Create or edit an IVR menu {#edit}

The edit page has the key options and the announcement on the left and the settings on the right. Once a menu is saved, the page also shows its [call flow](#call-flow) and a [test call](#test-call).

### Key options {#keys}

Click **Add option** for each key the caller may press. Each option has:

- **Key**: `0`–`9`, `*` or `#`. Each key can be used once per menu.
- **Label**: optional, for example `Sales`. It is used in the recording script and in the call flow.
- **Destination**: where the key leads, see [Destinations](#destinations). Besides phones, groups and so on, a key can lead to a voicemail box, *Repeat the menu* or *Hang up*.

Drag an option by its handle, or use the arrow buttons, to change the order. The order is the order in which the options should be announced; it is used by **Write from options**. The **x** button removes an option.

### Announcement {#announcement}

The announcement is played when the call reaches the menu. Callers can press a key while it plays. Choose the **Source**:

- **Uploaded audio**: choose a file under **Announcement**, or drop an audio file (WAV, MP3, OGG or FLAC, up to 16 MB) on the upload area. The file is converted to 8 kHz mono, which is what telephones use, and can be played in the browser. Uploaded announcements are also listed under [*Services → Media*]({{< relref "/services/media.md" >}}).
- **Built-in sound**: an Asterisk sound in the prompt language of the system, for example `welcome`. You can also type the name of another installed sound.

> If the system cannot convert other formats, only PCM WAV files are accepted; the error message shows how to convert a file with `sox`.

The **Recording script** helps you record a matching announcement. **Write from options** fills it from the key options in their order, in the prompt language of the system, for example "For Sales, press 1. For Support, press 2.". Edit the text if you like, **Copy** it, record it with any recording app and upload the file. The script itself is never played.

### Settings {#settings}

| Field | Meaning | Default |
|---|---|---|
| Name | A name for lists and destination pickers. | – |
| Number | Optional internal number (1–20 digits) to call the menu directly. Menus can also be used only as destinations. | empty |
| Description | A note for your reference. | empty |
| Reachable from outside | Callers from providers may reach the menu directly by its number. | off |
| Public name | With *Reachable from outside*: an alternative number or name for callers from outside. | empty |
| Wait for a key (s) | How long the menu waits for a key after the announcement (1–60). | 5 |
| Repeat the menu | How many times the announcement is repeated when no key is pressed (0–9). | 2 |
| When no key is pressed | Where the call goes after the last repetition without a key. Any [destination](#destinations) except *Repeat the menu*, and not the menu itself. | Hang up |
| When an unknown key is pressed | Where the call goes when the caller presses a key without an option. *Repeat the menu* says that the option is invalid and plays the menu again; this counts as one of the repetitions. | Repeat the menu |
| Callers may dial extensions directly | Callers can dial an internal number during the announcement instead of a key. Callers from outside reach only numbers that are reachable from outside. | off |
| Enabled | Disabled menus are left out of the configuration. | on |

With the defaults, a caller who presses nothing hears the announcement three times (once plus two repetitions), waiting 5 seconds after each, and is then hung up.

> Callers from outside never get the transfer feature codes in calls that come through a menu, and with direct dialling they reach only public numbers. Internal callers can dial every internal number.

### Call flow {#call-flow}

Below a saved menu, **Call flow** shows the menu as it was saved, as a tree: each key with its label and destination. Sub-menus are expanded up to three levels, with an **Edit** link; a key that leads back to a menu already on the path is shown as "back to …".

### Test call {#test-call}

**Test call** rings a phone and connects it to the menu once it is answered, as if the phone had dialled the menu. Choose the phone under **Ring phone** and click **Call me**. Only enabled SIP and IAX phones can be chosen.

The test call uses the menu **as it was last applied**: apply your changes first.

### Build a simple menu {#example}

1. Upload or choose an announcement (or create the options first, use **Write from options** and record the script).
2. Add option `1` → call group *Sales*, option `2` → call group *Support*, option `0` → the reception phone.
3. Set **When no key is pressed** to the reception phone so that callers who do not press a key are still answered.
4. Click **Create**, apply the changes and use **Test call** to listen to it.
5. Route your number to the menu with an [incoming route]({{< relref "/accounts/providers.md#route-to-ivr" >}}).

## Destinations {#destinations}

Incoming routes, IVR keys and business hours all choose a destination from the same picker. Which types are available depends on where you choose:

| Destination | What happens | Incoming route | IVR key / unknown key | No key pressed | Business hours |
|---|---|---|---|---|---|
| Phones | Rings the phone, with its ring time, voicemail and call forwarding. | yes | yes | yes | yes |
| Call groups | Rings the [call group]({{< relref "/dialplan/callgroups.md" >}}). | yes | yes | yes | yes |
| Conference rooms | Joins the [conference room]({{< relref "/services/conferencing.md" >}}), asking for the PIN if it has one. | yes | yes | yes | yes |
| Applications | Runs the [application]({{< relref "/dialplan/applications.md" >}}). | yes | yes | yes | yes |
| IVR menus | Plays another menu. | yes | yes | yes | yes |
| Business hours | Continues by [business hours]({{< relref "/dialplan/hours.md" >}}). | yes | yes | yes | no |
| Voicemail | Takes the caller straight to the voicemail box of a phone, without ringing it. Only phones with voicemail are listed. | no | yes | yes | yes |
| Repeat the menu | Plays the menu again. | no | yes | no | no |
| Hang up | Ends the call. | no | yes | yes | yes |

Disabled phones, applications and menus are not reached: a call to them ends. When an object is deleted, routes and keys that led to it are removed, and fixed destinations fall back to *Hang up* (*Repeat the menu* for an unknown key).
