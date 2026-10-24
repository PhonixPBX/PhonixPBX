# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Shared service-layer plumbing: errors, audit trail, dirty tracking."""

from __future__ import annotations

import secrets
import string
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix.core.models import (
    Application,
    AuditLog,
    BusinessHours,
    BusinessHoursSpecial,
    CallGroup,
    ConferenceRoom,
    Dirty,
    IvrMenu,
    Phone,
    utcnow,
)
from phonix.core.settings import FeatureSettings
from phonix.core.settings import load as load_settings
from phonix.i18n import N_, _


class ServiceError(Exception):
    """A user-facing error. ``fields`` maps form field names to messages."""

    def __init__(self, message: str = "", fields: dict[str, str] | None = None) -> None:
        self.fields = fields or {}
        super().__init__(message or "; ".join(f"{k}: {v}" for k, v in self.fields.items()))
        self.message = message


class NotFound(ServiceError):
    pass


def _validation_message(err: Any) -> str:
    """Our own (translated) text for pydantic's built-in English messages."""
    kind = err["type"]
    ctx = err.get("ctx") or {}
    if kind == "missing":
        return _("This field is required")
    if kind in ("int_parsing", "int_type", "int_from_float"):
        return _("Must be a whole number")
    if kind in ("float_parsing", "float_type", "decimal_parsing", "decimal_type"):
        return _("Must be a number")
    if kind in ("bool_parsing", "bool_type"):
        return _("Must be yes or no")
    if kind == "greater_than_equal":
        return _("Must be at least %(ge)s", ge=ctx.get("ge"))
    if kind == "greater_than":
        return _("Must be greater than %(gt)s", gt=ctx.get("gt"))
    if kind == "less_than_equal":
        return _("Must be at most %(le)s", le=ctx.get("le"))
    if kind == "less_than":
        return _("Must be less than %(lt)s", lt=ctx.get("lt"))
    if kind == "string_too_long":
        return _("At most %(max)s characters allowed", max=ctx.get("max_length"))
    if kind == "string_too_short":
        return _("At least %(min)s characters required", min=ctx.get("min_length"))
    if kind == "too_long":
        return _("At most %(max)s entries allowed", max=ctx.get("max_length"))
    if kind == "too_short":
        return _("At least %(min)s entries required", min=ctx.get("min_length"))
    if kind in ("literal_error", "enum"):
        return _("Invalid choice")
    if kind == "string_pattern_mismatch":
        return _("Invalid format")
    if kind in ("string_type", "list_type", "dict_type", "model_type"):
        return _("Invalid value")
    msg = str(err["msg"])
    if msg.startswith("Value error, "):  # our own validators, already translated
        msg = msg[len("Value error, ") :]
    return msg


def errors_from_validation(exc: ValidationError) -> dict[str, str]:
    out: dict[str, str] = {}
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"] if p != "__root__") or "__all__"
        out.setdefault(loc, _validation_message(err))
    return out


def parse(model: type[BaseModel], data: dict[str, Any]) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ServiceError(fields=errors_from_validation(exc)) from exc


# --- areas: what an "apply" will touch, shown in the pending-changes banner --

AREAS = {
    "accounts": N_("Phones and providers"),
    "dialplan": N_("Dialplan"),
    "services": N_("Voicemail, conferencing and media"),
    "telephony": N_("SIP, IAX and RTP settings"),
    "manager": N_("Asterisk manager users"),
    "email": N_("E-mail notifications"),
    "network": N_("Network"),
    "system": N_("System settings"),
    "firewall": N_("Firewall"),
}


def mark_dirty(session: Session, *areas: str) -> None:
    for area in areas:
        if session.get(Dirty, area) is None:
            session.add(Dirty(area=area))
    session.flush()


def dirty_areas(session: Session) -> list[str]:
    return [d.area for d in session.scalars(select(Dirty).order_by(Dirty.since))]


def clear_dirty(session: Session) -> None:
    session.query(Dirty).delete()
    session.flush()


def audit(
    session: Session,
    username: str,
    action: str,
    object_type: str = "",
    object_id: Any = "",
    summary: str = "",
    diff: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            ts=utcnow(),
            username=username or "system",
            action=action,
            object_type=object_type,
            object_id=str(object_id),
            summary=summary[:255],
            diff=diff,
        )
    )


def diff_dicts(
    before: dict[str, Any], after: dict[str, Any], hide: set[str] | None = None
) -> dict[str, dict[str, Any]]:
    hide = hide or set()
    out: dict[str, dict[str, Any]] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            if key in hide:
                out[key] = {"changed": True}
            else:
                out[key] = {"from": before.get(key), "to": after.get(key)}
    return out


# --- secrets ----------------------------------------------------------------

_ALPHABET = string.ascii_letters + string.digits


def generate_secret(length: int = 16) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def generate_pin(length: int = 4) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


# --- extension namespace ----------------------------------------------------


def extension_owner(session: Session, number: str) -> str | None:
    """Return a description of whatever already uses ``number`` (or None)."""
    phone = session.scalar(select(Phone).where(Phone.extension == number))
    if phone:
        return _("phone %(callerid)s <%(extension)s>", callerid=phone.callerid, extension=phone.extension)
    group = session.scalar(select(CallGroup).where(CallGroup.extension == number))
    if group:
        return _("call group %(name)s", name=group.name)
    room = session.scalar(select(ConferenceRoom).where(ConferenceRoom.number == number))
    if room:
        return _("conference room %(name)s", name=room.name)
    app = session.scalar(select(Application).where(Application.extension == number))
    if app:
        return _("application %(name)s", name=app.name)
    menu = session.scalar(select(IvrMenu).where(IvrMenu.extension == number))
    if menu:
        return _("IVR menu %(name)s", name=menu.name)
    hours = session.scalar(select(BusinessHours).where(BusinessHours.feature_code == number))
    if hours:
        return _("the feature code of business hours %(name)s", name=hours.name)
    special = session.scalar(select(BusinessHoursSpecial).where(BusinessHoursSpecial.feature_code == number))
    if special:
        return _("the feature code of the special period %(name)s", name=special.name)
    features = load_settings(session, FeatureSettings)
    if number == features.park_ext:
        return _("call parking")
    if number.isdigit() and features.park_start <= int(number) <= features.park_end:
        return _("a parking slot")
    return None


def ensure_extension_free(session: Session, number: str, field: str, own: tuple[type, int] | None = None) -> None:
    """Raise if ``number`` is used by another object than ``own`` (model, id)."""
    owners: list[tuple[type, Any]] = [
        (Phone, Phone.extension),
        (CallGroup, CallGroup.extension),
        (ConferenceRoom, ConferenceRoom.number),
        (Application, Application.extension),
        (IvrMenu, IvrMenu.extension),
        (BusinessHours, BusinessHours.feature_code),
        (BusinessHoursSpecial, BusinessHoursSpecial.feature_code),
    ]
    for model, column in owners:
        obj = session.scalar(select(model).where(column == number))
        if obj is not None and (own is None or not (model is own[0] and obj.id == own[1])):
            raise ServiceError(
                fields={field: _("Number already used by %(owner)s", owner=extension_owner(session, number))}
            )
    features = load_settings(session, FeatureSettings)
    if number == features.park_ext or (number.isdigit() and features.park_start <= int(number) <= features.park_end):
        raise ServiceError(fields={field: _("Number is reserved for call parking")})
