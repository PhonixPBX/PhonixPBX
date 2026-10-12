"""SQLAlchemy ORM models - the single source of truth for the PBX configuration.

Naming follows the legacy config.xml concepts (phones, providers, call groups,
applications, conference rooms) so the legacy importer maps 1:1. Every entity
that existed in config.xml carries ``legacy_uniqid`` to keep import/export
round-trips stable.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from phonix.core.db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


# --- enumerations (stored as plain strings) ---------------------------------

PHONE_TECHS = ("pjsip", "iax", "external")
PROVIDER_TECHS = ("pjsip", "iax")
DTMF_MODES = ("rfc4733", "inband", "info", "auto")
EXTERNAL_DIAL_TYPES = ("sip_uri", "iax_uri", "provider")
CALLERID_SOURCES = ("phones", "string")
INCOMING_CID_OVERRIDES = ("", "replacenamewithnum", "replace", "prepend")
DESTINATION_TYPES = ("phone", "callgroup", "application", "conference")
CALLGROUP_STRATEGIES = ("ringall", "linear")
IAX_AUTH = ("md5", "plaintext", "rsa")
SIP_TRANSPORTS = ("udp", "tcp", "tls")
MEDIA_KINDS = ("moh", "vm_greeting", "prompt")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="admin")
    must_change_pw: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    last_login: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    # web interface language (phonix.i18n.LANGUAGE_NAMES); None = English
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    api_tokens: Mapped[list[ApiToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class ApiToken(Base):
    """Bearer token for /api/v1; only the sha256 of the token is stored."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # start of the token, to recognise it in lists
    prefix: Mapped[str] = mapped_column(String(16))
    read_only: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    # None = unlimited
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="api_tokens")


class Setting(Base):
    """One row per settings group; ``data`` holds the pydantic model as JSON."""

    __tablename__ = "settings"

    group: Mapped[str] = mapped_column(String(32), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PhoneBlockedProvider(Base):
    """Providers a phone may NOT use for outgoing calls (legacy "Block Providers")."""

    __tablename__ = "phone_blocked_providers"

    phone_id: Mapped[int] = mapped_column(ForeignKey("phones.id", ondelete="CASCADE"), primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), primary_key=True)


class PhoneProviderCallerId(Base):
    """Per phone + provider outgoing caller id override (legacy outgoingcalleridmap)."""

    __tablename__ = "phone_provider_callerids"

    phone_id: Mapped[int] = mapped_column(ForeignKey("phones.id", ondelete="CASCADE"), primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), primary_key=True)
    callerid: Mapped[str] = mapped_column(String(128))


class Phone(Base):
    __tablename__ = "phones"

    id: Mapped[int] = mapped_column(primary_key=True)
    tech: Mapped[str] = mapped_column(String(16))
    extension: Mapped[str] = mapped_column(String(32), unique=True)
    callerid: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(255), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # seconds to ring; None = ring indefinitely
    ringlength: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="en")

    # sip / iax account
    secret: Mapped[str] = mapped_column(String(128), default="")
    codecs: Mapped[list[str]] = mapped_column(JSON, default=list)
    dtmf_mode: Mapped[str] = mapped_column(String(16), default="rfc4733")
    nat: Mapped[bool] = mapped_column(Boolean, default=True)
    qualify: Mapped[int] = mapped_column(Integer, default=60)
    max_contacts: Mapped[int] = mapped_column(Integer, default=1)
    busylevel: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # reachable from providers / anonymous callers
    public_access: Mapped[bool] = mapped_column(Boolean, default=False)
    public_name: Mapped[str] = mapped_column(String(64), default="")

    # voicemail / notifications
    vm_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    vm_pin: Mapped[str] = mapped_column(String(16), default="")
    vm_email: Mapped[str] = mapped_column(String(255), default="")
    notify_missed: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_email: Mapped[str] = mapped_column(String(255), default="")

    # external phones (tech == "external")
    dial_type: Mapped[str] = mapped_column(String(16), default="provider")
    dial_provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id", ondelete="SET NULL"), nullable=True)
    dial_string: Mapped[str] = mapped_column(String(255), default="")

    # raw "key=value" lines appended to the generated endpoint section
    manual_attributes: Mapped[str] = mapped_column(Text, default="")
    legacy_uniqid: Mapped[str | None] = mapped_column(String(64), nullable=True)

    blocked_providers: Mapped[list[Provider]] = relationship(
        secondary="phone_blocked_providers", lazy="selectin", order_by="Provider.name"
    )
    provider_callerids: Mapped[list[PhoneProviderCallerId]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    dial_provider: Mapped[Provider | None] = relationship(foreign_keys=[dial_provider_id], lazy="selectin")


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    tech: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transport: Mapped[str] = mapped_column(String(8), default="udp")
    username: Mapped[str] = mapped_column(String(128))
    secret: Mapped[str] = mapped_column(String(128), default="")
    auth_user: Mapped[str] = mapped_column(String(128), default="")
    from_user: Mapped[str] = mapped_column(String(128), default="")
    from_domain: Mapped[str] = mapped_column(String(255), default="")
    registration: Mapped[bool] = mapped_column(Boolean, default=True)
    iax_auth: Mapped[str] = mapped_column(String(16), default="md5")

    language: Mapped[str] = mapped_column(String(16), default="en")
    codecs: Mapped[list[str]] = mapped_column(JSON, default=list)
    dtmf_mode: Mapped[str] = mapped_column(String(16), default="rfc4733")
    nat: Mapped[bool] = mapped_column(Boolean, default=True)
    qualify: Mapped[int] = mapped_column(Integer, default=60)

    # number read back to callers / used as default incoming DID
    readback_number: Mapped[str] = mapped_column(String(32), default="")
    # outgoing caller id
    callerid_source: Mapped[str] = mapped_column(String(16), default="phones")
    callerid_string: Mapped[str] = mapped_column(String(128), default="")
    # incoming caller id manipulation
    incoming_cid_override: Mapped[str] = mapped_column(String(32), default="")
    incoming_cid_string: Mapped[str] = mapped_column(String(128), default="")

    failover_provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("providers.id", ondelete="SET NULL"), nullable=True
    )
    manual_attributes: Mapped[str] = mapped_column(Text, default="")
    legacy_uniqid: Mapped[str | None] = mapped_column(String(64), nullable=True)

    dialpatterns: Mapped[list[ProviderDialPattern]] = relationship(
        cascade="all, delete-orphan",
        order_by="ProviderDialPattern.position",
        lazy="selectin",
    )
    incoming_routes: Mapped[list[ProviderIncomingRoute]] = relationship(
        cascade="all, delete-orphan",
        order_by="ProviderIncomingRoute.position",
        lazy="selectin",
    )
    failover_provider: Mapped[Provider | None] = relationship(remote_side=[id], lazy="selectin")


