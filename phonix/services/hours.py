# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Business hours: route calls to one destination while open and another while closed.

The schedule (weekly time ranges and holidays) is configuration. The live mode
(automatic, forced open, forced closed) is runtime state in the Asterisk database
(``phonix-hours/<id>``), so the feature code and the UI switch it immediately,
without an apply, and it survives restarts like call forwarding.
"""

from __future__ import annotations

import calendar
import datetime as dt
import logging
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix import ami
from phonix.core import settings as st
from phonix.core import validation as v
from phonix.core.models import BusinessHours, BusinessHoursHoliday, BusinessHoursRange, BusinessHoursSpecial
from phonix.generators.dialplan import HOURS_DB, OVERRIDE_DB, SPECIAL_DB, hours_device, special_device
from phonix.i18n import N_, _
from phonix.services import destinations as dst
from phonix.services.common import NotFound, ServiceError, audit, diff_dicts, ensure_extension_free, mark_dirty

log = logging.getLogger(__name__)

ASTDB_FAMILY = HOURS_DB
MODES = ("auto", "open", "closed")
WEEKDAYS = (N_("Monday"), N_("Tuesday"), N_("Wednesday"), N_("Thursday"), N_("Friday"), N_("Saturday"), N_("Sunday"))
MONTHS = (
    N_("January"),
    N_("February"),
    N_("March"),
    N_("April"),
    N_("May"),
    N_("June"),
    N_("July"),
    N_("August"),
    N_("September"),
    N_("October"),
    N_("November"),
    N_("December"),
)
_TIME = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


def _minutes(value: str) -> int:
    return 24 * 60 if value == "24:00" else int(value[:2]) * 60 + int(value[3:])


class RangeIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    weekday: int = Field(ge=0, le=6)
    start: str
    # exclusive; "24:00" = until midnight
    end: str

    @field_validator("start", "end")
    @classmethod
    def _time(cls, value: str) -> str:
        value = value.strip()
        if len(value) == 4 and value[1] == ":":
            value = "0" + value
        if not _TIME.match(value) and value != "24:00":
            raise ValueError(_("Enter a time as HH:MM"))
        return value

    @model_validator(mode="after")
    def _order(self) -> RangeIn:
        if self.start == "24:00" or _minutes(self.start) >= _minutes(self.end):
            raise ValueError(_("The end must be after the start"))
        return self


class HolidayIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: dt.date
    name: str = Field(default="", max_length=80)
    yearly: bool = False

    _name = field_validator("name")(lambda cls, x: v.config_value(x, N_("Name")))


class SpecialIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str
    enabled: bool = False
    start: dt.date | None = None
    end: dt.date | None = None
    yearly: bool = False
    feature_code: str = ""
    dest_type: dst.SpecialType
    dest_id: int | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = v.config_value(value, N_("Name"))
        if not value:
            raise ValueError(_("Name is required"))
        return value

    _dest = field_validator("dest_type", mode="before")(lambda cls, x: dst.required(x))

    @field_validator("feature_code")
    @classmethod
    def _code(cls, value: str) -> str:
        return v.feature_code(value) if value.strip() else ""

    @model_validator(mode="after")
    def _period(self) -> SpecialIn:
        if (self.start is None) != (self.end is None):
            raise ValueError(_("Enter both the first and the last day, or neither"))
        if self.start is None:
            self.yearly = False  # "every year" only means something with dates
        if self.start and self.end and self.start > self.end and not self.yearly:
            raise ValueError(_("The last day must not be before the first day"))
        return self


class BusinessHoursIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    feature_code: str = ""
    open_dest_type: dst.HoursType
    open_dest_id: int | None = None
    closed_dest_type: dst.HoursType = "hangup"
    closed_dest_id: int | None = None
    ranges: list[RangeIn] = Field(default_factory=list, max_length=70)
    holidays: list[HolidayIn] = Field(default_factory=list, max_length=200)
    specials: list[SpecialIn] = Field(default_factory=list, max_length=50)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = v.config_value(value, N_("Name"))
        if not value:
            raise ValueError(_("Name is required"))
        return value

    _dests = field_validator("open_dest_type", "closed_dest_type", mode="before")(lambda cls, x: dst.required(x))
    _desc = field_validator("description")(lambda cls, x: v.no_control(x.strip(), N_("Description")))

    @field_validator("feature_code")
    @classmethod
    def _code(cls, value: str) -> str:
        return v.feature_code(value) if value.strip() else ""


def list_hours(session: Session) -> list[BusinessHours]:
    return list(session.scalars(select(BusinessHours).order_by(BusinessHours.name, BusinessHours.id)))


def get_hours(session: Session, hours_id: int) -> BusinessHours:
    hours = session.get(BusinessHours, hours_id)
    if hours is None:
        raise NotFound(_("Business hours not found"))
    return hours


def to_dict(h: BusinessHours) -> dict[str, Any]:
    return {
        "id": h.id,
        "name": h.name,
        "description": h.description,
        "feature_code": h.feature_code or "",
        "open_dest_type": h.open_dest_type,
        "open_dest_id": h.open_dest_id,
        "closed_dest_type": h.closed_dest_type,
        "closed_dest_id": h.closed_dest_id,
        "ranges": [{"weekday": r.weekday, "start": r.start, "end": r.end} for r in h.ranges],
        "holidays": [{"date": r.date.isoformat(), "name": r.name, "yearly": r.yearly} for r in h.holidays],
        "specials": [
            {
                "id": sp.id,
                "name": sp.name,
                "enabled": sp.enabled,
                "start": sp.start.isoformat() if sp.start else None,
                "end": sp.end.isoformat() if sp.end else None,
                "yearly": sp.yearly,
                "feature_code": sp.feature_code or "",
                "dest_type": sp.dest_type,
                "dest_id": sp.dest_id,
            }
            for sp in h.specials
        ],
    }


def defaults() -> dict[str, Any]:
    """A new schedule: Monday to Friday 08:00-12:00 and 13:00-17:00."""
    ranges = [
        {"weekday": day, "start": start, "end": end}
        for day in range(5)
        for start, end in (("08:00", "12:00"), ("13:00", "17:00"))
    ]
    return {"open_dest_type": "hangup", "closed_dest_type": "hangup", "ranges": ranges, "holidays": [], "specials": []}


def _check_specials(session: Session, data: BusinessHoursIn, own_id: int | None) -> None:
    """Special periods: destinations, unique feature codes and the one-level rule."""
    if data.specials and own_id is not None:
        referenced_by = session.scalar(
            select(BusinessHoursSpecial.id).where(
                BusinessHoursSpecial.dest_type == "hours", BusinessHoursSpecial.dest_id == own_id
            )
        )
        if referenced_by is not None:
            raise ServiceError(
                fields={"specials": _("Business hours used by a special period cannot have special periods")}
            )
    pickup = st.load(session, st.FeatureSettings).pickup
    own_ids = {sp.id for sp in get_hours(session, own_id).specials} if own_id is not None else set[int]()
    codes: dict[str, int] = {data.feature_code: -1} if data.feature_code else {}
    for idx, sp in enumerate(data.specials):
        dst.check(session, sp.dest_type, sp.dest_id, f"specials.{idx}.dest")
        if sp.dest_type == "hours":
            target = get_hours(session, sp.dest_id) if sp.dest_id is not None else None
            if target is not None and (target.id == own_id or target.specials):
                raise ServiceError(
                    fields={f"specials.{idx}.dest": _("Choose business hours without special periods of their own")}
                )
        if not sp.feature_code:
            continue
        field = f"specials.{idx}.feature_code"
        if sp.feature_code in codes:
            raise ServiceError(fields={field: _("This code is used more than once")})
        codes[sp.feature_code] = idx
        own = (BusinessHoursSpecial, sp.id) if sp.id in own_ids and sp.id is not None else None
        ensure_extension_free(session, sp.feature_code, field, own=own)
        if sp.feature_code.startswith(pickup):
            raise ServiceError(fields={field: _("Codes starting with %(code)s are used for call pickup", code=pickup)})


def _check(session: Session, data: BusinessHoursIn, own_id: int | None) -> None:
    if data.feature_code:
        ensure_extension_free(
            session, data.feature_code, "feature_code", own=(BusinessHours, own_id) if own_id else None
        )
        pickup = st.load(session, st.FeatureSettings).pickup
        if data.feature_code.startswith(pickup):
            raise ServiceError(
                fields={"feature_code": _("Codes starting with %(code)s are used for call pickup", code=pickup)}
            )
    _check_specials(session, data, own_id)
    dst.check(session, data.open_dest_type, data.open_dest_id, "open_dest")
    dst.check(session, data.closed_dest_type, data.closed_dest_id, "closed_dest")
    seen: set[tuple[dt.date, bool]] = set()
    for idx, h in enumerate(data.holidays):
        if (h.date, h.yearly) in seen:
            raise ServiceError(fields={f"holidays.{idx}": _("This day is listed more than once")})
        seen.add((h.date, h.yearly))


def _apply(hours: BusinessHours, data: BusinessHoursIn) -> None:
    hours.name = data.name
    hours.description = data.description
    hours.feature_code = data.feature_code or None
    hours.open_dest_type = data.open_dest_type
    hours.open_dest_id = None if data.open_dest_type in dst.ACTIONS else data.open_dest_id
    hours.closed_dest_type = data.closed_dest_type
    hours.closed_dest_id = None if data.closed_dest_type in dst.ACTIONS else data.closed_dest_id
    ranges = sorted({(r.weekday, r.start, r.end) for r in data.ranges})
    hours.ranges = [BusinessHoursRange(weekday=d, start=s, end=e) for d, s, e in ranges]
    hours.holidays = [BusinessHoursHoliday(date=h.date, name=h.name, yearly=h.yearly) for h in data.holidays]
    # periods are updated in place by id (they carry runtime state elsewhere); unknown ids are new
    existing = {sp.id: sp for sp in hours.specials}
    specials: list[BusinessHoursSpecial] = []
    for position, item in enumerate(data.specials):
        sp = existing.pop(item.id, None) if item.id is not None else None
        if sp is None:
            sp = BusinessHoursSpecial()
        sp.position = position
        sp.name = item.name
        sp.enabled = item.enabled
        sp.start = item.start
        sp.end = item.end
        sp.yearly = item.yearly
        sp.feature_code = item.feature_code or None
        sp.dest_type = item.dest_type
        sp.dest_id = None if item.dest_type in dst.ACTIONS else item.dest_id
        specials.append(sp)
    hours.specials = specials


def create_hours(session: Session, data: BusinessHoursIn, user: str = "") -> BusinessHours:
    _check(session, data, None)
    hours = BusinessHours()
    _apply(hours, data)
    session.add(hours)
    session.flush()
    audit(session, user, "create", "hours", hours.id, hours.name)
    mark_dirty(session, "dialplan")
    return hours


def update_hours(session: Session, hours_id: int, data: BusinessHoursIn, user: str = "") -> BusinessHours:
    hours = get_hours(session, hours_id)
    _check(session, data, hours.id)
    before = to_dict(hours)
    _apply(hours, data)
    session.flush()
    audit(session, user, "update", "hours", hours.id, hours.name, diff_dicts(before, to_dict(hours)))
    mark_dirty(session, "dialplan")
    was = {sp["id"]: sp["enabled"] for sp in before["specials"]}
    _forget_runtime(specials=set(was) - {sp.id for sp in hours.specials})
    _push_special_state(session, [sp for sp in hours.specials if was.get(sp.id) != sp.enabled])
    return hours


def _push_special_state(session: Session, changed: list[BusinessHoursSpecial]) -> None:
    """Write switches changed in the form to the Asterisk database and refresh the lamps.

    Only changed switches are written, so saving a form opened before a phone switched a
    period does not undo that. Best effort: the monitor reconciles when Asterisk is down.
    """
    if not changed:
        return
    try:
        with ami.AmiClient(timeout=3.0) as client:
            for sp in changed:
                client.command(f"database put {SPECIAL_DB} {sp.id} {int(sp.enabled)}")
            refresh_lamps(session, client, read_runtime(client), dt.datetime.now())
    except (ami.AmiError, OSError):
        pass


def _forget_runtime(hours: Collection[int] = (), specials: Collection[int] = ()) -> None:
    """Remove the runtime state of deleted business hours and periods, so a reused id starts clean.

    Best effort: the minute sync removes entries of unknown ids when Asterisk is down now.
    """
    commands = [f"database del {family} {i}" for i in hours for family in (ASTDB_FAMILY, OVERRIDE_DB)]
    commands += [f"database del {SPECIAL_DB} {i}" for i in specials]
    if not commands:
        return
    try:
        with ami.AmiClient(timeout=3.0) as client:
            for command in commands:
                client.command(command)
    except (ami.AmiError, OSError):
        pass


def delete_hours(session: Session, hours_id: int, user: str = "") -> None:
    hours = get_hours(session, hours_id)
    audit(session, user, "delete", "hours", hours.id, hours.name)
    dst.forget(session, "hours", hours.id)
    specials = [sp.id for sp in hours.specials]
    session.delete(hours)
    session.flush()
    mark_dirty(session, "dialplan")
    _forget_runtime(hours=[hours_id], specials=specials)


def reset_runtime(session: Session) -> None:
    """After a restore or import: drop all runtime state and switch the periods as configured.

    The database ids start again at 1, so permanent modes, overrides and switches of the
    replaced configuration would otherwise attach to the restored objects. Best effort: a
    restore never fails because Asterisk is not running.
    """
    try:
        with ami.AmiClient(timeout=3.0) as client:
            for family in (ASTDB_FAMILY, OVERRIDE_DB, SPECIAL_DB):
                client.command(f"database deltree {family}")
            for h in list_hours(session):
                for sp in h.specials:
                    client.command(f"database put {SPECIAL_DB} {sp.id} {int(sp.enabled)}")
            refresh_lamps(session, client, read_runtime(client), dt.datetime.now())
    except (ami.AmiError, OSError) as exc:
        log.warning("business hours: runtime state not reset, Asterisk unavailable (%s)", exc)


# --- schedule and live mode -------------------------------------------------------------


def holiday_on(hours: BusinessHours, day: dt.date) -> BusinessHoursHoliday | None:
    for h in hours.holidays:
        if h.date == day or (h.yearly and (h.date.month, h.date.day) == (day.month, day.day)):
            return h
    return None


def scheduled_open(hours: BusinessHours, now: dt.datetime) -> bool:
    """Open by the weekly ranges and holidays (``now`` in the system time zone)."""
    if holiday_on(hours, now.date()) is not None:
        return False
    minute = now.hour * 60 + now.minute
    return any(r.weekday == now.weekday() and _minutes(r.start) <= minute < _minutes(r.end) for r in hours.ranges)


@dataclass
class Runtime:
    """Runtime state from the Asterisk database: permanent modes, temporary overrides, special switches."""

    modes: dict[int, str] = field(default_factory=dict)
    overrides: dict[int, tuple[str, dt.date]] = field(default_factory=dict)
    active: dict[int, bool] = field(default_factory=dict)


def parse_override(value: str) -> tuple[str, dt.date] | None:
    """An override value ``<open|closed>:<YYYY-MM-DD>`` (the state and the day of the press)."""
    state, _sep, day = value.strip().partition(":")
    if state not in ("open", "closed"):
        return None
    try:
        return state, dt.date.fromisoformat(day)
    except ValueError:
        return None


def _astdb_family(client: ami.AmiClient, family: str) -> dict[int, str]:
    """Numeric keys and values of one Asterisk database family."""
    out = client.command(f"database show {family}")
    pattern = re.compile(rf"^/{re.escape(family)}/(\d+)\s*:\s*(.*?)\s*$")
    return {int(m[1]): m[2] for line in out.splitlines() if (m := pattern.match(line.strip()))}


def read_runtime(client: ami.AmiClient) -> Runtime:
    modes = {k: x for k, x in _astdb_family(client, ASTDB_FAMILY).items() if x in ("open", "closed")}
    overrides = {k: o for k, x in _astdb_family(client, OVERRIDE_DB).items() if (o := parse_override(x))}
    active = {k: x == "1" for k, x in _astdb_family(client, SPECIAL_DB).items() if x in ("0", "1")}
    return Runtime(modes=modes, overrides=overrides, active=active)


def load_runtime() -> Runtime | None:
    """The runtime state, or ``None`` when Asterisk cannot be asked."""
    try:
        with ami.AmiClient(timeout=3.0) as client:
            return read_runtime(client)
    except (ami.AmiError, OSError):
        return None


def special_on(p: BusinessHoursSpecial, rt: Runtime) -> bool:
    """The runtime switch of a period; the configured value until Asterisk has one."""
    return rt.active.get(p.id, p.enabled)


def _month_day(day: dt.date) -> tuple[int, int]:
    return day.month, day.day


def special_matches(p: BusinessHoursSpecial, day: dt.date) -> bool:
    """Whether the period's dates include ``day`` (always without dates; yearly may cross the new year)."""
    if p.start is None or p.end is None:
        return True
    if not p.yearly:
        return p.start <= day <= p.end
    start, end, md = _month_day(p.start), _month_day(p.end), _month_day(day)
    if start <= end:
        return start <= md <= end
    return md >= start or md <= end


