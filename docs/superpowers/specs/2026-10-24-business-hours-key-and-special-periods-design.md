# Business hours: override key with lamp, and special periods

Status: design, agreed in conversation on 2026-10-24; awaiting approval of this document.

## Intent

A company runs PhonixPBX with Snom phones. Every phone should have one function key that

- shows whether the company is currently **closed** ("out of office"): the lamp is lit while closed, dark while open, on all phones at the same time, and
- lets anybody **override** the business hours automatic with a single press, and return to the automatic with a second press.

The company also wants **special periods**: Christmas/New Year, summer company holidays, or an emergency routing that can be switched on by hand. While one applies, calls are routed completely differently (another IVR, other hours), without changing the normal weekly schedule. Special periods can be prepared in advance and switched on and off, also from a phone key.

All of this applies to the whole company (a business hours object), not to individual users. Per-user "do not disturb" is out of scope; Snom phones have their own DND key for that.

## Goals

1. A BLF function key on a Snom phone, pointed at the feature code of a business hours object (e.g. `*80`), shows the *effective* state of that object: lit = closed, dark = open. The lamp follows every level of the precedence below, changes within about a minute of a schedule boundary or date change, and immediately on a key press, a mode change or a special period being switched.
2. Pressing that key always inverts the lamp:
   - if no manual mode is active, it sets a **temporary override** to the opposite of the automatic state;
   - if a temporary override **or a permanent mode** (set in the UI/API/MCP) is active, it removes it, so the automatic applies again (agreed with the user);
   - **(my call)** if a permanent mode is active that equals the automatic state (e.g. permanent "closed" on a Friday evening), removing it alone would not change the lamp; the press removes it *and* sets a temporary override to the opposite state, so the lamp still inverts.
   An announcement tells the caller the result (closed / open / automatic).
3. A temporary override ends by itself at the **first change of the automatic state** after the press, i.e. as soon as the automatic state equals the overridden value (e.g. "closed" pressed at 15:00 ends at 17:00 when the schedule closes; callers notice nothing), and **always at midnight at the latest** (agreed with the user). A forgotten press therefore never keeps the office open over a weekend, a holiday or into a special period that starts the next day. When the applying special period points to business hours "B", a change of B's effective state is a change of the automatic state of the referring object (my call).
4. **Special periods** per business hours object, as an **ordered list** (agreed with the user). Each has a name, an **active** switch, an optional date range (from–to, whole days, inclusive; empty = "always"), an optional **yearly** repeat, an optional **feature code**, and a destination. A period applies when it is active and, if it has dates, today is within them. The **first** applying period in list order wins; overlaps are allowed and resolved by the order.
5. A special period's feature code toggles its active switch immediately (no apply), with an announcement (activated / deactivated), and has its own BLF lamp: lit = the period is switched on (agreed with the user; example: emergency routing).
6. The UI, REST API and MCP show the effective state and *why* (schedule, holiday, which special period, temporary override, permanent mode), and let the admin switch special periods on and off immediately.

## Non-goals

- No phone provisioning. Admins configure the Snom keys themselves (type BLF, number = feature code); the manual explains it.
- No per-user out-of-office.
- No separate "back to automatic" key: the second press is that (agreed with the user).
- The UI does not need a button to set a *temporary* override; the UI keeps its existing modes auto / open / closed (permanent).

## Anti-goals

- A forgotten press must not silently leave the company open (or closed) for days. That is why temporary overrides expire (goal 3).
- The lamp must not show something different from what callers experience. Routing and lamp are computed from the same rules; if they ever disagree, routing wins and the lamp catches up within a minute.
- A special period must never block the out-of-office key: the key sits above all special periods in the precedence (agreed with the user).
- Blinking lamps must not be used to encode state: on a Snom, pressing a blinking (ringing) BLF key performs a call pickup instead of dialling.

## Behaviour

### Precedence when a call arrives (and for the lamp) — agreed with the user

