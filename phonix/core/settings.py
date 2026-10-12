"""Typed settings groups stored as JSON rows in the ``settings`` table.

Each group is a pydantic model with sane defaults, so a fresh database (or a
partially filled one after an upgrade) always yields a complete configuration.
"""

from __future__ import annotations

from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from phonix.core import validation as v
from phonix.core.models import Setting


class SettingsGroup(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)
    group: str = Field(default="", exclude=True)


class SystemSettings(SettingsGroup):
    group: str = Field(default="system", exclude=True)
    hostname: str = "phonix"
    domain: str = "local"
    timezone: str = "UTC"
    # Asterisk indications zone (dial/busy tones)
    tonezone: str = "us"
    # default Asterisk prompt language
    prompt_language: str = "en"
    # web UI language
    ui_language: str = "en"
    ntp_servers: list[str] = Field(default_factory=lambda: ["pool.ntp.org"])
    ssh_enabled: bool = False

    @field_validator("hostname")
    @classmethod
    def _hostname(cls, value: str) -> str:
        return v.hostname_label(value)

    @field_validator("domain")
    @classmethod
    def _domain(cls, value: str) -> str:
        return v.domain(value)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        return v.timezone(value)

    @field_validator("ntp_servers")
    @classmethod
    def _ntp(cls, value: list[str]) -> list[str]:
        return [v.host(s) for s in value if s.strip()]

    @field_validator("tonezone")
    @classmethod
    def _tonezone(cls, value: str) -> str:
        return v.tonezone(value)

    @field_validator("prompt_language", "ui_language")
    @classmethod
    def _lang(cls, value: str) -> str:
        return v.language(value)


class NetworkSettings(SettingsGroup):
    group: str = Field(default="network", exclude=True)
    interface: str = "eth0"
    mode: Literal["dhcp", "static"] = "dhcp"
    address: str = "192.168.1.2"
    prefix: int = Field(default=24, ge=1, le=32)
    gateway: str = ""
    dns_servers: list[str] = Field(default_factory=list)
    ipv6: Literal["auto", "off"] = "auto"
    # NAT topology for SIP/RTP (legacy interfaces/lan/topology)
    topology: Literal["public", "natstatic", "natdynamichost"] = "public"
    external_address: str = ""
    external_hostname: str = ""

    @field_validator("interface")
    @classmethod
    def _iface(cls, value: str) -> str:
        return v.interface_name(value)

    @field_validator("address")
    @classmethod
    def _addr(cls, value: str) -> str:
        return v.ipv4(value)

    @field_validator("gateway", "external_address")
    @classmethod
    def _optional_ip(cls, value: str) -> str:
        return v.ipv4(value) if value else ""

    @field_validator("external_hostname")
    @classmethod
    def _ext_host(cls, value: str) -> str:
        return v.host(value) if value else ""

    @field_validator("dns_servers")
    @classmethod
    def _dns(cls, value: list[str]) -> list[str]:
        return [v.ip(s) for s in value if s.strip()]


class RtpSettings(SettingsGroup):
    group: str = Field(default="rtp", exclude=True)
    port_start: int = Field(default=10000, ge=1024, le=65535)
    port_end: int = Field(default=20000, ge=1024, le=65535)


class SipSettings(SettingsGroup):
    group: str = Field(default="sip", exclude=True)
    udp_port: int = Field(default=5060, ge=1, le=65535)
    tcp_enabled: bool = False
    tls_enabled: bool = False
    tls_port: int = Field(default=5061, ge=1, le=65535)
    default_expiry: int = Field(default=3600, ge=60)
    min_expiry: int = Field(default=60, ge=10)
    max_expiry: int = Field(default=7200, ge=60)
    srv_lookup: bool = True
    # SRTP offered to endpoints that support it
    srtp: Literal["off", "optional"] = "off"
    # raw lines appended to the [global] section
    manual_attributes: str = ""


class IaxSettings(SettingsGroup):
    group: str = Field(default="iax", exclude=True)
    enabled: bool = True
    port: int = Field(default=4569, ge=1, le=65535)
    jitterbuffer: bool = False
    force_jitterbuffer: bool = False
    manual_attributes: str = ""


class VoicemailSettings(SettingsGroup):
    group: str = Field(default="voicemail", exclude=True)
    from_address: str = ""
    from_name: str = "PhonixPBX Voicemail"
    attach_audio: bool = True
    keep_messages: bool = True
    max_message_seconds: int = Field(default=180, ge=10, le=3600)
    custom_subject: str = ""
    custom_body: str = ""

    @field_validator("from_address")
    @classmethod
    def _from(cls, value: str) -> str:
        return v.email(value) if value else ""


