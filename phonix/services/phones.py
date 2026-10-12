"""Phones: PJSIP and IAX accounts plus "external" phones (forward to a number)."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix.core import validation as v
from phonix.core.models import Phone, PhoneProviderCallerId, Provider, ProviderIncomingRoute
from phonix.services.common import (
    NotFound,
    ServiceError,
    audit,
    diff_dicts,
    ensure_extension_free,
    generate_pin,
    generate_secret,
    mark_dirty,
    parse,
)

DEFAULT_CODECS = ["g722", "alaw", "ulaw", "opus"]
DEFAULT_START_EXTENSION = 101

_PUBLIC_NAME = re.compile(r"^[A-Za-z0-9._+\-]{1,64}$")
_URI = re.compile(r"^[A-Za-z0-9._+\-*#]+@[A-Za-z0-9.\-:\[\]]+$")


def public_name(value: str) -> str:
    value = value.strip()
    if value and not _PUBLIC_NAME.match(value):
        raise ValueError("Public name may only contain letters, digits and . _ + -")
    return value


class PhoneIn(BaseModel):
    """Create/update payload. An empty ``secret`` on update keeps the old one."""

    model_config = ConfigDict(extra="ignore")

    tech: Literal["pjsip", "iax", "external"] = "pjsip"
    extension: str
    callerid: str
    description: str = ""
    enabled: bool = True
    ringlength: int | None = Field(default=None, ge=5, le=600)
    language: str = "en"
    secret: str = ""
    codecs: list[str] = Field(default_factory=lambda: list(DEFAULT_CODECS))
    dtmf_mode: Literal["rfc4733", "inband", "info", "auto"] = "rfc4733"
    nat: bool = True
    qualify: int = Field(default=60, ge=0, le=3600)
    max_contacts: int = Field(default=1, ge=1, le=10)
    busylevel: int | None = Field(default=None, ge=1, le=100)
    public_access: bool = False
    public_name: str = ""
    vm_enabled: bool = False
    vm_pin: str = ""
    vm_email: str = ""
    notify_missed: bool = False
    notify_email: str = ""
    dial_type: Literal["sip_uri", "iax_uri", "provider"] = "provider"
    dial_provider_id: int | None = None
    dial_string: str = ""
    manual_attributes: str = ""
    blocked_provider_ids: list[int] = Field(default_factory=list)
    # provider id -> caller id string used when calling via that provider
    provider_callerids: dict[int, str] = Field(default_factory=dict)

    _ext = field_validator("extension")(lambda cls, x: v.extension(x))
    _cid = field_validator("callerid")(lambda cls, x: v.callerid_name(x))
    _desc = field_validator("description")(lambda cls, x: v.no_control(x.strip(), "Description"))
    _lang = field_validator("language")(lambda cls, x: v.language(x))
    _codecs = field_validator("codecs")(lambda cls, x: v.codecs(x))
    _pub = field_validator("public_name")(lambda cls, x: public_name(x))
    _attrs = field_validator("manual_attributes")(lambda cls, x: v.manual_attributes(x))
    _pin = field_validator("vm_pin")(lambda cls, x: v.pin(x))

    @field_validator("secret")
    @classmethod
    def _secret(cls, value: str) -> str:
        return v.secret(value) if value else ""

    @field_validator("vm_email", "notify_email")
    @classmethod
    def _mail(cls, value: str) -> str:
        return v.email(value) if value.strip() else ""

    @field_validator("provider_callerids")
    @classmethod
    def _cids(cls, value: dict[int, str]) -> dict[int, str]:
        return {k: v.callerid_string(s) for k, s in value.items() if s.strip()}

    @model_validator(mode="after")
    def _cross(self) -> PhoneIn:
        if self.notify_missed and not self.notify_email:
            raise ValueError("notify_email: required for missed call notifications")
        if self.tech == "external":
            if not self.dial_string.strip():
                raise ValueError("dial_string: required for external phones")
            ds = v.no_control(self.dial_string.strip(), "Number")
            if self.dial_type == "provider":
                if not self.dial_provider_id:
                    raise ValueError("dial_provider_id: select a provider")
                if not re.match(r"^\+?[0-9*#]{1,32}$", ds):
                    raise ValueError("dial_string: must be a phone number")
            elif not _URI.match(ds):
                raise ValueError("dial_string: must look like user@host")
            self.dial_string = ds
        return self


def _phone_errors(exc: ServiceError) -> ServiceError:
    """Map 'field: message' model errors raised by model validators to fields."""
    fields = {}
    for key, msg in exc.fields.items():
        if key == "__all__" and ": " in msg:
            fname, fmsg = msg.split(": ", 1)
            fields[fname] = fmsg
        else:
            fields[key] = msg
    return ServiceError(exc.message, fields)


def parse_phone(data: dict[str, Any]) -> PhoneIn:
    try:
        return parse(PhoneIn, data)
    except ServiceError as exc:
        raise _phone_errors(exc) from None


def list_phones(session: Session, tech: str | None = None) -> list[Phone]:
    stmt = select(Phone)
    if tech:
        stmt = stmt.where(Phone.tech == tech)
    phones = list(session.scalars(stmt))
    phones.sort(key=lambda p: (len(p.extension), p.extension))
    return phones


def get_phone(session: Session, phone_id: int) -> Phone:
    phone = session.get(Phone, phone_id)
    if phone is None:
        raise NotFound("Phone not found")
    return phone


def next_free_extension(session: Session) -> str:
    used = {p.extension for p in session.scalars(select(Phone))}
    number = DEFAULT_START_EXTENSION
    while str(number) in used:
        number += 1
    return str(number)


def defaults(session: Session, tech: str = "pjsip") -> dict[str, Any]:
    return {
        "tech": tech,
        "extension": next_free_extension(session),
        "callerid": "",
        "secret": generate_secret(),
        "vm_pin": generate_pin(),
        "codecs": list(DEFAULT_CODECS),
    }


def to_dict(phone: Phone, with_secret: bool = False) -> dict[str, Any]:
    data = {
        "id": phone.id,
        "tech": phone.tech,
        "extension": phone.extension,
        "callerid": phone.callerid,
        "description": phone.description,
        "enabled": phone.enabled,
        "ringlength": phone.ringlength,
        "language": phone.language,
        "codecs": list(phone.codecs or []),
        "dtmf_mode": phone.dtmf_mode,
        "nat": phone.nat,
        "qualify": phone.qualify,
        "max_contacts": phone.max_contacts,
        "busylevel": phone.busylevel,
        "public_access": phone.public_access,
        "public_name": phone.public_name,
        "vm_enabled": phone.vm_enabled,
        "vm_pin": phone.vm_pin,
        "vm_email": phone.vm_email,
        "notify_missed": phone.notify_missed,
        "notify_email": phone.notify_email,
        "dial_type": phone.dial_type,
        "dial_provider_id": phone.dial_provider_id,
        "dial_string": phone.dial_string,
        "manual_attributes": phone.manual_attributes,
        "blocked_provider_ids": [p.id for p in phone.blocked_providers],
        "provider_callerids": {c.provider_id: c.callerid for c in phone.provider_callerids},
    }
    if with_secret:
        data["secret"] = phone.secret
    return data


def _apply(session: Session, phone: Phone, data: PhoneIn) -> None:
    for field in (
        "tech",
        "extension",
        "callerid",
        "description",
        "enabled",
        "ringlength",
        "language",
        "codecs",
        "dtmf_mode",
        "nat",
        "qualify",
        "max_contacts",
        "busylevel",
        "public_access",
        "public_name",
        "vm_enabled",
        "vm_pin",
        "vm_email",
        "notify_missed",
        "notify_email",
        "dial_type",
        "dial_string",
        "manual_attributes",
    ):
        setattr(phone, field, getattr(data, field))
    if data.secret:
        phone.secret = data.secret
    phone.dial_provider_id = data.dial_provider_id if data.tech == "external" else None

    providers = {p.id: p for p in session.scalars(select(Provider))}
    unknown = [pid for pid in data.blocked_provider_ids if pid not in providers]
    if unknown or (phone.dial_provider_id and phone.dial_provider_id not in providers):
        raise ServiceError(fields={"blocked_provider_ids": "Unknown provider"})
    phone.blocked_providers = [providers[pid] for pid in data.blocked_provider_ids]
    phone.provider_callerids = [
        PhoneProviderCallerId(provider_id=pid, callerid=cid)
        for pid, cid in data.provider_callerids.items()
        if pid in providers
    ]


def create_phone(session: Session, data: PhoneIn, user: str = "") -> Phone:
    ensure_extension_free(session, data.extension, "extension")
    if data.tech != "external" and not data.secret:
        data.secret = generate_secret()
    if data.vm_enabled and not data.vm_pin:
        data.vm_pin = generate_pin()
    phone = Phone()
    session.add(phone)
    _apply(session, phone, data)
    session.flush()
    audit(session, user, "create", "phone", phone.id, f"{phone.callerid} <{phone.extension}>")
    mark_dirty(session, "accounts")
    return phone


def update_phone(session: Session, phone_id: int, data: PhoneIn, user: str = "") -> Phone:
    phone = get_phone(session, phone_id)
    ensure_extension_free(session, data.extension, "extension", own=(Phone, phone.id))
    before = to_dict(phone, with_secret=True)
    _apply(session, phone, data)
    session.flush()
    diff = diff_dicts(before, to_dict(phone, with_secret=True), hide={"secret", "vm_pin"})
    audit(session, user, "update", "phone", phone.id, f"{phone.callerid} <{phone.extension}>", diff)
    mark_dirty(session, "accounts")
    return phone


def set_enabled(session: Session, phone_id: int, enabled: bool, user: str = "") -> Phone:
    phone = get_phone(session, phone_id)
    phone.enabled = enabled
    audit(session, user, "enable" if enabled else "disable", "phone", phone.id, phone.extension)
    mark_dirty(session, "accounts")
    return phone


def delete_phone(session: Session, phone_id: int, user: str = "") -> None:
    phone = get_phone(session, phone_id)
    # legacy dialplan_remove_incomingextensionmap_reference_from_providers()
    session.query(ProviderIncomingRoute).filter(
        ProviderIncomingRoute.dest_type == "phone", ProviderIncomingRoute.dest_id == phone.id
    ).delete()
    audit(session, user, "delete", "phone", phone.id, f"{phone.callerid} <{phone.extension}>")
    session.delete(phone)
    session.flush()
    mark_dirty(session, "accounts", "dialplan")