1. Permanent mode from UI/API/MCP (`open` / `closed`).
2. Temporary override from the out-of-office key (`open` / `closed`).
3. Special periods, in list order: the first one that is active and whose dates match today (or that has no dates) → its destination.
4. Holiday → closed.
5. Weekly ranges → open or closed.

"Automatic state" means levels 3–5.

When forced open (1 or 2) while a special period applies, calls go to the object's normal **open** destination, as on a normal working day; forced closed goes to the normal **closed** destination.

### Special period destination and its open/closed meaning

- A special period's destination may be any destination business hours already allow (phone, call group, application, conference, IVR, voicemail, hangup) **or another business hours object**.
- Destination is not business hours → the period counts as **closed** (out-of-office lamp lit).
- Destination is business hours "B" → the state is **B's effective state** (B's own mode, override, holidays and ranges). Example: "Christmas" hours open 09:00–12:00 → lamp dark in the morning, lit otherwise.

Today business hours may not point to business hours (`HoursType` in `phonix/services/destinations.py`, "no loops"). **Constraint (my call):** special periods may point to business hours, but only one level deep: the target must not have special periods itself, and an object with special periods cannot be used as such a target. This rules out loops and keeps the lamp computation simple. Validation errors use `ServiceError(fields=...)`.

### Walkthroughs (from the conversation)

- Summer holidays apply → lamp lit, calls go to the holiday IVR. Someone comes into the office and presses the out-of-office key → temporary override open, lamp dark, calls ring in the office. Leaving, they press again → override removed, holiday routing applies again, lamp lit. If they forget, the override ends at midnight.
- List: 1 "Emergency routing" (always, off), 2 "Christmas" (24.12.–02.01., yearly, on), 3 "Summer 2027" (dates, on). Someone presses the emergency key on 27 December → emergency routing is on (its lamp lit) and wins over Christmas. The out-of-office key still works above it.

## Current state (for orientation)

- Model: `BusinessHours`, `BusinessHoursRange`, `BusinessHoursHoliday` in `phonix/core/models.py`; service `phonix/services/hours.py` (`scheduled_open`, `status`, `live_status`, `get_mode`, `set_mode`).
- Live mode in AstDB `phonix-hours/<id>` = `open` | `closed` | absent (automatic); read and written over the AMI CLI `database get/put/del`. It is not part of backups.
- Dialplan (`phonix/generators/dialplan.py`): `business_hours()` builds `hours-<id>` / `hours-<id>-pub` contexts with `GotoIfTime()` and holiday date comparisons; the feature code (`internal` context) currently toggles closed ⇄ automatic and plays `activated` / `de-activated`.
- Hints exist only for phones (`internal` context, "device state hints"). Phones subscribe from `phone-<ext>`, which includes `internal`.
- `phonix-monitor` (`phonix/services/monitor.py`, OpenRC `system/openrc/init.d/phonix-monitor`, OCI `system/container/entrypoint`) is a long-running process blocked on AMI security events.
- Feature codes and extensions are unique across the system (service layer, `ensure_extension_free`).
- Config backup format `phonix-config` version 4 contains `business_hours`.

## Design decisions