class ProviderDialPattern(Base):
    """Outgoing pattern in legacy syntax: ``[addprefix+][stripprefix|]pattern``."""

    __tablename__ = "provider_dialpatterns"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"))
    pattern: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, default=0)


class ProviderIncomingRoute(Base):
    """Maps incoming numbers (pattern, empty = catch-all) to a destination."""

    __tablename__ = "provider_incoming_routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"))
    pattern: Mapped[str] = mapped_column(String(64), default="")
    dest_type: Mapped[str] = mapped_column(String(16))
    dest_id: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=0)


class CallGroup(Base):
    __tablename__ = "callgroups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    extension: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    strategy: Mapped[str] = mapped_column(String(16), default="ringall")
    ringlength: Mapped[int | None] = mapped_column(Integer, nullable=True)
    public_access: Mapped[bool] = mapped_column(Boolean, default=False)
    public_name: Mapped[str] = mapped_column(String(64), default="")
    legacy_uniqid: Mapped[str | None] = mapped_column(String(64), nullable=True)

    members: Mapped[list[CallGroupMember]] = relationship(
        cascade="all, delete-orphan", order_by="CallGroupMember.position", lazy="selectin"
    )


class CallGroupMember(Base):
    __tablename__ = "callgroup_members"
    __table_args__ = (UniqueConstraint("group_id", "phone_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("callgroups.id", ondelete="CASCADE"))
    phone_id: Mapped[int] = mapped_column(ForeignKey("phones.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)

    phone: Mapped[Phone] = relationship(lazy="selectin")


class ConferenceRoom(Base):
    __tablename__ = "conference_rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    pin: Mapped[str] = mapped_column(String(16), default="")
    admin_pin: Mapped[str] = mapped_column(String(16), default="")
    public_access: Mapped[bool] = mapped_column(Boolean, default=False)
    public_name: Mapped[str] = mapped_column(String(64), default="")
    legacy_uniqid: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Application(Base):
    """Custom dialplan snippet; ``logic`` holds ``priority,App(args)`` lines."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    extension: Mapped[str] = mapped_column(String(32), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    logic: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    public_access: Mapped[bool] = mapped_column(Boolean, default=False)
    public_name: Mapped[str] = mapped_column(String(64), default="")
    legacy_uniqid: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AmiUser(Base):
    __tablename__ = "ami_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    secret: Mapped[str] = mapped_column(String(128))
    # list of CIDRs allowed to connect
    permit: Mapped[list[str]] = mapped_column(JSON, default=list)
    read_perms: Mapped[list[str]] = mapped_column(JSON, default=list)
    write_perms: Mapped[list[str]] = mapped_column(JSON, default=list)
    legacy_uniqid: Mapped[str | None] = mapped_column(String(64), nullable=True)


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(128))
    # path relative to the media directory
    path: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(32))
    object_type: Mapped[str] = mapped_column(String(32), default="")
    object_id: Mapped[str] = mapped_column(String(64), default="")
    summary: Mapped[str] = mapped_column(String(255), default="")
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Dirty(Base):
    """Areas with saved-but-not-applied changes (drives the "Apply" banner)."""

    __tablename__ = "dirty"

    area: Mapped[str] = mapped_column(String(32), primary_key=True)
    since: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