def _occurrence_end(p: BusinessHoursSpecial, day: dt.date) -> dt.date | None:
    """The last day of the occurrence of a matching period that includes ``day``."""
    if p.start is None or p.end is None:
        return None
    if not p.yearly:
        return p.end
    year = day.year
    if _month_day(p.start) > _month_day(p.end) and _month_day(day) >= _month_day(p.start):
        year += 1
    try:
        return p.end.replace(year=year)
    except ValueError:  # 29 February in a common year
        return dt.date(year, 2, 28)


def automatic(
    hours: BusinessHours, rt: Runtime, now: dt.datetime, others: Mapping[int, BusinessHours]
) -> dict[str, Any]:
    """The automatic state: the first applying special period, then holidays, then the weekly ranges.

    A period pointing to other business hours takes their effective state (closed when they are
    unknown); any other destination counts as closed.
    """
    out: dict[str, Any] = {"holiday": None, "special": None, "special_id": None, "until": None}
    day = now.date()
    for p in hours.specials:
        if not (special_on(p, rt) and special_matches(p, day)):
            continue
        is_open = False
        if p.dest_type == "hours":
            target = others.get(p.dest_id) if p.dest_id is not None else None
            # one level deep: the target's own special periods are not followed
            if target is not None and target.id != hours.id:
                is_open = status(target, rt, now, {})["open"]
        out.update(special=p.name, special_id=p.id, until=_occurrence_end(p, day))
        return {"open": is_open, "reason": "special", **out}
    holiday = holiday_on(hours, day)
    if holiday is not None:
        return {"open": False, "reason": "holiday", **out, "holiday": holiday.name}
    return {"open": scheduled_open(hours, now), "reason": "schedule", **out}