1. **Hints:** for every business hours object with a feature code, `exten => <code>,hint,Custom:phonix-hours-<id>` in `internal` (`INUSE` = closed, `NOT_INUSE` = open). For every special period with a feature code, `exten => <code>,hint,Custom:phonix-special-<id>` (`INUSE` = switched on).
2. **Runtime state in AstDB**, so routing and keys work without the web app: the mode (existing), the temporary override, and the **active switch of each special period**. The encoding is the builder's choice; it must let both the dialplan and Python distinguish permanent from temporary and tell when a temporary override has expired (e.g. store the overridden value plus the date of the press: expired when the date is not today or the automatic state equals the value).
3. **Active switch: storage (my call).** Because a phone key flips it without an apply, the AstDB value is authoritative at runtime. It is also stored on the period in SQLite as the configured value, so it is part of backups and survives a restore: changes from the UI/API/MCP write both; a feature code press writes AstDB, and the background job copies changed AstDB values back into SQLite. Apply/startup writes SQLite → AstDB only for periods that have no AstDB entry yet (new periods, restored backups).
4. **Dialplan computes the automatic state itself.** Refactor `hours-<id>` so the automatic decision (special periods in order, holidays, ranges) is a reusable subroutine used by routing and by the out-of-office feature code, so a press sets the lamp immediately and correctly even exactly at a boundary. Routing honours temporary overrides and treats an expired one as absent even if the background job has not removed it yet.
5. **Background job** (minute loop) inside the `phonix monitor` process as a separate thread (my call; no new service, and the monitor already runs on the appliance and in the OCI image). For each business hours object it computes the effective state in Python (extend `status()`), removes expired temporary overrides, syncs active switches (decision 3), and sets the `Custom:` device states over AMI when they changed, once at start and after Asterisk restarts. The Python and dialplan rules must agree; tests run both against the same cases.
6. **Mode changes from UI/API/MCP** (`set_mode`) also clear any temporary override and update the device state immediately; switching a special period from UI/API/MCP does the same for its own and the object's lamp.
7. **Announcements:** existing Asterisk core sounds shipped on the image (builder picks; no new recordings): closed / open / automatic for the out-of-office key, activated / deactivated for a special period key.
8. **Status reasons** in `status()` / `live_status()` and the UI: `schedule`, `holiday`, `special` (with the period's name and, if dated, its end), `override` (temporary, with the state it reverts to), `forced` (permanent).
9. **Changed behaviour of the existing feature code** (previously closed ⇄ automatic) goes into `CHANGELOG.md` under *Changed*, written for administrators, with how to set up the Snom keys.

## Special periods: data and surfaces

- New model `BusinessHoursSpecial`: `name`, `position` (list order), `enabled`, `start` / `end` dates (both empty = always; inclusive), `yearly`, `feature_code` (optional, unique like other feature codes and extensions), `dest_type`, `dest_id`. Child of `BusinessHours` like holidays; Alembic revision; nested in `BusinessHoursIn` / `to_dict` like `holidays`, so REST CRUD and MCP tools (generated from `RESOURCES`) pick it up.
- A separate immediate endpoint/tool to switch a period on or off (like `PUT /business-hours/{id}/mode` and `set_business_hours_mode`), since the generic update would require an apply.
- Yearly periods may cross the new year (e.g. 24.12.–02.01.). Start and end must be both set or both empty.
- Deleting a destination object makes the period fall back to hangup (as with the existing fixed destinations in `destinations.py`); deleting business hours referenced by a period does the same.
- Config backup: add the periods to `business_hours`, bump `phonix-config` to version 5, and keep reading version 4. Periods that point to business hours are resolved in the existing second pass.
- Legacy export: no equivalent; reported as omitted together with business hours (as today).
- UI: the *Dialplan → Business Hours* form gets a "Special periods" section next to holidays, ordered with up/down controls like the IVR keys; the list page shows the current state and reason and has on/off toggles for the periods. The manual (de/en) explains special periods, the precedence and the Snom key setup.

## Left to the builder

- AstDB encoding of the temporary override and the active switches, and the dialplan subroutine structure.
- Thread details inside `phonix monitor`, reconnect handling.
- Exact sound files for the announcements.
- UI layout of the special periods editor (follow the holidays editor and the IVR key ordering).

## Project obligations

Alembic revision matching the models; golden files (`UPDATE_GOLDEN=1`); i18n update + all 11 catalogs; manual chapters de/en + built help; `CHANGELOG.md` (Added: out-of-office key with lamp, special periods with keys; Changed: feature code behaviour); `docs/SPEC.md` (data model, business hours feature, API/MCP, implementation notes, backup format version 5); Asterisk/SIPp integration test for the key toggles and device states.
