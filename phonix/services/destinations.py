# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Call destinations: where provider incoming routes, IVR keys and business hours lead.

A destination is a ``(type, id)`` pair. Object types point to a row (``voicemail``
is the mailbox of a phone); the actions ``repeat`` (play the IVR menu again) and
``hangup`` have no id. Pickers submit them as ``"type:id"`` or ``"type"``.
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix.core.models import (
    Application,
    BusinessHours,
    CallGroup,
    ConferenceRoom,
    IvrMenu,
    IvrOption,
    Phone,
    ProviderIncomingRoute,
)
from phonix.i18n import N_, _
from phonix.services.common import ServiceError

RouteType = Literal["phone", "callgroup", "application", "conference", "ivr", "hours"]
# IVR keys and the "unknown key" destination; "repeat" plays the menu again
IvrType = Literal["phone", "callgroup", "application", "conference", "ivr", "hours", "voicemail", "repeat", "hangup"]
# no key pressed: "repeat" would never end, the menu repeats ``repeats`` times by itself
IvrTimeoutType = Literal["phone", "callgroup", "application", "conference", "ivr", "hours", "voicemail", "hangup"]
# business hours cannot point to business hours (no loops without a caller decision)
HoursType = Literal["phone", "callgroup", "application", "conference", "ivr", "voicemail", "hangup"]

ROUTE_TYPES: tuple[str, ...] = RouteType.__args__  # type: ignore[attr-defined]
IVR_TYPES: tuple[str, ...] = IvrType.__args__  # type: ignore[attr-defined]
IVR_TIMEOUT_TYPES: tuple[str, ...] = IvrTimeoutType.__args__  # type: ignore[attr-defined]
HOURS_TYPES: tuple[str, ...] = HoursType.__args__  # type: ignore[attr-defined]

ACTIONS = ("repeat", "hangup")

MODELS: dict[str, type] = {
    "phone": Phone,
    "callgroup": CallGroup,
    "application": Application,
    "conference": ConferenceRoom,
    "ivr": IvrMenu,
    "hours": BusinessHours,
    "voicemail": Phone,
}

# picker groups, in display order
GROUPS: dict[str, str] = {
    "phone": N_("Phones"),
    "callgroup": N_("Call groups"),
    "conference": N_("Conference rooms"),
    "application": N_("Applications"),
    "ivr": N_("IVR menus"),
    "hours": N_("Business hours"),
    "voicemail": N_("Voicemail"),
    "repeat": N_("Other"),
    "hangup": N_("Other"),
}


def value(dest_type: str, dest_id: int | None) -> str:
    """The picker value of a destination."""
    return dest_type if dest_type in ACTIONS else f"{dest_type}:{dest_id}"


def parse_value(text: str) -> tuple[str, int | None] | None:
    """``"type:id"`` / ``"type"`` from a picker; ``None`` for an empty or malformed value."""
    text = text.strip()
    if text in ACTIONS:
        return text, None
    dest_type, sep, dest_id = text.partition(":")
    if not sep or dest_type not in MODELS or not dest_id.isdigit():
        return None
    return dest_type, int(dest_id)


def _object_label(obj: Any, dest_type: str) -> str:
    if dest_type == "voicemail":
        return _("Voicemail box %(number)s (%(name)s)", number=obj.extension, name=obj.callerid)
    if isinstance(obj, Phone):
        return f"{obj.callerid} <{obj.extension}>"
    if isinstance(obj, ConferenceRoom):
        return _("Conference %(name)s <%(number)s>", name=obj.name, number=obj.number)
    if isinstance(obj, CallGroup):
        if obj.extension:
            return _("Call group %(name)s <%(number)s>", name=obj.name, number=obj.extension)
        return _("Call group %(name)s", name=obj.name)
    if isinstance(obj, IvrMenu):
        if obj.extension:
            return _("IVR menu %(name)s <%(number)s>", name=obj.name, number=obj.extension)
        return _("IVR menu %(name)s", name=obj.name)
    if isinstance(obj, BusinessHours):
        return _("Business hours %(name)s", name=obj.name)
    return _("Application %(name)s <%(number)s>", name=obj.name, number=obj.extension)


