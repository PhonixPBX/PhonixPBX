"""Providers (trunks): PJSIP and IAX, with outgoing dial patterns and incoming routes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix.core import validation as v
from phonix.core.models import (
    Application,
    CallGroup,
    ConferenceRoom,
    Phone,
    Provider,
    ProviderDialPattern,
    ProviderIncomingRoute,
)
from phonix.i18n import N_, _
from phonix.services.common import (
    NotFound,
    ServiceError,
    audit,
    diff_dicts,
    mark_dirty,
    parse,
)

DEFAULT_CODECS = ["alaw", "ulaw", "g722"]


class IncomingRouteIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # empty pattern = catch-all
    pattern: str = ""
    dest_type: Literal["phone", "callgroup", "application", "conference"]
    dest_id: int

    @field_validator("pattern")
    @classmethod
    def _pattern(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if value.isdigit():
            return value
        return v.dialpattern(value.lstrip("_"), incoming=True)


class ProviderIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tech: Literal["pjsip", "iax"] = "pjsip"
    name: str
    enabled: bool = True
    host: str
    port: int | None = Field(default=None, ge=1, le=65535)
    transport: Literal["udp", "tcp", "tls"] = "udp"
    username: str
    secret: str = ""
    auth_user: str = ""
    from_user: str = ""
    from_domain: str = ""
    registration: bool = True
    iax_auth: Literal["md5", "plaintext", "rsa"] = "md5"
    language: str = "en"
    codecs: list[str] = Field(default_factory=lambda: list(DEFAULT_CODECS))
    dtmf_mode: Literal["rfc4733", "inband", "info", "auto"] = "rfc4733"
    nat: bool = True
    qualify: int = Field(default=60, ge=0, le=3600)
    readback_number: str = ""
    callerid_source: Literal["phones", "string"] = "phones"
    callerid_string: str = ""
    incoming_cid_override: Literal["", "replacenamewithnum", "replace", "prepend"] = ""
    incoming_cid_string: str = ""
    failover_provider_id: int | None = None
    manual_attributes: str = ""
    dialpatterns: list[str] = Field(default_factory=list)
    incoming_routes: list[IncomingRouteIn] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = v.config_value(value, N_("Name"))
        if not value:
            raise ValueError(_("Name is required"))
        return value

    @field_validator("host")
    @classmethod
    def _host(cls, value: str) -> str:
        return v.host(value)

    @field_validator("username")
    @classmethod
    def _user(cls, value: str) -> str:
        return v.sip_username(value)

    @field_validator("auth_user", "from_user")
    @classmethod
    def _opt_user(cls, value: str) -> str:
        return v.sip_username(value) if value.strip() else ""

    @field_validator("from_domain")
    @classmethod
    def _from_domain(cls, value: str) -> str:
        return v.host(value) if value.strip() else ""

    @field_validator("secret")
    @classmethod
    def _secret(cls, value: str) -> str:
        return v.secret(value) if value else ""

    @field_validator("language")
    @classmethod
    def _lang(cls, value: str) -> str:
        return v.language(value)

    @field_validator("codecs")
    @classmethod
    def _codecs(cls, value: list[str]) -> list[str]:
        return v.codecs(value)

    @field_validator("readback_number")
    @classmethod
    def _readback(cls, value: str) -> str:
        value = value.strip()
        if value and not value.lstrip("+").isdigit():
            raise ValueError(_("Public number must consist of digits"))
        return value

    @field_validator("callerid_string", "incoming_cid_string")
    @classmethod
    def _cid(cls, value: str) -> str:
        return v.config_value(value, N_("Caller ID")) if value else ""

    @field_validator("manual_attributes")
    @classmethod
    def _attrs(cls, value: str) -> str:
        return v.manual_attributes(value)

    @field_validator("dialpatterns")
    @classmethod
    def _patterns(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for pattern in value:
            if pattern.strip():
                pattern = v.dialpattern(pattern)
                if pattern not in out:
                    out.append(pattern)
        return out

    @model_validator(mode="after")
    def _cross(self) -> ProviderIn:
        if self.callerid_source == "string" and not self.callerid_string:
            raise ValueError("callerid_string: " + _("required when the caller id source is a fixed string"))
        if self.incoming_cid_override in ("replace", "prepend") and not self.incoming_cid_string:
            raise ValueError("incoming_cid_string: " + _("required for this caller id override"))
        if self.tech == "iax" and self.transport != "udp":
            self.transport = "udp"
        return self


def parse_provider(data: dict[str, Any]) -> ProviderIn:
    try:
        return parse(ProviderIn, data)
    except ServiceError as exc:
        fields = {}
        for key, msg in exc.fields.items():
            if key == "__all__" and ": " in msg:
                fname, fmsg = msg.split(": ", 1)
                fields[fname] = fmsg
            else:
                fields[key] = msg
        raise ServiceError(exc.message, fields) from None


def list_providers(session: Session, tech: str | None = None) -> list[Provider]:
    stmt = select(Provider).order_by(Provider.name)
    if tech:
        stmt = stmt.where(Provider.tech == tech)
    return list(session.scalars(stmt))


def get_provider(session: Session, provider_id: int) -> Provider:
    provider = session.get(Provider, provider_id)
    if provider is None:
        raise NotFound(_("Provider not found"))
    return provider


def defaults() -> dict[str, Any]:
    return {"tech": "pjsip", "codecs": list(DEFAULT_CODECS), "registration": True, "qualify": 60}


def to_dict(p: Provider, with_secret: bool = False) -> dict[str, Any]:
    data = {
        "id": p.id,
        "tech": p.tech,
        "name": p.name,
        "enabled": p.enabled,
        "host": p.host,
        "port": p.port,
        "transport": p.transport,
        "username": p.username,
        "auth_user": p.auth_user,
        "from_user": p.from_user,
        "from_domain": p.from_domain,
        "registration": p.registration,
        "iax_auth": p.iax_auth,
        "language": p.language,
        "codecs": list(p.codecs or []),
        "dtmf_mode": p.dtmf_mode,
        "nat": p.nat,
        "qualify": p.qualify,
        "readback_number": p.readback_number,
        "callerid_source": p.callerid_source,
        "callerid_string": p.callerid_string,
        "incoming_cid_override": p.incoming_cid_override,
        "incoming_cid_string": p.incoming_cid_string,
        "failover_provider_id": p.failover_provider_id,
        "manual_attributes": p.manual_attributes,
        "dialpatterns": [d.pattern for d in p.dialpatterns],
        "incoming_routes": [
            {"pattern": r.pattern, "dest_type": r.dest_type, "dest_id": r.dest_id} for r in p.incoming_routes
        ],
    }
    if with_secret:
        data["secret"] = p.secret
    return data


DEST_MODELS: dict[str, type] = {
    "phone": Phone,
    "callgroup": CallGroup,
    "application": Application,
    "conference": ConferenceRoom,
}


def destination_label(session: Session, dest_type: str, dest_id: int) -> str:
    model = DEST_MODELS.get(dest_type)
    obj = session.get(model, dest_id) if model else None
    if obj is None:
        return _("(missing %(type)s)", type=dest_type)
    if isinstance(obj, Phone):
        return f"{obj.callerid} <{obj.extension}>"
    if isinstance(obj, ConferenceRoom):
        return _("Conference %(name)s <%(number)s>", name=obj.name, number=obj.number)
    if isinstance(obj, CallGroup):
        if obj.extension:
            return _("Call group %(name)s <%(number)s>", name=obj.name, number=obj.extension)
        return _("Call group %(name)s", name=obj.name)
    return _("Application %(name)s <%(number)s>", name=obj.name, number=obj.extension)


def destinations(session: Session) -> list[tuple[str, str]]:
    """All possible incoming destinations as (``type:id``, label) for pickers."""
    out: list[tuple[str, str]] = []
    for phone in session.scalars(select(Phone).order_by(Phone.extension)):
        out.append((f"phone:{phone.id}", f"{phone.callerid} <{phone.extension}>"))
    for group in session.scalars(select(CallGroup).order_by(CallGroup.name)):
        out.append((f"callgroup:{group.id}", destination_label(session, "callgroup", group.id)))
    for room in session.scalars(select(ConferenceRoom).order_by(ConferenceRoom.number)):
        out.append((f"conference:{room.id}", destination_label(session, "conference", room.id)))
    for app in session.scalars(select(Application).order_by(Application.extension)):
        out.append((f"application:{app.id}", destination_label(session, "application", app.id)))
    return out


def _check_refs(session: Session, data: ProviderIn, own_id: int | None) -> None:
    for idx, route in enumerate(data.incoming_routes):
        model = DEST_MODELS[route.dest_type]
        if session.get(model, route.dest_id) is None:
            raise ServiceError(fields={f"incoming_routes.{idx}": _("Destination does not exist")})
    if data.failover_provider_id is not None:
        if data.failover_provider_id == own_id:
            raise ServiceError(fields={"failover_provider_id": _("A provider cannot fail over to itself")})
        if session.get(Provider, data.failover_provider_id) is None:
            raise ServiceError(fields={"failover_provider_id": _("Unknown provider")})
    # legacy pbx_dialpattern_exists(): identical patterns on two providers are ambiguous
    for pattern in data.dialpatterns:
        stmt = select(ProviderDialPattern).where(ProviderDialPattern.pattern == pattern)
        for other in session.scalars(stmt):
            if other.provider_id != own_id:
                name = session.get(Provider, other.provider_id).name  # type: ignore[union-attr]
                raise ServiceError(
                    fields={
                        "dialpatterns": _("Pattern %(pattern)s is already used by %(name)s", pattern=pattern, name=name)
                    }
                )


def _apply(provider: Provider, data: ProviderIn) -> None:
    for field in (
        "tech",
        "name",
        "enabled",
        "host",
        "port",
        "transport",
        "username",
        "auth_user",
        "from_user",
        "from_domain",
        "registration",
        "iax_auth",
        "language",
        "codecs",
        "dtmf_mode",
        "nat",
        "qualify",
        "readback_number",
        "callerid_source",
        "callerid_string",
        "incoming_cid_override",
        "incoming_cid_string",
        "failover_provider_id",
        "manual_attributes",
    ):
        setattr(provider, field, getattr(data, field))
    if data.secret:
        provider.secret = data.secret
    provider.dialpatterns = [ProviderDialPattern(pattern=p, position=i) for i, p in enumerate(data.dialpatterns)]
    provider.incoming_routes = [
        ProviderIncomingRoute(pattern=r.pattern, dest_type=r.dest_type, dest_id=r.dest_id, position=i)
        for i, r in enumerate(data.incoming_routes)
    ]


def create_provider(session: Session, data: ProviderIn, user: str = "") -> Provider:
    _check_refs(session, data, None)
    provider = Provider()
    _apply(provider, data)
    session.add(provider)
    session.flush()
    audit(session, user, "create", "provider", provider.id, provider.name)
    mark_dirty(session, "accounts", "dialplan")
    return provider


def update_provider(session: Session, provider_id: int, data: ProviderIn, user: str = "") -> Provider:
    provider = get_provider(session, provider_id)
    _check_refs(session, data, provider.id)
    before = to_dict(provider, with_secret=True)
    _apply(provider, data)
    session.flush()
    diff = diff_dicts(before, to_dict(provider, with_secret=True), hide={"secret"})
    audit(session, user, "update", "provider", provider.id, provider.name, diff)
    mark_dirty(session, "accounts", "dialplan")
    return provider


def set_enabled(session: Session, provider_id: int, enabled: bool, user: str = "") -> Provider:
    provider = get_provider(session, provider_id)
    provider.enabled = enabled
    audit(session, user, "enable" if enabled else "disable", "provider", provider.id, provider.name)
    mark_dirty(session, "accounts", "dialplan")
    return provider


def delete_provider(session: Session, provider_id: int, user: str = "") -> None:
    provider = get_provider(session, provider_id)
    audit(session, user, "delete", "provider", provider.id, provider.name)
    # external phones dialing through this provider lose their route
    for phone in session.scalars(select(Phone).where(Phone.dial_provider_id == provider.id)):
        phone.dial_provider_id = None
        phone.enabled = False
    session.delete(provider)
    session.flush()
    mark_dirty(session, "accounts", "dialplan")