def day_plan(hours: BusinessHours, rt: Runtime, day: dt.date) -> dict[str, Any]:
    """What applies on ``day`` by plan, ignoring manual modes and overrides: ``kind`` is ``special``
    (with the period's name and position), ``holiday``, ``open`` (weekly hours on that weekday) or ``closed``."""
    for idx, p in enumerate(hours.specials):
        if special_on(p, rt) and special_matches(p, day):
            return {"date": day, "kind": "special", "name": p.name, "special": idx}
    holiday = holiday_on(hours, day)
    if holiday is not None:
        return {"date": day, "kind": "holiday", "name": holiday.name, "special": None}
    kind = "open" if any(r.weekday == day.weekday() for r in hours.ranges) else "closed"
    return {"date": day, "kind": kind, "name": "", "special": None}


def year_plan(hours: BusinessHours, rt: Runtime, today: dt.date, count: int = 12) -> list[dict[str, Any]]:
    """``count`` months from the month of ``today``: per month the weeks (Monday first) of ``day_plan()``
    entries, ``None`` for the days outside the month."""
    months = []
    year, month = today.year, today.month
    for _i in range(count):
        weeks = [
            [day_plan(hours, rt, dt.date(year, month, d)) if d else None for d in week]
            for week in calendar.monthcalendar(year, month)
        ]
        months.append({"year": year, "month": month, "weeks": weeks})
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def get_mode(hours_id: int) -> str | None:
    """The live mode, or ``None`` when Asterisk cannot be asked."""
    try:
        with ami.AmiClient(timeout=3.0) as client:
            out = client.command(f"database get {ASTDB_FAMILY} {hours_id}")
    except (ami.AmiError, OSError):
        return None
    value = out.split("Value:", 1)[1].strip() if "Value:" in out else ""
    return value if value in ("open", "closed") else "auto"


