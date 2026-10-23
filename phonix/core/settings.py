# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Typed settings groups stored as JSON rows in the ``settings`` table.

Each group is a pydantic model with sane defaults, so a fresh database (or a
partially filled one after an upgrade) always yields a complete configuration.
"""

from __future__ import annotations

import re
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from phonix.core import validation as v
from phonix.core.models import Setting
from phonix.core.shacrypt import HASH_RE
from phonix.i18n import N_, _


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
    # announce <hostname>.local and the web interface on the LAN (mDNS/DNS-SD)
    mdns_enabled: bool = True
    ssh_enabled: bool = False
    # root password for SSH logins (SHA-512 crypt, see core/shacrypt); empty = keys only
    ssh_password_hash: str = ""

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

    @field_validator("ssh_password_hash")
    @classmethod
    def _ssh_password_hash(cls, value: str) -> str:
        if value and not HASH_RE.match(value):
            raise ValueError(_("Invalid password hash"))
        return value

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


# control characters other than line breaks and tabs
_TEXT_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class NotificationTexts(BaseModel):
    """E-mail texts of one language; an empty text uses the built-in (translated) default."""

    model_config = ConfigDict(extra="ignore")
    vm_subject: str = Field(default="", max_length=200)
    vm_body: str = Field(default="", max_length=4000)
    missed_subject: str = Field(default="", max_length=200)
    missed_body: str = Field(default="", max_length=4000)

    @field_validator("vm_subject", "missed_subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        return v.no_control(value.strip(), N_("Subject"))

    @field_validator("vm_body", "missed_body")
    @classmethod
    def _body(cls, value: str) -> str:
        value = value.replace("\r\n", "\n").rstrip()
        if _TEXT_CONTROL.search(value):
            raise ValueError(_("The text must not contain control characters"))
        return value

    @property
    def empty(self) -> bool:
        return not (self.vm_subject or self.vm_body or self.missed_subject or self.missed_body)


class VoicemailSettings(SettingsGroup):
    group: str = Field(default="voicemail", exclude=True)
    from_address: str = ""
    from_name: str = "PhonixPBX Voicemail"
    attach_audio: bool = True
    keep_messages: bool = True
    max_message_seconds: int = Field(default=180, ge=10, le=3600)
    # language -> customised voicemail and missed call e-mail texts
    templates: dict[str, NotificationTexts] = Field(default_factory=dict)

    @field_validator("from_address")
    @classmethod
    def _from(cls, value: str) -> str:
        return v.email(value) if value else ""

    @field_validator("templates")
    @classmethod
    def _templates(cls, value: dict[str, NotificationTexts]) -> dict[str, NotificationTexts]:
        return {v.language(lang): texts for lang, texts in sorted(value.items()) if not texts.empty}


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


class OutgoingSettings(SettingsGroup):
    group: str = Field(default="outgoing", exclude=True)
    # a dialled "+41..." becomes "<plus_replacement>41..." before the dial patterns are matched
    # ("+" separates the prefix to add in a dial pattern, so no pattern can match it); empty = off
    plus_replacement: str = "00"

    @field_validator("plus_replacement")
    @classmethod
    def _plus(cls, value: str) -> str:
        return v.plus_replacement(value)


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


ACME_SERVERS = {
    "letsencrypt": "https://acme-v02.api.letsencrypt.org/directory",
    "letsencrypt-staging": "https://acme-staging-v02.api.letsencrypt.org/directory",
    "zerossl": "https://acme.zerossl.com/v2/DV90",
}
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
# variables lego must not get from the provider credentials
_ENV_RESERVED = ("PATH", "HOME", "LD_", "LEGO_", "SSL_CERT_")


class AcmeSettings(SettingsGroup):
    """Certificate from an ACME CA (Let's Encrypt, ZeroSSL, ...) obtained with lego."""

    group: str = Field(default="acme", exclude=True)
    enabled: bool = False
    email: str = ""
    server: Literal["letsencrypt", "letsencrypt-staging", "zerossl", "custom"] = "letsencrypt"
    server_url: str = ""
    # external account binding (ZeroSSL, some private CAs)
    eab_kid: str = ""
    eab_hmac: str = ""
    # empty = hostname.domain from the system settings
    domains: list[str] = Field(default_factory=list)
    challenge: Literal["http", "dns"] = "http"
    # lego DNS provider code and its credentials (environment variables)
    dns_provider: str = ""
    dns_env: dict[str, str] = Field(default_factory=dict)
    dns_resolvers: list[str] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return v.email(value) if value else ""

    @field_validator("server_url")
    @classmethod
    def _server_url(cls, value: str) -> str:
        value = v.no_control(value.strip(), "URL")
        if value and not value.startswith("https://"):
            raise ValueError(_("The directory URL must start with https://"))
        return value

    @field_validator("eab_kid", "eab_hmac")
    @classmethod
    def _eab(cls, value: str) -> str:
        value = value.strip()
        if value and not re.fullmatch(r"[A-Za-z0-9_=+/-]{1,512}", value):
            raise ValueError(_("Invalid characters"))
        return value

    @field_validator("domains")
    @classmethod
    def _domains(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for item in value:
            item = item.strip().lower()
            if not item:
                continue
            name = item[2:] if item.startswith("*.") else item
            if "." not in v.domain(name):
                raise ValueError(_("%(name)s is not a fully qualified domain name", name=item))
            if item not in out:
                out.append(item)
        return out

    @field_validator("dns_provider")
    @classmethod
    def _provider(cls, value: str) -> str:
        value = value.strip()
        if value and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", value):
            raise ValueError(_("Invalid DNS provider code"))
        return value

    @field_validator("dns_env")
    @classmethod
    def _dns_env(cls, value: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for key, val in value.items():
            key = key.strip()
            if not _ENV_NAME.match(key) or key.startswith(_ENV_RESERVED):
                raise ValueError(_("Invalid variable name %(name)r", name=key))
            out[key] = v.no_control(val.strip(), key)
        return out

    @field_validator("dns_resolvers")
    @classmethod
    def _resolvers(cls, value: list[str]) -> list[str]:
        out = []
        for item in value:
            item = item.strip()
            if not item:
                continue
            host, _sep, port = item.rpartition(":") if item.count(":") == 1 else (item, "", "")
            v.host(host)
            if port and not (port.isdigit() and 0 < int(port) < 65536):
                raise ValueError(_("Invalid port in %(value)s", value=item))
            out.append(item)
        return out

    @model_validator(mode="after")
    def _consistent(self) -> AcmeSettings:
        if self.challenge == "http" and any(d.startswith("*.") for d in self.domains):
            raise ValueError(_("Wildcard domains need DNS validation"))
        if self.enabled:
            if not self.email:
                raise ValueError(_("An e-mail address is required for the ACME account"))
            if self.server == "custom" and not self.server_url:
                raise ValueError(_("Enter the directory URL of the ACME server"))
            if self.server == "zerossl" and not (self.eab_kid and self.eab_hmac):
                raise ValueError(_("ZeroSSL needs the EAB key ID and HMAC key from the ZeroSSL dashboard"))
            if self.challenge == "dns" and not self.dns_provider:
                raise ValueError(_("Choose a DNS provider"))
        return self

    @property
    def directory_url(self) -> str:
        return self.server_url if self.server == "custom" else ACME_SERVERS[self.server]


class GuiSettings(SettingsGroup):
    group: str = Field(default="gui", exclude=True)
    # no longer shown (forms use tabs, nothing is collapsed); kept so config.json stays compatible
    expand_advanced: bool = False
    session_minutes: int = Field(default=60, ge=5, le=24 * 60)


# latest non-pre-release of the project (the rolling "nightly" is a pre-release)
DEFAULT_UPDATE_CHECK_URL = "https://api.github.com/repos/PhonixPBX/PhonixPBX/releases/latest"


class UpdateSettings(SettingsGroup):
    group: str = Field(default="update", exclude=True)
    check_url: str = DEFAULT_UPDATE_CHECK_URL
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
    OutgoingSettings,
    MediaSettings,
    FirewallSettings,
    AcmeSettings,
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
