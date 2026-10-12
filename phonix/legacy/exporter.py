"""Export the PhonixPBX configuration as a legacy ``config.xml`` (version 2.1).

The inverse of the importer, for rolling back to the old firmware or for
interoperability. Objects keep their ``legacy_uniqid``; objects created in PhonixPBX
get a stable, legacy-looking uniqid derived from their database id, so
exporting twice yields the same references.

The file layout follows PHP's ``array_to_xml()``: tab indentation, list tags
repeated, ``true`` written as an empty element and ``false`` left out. PhonixPBX-only
data that config.xml cannot represent is listed in the :class:`ExportReport`.

The file contains plaintext secrets (the legacy format requires them), so each
export is recorded in the audit log.
"""

from __future__ import annotations

import base64
import re
import time
from typing import Any
from xml.sax.saxutils import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix.core import settings as st
from phonix.core.models import (
    AmiUser,
    Application,
    CallGroup,
    ConferenceRoom,
    Phone,
    Provider,
    User,
)
from phonix.legacy import mapping as m
from phonix.legacy.report import ExportReport
from phonix.legacy.upgrade import LATEST
from phonix.services.common import audit

ROOT_TAG = "askoziapbx"
# placeholder for the legacy web login: PhonixPBX only stores password hashes
DEFAULT_LEGACY_PASSWORD = "askozia"  # noqa: S105 - legacy factory default, reported


def export(session: Session, user: str = "") -> tuple[bytes, ExportReport]:
    """Return ``(config.xml bytes, report)`` for the current configuration."""
    report = ExportReport()
    tree = build_tree(session, report)
    xml = emit(tree)
    audit(
        session,
        user,
        "legacy-export",
        "config",
        "",
        "Exported legacy config.xml (contains plaintext secrets)",
        {"counts": report.counts},
    )
    return xml, report


class _Uniqids:
    """Legacy uniqid for every exported object (reused or generated)."""

    def __init__(self) -> None:
        self.ids: dict[tuple[str, int], str] = {}
        self.used: set[str] = set()

    def register(self, kind: str, tech: str, obj: Any) -> None:
        uniqid = obj.legacy_uniqid
        if not uniqid or uniqid in self.used:
            uniqid = m.generated_uniqid(kind, tech, obj.id)
        self.used.add(uniqid)
        self.ids[(kind, obj.id)] = uniqid

    def __call__(self, kind: str, obj_id: int) -> str:
        return self.ids[(kind, obj_id)]


def build_tree(session: Session, report: ExportReport) -> dict[str, Any]:
    phones = list(session.scalars(select(Phone).order_by(Phone.id)))
    providers = list(session.scalars(select(Provider).order_by(Provider.id)))
    groups = list(session.scalars(select(CallGroup).order_by(CallGroup.id)))
    rooms = list(session.scalars(select(ConferenceRoom).order_by(ConferenceRoom.id)))
    apps = list(session.scalars(select(Application).order_by(Application.id)))
    ami_users = list(session.scalars(select(AmiUser).order_by(AmiUser.username)))

    uid = _Uniqids()
    for p in phones:
        uid.register("phone", p.tech, p)
    for pr in providers:
        uid.register("provider", pr.tech, pr)
    for g in groups:
        uid.register("callgroup", "", g)
    for r in rooms:
        uid.register("conference", "", r)
    for a in apps:
        uid.register("application", "", a)

    def phones_of(tech: str) -> list[dict[str, Any]]:
        return [m.phone_out(p, uid, report) for p in phones if p.tech == tech]

    def providers_of(tech: str) -> list[dict[str, Any]]:
        out = []
        for pr in providers:
            if pr.tech != tech:
                continue
            routes = [(r.pattern, r.dest_type, r.dest_id) for r in pr.incoming_routes]
            out.append(m.provider_out(pr, uid, routes, report))
        return out

    cfg = st.load_all(session)
    tree: dict[str, Any] = {
        "version": LATEST,
        "lastchange": str(int(time.time())),
        "system": _system(session, cfg, report),
        "interfaces": {"lan": _lan(cfg, report)},
        "sip": {"phone": phones_of("pjsip"), "provider": providers_of("pjsip")},
        "iax": {"phone": phones_of("iax"), "provider": providers_of("iax")},
        "external": {"phone": phones_of("external")},
        "conferencing": {"room": [m.room_out(r, uid) for r in rooms]},
        "dialplan": {
            "application": [m.application_out(a, uid) for a in apps],
            "callgroup": [m.callgroup_out(g, uid, report) for g in groups],
            **_features(cfg, report),
        },
        "voicemail": _voicemail(cfg, report),
        "notifications": {"email": _email(cfg, report)},
        "services": {
            **_services(cfg, report),
            "manager": {"manager-user": [m.ami_user_out(u, report) for u in ami_users]},
        },
    }
    report.counts = {
        "phones": len(phones),
        "providers": len(providers),
        "callgroups": len(groups),
        "rooms": len(rooms),
        "applications": len(apps),
        "ami_users": len(ami_users),
    }
    for group in ("firewall", "gui", "update", "media"):
        defaults = type(cfg[group])().model_dump()
        if cfg[group].model_dump() != defaults:
            report.omit("settings", group, "PhonixPBX-only settings group")
    return tree


