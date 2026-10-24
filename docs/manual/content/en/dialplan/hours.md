---
title: "Business Hours"
weight: 40
description: "Route calls to one destination while open and to another while closed, with holidays, special periods, an out-of-office key and a manual switch."
---
Business hours send calls to one destination while you are open and to another one while you are closed, for example to the reception during the day and to an after-hours IVR menu or a voicemail box at night. They follow a weekly schedule, a list of holidays and optional special periods such as company holidays or an emergency routing, and can be switched to open or closed by hand or with a key on the phones. Business hours are managed under *Dialplan → Business Hours*.

Business hours have no internal number of their own. Use them as the destination of a provider's [incoming route]({{< relref "/accounts/providers.md#incoming-routes" >}}) or of an [IVR key]({{< relref "/dialplan/ivr.md#keys" >}}). Changes to the schedule and destinations take effect after you apply them, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}); the [mode](#mode), the [out-of-office key](#key) and the switches of the [special periods](#specials) take effect immediately.

## Business hours list {#list}

Click **Business hours** above the list to add a schedule. The list shows:

| Column | Meaning |
|---|---|
| Name | The name and description. Click it to edit. |
| Now | *open now* or *closed now* and why: *switched manually* (permanent mode), *switched by key until the next change* (out-of-office key), the name of the applying special period (with its last day, if it has dates) or of today's holiday. Below it, one switch per special period, see [Special periods](#specials). |
| When open | The destination while open. |
| When closed | The destination while closed. |
| Feature code | The code of the [out-of-office key](#key), or `–`. |

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

### Special periods {#specials}

Special periods route calls completely differently for a while, without touching the weekly hours: Christmas and New Year, the summer company holidays, or an emergency routing that you switch on by hand. They take precedence over holidays and the weekly hours. Click **Add special period** and fill in one row per period:

| Field | Meaning |
|---|---|
| Name | For example `Christmas` or `Emergency`. |
| Destination | Where calls go while the period applies: any destination of business hours, and also **other business hours**, for example shorter opening hours over Christmas. Then those decide between open and closed. |
| on | Only for a new period: whether it starts switched on. Saved periods are switched on and off at the top of the page. |
| First day, Last day | Optional. The period applies only from the first to the last day (whole days, both included). Enter both or neither; without days, a period applies whenever it is on, for example an emergency routing. |
| every year | Repeats the days every year. The period may cross the new year, for example 24 December to 2 January. |
| Feature code | Optional, for example `*32`. Dialled on an internal phone, it switches the period on or off; a phone key (BLF) on it is lit while the period is on, see [Phone keys](#key). |

A period **applies** when it is switched on and, if it has days, today is one of them. The **first** applying period in the list wins, so overlapping periods are allowed: put the more important one higher. Change the order with the arrows or by dragging the handle at the start of the row. The **x** button removes a period. Up to 50 periods can be listed.

Business hours used as the destination of a special period must not have special periods of their own, and business hours with special periods cannot be such a destination.

### Routing {#routing}

| Field | Meaning | Default |
|---|---|---|
| Name | A name for lists and destination pickers. | – |
| Description | A note for your reference. | empty |
| When open | Where calls go during the opening hours. | Hang up |
| When closed | Where calls go outside the opening hours and on holidays. | Hang up |
| Feature code | Optional code, for example `*31`, of the [out-of-office key](#key). Digits, `*` and `#`; it must not be used by another number and must not start with the call pickup code (`*8` by default). | empty |

Both destinations can be a phone, call group, conference room, application, IVR menu, voicemail box or *Hang up*, but not other business hours (only a [special period](#specials) can lead to other business hours). See [Destinations]({{< relref "/dialplan/ivr.md#destinations" >}}).

## Switch between open and closed {#mode}

On a saved schedule, the box at the top shows whether you are open **Right now** and lets you choose the **Mode**:

| Mode | Behaviour |
|---|---|
| Automatic | Follows the special periods, holidays and opening hours. |
| Open | Open until switched back, for example for a special event. |
| Closed | Closed until switched back, for example when the office closes early. |

Click **Switch now** to change it. The mode **takes effect immediately, without applying the configuration**, and survives a restart. Asterisk must be running; otherwise the mode is unknown and cannot be changed.

Switching the mode also ends a temporary switch made with the [out-of-office key](#key).

If special periods are configured, the box also has one switch per period under **Special periods**. A click switches the period on or off immediately, without applying the configuration. A period that is on applies only on its days, if it has any; the tooltip says *On, applies today*, *On, but not today* or *Off*. The same switches are on the list page.

> The mode and the out-of-office key are runtime state and are not part of a backup. Restoring a backup (or importing a configuration) sets all business hours back to **Automatic** and ends every out-of-office key state; special periods are switched on or off as they were saved in the backup.

## Which rule applies {#precedence}

When a call arrives, and for the lamp of the out-of-office key, the first matching rule decides:

1. The **mode** *Open* or *Closed* set on this page, with the REST API or MCP.
2. A temporary switch with the **out-of-office key**.
3. The first **special period** in the list that is on and whose days include today: calls go to its destination.
4. A **holiday**: closed.
5. The **weekly opening hours**: open or closed.

Rules 3 to 5 together are *Automatic*. While a special period applies, *Open* (by mode or key) sends calls to the normal **When open** destination as on a normal working day, and *Closed* to **When closed**. A special period whose destination is not business hours counts as closed; one that leads to other business hours is open or closed as those are.

## Out-of-office key {#key}

With the **Feature code** of the business hours, every phone can get an out-of-office key: its lamp shows the state for everybody, and a press switches it.

- The lamp is **lit while closed** and dark while open, whatever the reason: opening hours, holiday, special period, key or mode. It follows the schedule within about a minute and changes immediately on a press.
- A press always switches to the **opposite** state, for example to open the office during the company holidays or to close it early. You hear "enabled" (now open) or "disabled" (now closed).
- This switch is **temporary**: it ends by itself at the next change of the automatic state, at midnight at the latest. "Closed" pressed at 15:00 ends at 17:00 when the office closes anyway; a forgotten press never keeps the office open over a weekend or holiday.
- Pressed again while the switch is active, the key returns to *Automatic* ("cancelled"). It also ends a mode set on this page; if that mode equals the automatic state, the key switches to the opposite instead, so the lamp always changes.

The **Feature code** of a special period works the same way for that period: a press switches it on ("activated") or off ("de-activated"), and its lamp is **lit while the period is switched on**, for example for an emergency routing. A period that is on but not due today keeps its lamp lit.

The lamps are kept up to date by the PBX's monitor service; after a restart of Asterisk they are correct again within a minute.

### Set up the keys on Snom phones {#snom}

1. Open the phone's web interface and go to **Function Keys**.
2. Choose a free key, set its **Type** to **BLF** and enter the feature code as **Number**, for example `*31` for the out-of-office key or `*32` for a special period.
3. Use the account (identity) that is registered with PhonixPBX as context, and save.

Phone users find the key described under [Using your phone]({{< relref "/phone-users/_index.md#business-hours" >}}).

### Route calls outside office hours {#example}

1. Create an IVR menu or choose a phone with voicemail for the time you are closed.
2. Add business hours, set the weekly ranges and holidays, and choose **When open** (for example the reception call group) and **When closed** (the after-hours menu).
3. Click **Create** and apply the changes.
4. Set the business hours as the destination of your number's [incoming route]({{< relref "/accounts/providers.md#incoming-routes" >}}).

### Company holidays and emergency routing {#example-specials}

1. Create the destinations, for example a holiday IVR menu and business hours `Christmas` that are open 09:00–12:00.
2. In your main business hours, add the special periods in this order:
   - `Emergency`: destination the emergency phone, no days, feature code `*32`.
   - `Christmas`: destination the business hours `Christmas`, 24 December to 2 January, **every year**, **on**.
   - `Summer 2027`: destination the holiday menu, with its dates, **on**.
3. Save and apply. Over Christmas, calls follow the shorter hours; pressing the `*32` key switches the emergency routing on, which wins over Christmas because it is first in the list. The out-of-office key still works above both.
