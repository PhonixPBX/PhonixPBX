# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
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
    CheckConstraint,
    Date,
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
DESTINATION_TYPES = ("phone", "callgroup", "application", "conference", "ivr", "hours")
CALLGROUP_STRATEGIES = ("ringall", "linear")
IAX_AUTH = ("md5", "plaintext", "rsa")
SIP_TRANSPORTS = ("udp", "tcp", "tls")
MEDIA_KINDS = ("moh", "vm_greeting", "ivr_prompt")


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
    # may place calls (POST /api/v1/calls, MCP originate_call), independent of read_only
    allow_calls: Mapped[bool] = mapped_column(Boolean, default=False)
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
    # language of the voicemail and missed call e-mails; "" = same as ``language``
    notify_language: Mapped[str] = mapped_column(String(16), default="")

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
        cascade="all, delete-orphan",
        order_by="CallGroupMember.position",
        lazy="selectin",
        foreign_keys="CallGroupMember.group_id",
    )


class CallGroupMember(Base):
    """One member of a call group: either a phone or another call group."""

    __tablename__ = "callgroup_members"
    __table_args__ = (
        UniqueConstraint("group_id", "phone_id"),
        UniqueConstraint("group_id", "member_group_id"),
        CheckConstraint("(phone_id IS NULL) != (member_group_id IS NULL)", name="ck_callgroup_member_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("callgroups.id", ondelete="CASCADE"))
    phone_id: Mapped[int | None] = mapped_column(ForeignKey("phones.id", ondelete="CASCADE"), nullable=True)
    member_group_id: Mapped[int | None] = mapped_column(ForeignKey("callgroups.id", ondelete="CASCADE"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    phone: Mapped[Phone | None] = relationship(lazy="selectin")
    member_group: Mapped[CallGroup | None] = relationship(lazy="selectin", foreign_keys=[member_group_id])

    @property
    def ref(self) -> str:
        """``phone:<id>`` or ``callgroup:<id>``, the notation of the API ``members`` field."""
        if self.member_group_id is not None:
            return f"callgroup:{self.member_group_id}"
        return f"phone:{self.phone_id}"


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


class IvrMenu(Base):
    """Voice menu (auto attendant): an announcement, then one destination per key.

    Destinations are ``(type, id)`` pairs like provider incoming routes (see
    ``phonix.services.destinations``); ``repeat`` and ``hangup`` need no id.
    """

    __tablename__ = "ivr_menus"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    extension: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    public_access: Mapped[bool] = mapped_column(Boolean, default=False)
    public_name: Mapped[str] = mapped_column(String(64), default="")
    # announcement: an uploaded prompt (media file) or an Asterisk sound
    prompt_mode: Mapped[str] = mapped_column(String(16), default="upload")
    prompt_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True
    )
    prompt_sound: Mapped[str] = mapped_column(String(64), default="")
    # recording script for the announcement (text only, not played)
    prompt_text: Mapped[str] = mapped_column(Text, default="")
    # seconds to wait for a key after the announcement
    timeout: Mapped[int] = mapped_column(Integer, default=5)
    # how often the announcement is repeated before the timeout destination
    repeats: Mapped[int] = mapped_column(Integer, default=2)
    # callers may dial internal (or, from outside, public) numbers directly
    direct_dial: Mapped[bool] = mapped_column(Boolean, default=False)
    timeout_dest_type: Mapped[str] = mapped_column(String(16), default="hangup")
    timeout_dest_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invalid_dest_type: Mapped[str] = mapped_column(String(16), default="repeat")
    invalid_dest_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    legacy_uniqid: Mapped[str | None] = mapped_column(String(64), nullable=True)

    options: Mapped[list[IvrOption]] = relationship(
        cascade="all, delete-orphan", order_by="IvrOption.position", lazy="selectin"
    )
    prompt_media: Mapped[MediaFile | None] = relationship(lazy="selectin")


class IvrOption(Base):
    __tablename__ = "ivr_options"
    __table_args__ = (UniqueConstraint("menu_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("ivr_menus.id", ondelete="CASCADE"))
    # 0-9, * or #
    key: Mapped[str] = mapped_column(String(1))
    label: Mapped[str] = mapped_column(String(80), default="")
    dest_type: Mapped[str] = mapped_column(String(16))
    dest_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # order of the announcement (and of the list in the UI)
    position: Mapped[int] = mapped_column(Integer, default=0)


class BusinessHours(Base):
    """Time switch: one destination while open, another while closed.

    The live mode (automatic, forced open, forced closed) is runtime state in the
    Asterisk database, like call forwarding, so a feature code can switch it
    without an apply.
    """

    __tablename__ = "business_hours"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(255), default="")
    # dialled on an internal phone: toggles between automatic and closed ("" = none)
    feature_code: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    open_dest_type: Mapped[str] = mapped_column(String(16))
    open_dest_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    closed_dest_type: Mapped[str] = mapped_column(String(16))
    closed_dest_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    legacy_uniqid: Mapped[str | None] = mapped_column(String(64), nullable=True)

    ranges: Mapped[list[BusinessHoursRange]] = relationship(
        cascade="all, delete-orphan",
        order_by="(BusinessHoursRange.weekday, BusinessHoursRange.start)",
        lazy="selectin",
    )
    holidays: Mapped[list[BusinessHoursHoliday]] = relationship(
        cascade="all, delete-orphan", order_by="BusinessHoursHoliday.date", lazy="selectin"
    )


class BusinessHoursRange(Base):
    """Open from ``start`` to ``end`` ("HH:MM", end exclusive) on ``weekday`` (0 = Monday)."""

    __tablename__ = "business_hours_ranges"

    id: Mapped[int] = mapped_column(primary_key=True)
    hours_id: Mapped[int] = mapped_column(ForeignKey("business_hours.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(Integer)
    start: Mapped[str] = mapped_column(String(5))
    end: Mapped[str] = mapped_column(String(5))


class BusinessHoursHoliday(Base):
    """Closed all day; ``yearly`` holidays repeat on the same day every year."""

    __tablename__ = "business_hours_holidays"

    id: Mapped[int] = mapped_column(primary_key=True)
    hours_id: Mapped[int] = mapped_column(ForeignKey("business_hours.id", ondelete="CASCADE"))
    date: Mapped[dt.date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(80), default="")
    yearly: Mapped[bool] = mapped_column(Boolean, default=False)


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
