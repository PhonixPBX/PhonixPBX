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
    CallGroup,
    ConferenceRoom,
    Dirty,
    Phone,
    utcnow,
)
from phonix.core.settings import FeatureSettings
from phonix.core.settings import load as load_settings


class ServiceError(Exception):
    """A user-facing error. ``fields`` maps form field names to messages."""

    def __init__(self, message: str = "", fields: dict[str, str] | None = None) -> None:
        self.fields = fields or {}
        super().__init__(message or "; ".join(f"{k}: {v}" for k, v in self.fields.items()))
        self.message = message


class NotFound(ServiceError):
    pass


def errors_from_validation(exc: ValidationError) -> dict[str, str]:
    out: dict[str, str] = {}
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"] if p != "__root__") or "__all__"
        msg = err["msg"]
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]
        out.setdefault(loc, msg)
    return out


def parse(model: type[BaseModel], data: dict[str, Any]) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ServiceError(fields=errors_from_validation(exc)) from exc


# --- areas: what an "apply" will touch, shown in the pending-changes banner --

AREAS = {
    "accounts": "Phones and providers",
    "dialplan": "Dialplan",
    "services": "Voicemail, conferencing and media",
    "telephony": "SIP, IAX and RTP settings",
    "manager": "Asterisk manager users",
    "email": "E-mail notifications",
    "network": "Network",
    "system": "System settings",
    "firewall": "Firewall",
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
        return f"phone {phone.callerid} <{phone.extension}>"
    group = session.scalar(select(CallGroup).where(CallGroup.extension == number))
    if group:
        return f"call group {group.name}"
    room = session.scalar(select(ConferenceRoom).where(ConferenceRoom.number == number))
    if room:
        return f"conference room {room.name}"
    app = session.scalar(select(Application).where(Application.extension == number))
    if app:
        return f"application {app.name}"
    features = load_settings(session, FeatureSettings)
    if number == features.park_ext:
        return "call parking"
    if number.isdigit() and features.park_start <= int(number) <= features.park_end:
        return "a parking slot"
    return None


def ensure_extension_free(session: Session, number: str, field: str, own: tuple[type, int] | None = None) -> None:
    """Raise if ``number`` is used by another object than ``own`` (model, id)."""
    owners: list[tuple[type, Any]] = [
        (Phone, Phone.extension),
        (CallGroup, CallGroup.extension),
        (ConferenceRoom, ConferenceRoom.number),
        (Application, Application.extension),
    ]
    for model, column in owners:
        obj = session.scalar(select(model).where(column == number))
        if obj is not None and (own is None or not (model is own[0] and obj.id == own[1])):
            raise ServiceError(fields={field: f"Number already used by {extension_owner(session, number)}"})
    features = load_settings(session, FeatureSettings)
    if number == features.park_ext or (number.isdigit() and features.park_start <= int(number) <= features.park_end):
        raise ServiceError(fields={field: "Number is reserved for call parking"})