def _system(session: Session, cfg: dict[str, st.SettingsGroup], report: ExportReport) -> dict:
    system = cfg["system"]
    network = cfg["network"]
    assert isinstance(system, st.SystemSettings)
    assert isinstance(network, st.NetworkSettings)
    web_users = list(session.scalars(select(User).order_by(User.id)))
    names = [u.username for u in web_users]
    username = "admin" if "admin" in names or not names else names[0]
    legacy_name = re.sub(r"[^A-Za-z0-9]", "", username) or "admin"
    report.warning(
        "system",
        "password",
        f"Web passwords are stored as hashes and cannot be exported; the legacy login is "
        f"{legacy_name!r} with the factory password {DEFAULT_LEGACY_PASSWORD!r} - change it "
        "after importing on the old firmware",
    )
    if len(web_users) > 1:
        others = [n for n in names if n != username]
        report.omit("system", "users", f"additional web users: {', '.join(others)}")
    timezone = m.TIMEZONES_OUT.get(system.timezone)
    if timezone is None:
        report.omit("system", "timezone", f"{system.timezone} has no legacy equivalent (UTC used)")
        timezone = "0000"
    if system.prompt_language != "en":
        report.omit("system", "prompt_language", system.prompt_language)
    if system.ssh_enabled:
        report.omit("system", "ssh_enabled", "SSH access")
    return {
        "hostname": system.hostname,
        "domain": system.domain,
        "dnsserver": list(network.dns_servers),
        "username": legacy_name,
        "password": DEFAULT_LEGACY_PASSWORD,
        "timezone": timezone,
        "tonezone": system.tonezone,
        "time-update-interval": "4-hours",
        "timeservers": " ".join(system.ntp_servers),
        "webgui": {
            "protocol": "http",
            "language": m.UI_LANGUAGE_OUT.get(system.ui_language, "en_US"),
        },
    }


def _lan(cfg: dict[str, st.SettingsGroup], report: ExportReport) -> dict[str, Any]:
    net = cfg["network"]
    assert isinstance(net, st.NetworkSettings)
    return {
        "dhcp": net.mode == "dhcp",
        "if": net.interface,
        "ipaddr": net.address,
        "subnet": str(net.prefix),
        "gateway": net.gateway or None,
        "topology": net.topology,
        "extipaddr": net.external_address or None,
        "exthostname": net.external_hostname or None,
    }


