---
title: "Business Hours"
weight: 40
description: "Route calls to one destination while open and to another while closed, with holidays and a manual switch."
---
Business hours send calls to one destination while you are open and to another one while you are closed, for example to the reception during the day and to an after-hours IVR menu or a voicemail box at night. They follow a weekly schedule and a list of holidays, and can be switched to open or closed by hand. Business hours are managed under *Dialplan → Business Hours*.

Business hours have no internal number of their own. Use them as the destination of a provider's [incoming route]({{< relref "/accounts/providers.md#incoming-routes" >}}) or of an [IVR key]({{< relref "/dialplan/ivr.md#keys" >}}). Changes to the schedule and destinations take effect after you apply them, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}); the [mode](#mode) switches immediately.

## Business hours list {#list}

Click **Business hours** above the list to add a schedule. The list shows:

| Column | Meaning |
|---|---|
| Name | The name and description. Click it to edit. |
| Now | *open now* or *closed now*, with *switched manually* when the mode is forced, or the name of today's holiday. |
| When open | The destination while open. |
| When closed | The destination while closed. |
| Feature code | The code that switches the mode from a phone, or `–`. |

The buttons at the end of each row edit and delete the schedule. Deleting it removes the incoming routes and IVR keys that led to it.

## Create or edit business hours {#edit}

### Weekly opening hours {#weekly}

Each weekday has its own time ranges. Click **Add time range** to add one; a day can have several ranges, for example `08:00`–`12:00` and `13:00`–`17:00` for a lunch break. A day without ranges is *Closed all day*. The **x** button removes a range.

- The times are in the time zone of the system, see [*System → General Setup*]({{< relref "/system/general.md#time" >}}).
- The end is the first minute you are closed: `08:00`–`17:00` is open until 16:59.
- An end of `23:59` means until midnight.
- The end must be after the start. A range over midnight is entered as two ranges on two days.

New business hours start with Monday to Friday, 08:00–12:00 and 13:00–17:00. **Week at a glance** shows the open times as green bars; on a saved schedule, a line marks the current time.

### Holidays and closing days {#holidays}

On the days listed here you are closed all day, whatever the weekly hours say. Click **Add day** and enter the **Date** and an optional **Name**, for example `Christmas Day`. With **every year** the day repeats on the same date every year. Days that move every year, like Easter, are entered once per year. Up to 200 days can be listed.

### Routing {#routing}

| Field | Meaning | Default |
|---|---|---|
| Name | A name for lists and destination pickers. | – |
| Description | A note for your reference. | empty |
| When open | Where calls go during the opening hours. | Hang up |
| When closed | Where calls go outside the opening hours and on holidays. | Hang up |
| Feature code | Optional code, for example `*31`, that switches between *Automatic* and *Closed* when dialled on an internal phone. Digits, `*` and `#`; it must not be used by another number and must not start with the call pickup code (`*8` by default). | empty |

Both destinations can be a phone, call group, conference room, application, IVR menu, voicemail box or *Hang up*, but not other business hours. See [Destinations]({{< relref "/dialplan/ivr.md#destinations" >}}).

## Switch between open and closed {#mode}

On a saved schedule, the box at the top shows whether you are open **Right now** and lets you choose the **Mode**:

| Mode | Behaviour |
|---|---|
| Automatic | Follows the weekly opening hours and holidays. |
| Open | Open until switched back, for example for a special event. |
| Closed | Closed until switched back, for example when the office closes early. |

Click **Switch now** to change it. The mode **takes effect immediately, without applying the configuration**, and survives a restart. Asterisk must be running; otherwise the mode is unknown and cannot be changed.

Phone users can switch the mode with the **Feature code**: dialling it once switches to *Closed* (the PBX says "activated"), dialling it again returns to *Automatic* ("de-activated"). If the mode was *Open*, the code switches to *Automatic*. See also [Using your phone]({{< relref "/phone-users/_index.md#business-hours" >}}).

> The mode is runtime state and is not part of a backup. A forced mode can be lost when a backup is restored; check the mode afterwards.

### Route calls outside office hours {#example}

1. Create an IVR menu or choose a phone with voicemail for the time you are closed.
2. Add business hours, set the weekly ranges and holidays, and choose **When open** (for example the reception call group) and **When closed** (the after-hours menu).
3. Click **Create** and apply the changes.
4. Set the business hours as the destination of your number's [incoming route]({{< relref "/accounts/providers.md#incoming-routes" >}}).