def refresh_lamps(session: Session, client: ami.AmiClient, rt: Runtime, now: dt.datetime) -> None:
    """Set the phone lamps: ``INUSE`` = closed / switched on, ``NOT_INUSE`` = open / switched off."""
    all_hours = list_hours(session)
    others = {h.id: h for h in all_hours}
    for h in all_hours:
        if h.feature_code:
            lamp = "NOT_INUSE" if status(h, rt, now, others)["open"] else "INUSE"
            client.command(f"devstate change {hours_device(h.id)} {lamp}")
        for sp in h.specials:
            if sp.feature_code:
                lamp = "INUSE" if special_on(sp, rt) else "NOT_INUSE"
                client.command(f"devstate change {special_device(sp.id)} {lamp}")


def set_mode(session: Session, hours_id: int, mode: str, user: str = "") -> str:
    hours = get_hours(session, hours_id)
    if mode not in MODES:
        raise ServiceError(fields={"mode": _("Invalid choice")})
    command = (
        f"database del {ASTDB_FAMILY} {hours.id}"
        if mode == "auto"
        else f"database put {ASTDB_FAMILY} {hours.id} {mode}"
    )
    try:
        with ami.AmiClient(timeout=3.0) as client:
            client.command(command)
            # a permanent mode replaces a temporary override
            client.command(f"database del {OVERRIDE_DB} {hours.id}")
            refresh_lamps(session, client, read_runtime(client), dt.datetime.now())
    except (ami.AmiError, OSError) as exc:
        raise ServiceError(_("Asterisk is not running, the mode cannot be changed: %(error)s", error=str(exc))) from exc
    audit(session, user, "mode", "hours", hours.id, f"{hours.name}: {mode}")
    return mode