def _features(cfg: dict[str, st.SettingsGroup], report: ExportReport) -> dict[str, Any]:
    f = cfg["features"]
    assert isinstance(f, st.FeatureSettings)
    if f.disconnect != st.FeatureSettings().disconnect:
        report.omit("features", "disconnect", f.disconnect)
    return {
        "callparking": {
            "parkext": f.park_ext,
            "parkposstart": str(f.park_start),
            "parkposend": str(f.park_end),
            "parktime": str(f.park_time_s),
        },
        "featuremap": {
            "attendedtransfer": f.attended_transfer,
            "blindtransfer": f.blind_transfer,
            "pickupexten": f.pickup,
            "featuredigittimeout": str(f.feature_digit_timeout_ms),
            "atxfernoanswertimeout": str(f.atxfer_noanswer_timeout_s),
            "transferdigittimeout": str(f.transfer_digit_timeout_s),
        },
    }


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def _voicemail(cfg: dict[str, st.SettingsGroup], report: ExportReport) -> dict[str, Any]:
    vm = cfg["voicemail"]
    assert isinstance(vm, st.VoicemailSettings)
    defaults = st.VoicemailSettings()
    for name in ("from_name", "attach_audio", "keep_messages", "max_message_seconds"):
        if getattr(vm, name) != getattr(defaults, name):
            report.omit("voicemail", name, str(getattr(vm, name)))
    custom = bool(vm.custom_subject or vm.custom_body)
    return {
        "fromaddress": vm.from_address or None,
        "user_defined": custom,
        "user_subject": _b64(m.voicemail_tokens_out(vm.custom_subject)) if custom else None,
        "user_body": _b64(m.voicemail_tokens_out(vm.custom_body)) if custom else None,
    }


def _email(cfg: dict[str, st.SettingsGroup], report: ExportReport) -> dict[str, Any] | None:
    mail = cfg["email"]
    assert isinstance(mail, st.EmailSettings)
    if not mail.host:
        return None
    return {
        "host": mail.host,
        "port": str(mail.port),
        "username": mail.username if mail.auth and mail.username else None,
        "password": mail.password if mail.auth and mail.password else None,
        "address": mail.from_address or None,
        "authtype": "on" if mail.auth and mail.username else None,
        "enctype": {"none": "none", "starttls": "tls", "tls": "smtps"}[mail.encryption],
        "disablecertcheck": not mail.verify_cert,
    }


def _services(cfg: dict[str, st.SettingsGroup], report: ExportReport) -> dict[str, Any]:
    sip, iax, rtp = cfg["sip"], cfg["iax"], cfg["rtp"]
    assert isinstance(sip, st.SipSettings)
    assert isinstance(iax, st.IaxSettings)
    assert isinstance(rtp, st.RtpSettings)
    if sip.tcp_enabled:
        report.omit("sip", "tcp_enabled", "SIP over TCP")
    if sip.tls_enabled:
        report.omit("sip", "tls", f"SIP over TLS (port {sip.tls_port})")
    if sip.srtp != "off":
        report.omit("sip", "srtp", sip.srtp)
    if sip.manual_attributes:
        report.omit("sip", "manual_attributes", "PJSIP [global] options")
    if not iax.enabled:
        report.omit("iax", "enabled", "IAX disabled")
    iax_lines = [line for line in iax.manual_attributes.split("\n") if line.strip()]
    return {
        "sip": {
            "port": str(sip.udp_port),
            "defaultexpiry": str(sip.default_expiry),
            "minexpiry": str(sip.min_expiry),
            "maxexpiry": str(sip.max_expiry),
            "disablesrv": not sip.srv_lookup,
        },
        "iax": {
            "port": str(iax.port),
            "jbenable": iax.jitterbuffer,
            "jbforce": iax.force_jitterbuffer,
            "manual-attribute": [_b64(line) for line in iax_lines],
        },
        "rtp": {"lowport": str(rtp.port_start), "highport": str(rtp.port_end)},
    }


# --- XML emission (PHP array_to_xml() layout) --------------------------------------


def emit(tree: dict[str, Any]) -> bytes:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', f"<{ROOT_TAG}>"]
    _emit_dict(tree, 1, lines)
    lines.append(f"</{ROOT_TAG}>")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _emit_dict(data: dict[str, Any], indent: int, lines: list[str]) -> None:
    for key, value in data.items():
        if isinstance(value, list):
            for item in value:
                _emit_value(key, item, indent, lines)
        else:
            _emit_value(key, value, indent, lines)


def _emit_value(key: str, value: Any, indent: int, lines: list[str]) -> None:
    pad = "\t" * indent
    if value is None or value is False:
        return
    if isinstance(value, dict):
        lines.append(f"{pad}<{key}>")
        _emit_dict(value, indent + 1, lines)
        lines.append(f"{pad}</{key}>")
    elif value is True or value == "":
        lines.append(f"{pad}<{key}/>")
    else:
        lines.append(f"{pad}<{key}>{escape(str(value))}</{key}>")