def label(session: Session, dest_type: str, dest_id: int | None) -> str:
    if dest_type == "repeat":
        return _("Repeat the menu")
    if dest_type == "hangup":
        return _("Hang up")
    model = MODELS.get(dest_type)
    obj = session.get(model, dest_id) if model and dest_id is not None else None
    if obj is None:
        return _("(missing %(type)s)", type=dest_type)
    return _object_label(obj, dest_type)


def _objects(session: Session, dest_type: str) -> list[Any]:
    if dest_type == "phone":
        return list(session.scalars(select(Phone).order_by(Phone.extension)))
    if dest_type == "voicemail":
        return list(session.scalars(select(Phone).where(Phone.vm_enabled.is_(True)).order_by(Phone.extension)))
    if dest_type == "callgroup":
        return list(session.scalars(select(CallGroup).order_by(CallGroup.name)))
    if dest_type == "conference":
        return list(session.scalars(select(ConferenceRoom).order_by(ConferenceRoom.number)))
    if dest_type == "application":
        return list(session.scalars(select(Application).order_by(Application.extension)))
    if dest_type == "ivr":
        return list(session.scalars(select(IvrMenu).order_by(IvrMenu.name)))
    return list(session.scalars(select(BusinessHours).order_by(BusinessHours.name)))


def choices(session: Session, types: tuple[str, ...]) -> list[tuple[str, list[tuple[str, str]]]]:
    """Picker options grouped as ``[(group title, [(value, label), ...]), ...]``."""
    groups: dict[str, list[tuple[str, str]]] = {}
    for dest_type in GROUPS:
        if dest_type not in types:
            continue
        options = groups.setdefault(_(GROUPS[dest_type]), [])
        if dest_type in ACTIONS:
            options.append((dest_type, label(session, dest_type, None)))
            continue
        for obj in _objects(session, dest_type):
            options.append((value(dest_type, obj.id), _object_label(obj, dest_type)))
    return [(title, options) for title, options in groups.items() if options]


def flat_choices(session: Session, types: tuple[str, ...]) -> list[tuple[str, str]]:
    return [option for _title, options in choices(session, types) for option in options]


def check(session: Session, dest_type: str, dest_id: int | None, field: str) -> None:
    """Raise a ``ServiceError`` on ``field`` if the destination does not exist."""
    if dest_type in ACTIONS:
        return
    model = MODELS.get(dest_type)
    obj = session.get(model, dest_id) if model and dest_id is not None else None
    if obj is None:
        raise ServiceError(fields={field: _("Destination does not exist")})
    if dest_type == "voicemail" and not obj.vm_enabled:
        raise ServiceError(fields={field: _("This phone has no voicemail box")})


def forget(session: Session, dest_type: str, dest_id: int) -> None:
    """Remove every reference to a destination that is about to be deleted.

    Incoming routes and IVR keys that led there are removed; the fixed
    destinations of IVR menus and business hours fall back to hanging up.
    """
    session.flush()
    session.query(ProviderIncomingRoute).filter(
        ProviderIncomingRoute.dest_type == dest_type, ProviderIncomingRoute.dest_id == dest_id
    ).delete()
    session.query(IvrOption).filter(IvrOption.dest_type == dest_type, IvrOption.dest_id == dest_id).delete()
    for menu in session.scalars(select(IvrMenu)):
        if (menu.timeout_dest_type, menu.timeout_dest_id) == (dest_type, dest_id):
            menu.timeout_dest_type, menu.timeout_dest_id = "hangup", None
        if (menu.invalid_dest_type, menu.invalid_dest_id) == (dest_type, dest_id):
            menu.invalid_dest_type, menu.invalid_dest_id = "repeat", None
    for hours in session.scalars(select(BusinessHours)):
        if (hours.open_dest_type, hours.open_dest_id) == (dest_type, dest_id):
            hours.open_dest_type, hours.open_dest_id = "hangup", None
        if (hours.closed_dest_type, hours.closed_dest_id) == (dest_type, dest_id):
            hours.closed_dest_type, hours.closed_dest_id = "hangup", None
    # the bulk deletes bypass the loaded relationships (provider routes, menu options)
    session.flush()
    session.expire_all()


def required(value: Any) -> Any:
    """``field_validator(mode="before")`` for a destination type: a clear message when none is chosen."""
    if value in ("", None):
        raise ValueError(_("Choose a destination"))
    return value
