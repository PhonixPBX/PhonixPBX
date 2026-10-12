"""Call groups, conference rooms and custom dialplan applications."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from askozia.core import validation as v
from askozia.core.models import (
    Application,
    CallGroup,
    CallGroupMember,
    ConferenceRoom,
    Phone,
    ProviderIncomingRoute,
)
from askozia.services.common import (
    NotFound,
    ServiceError,
    audit,
    ensure_extension_free,
    mark_dirty,
)
from askozia.services.phones import public_name


def _drop_routes(session: Session, dest_type: str, dest_id: int) -> None:
    session.query(ProviderIncomingRoute).filter(
        ProviderIncomingRoute.dest_type == dest_type, ProviderIncomingRoute.dest_id == dest_id
    ).delete()


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
    member_ids: list[int] = Field(default_factory=list)

    _name = field_validator("name")(lambda cls, x: _required_name(x))
    _desc = field_validator("description")(lambda cls, x: v.no_control(x.strip(), "Description"))
    _pub = field_validator("public_name")(lambda cls, x: public_name(x))

    @field_validator("extension")
    @classmethod
    def _ext(cls, value: str) -> str:
        return v.extension(value) if value.strip() else ""

    @field_validator("member_ids")
    @classmethod
    def _members(cls, value: list[int]) -> list[int]:
        seen: list[int] = []
        for pid in value:
            if pid not in seen:
                seen.append(pid)
        if not seen:
            raise ValueError("Select at least one member")
        return seen


def _required_name(value: str) -> str:
    value = v.config_value(value, "Name")
    if not value:
        raise ValueError("Name is required")
    return value


def list_callgroups(session: Session) -> list[CallGroup]:
    return list(session.scalars(select(CallGroup).order_by(CallGroup.name)))


def get_callgroup(session: Session, group_id: int) -> CallGroup:
    group = session.get(CallGroup, group_id)
    if group is None:
        raise NotFound("Call group not found")
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
        "member_ids": [m.phone_id for m in g.members],
    }


def _apply_callgroup(session: Session, group: CallGroup, data: CallGroupIn) -> None:
    phones = {p.id for p in session.scalars(select(Phone))}
    missing = [pid for pid in data.member_ids if pid not in phones]
    if missing:
        raise ServiceError(fields={"member_ids": "Unknown phone selected"})
    group.name = data.name
    group.extension = data.extension or None
    group.description = data.description
    group.strategy = data.strategy
    group.ringlength = data.ringlength
    group.public_access = data.public_access
    group.public_name = data.public_name
    group.members = [
        CallGroupMember(phone_id=pid, position=i) for i, pid in enumerate(data.member_ids)
    ]


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
    _drop_routes(session, "callgroup", group.id)
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
        raise NotFound("Conference room not found")
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
        raise ServiceError(fields={"admin_pin": "Admin PIN must differ from the user PIN"})
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
    _drop_routes(session, "conference", room.id)
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
    _desc = field_validator("description")(lambda cls, x: v.no_control(x.strip(), "Description"))
    _logic = field_validator("logic")(lambda cls, x: v.application_logic(x))
    _pub = field_validator("public_name")(lambda cls, x: public_name(x))


def list_applications(session: Session) -> list[Application]:
    return list(session.scalars(select(Application).order_by(Application.extension)))


def get_application(session: Session, app_id: int) -> Application:
    app = session.get(Application, app_id)
    if app is None:
        raise NotFound("Application not found")
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
    _drop_routes(session, "application", app.id)
    audit(session, user, "delete", "application", app.id, app.name)
    session.delete(app)
    session.flush()
    mark_dirty(session, "dialplan")


# Defaults shipped with every new installation, ported from the legacy
# target/pbx-generic-pc/config.xml and adapted to Asterisk 22 (no Macro,
# no MeetMe; "Read IP" uses the generated ASKOZIA_LAN_IP global).
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
        "logic": "1,Answer()\n2,Set(IPOUTPUT=${ASKOZIA_LAN_IP})\n3,NoOp(IPOUTPUT: ${IPOUTPUT})\n"
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
