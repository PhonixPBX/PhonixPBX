# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Business hours: route calls to one destination while open and another while closed.

The schedule (weekly time ranges and holidays) is configuration. The live mode
(automatic, forced open, forced closed) is runtime state in the Asterisk database
(``phonix-hours/<id>``), so the feature code and the UI switch it immediately,
without an apply, and it survives restarts like call forwarding.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix import ami
from phonix.core import settings as st
from phonix.core import validation as v
from phonix.core.models import BusinessHours, BusinessHoursHoliday, BusinessHoursRange
from phonix.generators.dialplan import HOURS_DB
from phonix.i18n import N_, _
from phonix.services import destinations as dst
from phonix.services.common import NotFound, ServiceError, audit, diff_dicts, ensure_extension_free, mark_dirty

ASTDB_FAMILY = HOURS_DB
MODES = ("auto", "open", "closed")
WEEKDAYS = (N_("Monday"), N_("Tuesday"), N_("Wednesday"), N_("Thursday"), N_("Friday"), N_("Saturday"), N_("Sunday"))
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
    }


def defaults() -> dict[str, Any]:
    """A new schedule: Monday to Friday 08:00-12:00 and 13:00-17:00."""
    ranges = [
        {"weekday": day, "start": start, "end": end}
        for day in range(5)
        for start, end in (("08:00", "12:00"), ("13:00", "17:00"))
    ]
    return {"open_dest_type": "hangup", "closed_dest_type": "hangup", "ranges": ranges, "holidays": []}


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
    return hours


def delete_hours(session: Session, hours_id: int, user: str = "") -> None:
    hours = get_hours(session, hours_id)
    audit(session, user, "delete", "hours", hours.id, hours.name)
    dst.forget(session, "hours", hours.id)
    session.delete(hours)
    session.flush()
    mark_dirty(session, "dialplan")


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


def get_mode(hours_id: int) -> str | None:
    """The live mode, or ``None`` when Asterisk cannot be asked."""
    try:
        with ami.AmiClient(timeout=3.0) as client:
            out = client.command(f"database get {ASTDB_FAMILY} {hours_id}")
    except (ami.AmiError, OSError):
        return None
    value = out.split("Value:", 1)[1].strip() if "Value:" in out else ""
    return value if value in ("open", "closed") else "auto"


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
    except (ami.AmiError, OSError) as exc:
        raise ServiceError(_("Asterisk is not running, the mode cannot be changed: %(error)s", error=str(exc))) from exc
    audit(session, user, "mode", "hours", hours.id, f"{hours.name}: {mode}")
    return mode


def status(hours: BusinessHours, mode: str | None, now: dt.datetime) -> dict[str, Any]:
    """``open`` now, and why (``schedule``, ``holiday``, ``forced``)."""
    if mode in ("open", "closed"):
        return {"open": mode == "open", "reason": "forced", "holiday": None}
    holiday = holiday_on(hours, now.date())
    if holiday is not None:
        return {"open": False, "reason": "holiday", "holiday": holiday.name}
    return {"open": scheduled_open(hours, now), "reason": "schedule", "holiday": None}


def live_status(session: Session, hours_id: int, now: dt.datetime | None = None) -> dict[str, Any]:
    """Mode and open/closed right now; ``mode`` is ``None`` when Asterisk is not reachable."""
    hours = get_hours(session, hours_id)
    mode = get_mode(hours.id)
    return {"id": hours.id, "name": hours.name, "mode": mode, **status(hours, mode, now or dt.datetime.now())}


Mode = Literal["auto", "open", "closed"]