def set_special_active(session: Session, hours_id: int, special_id: int, active: bool, user: str = "") -> bool:
    """Switch a special period on or off immediately (runtime state, no apply)."""
    hours = get_hours(session, hours_id)
    special = next((sp for sp in hours.specials if sp.id == special_id), None)
    if special is None:
        raise NotFound(_("Special period not found"))
    try:
        with ami.AmiClient(timeout=3.0) as client:
            client.command(f"database put {SPECIAL_DB} {special.id} {int(active)}")
            refresh_lamps(session, client, read_runtime(client), dt.datetime.now())
    except (ami.AmiError, OSError) as exc:
        raise ServiceError(_("Asterisk is not running, the mode cannot be changed: %(error)s", error=str(exc))) from exc
    special.enabled = active
    audit(session, user, "special", "hours", hours.id, f"{hours.name}/{special.name}: {'on' if active else 'off'}")
    return active


def status(hours: BusinessHours, rt: Runtime, now: dt.datetime, others: Mapping[int, BusinessHours]) -> dict[str, Any]:
    """The effective state: permanent mode, then a temporary override, then :func:`automatic`.

    ``reason`` is ``forced`` (permanent mode), ``override`` (temporary, ``reverts_to`` is the
    automatic state it gives way to) or the automatic reason. Expired overrides are ignored.
    """
    out: dict[str, Any] = {**automatic(hours, rt, now, others), "override": None, "reverts_to": None}
    mode = rt.modes.get(hours.id)
    if mode in ("open", "closed"):
        out.update(open=mode == "open", reason="forced")
        return out
    override = rt.overrides.get(hours.id)
    # ends at midnight, or as soon as the automatic state reaches the overridden value
    if override is not None and override[1] == now.date() and (override[0] == "open") != out["open"]:
        out.update(open=override[0] == "open", reason="override", override=override[0], reverts_to=out["open"])
    return out


