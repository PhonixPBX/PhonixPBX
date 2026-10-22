# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Call groups, conference rooms and custom dialplan applications."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix.core import validation as v
from phonix.core.models import (
    Application,
    CallGroup,
    CallGroupMember,
    ConferenceRoom,
    Phone,
)
from phonix.i18n import N_, _
from phonix.services import destinations as dst
from phonix.services.common import (
    NotFound,
    ServiceError,
    audit,
    ensure_extension_free,
    mark_dirty,
)
from phonix.services.phones import public_name

# --- call groups ------------------------------------------------------------


class CallGroupIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    extension: str = ""
    description: str = ""
    strategy: Literal["ringall", "linear"] = "ringall"
    ringlength: int | None = Field(default=None, ge=5, le=600)
    public_access: bool = False
    public_name: str = ""
    # ordered "phone:<id>" / "callgroup:<id>"; ``member_ids`` (phones only) is the pre-1.9 form
    members: list[str] = Field(default_factory=list, validate_default=True)
    member_ids: list[int] = Field(default_factory=list)

    _name = field_validator("name")(lambda cls, x: _required_name(x))
    _desc = field_validator("description")(lambda cls, x: v.no_control(x.strip(), N_("Description")))
    _pub = field_validator("public_name")(lambda cls, x: public_name(x))

    @field_validator("extension")
    @classmethod
    def _ext(cls, value: str) -> str:
        return v.extension(value) if value.strip() else ""

    @model_validator(mode="before")
    @classmethod
    def _legacy_member_ids(cls, data: Any) -> Any:
        # a pre-1.9 client sends (or edits a fetched copy of) member_ids only: those phones win,
        # nested call groups listed in members are kept after them
        if not isinstance(data, dict) or not isinstance(data.get("member_ids"), list):
            return data
        members = data.get("members") or []
        if not isinstance(members, list):
            return data
        phones = [f"phone:{i}" for i in data["member_ids"]]
        if [m for m in members if str(m).startswith("phone:")] == phones:
            return data
        groups = [m for m in members if not str(m).startswith("phone:")]
        return {**data, "members": [*phones, *groups]}

    @field_validator("members")
    @classmethod
    def _members(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for text in value:
            ref = dst.parse_value(text)
            if ref is None or ref[0] not in MEMBER_TYPES:
                raise ValueError(_("Invalid member: %(member)s", member=text))
            norm = f"{ref[0]}:{ref[1]}"
            if norm not in seen:
                seen.append(norm)
        if not seen:
            raise ValueError(_("Select at least one member"))
        return seen

    @model_validator(mode="after")
    def _phone_ids(self) -> CallGroupIn:
        self.member_ids = [i for t, i in self.member_refs if t == "phone"]
        return self

    @property
    def member_refs(self) -> list[tuple[str, int]]:
        refs = []
        for text in self.members:
            kind, _sep, ident = text.partition(":")
            refs.append((kind, int(ident)))
        return refs


MEMBER_TYPES = ("phone", "callgroup")


def _required_name(value: str) -> str:
    value = v.config_value(value, N_("Name"))
    if not value:
        raise ValueError(_("Name is required"))
    return value


def list_callgroups(session: Session) -> list[CallGroup]:
    return list(session.scalars(select(CallGroup).order_by(CallGroup.name)))


def get_callgroup(session: Session, group_id: int) -> CallGroup:
    group = session.get(CallGroup, group_id)
    if group is None:
        raise NotFound(_("Call group not found"))
    return group


def callgroup_to_dict(g: CallGroup) -> dict[str, Any]:
    return {
        "id": g.id,
        "name": g.name,
        "extension": g.extension or "",
        "description": g.description,
        "strategy": g.strategy,
        "ringlength": g.ringlength,
        "public_access": g.public_access,
        "public_name": g.public_name,
        "members": [m.ref for m in g.members],
        "member_ids": [m.phone_id for m in g.members if m.phone_id is not None],
    }


def contains_callgroup(session: Session, start: int, target: int) -> bool:
    """Whether call group ``start`` contains ``target``, directly or through nested groups."""
    edges: dict[int, list[int]] = {}
    for parent, child in session.execute(
        select(CallGroupMember.group_id, CallGroupMember.member_group_id).where(
            CallGroupMember.member_group_id.is_not(None)
        )
    ):
        edges.setdefault(parent, []).append(child)
    todo, seen = [start], set()
    while todo:
        gid = todo.pop()
        if gid == target:
            return True
        if gid not in seen:
            seen.add(gid)
            todo.extend(edges.get(gid, []))
    return False


def member_choices(session: Session, group_id: int | None) -> list[tuple[str, list[tuple[str, str]]]]:
    """Grouped member options for the call group form, without the groups that would make a loop."""
    phones = [
        (f"phone:{p.id}", f"{p.extension} - {p.callerid}")
        for p in session.scalars(select(Phone).order_by(Phone.extension))
    ]
    groups = [
        (f"callgroup:{g.id}", dst.label(session, "callgroup", g.id))
        for g in list_callgroups(session)
        if group_id is None or not contains_callgroup(session, g.id, group_id)
    ]
    return [(_("Phones"), phones), (_("Call groups"), groups)]


def _apply_callgroup(session: Session, group: CallGroup, data: CallGroupIn) -> None:
    refs = data.member_refs
    phones = {p.id for p in session.scalars(select(Phone))}
    if any(i not in phones for t, i in refs if t == "phone"):
        raise ServiceError(fields={"members": _("Unknown phone selected")})
    groups = {g.id for g in session.scalars(select(CallGroup))}
    child_ids = [i for t, i in refs if t == "callgroup"]
    if any(i not in groups for i in child_ids):
        raise ServiceError(fields={"members": _("Unknown call group selected")})
    if group.id is not None and any(contains_callgroup(session, i, group.id) for i in child_ids):
        raise ServiceError(
            fields={"members": _("A call group cannot contain itself, directly or through another group")}
        )
    group.name = data.name
    group.extension = data.extension or None
    group.description = data.description
    group.strategy = data.strategy
    group.ringlength = data.ringlength
    group.public_access = data.public_access
    group.public_name = data.public_name
    # reuse the existing rows: the flush inserts new members before it deletes orphans,
    # so a fresh row for a member that stays in the group violates the unique constraints
    existing = {m.ref: m for m in group.members}
    members = []
    for i, (kind, ident) in enumerate(refs):
        member = existing.get(f"{kind}:{ident}")
        if member is None:
            member = CallGroupMember(phone_id=ident) if kind == "phone" else CallGroupMember(member_group_id=ident)
        member.position = i
        members.append(member)
    group.members = members


def create_callgroup(session: Session, data: CallGroupIn, user: str = "") -> CallGroup:
    if data.extension:
        ensure_extension_free(session, data.extension, "extension")
    group = CallGroup()
    _apply_callgroup(session, group, data)
    session.add(group)
    session.flush()
    audit(session, user, "create", "callgroup", group.id, group.name)
    mark_dirty(session, "dialplan")
    return group


def update_callgroup(session: Session, group_id: int, data: CallGroupIn, user: str = "") -> CallGroup:
    group = get_callgroup(session, group_id)
    if data.extension:
        ensure_extension_free(session, data.extension, "extension", own=(CallGroup, group.id))
    _apply_callgroup(session, group, data)
    session.flush()
    audit(session, user, "update", "callgroup", group.id, group.name)
    mark_dirty(session, "dialplan")
    return group


def delete_callgroup(session: Session, group_id: int, user: str = "") -> None:
    group = get_callgroup(session, group_id)
    dst.forget(session, "callgroup", group.id)
    audit(session, user, "delete", "callgroup", group.id, group.name)
    session.delete(group)
    session.flush()
    mark_dirty(session, "dialplan")


# --- conference rooms -------------------------------------------------------


class ConferenceRoomIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    number: str
    name: str
    pin: str = ""
    admin_pin: str = ""
    public_access: bool = False
    public_name: str = ""

    _num = field_validator("number")(lambda cls, x: v.extension(x))
    _name = field_validator("name")(lambda cls, x: _required_name(x))
    _pins = field_validator("pin", "admin_pin")(lambda cls, x: v.pin(x))
    _pub = field_validator("public_name")(lambda cls, x: public_name(x))


def list_rooms(session: Session) -> list[ConferenceRoom]:
    rooms = list(session.scalars(select(ConferenceRoom)))
    rooms.sort(key=lambda r: (len(r.number), r.number))
    return rooms


def get_room(session: Session, room_id: int) -> ConferenceRoom:
    room = session.get(ConferenceRoom, room_id)
    if room is None:
        raise NotFound(_("Conference room not found"))
    return room


def room_to_dict(r: ConferenceRoom) -> dict[str, Any]:
    return {
        "id": r.id,
        "number": r.number,
        "name": r.name,
        "pin": r.pin,
        "admin_pin": r.admin_pin,
        "public_access": r.public_access,
        "public_name": r.public_name,
    }


def _apply_room(room: ConferenceRoom, data: ConferenceRoomIn) -> None:
    if data.admin_pin and data.admin_pin == data.pin:
        raise ServiceError(fields={"admin_pin": _("Admin PIN must differ from the user PIN")})
    for field in ("number", "name", "pin", "admin_pin", "public_access", "public_name"):
        setattr(room, field, getattr(data, field))


def create_room(session: Session, data: ConferenceRoomIn, user: str = "") -> ConferenceRoom:
    ensure_extension_free(session, data.number, "number")
    room = ConferenceRoom()
    _apply_room(room, data)
    session.add(room)
    session.flush()
    audit(session, user, "create", "conference", room.id, room.name)
    mark_dirty(session, "services", "dialplan")
    return room


def update_room(session: Session, room_id: int, data: ConferenceRoomIn, user: str = "") -> ConferenceRoom:
    room = get_room(session, room_id)
    ensure_extension_free(session, data.number, "number", own=(ConferenceRoom, room.id))
    _apply_room(room, data)
    session.flush()
    audit(session, user, "update", "conference", room.id, room.name)
    mark_dirty(session, "services", "dialplan")
    return room


def delete_room(session: Session, room_id: int, user: str = "") -> None:
    room = get_room(session, room_id)
    dst.forget(session, "conference", room.id)
    audit(session, user, "delete", "conference", room.id, room.name)
    session.delete(room)
    session.flush()
    mark_dirty(session, "services", "dialplan")


# --- applications -----------------------------------------------------------


class ApplicationIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    extension: str
    description: str = ""
    logic: str
    enabled: bool = True
    public_access: bool = False
    public_name: str = ""

    _name = field_validator("name")(lambda cls, x: _required_name(x))
    _ext = field_validator("extension")(lambda cls, x: v.extension_or_pattern(x))
    _desc = field_validator("description")(lambda cls, x: v.no_control(x.strip(), N_("Description")))
    _logic = field_validator("logic")(lambda cls, x: v.application_logic(x))
    _pub = field_validator("public_name")(lambda cls, x: public_name(x))


def list_applications(session: Session) -> list[Application]:
    return list(session.scalars(select(Application).order_by(Application.extension)))


def get_application(session: Session, app_id: int) -> Application:
    app = session.get(Application, app_id)
    if app is None:
        raise NotFound(_("Application not found"))
    return app


def application_to_dict(a: Application) -> dict[str, Any]:
    return {
        "id": a.id,
        "name": a.name,
        "extension": a.extension,
        "description": a.description,
        "logic": a.logic,
        "enabled": a.enabled,
        "public_access": a.public_access,
        "public_name": a.public_name,
    }


def _apply_app(app: Application, data: ApplicationIn) -> None:
    for field in ("name", "extension", "description", "logic", "enabled", "public_access", "public_name"):
        setattr(app, field, getattr(data, field))


def create_application(session: Session, data: ApplicationIn, user: str = "") -> Application:
    ensure_extension_free(session, data.extension, "extension")
    app = Application()
    _apply_app(app, data)
    session.add(app)
    session.flush()
    audit(session, user, "create", "application", app.id, app.name)
    mark_dirty(session, "dialplan")
    return app


def update_application(session: Session, app_id: int, data: ApplicationIn, user: str = "") -> Application:
    app = get_application(session, app_id)
    ensure_extension_free(session, data.extension, "extension", own=(Application, app.id))
    _apply_app(app, data)
    session.flush()
    audit(session, user, "update", "application", app.id, app.name)
    mark_dirty(session, "dialplan")
    return app


def delete_application(session: Session, app_id: int, user: str = "") -> None:
    app = get_application(session, app_id)
    dst.forget(session, "application", app.id)
    audit(session, user, "delete", "application", app.id, app.name)
    session.delete(app)
    session.flush()
    mark_dirty(session, "dialplan")


# Defaults shipped with every new installation, ported from the legacy
# target/pbx-generic-pc/config.xml and adapted to Asterisk 22 (no Macro,
# no MeetMe; "Read IP" uses the generated PHONIX_LAN_IP global).
DEFAULT_APPLICATIONS: list[dict[str, Any]] = [
    {
        "name": "Read extension number",
        "extension": "000063",
        "description": "0000ME - Reads back the extension being used to call the application.",
        "logic": "1,Answer()\n2,Playback(beep)\n3,SayDigits(${CALLERID(number)})\n"
        "n,Playback(silence/1)\nn,Playback(silence/1)\nn,Playback(silence/1)\nn,Goto(2)",
    },
    {
        "name": "Read IP",
        "extension": "000047",
        "description": "0000IP - Reads back the system IP address.",
        "logic": "1,Answer()\n2,Set(IPOUTPUT=${PHONIX_LAN_IP})\n3,NoOp(IPOUTPUT: ${IPOUTPUT})\n"
        "4,Playback(beep)\n"
        "n,SayDigits(${CUT(IPOUTPUT,.,1)})\nn,Playback(silence/1)\n"
        "n,SayDigits(${CUT(IPOUTPUT,.,2)})\nn,Playback(silence/1)\n"
        "n,SayDigits(${CUT(IPOUTPUT,.,3)})\nn,Playback(silence/1)\n"
        "n,SayDigits(${CUT(IPOUTPUT,.,4)})\nn,Playback(silence/1)\n"
        "n,Playback(silence/1)\nn,Goto(4)",
    },
    {
        "name": "Echo",
        "extension": "00003246",
        "description": "0000ECHO - Echoes audio and video back to the caller. Used to test connection delay.",
        "logic": "1,Answer()\n2,Echo()\n3,Hangup()",
    },
    {
        "name": "Milliwatt",
        "extension": "000064554",
        "description": "0000MILLI - Generates a constant 1000Hz tone. Used to test connection quality.",
        "logic": "1,Answer()\n2,Milliwatt()\n3,Hangup()",
    },
    {
        "name": "Voicemail system",
        "extension": "000086",
        "description": "0000VM - Voicemail system",
        "logic": "1,Answer()\n2,VoiceMailMain(${CALLERID(num)}@default)\n3,Hangup()",
    },
    {
        "name": "Call forwarding",
        "extension": "000023",
        "description": "0000CF - Activate and deactivate call forwarding.",
        "logic": "1,Answer()\n"
        '2,GotoIf($["${DB(CF/${CALLERID(num)})}" != ""]?removecf:setcfnumber)\n'
        "3(setcfnumber),Playback(vm-enter-num-to-call)\n"
        "4,Read(CF_DESTINATION,beep,,,,5)\n"
        '5,GotoIf($["${CF_DESTINATION}" = "" | "${CF_DESTINATION}" = "${EXTEN}"]?10)\n'
        "6,Set(DB(CF/${CALLERID(num)})=${CF_DESTINATION})\n"
        "7,SayDigits(${CF_DESTINATION})\n"
        "8,Playback(auth-thankyou)\n"
        "9,Hangup()\n"
        "10,Playback(invalid)\n"
        "11,Hangup()\n"
        "12(removecf),Set(old=${DB_DELETE(CF/${CALLERID(num)})})\n"
        "13,PlayTones(!500/100,0/100,!500/100)\n"
        "14,Wait(1)\n"
        "15,Hangup()",
    },
    {
        "name": "Weasels",
        "extension": "00009327357",
        "description": "0000WEASELS",
        "logic": "1,Answer()\n2,Playback(tt-weasels)\n3,Hangup()",
    },
]

DEFAULT_CONFERENCE = {"number": "2663", "name": "Default Conference"}