class EmailSettings(SettingsGroup):
    group: str = Field(default="email", exclude=True)
    host: str = ""
    port: int = Field(default=587, ge=1, le=65535)
    encryption: Literal["none", "starttls", "tls"] = "starttls"
    auth: bool = True
    username: str = ""
    password: str = ""
    from_address: str = ""
    verify_cert: bool = True

    @field_validator("host")
    @classmethod
    def _host(cls, value: str) -> str:
        return v.host(value) if value else ""

    @field_validator("from_address")
    @classmethod
    def _from(cls, value: str) -> str:
        return v.email(value) if value else ""

    @property
    def configured(self) -> bool:
        return bool(self.host and self.from_address)


class FeatureSettings(SettingsGroup):
    group: str = Field(default="features", exclude=True)
    attended_transfer: str = "**"
    blind_transfer: str = "##"
    disconnect: str = "*0"
    pickup: str = "*8"
    feature_digit_timeout_ms: int = Field(default=1000, ge=100, le=10000)
    transfer_digit_timeout_s: int = Field(default=3, ge=1, le=60)
    atxfer_noanswer_timeout_s: int = Field(default=15, ge=1, le=600)
    park_ext: str = "700"
    park_start: int = 701
    park_end: int = 720
    park_time_s: int = Field(default=45, ge=5, le=3600)

    @field_validator("attended_transfer", "blind_transfer", "disconnect", "pickup")
    @classmethod
    def _code(cls, value: str) -> str:
        return v.feature_code(value)


class MediaSettings(SettingsGroup):
    group: str = Field(default="media", exclude=True)
    custom_moh: bool = False
    custom_vm_greeting: bool = False


class FirewallSettings(SettingsGroup):
    group: str = Field(default="firewall", exclude=True)
    enabled: bool = True
    # networks allowed to reach SIP/IAX signalling; empty = everyone
    sip_allowed_networks: list[str] = Field(default_factory=list)
    # networks allowed to reach the web UI and SSH; empty = everyone
    admin_allowed_networks: list[str] = Field(default_factory=list)
    ban_enabled: bool = True
    ban_threshold: int = Field(default=10, ge=1, le=1000)
    ban_seconds: int = Field(default=3600, ge=60)

    @field_validator("sip_allowed_networks", "admin_allowed_networks")
    @classmethod
    def _nets(cls, value: list[str]) -> list[str]:
        return [v.network(s) for s in value if s.strip()]


class GuiSettings(SettingsGroup):
    group: str = Field(default="gui", exclude=True)
    expand_advanced: bool = False
    session_minutes: int = Field(default=60, ge=5, le=24 * 60)


class UpdateSettings(SettingsGroup):
    group: str = Field(default="update", exclude=True)
    check_url: str = ""
    auto_check: bool = False


ALL_GROUPS: tuple[type[SettingsGroup], ...] = (
    SystemSettings,
    NetworkSettings,
    RtpSettings,
    SipSettings,
    IaxSettings,
    VoicemailSettings,
    EmailSettings,
    FeatureSettings,
    MediaSettings,
    FirewallSettings,
    GuiSettings,
    UpdateSettings,
)

T = TypeVar("T", bound=SettingsGroup)


def group_name(model: type[SettingsGroup]) -> str:
    default = model.model_fields["group"].default
    assert isinstance(default, str)
    return default


def load(session: Session, model: type[T]) -> T:
    row = session.get(Setting, group_name(model))
    data = row.data if row else {}
    try:
        return model.model_validate(data)
    except ValueError:
        # stored data no longer validates (e.g. after a rule change): keep
        # every field that still validates on its own, default the rest
        clean = {}
        for key, value in data.items():
            try:
                model.model_validate({key: value})
                clean[key] = value
            except ValueError:
                continue
        return model.model_validate(clean)


def save(session: Session, value: SettingsGroup) -> None:
    name = group_name(type(value))
    row = session.get(Setting, name)
    data = value.model_dump(mode="json")
    if row is None:
        session.add(Setting(group=name, data=data))
    else:
        row.data = data
    session.flush()


def load_all(session: Session) -> dict[str, SettingsGroup]:
    return {group_name(m): load(session, m) for m in ALL_GROUPS}