def live_status(session: Session, hours_id: int, now: dt.datetime | None = None) -> dict[str, Any]:
    """Mode and open/closed right now; ``mode`` is ``None`` when Asterisk is not reachable.

    ``specials`` lists the special periods: ``active`` is the on/off switch, ``applies`` whether
    it is on and its dates match today (the first such period wins, see ``special_id``).
    """
    hours = get_hours(session, hours_id)
    now = now or dt.datetime.now()
    loaded = load_runtime()
    rt = loaded or Runtime()
    mode = None if loaded is None else rt.modes.get(hours.id, "auto")
    others = {h.id: h for h in list_hours(session)}
    return {
        "id": hours.id,
        "name": hours.name,
        "mode": mode,
        **status(hours, rt, now, others),
        "specials": special_states(hours, rt, now.date()),
    }


def special_states(hours: BusinessHours, rt: Runtime, day: dt.date) -> list[dict[str, Any]]:
    """The special periods with their switch (``active``) and whether they apply on ``day``."""
    return [
        {
            "id": sp.id,
            "name": sp.name,
            "active": special_on(sp, rt),
            "applies": special_on(sp, rt) and special_matches(sp, day),
            "feature_code": sp.feature_code or "",
        }
        for sp in hours.specials
    ]


Mode = Literal["auto", "open", "closed"]
