"""Field mapping between the legacy ``config.xml`` model and NG.

Import direction: functions named ``*_in`` turn a legacy :class:`Node` into a
plain dict accepted by the service-layer input schemas (``PhoneIn``,
``ProviderIn``, ...). They never touch the database; references to other
objects (legacy uniqids) are resolved through :class:`Context`. Everything
that cannot be represented is reported, never silently dropped.

Export direction: functions named ``*_out`` turn NG objects into the nested
dict structure PHP's ``array_to_xml()`` would have produced, see
:mod:`askozia.legacy.exporter`.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from askozia.core import settings as st
from askozia.core import validation as v
from askozia.core.models import AmiUser, Application, CallGroup, ConferenceRoom, Phone, Provider
from askozia.legacy.parse import Node, decode_b64
from askozia.legacy.report import ExportReport, ImportReport
from askozia.legacy.upgrade import BUILTIN_MARKER
from askozia.services import dialplan as dp
from askozia.services import manager as mgr
from askozia.services import phones as ph
from askozia.services import providers as pv
from askozia.services.common import generate_secret

# --- constant tables -----------------------------------------------------------

TECH_PHONE = {"sip": "pjsip", "iax": "iax", "external": "external"}
TECH_PROVIDER = {"sip": "pjsip", "iax": "iax"}
LEGACY_TECH = {"pjsip": "sip", "iax": "iax", "external": "external"}

# uniqid prefixes used by the legacy code when creating objects
UNIQID_PREFIX = {
    ("phone", "pjsip"): "SIP-PHONE-",
    ("phone", "iax"): "IAX-PHONE-",
    ("phone", "external"): "EXTERNAL-PHONE-",
    ("provider", "pjsip"): "SIP-PROVIDER-",
    ("provider", "iax"): "IAX-PROVIDER-",
    ("callgroup", ""): "CALLGROUP-PARALLEL-",
    ("conference", ""): "CONFERENCE-ROOM-",
    ("application", ""): "DIALPLAN-APPLICATION-",
}

# prompt languages (display.inc) -> NG language codes
LANGUAGE_IN = {
    "en-us": "en",
    "en": "en",
    "en-gb": "en_GB",
    "da-dk": "da",
    "da": "da",
    "nl-nl": "nl",
    "nl": "nl",
    "fr-ca": "fr",
    "fr-fr": "fr",
    "fr": "fr",
    "de-de": "de",
    "de": "de",
    "it-it": "it",
    "it": "it",
    "ja-jp": "ja",
    "ja": "ja",
    "pl-pl": "pl",
    "pl": "pl",
    "pt-br": "pt_BR",
    "ru-ru": "ru",
    "ru": "ru",
    "es-es": "es",
    "es": "es",
    "se": "sv",
    "sv": "sv",
    "sv-se": "sv",
}
LANGUAGE_OUT = {
    "en": "en-us",
    "en_GB": "en-gb",
    "da": "da-dk",
    "nl": "nl-nl",
    "fr": "fr-ca",
    "de": "de-de",
    "it": "it-it",
    "ja": "ja-jp",
    "pl": "pl-pl",
    "pt_BR": "pt-br",
    "ru": "ru-ru",
    "es": "es-es",
    "sv": "se",
}

# web GUI locales (usr/www/locale) -> NG UI language
UI_LANGUAGE_OUT = {
    "en": "en_US",
    "en_GB": "en_US",
    "de": "de_DE",
    "fr": "fr_FR",
    "es": "es_ES",
    "it": "it_IT",
    "nl": "nl_NL",
    "da": "da_DK",
    "sv": "se_SE",
    "pl": "pl_PL",
    "pt_BR": "pt_BR",
    "ru": "ru_RU",
    "ja": "ja_JP",
}

CODEC_ALIASES = {"g729a": "g729", "mulaw": "ulaw", "pcmu": "ulaw", "pcma": "alaw"}

DTMF_IN = {
    "rfc2833": "rfc4733",
    "rfc4733": "rfc4733",
    "auto": "auto",
    "inband": "inband",
    "info": "info",
}
DTMF_OUT = {"rfc4733": "rfc2833", "auto": "auto", "inband": "inband", "info": "info"}

# legacy etc/inc/timezones.inc ids -> IANA names (legacy aliases modernised)
TIMEZONES_IN = {
    "0000": "UTC",
    "0100": "Asia/Jakarta",
    "0200": "Asia/Singapore",
    "0300": "Asia/Ulaanbaatar",
    "0350": "Asia/Tokyo",
    "0400": "Australia/Adelaide",
    "0500": "Australia/Brisbane",
    "0600": "Australia/Sydney",
    "0700": "Australia/Darwin",
    "0800": "Australia/Hobart",
    "0900": "Australia/Melbourne",
    "1000": "Australia/Perth",
    "1100": "Australia/Sydney",
    "1200": "America/Argentina/Buenos_Aires",
    "1300": "America/Sao_Paulo",
    "1400": "America/Chicago",
    "1500": "Europe/Amsterdam",
    "1600": "Europe/Athens",
    "1700": "Europe/Madrid",
    "1800": "Europe/Berlin",
    "1900": "Europe/Brussels",
    "2000": "Europe/Budapest",
    "2100": "Europe/Copenhagen",
    "2200": "Europe/Dublin",
    "2300": "Europe/Zurich",
    "2400": "Europe/Helsinki",
    "2500": "Europe/Kyiv",
    "2600": "Europe/Lisbon",
    "2700": "Europe/London",
    "2800": "Europe/Madrid",
    "2900": "Europe/Oslo",
    "3000": "Europe/Paris",
    "3100": "Europe/Prague",
    "3200": "Europe/Rome",
    "3300": "Europe/Moscow",
    "3500": "Europe/Stockholm",
    "3600": "Europe/Tallinn",
    "3700": "Pacific/Auckland",
    "3800": "Pacific/Auckland",
    "3900": "America/Anchorage",
    "4000": "America/Halifax",
    "4200": "America/Chicago",
    "4300": "America/New_York",
    "4400": "Pacific/Honolulu",
    "4500": "America/Denver",
    "4600": "America/Phoenix",
    "4700": "America/St_Johns",
    "4800": "America/Los_Angeles",
}
TIMEZONE_ALIASES = {"Europe/Kyiv": ("Europe/Kiev",)}
TIMEZONES_OUT: dict[str, str] = {}
for _tz_id, _tz_name in TIMEZONES_IN.items():
    TIMEZONES_OUT.setdefault(_tz_name, _tz_id)
TIMEZONES_OUT["Europe/Madrid"] = "2800"
TIMEZONES_OUT["Pacific/Auckland"] = "3700"
TIMEZONES_OUT["Australia/Sydney"] = "1100"
TIMEZONES_OUT["America/Chicago"] = "4200"

# legacy factory default applications (extension -> sha256 of normalised logic)
LEGACY_DEFAULT_LOGIC = {
    "000063": "dbde49e7fa8ef36ceaa5326ac2eeb18516f0d1c589241445cba19be435e611a8",
    "000047": "0f3ac4583f7060db9678e9a7e6336c57cc2a41553aa1f88e709cce31dd565c62",
    "00003246": "f32b60eb56cdf68ecbd2ec25064a28240ca13eb9fc6579139bfbb890ba799ae5",
    "000064554": "b783f0300c69ab369ebbf0e4da9176a8c42433f55918264cf83871753b078568",
    "000086": "4a78504b8e620a49d814d34edda76ceef955119789e6ca03ba6db662f4b6851a",
    "000023": "805d1080de236231a79869117ac29348faa5ed0c4c9b13aa96984376e815a4f0",
    "00009327357": "c821a41cf2319f59ca79fd27624bea82d2b446c991cb1ef527b2bfde3be3803e",
}
BUILTIN_APPLICATIONS = {a["extension"]: a for a in dp.DEFAULT_APPLICATIONS}

# PJSIP endpoint options that can safely follow the generated endpoint section;
# other (chan_sip) manual attributes are dropped and flagged for review
PJSIP_ENDPOINT_KEYS = frozenset(
    (
        "allow",
        "disallow",
        "callerid",
        "callerid_privacy",
        "callerid_tag",
        "direct_media",
        "rtp_symmetric",
        "force_rport",
        "rewrite_contact",
        "trust_id_inbound",
        "trust_id_outbound",
        "send_pai",
        "send_rpid",
        "send_diversion",
        "dtmf_mode",
        "media_encryption",
        "media_encryption_optimistic",
        "ice_support",
        "t38_udptl",
        "t38_udptl_ec",
        "t38_udptl_nat",
        "fax_detect",
        "timers",
        "timers_min_se",
        "timers_sess_expires",
        "tone_zone",
        "language",
        "moh_suggest",
        "device_state_busy_at",
        "allow_subscribe",
        "inband_progress",
        "rtp_timeout",
        "rtp_timeout_hold",
        "use_ptime",
        "from_user",
        "from_domain",
        "max_audio_streams",
        "max_video_streams",
        "rtp_keepalive",
        "bind_rtp_to_media_address",
        "user_eq_phone",
        "allow_transfer",
        "send_connected_line",
    )
)

# top level sections without NG equivalent
DROPPED_SECTIONS = {
    "analog": "analog phones, providers and fax (no telephony hardware support)",
    "isdn": "ISDN phones and providers (no telephony hardware support)",
    "skinny": "Skinny (SCCP) phones",
    "virtual": "virtual fax machines",
    "storage": "storage disks and services",
    "thirdparty": "third party integrations (humbug)",
    "dyndns": "dynamic DNS",
    "dnsupdate": "RFC 2136 DNS updates",
    "manual-file": "manually edited configuration files",
    "captiveportal": "captive portal",
    "gsm": "GSM interfaces",
    "provisioning": "phone provisioning",
    "redfone-gateway": "Redfone gateways",
}
KNOWN_SECTIONS = {
    "version",
    "lastchange",
    "system",
    "interfaces",
    "sip",
    "iax",
    "external",
    "dialplan",
    "conferencing",
    "voicemail",
    "notifications",
    "services",
    "media",
}
VOICEMAIL_TOKENS = (
    ("VM_MAILBOX", "${VM_MAILBOX}"),
    ("VM_NAME", "${VM_NAME}"),
    ("VM_DURATION", "${VM_DUR}"),
    ("VM_CALLERID", "${VM_CALLERID}"),
    ("VM_DATE", "${VM_DATE}"),
)
FEATURE_DEFAULTS = {  # legacy features_conf_generate() defaults
    "parkext": "700",
    "parkposstart": "701",
    "parkposend": "720",
    "parktime": "30",
    "attendedtransfer": "**",
    "blindtransfer": "##",
    "pickupexten": "*8",
    "featuredigittimeout": "500",
    "atxfernoanswertimeout": "15",
    "transferdigittimeout": "3",
}

_CALLERID_BAD = re.compile(r'["<>;\\\x00-\x1f\x7f]')
_PUBLIC_BAD = re.compile(r"[^A-Za-z0-9._+\-]")


# --- import context --------------------------------------------------------------


@dataclass
class Context:
    """Shared state while mapping one file: the report and uniqid resolution."""

    report: ImportReport
    # legacy uniqid -> (kind, NG id); kinds: phone provider callgroup application conference
    refs: dict[str, tuple[str, int]] = field(default_factory=dict)
    # legacy uniqid of objects in dropped sections -> human readable description
    dropped: dict[str, str] = field(default_factory=dict)
    # fallback lookup in the database (merge mode)
    lookup: Callable[[str], tuple[str, int] | None] | None = None

    def resolve(self, uniqid: str) -> tuple[str, int] | None:
        if uniqid in self.refs:
            return self.refs[uniqid]
        return self.lookup(uniqid) if self.lookup else None

    def provider_id(self, uniqid: str, section: str, name: str, what: str) -> int | None:
        """Resolve a provider reference, reporting dropped/unknown ones."""
        ref = self.resolve(uniqid)
        if ref and ref[0] == "provider":
            return ref[1]
        if uniqid in self.dropped:
            self.report.warning(section, name, f"{what}: {self.dropped[uniqid]} is not imported, reference dropped")
        else:
            self.report.warning(section, name, f"{what}: unknown provider {uniqid!r}, ignored")
        return None


# --- small converters ------------------------------------------------------------


def language_in(value: str, ctx: Context, section: str, name: str) -> str:
    if not value:
        return "en"
    code = LANGUAGE_IN.get(value.strip().lower())
    if code is None:
        ctx.report.warning(section, name, f"Unknown language {value!r}, using English")
        return "en"
    return code


def ui_language_in(value: str) -> str | None:
    if not value:
        return None
    value = value.strip()
    if value in v.LANGUAGES:
        return value
    if value.lower() in ("se_se", "sv_se"):
        return "sv"
    if value in ("pt_BR",):
        return "pt_BR"
    short = value.split("_", 1)[0].lower()
    return short if short in v.LANGUAGES else None


def timezone_in(value: str) -> str | None:
    value = value.strip()
    name = TIMEZONES_IN.get(value, value)
    for candidate in (name, *TIMEZONE_ALIASES.get(name, ())):
        try:
            return v.timezone(candidate)
        except ValueError:
            continue
    return None


def ringlength_in(value: str, ctx: Context, section: str, name: str) -> int | None:
    value = value.strip().lower()
    if not value or value == "indefinitely":
        return None
    if not value.isdigit():
        ctx.report.warning(section, name, f"Invalid ring length {value!r}, ringing indefinitely")
        return None
    seconds = int(value)
    clamped = min(max(seconds, 5), 600)
    if clamped != seconds:
        ctx.report.info(section, name, f"Ring length {seconds}s adjusted to {clamped}s")
    return clamped


def codecs_in(values: list[str], default: list[str], ctx: Context, section: str, name: str) -> list[str]:
    out: list[str] = []
    dropped: list[str] = []
    for raw in values:
        codec = raw.strip().lower()
        codec = CODEC_ALIASES.get(codec, codec)
        if codec in v.CODECS:
            if codec not in out:
                out.append(codec)
        elif raw.strip():
            dropped.append(raw.strip())
    if dropped:
        ctx.report.warning(section, name, f"Unsupported codecs dropped: {', '.join(dropped)}")
    if not out:
        if values:
            ctx.report.warning(section, name, f"No supported codec left, using {', '.join(default)}")
        return list(default)
    return out


def dtmf_in(value: str, ctx: Context, section: str, name: str) -> str:
    if not value:
        return "rfc4733"
    mode = DTMF_IN.get(value.strip().lower())
    if mode is None:
        ctx.report.warning(section, name, f"Unknown DTMF mode {value!r}, using rfc4733")
        return "rfc4733"
    return mode


def nat_in(value: str) -> bool:
    """chan_sip ``nat=``: yes/route/force_rport/comedia mean NAT handling on."""
    return value.strip().lower() not in ("no", "never")


def qualify_in(value: str) -> int:
    """Legacy qualify is chan_sip's latency limit (seconds, 0 = off).

    NG's value is the PJSIP qualify frequency, so "on" maps to the default 60s.
    """
    value = value.strip()
    return 0 if value == "0" else 60


def callerid_in(value: str, fallback: str, ctx: Context, section: str, name: str) -> str:
    clean = _CALLERID_BAD.sub("", value).strip()[:80]
    if clean != value.strip():
        ctx.report.warning(section, name, f'Caller ID {value!r} contained " < > ; \\, cleaned up')
    return clean or fallback


def public_name_in(value: str, ctx: Context, section: str, name: str) -> str:
    clean = _PUBLIC_BAD.sub("", value.strip())[:64]
    if clean != value.strip():
        ctx.report.warning(section, name, f"Public name {value!r} adjusted to {clean!r}")
    return clean


def description_in(value: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", value).strip()[:255]


def email_in(value: str, ctx: Context, section: str, name: str, what: str) -> str:
    if not value:
        return ""
    try:
        return v.email(value)
    except ValueError:
        ctx.report.warning(section, name, f"Invalid {what} e-mail address {value!r} ignored")
        return ""


def secret_in(value: str, ctx: Context, section: str, name: str, generate: bool) -> str:
    if not value:
        if generate:
            ctx.report.warning(section, name, "No secret set, a new random secret was generated")
            return generate_secret()
        return ""
    try:
        return v.secret(value)
    except ValueError:
        if generate:
            ctx.report.warning(
                section,
                name,
                "Secret does not meet the NG rules (4-128 characters, no spaces, quotes, ';' or "
                "backslashes); a new random secret was generated - reconfigure the device",
            )
            return generate_secret()
        ctx.report.warning(section, name, "Secret does not meet the NG rules and was not imported - re-enter it")
        return ""


def manual_attributes_in(raw: str | None, tech: str, ctx: Context, section: str, name: str) -> str:
    """Keep manual attribute lines that are valid for NG's generated sections."""
    if raw is None:
        ctx.report.warning(section, name, "Manual attributes are not valid base64, dropped")
        return ""
    lines = [line.strip() for line in raw.replace("\r\n", "\n").split("\n") if line.strip()]
    kept: list[str] = []
    review: list[str] = []
    for line in lines:
        if line.startswith(";"):
            continue
        key = re.split(r"\s*=>?\s*", line, maxsplit=1)[0].strip().lower()
        try:
            v.manual_attributes(line)
        except ValueError:
            review.append(line)
            continue
        if tech == "pjsip" and key not in PJSIP_ENDPOINT_KEYS:
            review.append(line)
            continue
        kept.append(line)
    if review:
        target = "PJSIP" if tech == "pjsip" else "Asterisk 22"
        ctx.report.warning(
            section,
            name,
            f"Review needed: manual attributes not valid for {target} were dropped: " + "; ".join(review),
        )
    return "\n".join(kept)


def _logic_hash(text: str) -> str:
    norm = "\n".join(line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip())
    return hashlib.sha256(norm.encode()).hexdigest()


BUILTIN_LOGIC_HASHES = {ext: _logic_hash(a["logic"]) for ext, a in BUILTIN_APPLICATIONS.items()}


def is_default_application(extension: str, logic: str) -> bool:
    """True when ``logic`` is the unmodified legacy (or NG) factory default."""
    digest = _logic_hash(logic)
    return digest in (LEGACY_DEFAULT_LOGIC.get(extension), BUILTIN_LOGIC_HASHES.get(extension))


# --- application logic rewriting ---------------------------------------------------

REMOVED_APPS = {
    "Macro": "Macro() was removed in Asterisk 21, rewrite it with Gosub()",
    "MacroExclusive": "MacroExclusive() was removed in Asterisk 21",
    "MeetMeCount": "MeetMe was replaced by ConfBridge; use CONFBRIDGE_INFO()",
    "MeetMeAdmin": "MeetMe was replaced by ConfBridge; use ConfKick()/ConfBridge menus",
    "MeetMeChannelAdmin": "MeetMe was replaced by ConfBridge",
    "DBdel": "DBdel() was removed, use Set(DB_DELETE(...))",
    "DBdeltree": "DBdeltree() was removed, use DB_DELETE()",
    "SetMusicOnHold": "SetMusicOnHold() was removed, use Set(CHANNEL(musicclass)=...)",
    "WaitMusicOnHold": "WaitMusicOnHold() was removed, use MusicOnHold(,duration)",
    "SetCallerPres": "SetCallerPres() was removed, use CALLERPRES()",
    "SIPAddHeader": "chan_sip is gone; use PJSIP_HEADER(add,...)",
    "SIPDtmfMode": "chan_sip is gone; use Set(CHANNEL(dtmf_mode)=...)",
    "SIPRemoveHeader": "chan_sip is gone; use PJSIP_HEADER(remove,...)",
}
REVIEW_FUNCTIONS = {
    "SIP_HEADER": "chan_sip is gone; use PJSIP_HEADER(read,...)",
    "SIPPEER": "chan_sip is gone; use PJSIP_ENDPOINT()/PJSIP_CONTACT()",
    "SIPCHANINFO": "chan_sip is gone; use CHANNEL()",
    "SHELL": "runs a shell command on the appliance; check the script exists on NG",
}


def _split_call(text: str, start: int) -> tuple[int, list[str]] | None:
    """Parse ``Name(args)`` arguments starting at the '(' at ``start``."""
    depth = 0
    args: list[str] = []
    current = ""
    for idx in range(start, len(text)):
        char = text[idx]
        if char == "(":
            depth += 1
            if depth == 1:
                continue
        elif char == ")":
            depth -= 1
            if depth == 0:
                args.append(current)
                return idx, args
        elif char == "," and depth == 1:
            args.append(current)
            current = ""
            continue
        current += char
    return None


def _rewrite_meetme(line: str, notes: list[tuple[str, str]]) -> str:
    out = line
    for match in reversed(list(re.finditer(r"(?<![A-Za-z])MeetMe\(", line))):
        parsed = _split_call(line, match.end() - 1)
        if parsed is None:
            continue
        end, args = parsed
        room = args[0].strip() if args else ""
        out = out[: match.start()] + f"ConfBridge({room})" + out[end + 1 :]
        extra = [a for a in args[1:] if a.strip()]
        if extra:
            notes.append(
                (
                    "warning",
                    f"Review needed: MeetMe options/PIN {','.join(extra)!r} dropped, ConfBridge uses the room settings",
                )
            )
        notes.append(("info", f"MeetMe({','.join(args)}) rewritten to ConfBridge({room})"))
    return out


def rewrite_logic(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Rewrite known Asterisk 1.8 constructs for Asterisk 22.

    Returns the new logic and a list of ``(level, message)`` notes.
    """
    notes: list[tuple[str, str]] = []
    out_lines = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if "${SHELL(/etc/scripts/parseip.sh)}" in line:
            line = line.replace("${SHELL(/etc/scripts/parseip.sh)}", "${ASKOZIA_LAN_IP}")
            notes.append(("info", "${SHELL(/etc/scripts/parseip.sh)} replaced by ${ASKOZIA_LAN_IP}"))
        if re.search(r"(?<![A-Za-z])MeetMe\(", line):
            line = _rewrite_meetme(line, notes)
        lang = re.search(r"CHANNEL\(language\)=([A-Za-z\-]+)", line)
        if lang and lang.group(1).lower() in LANGUAGE_IN:
            new = LANGUAGE_IN[lang.group(1).lower()]
            if new != lang.group(1):
                line = line.replace(lang.group(0), f"CHANNEL(language)={new}")
                notes.append(("info", f"Language {lang.group(1)} rewritten to {new}"))
        if re.search(r"(?<![A-Za-z])SIP/", line):
            line = re.sub(r"(?<![A-Za-z])SIP/", "PJSIP/", line)
            notes.append(
                (
                    "warning",
                    "Review needed: SIP/ channels rewritten to PJSIP/ - phone endpoints "
                    "keep their extension, provider endpoints are named prov-<id> in NG",
                )
            )
        for app, hint in REMOVED_APPS.items():
            if re.search(rf"(?<![A-Za-z]){app}\(", line):
                notes.append(("warning", f"Review needed: {hint} (line {line!r})"))
        for func, hint in REVIEW_FUNCTIONS.items():
            if re.search(rf"\$\{{{func}\(", line):
                notes.append(("warning", f"Review needed: {func}() {hint} (line {line!r})"))
        if re.search(r"(?:Playback|Background|ControlPlayback)\(askozia-music/", line):
            notes.append(
                (
                    "warning",
                    f"Review needed: askozia-music prompts are not shipped with NG (line {line!r})",
                )
            )
        out_lines.append(line)
    return "\n".join(out_lines), notes


# --- object mappings: legacy -> NG --------------------------------------------------


def phone_label(node: Node) -> str:
    cid = node.text("callerid")
    ext = node.text("extension")
    return f"{cid} <{ext}>" if cid else ext or node.text("uniqid") or "?"


def phone_in(node: Node, tech: str, ctx: Context) -> dict[str, Any] | None:
    """Legacy sip/iax/external phone -> ``PhoneIn`` data (None = skip)."""
    section = "phones"
    name = phone_label(node)
    report = ctx.report
    ext = node.text("extension")
    data: dict[str, Any] = {
        "tech": TECH_PHONE[tech],
        "extension": ext,
        "callerid": callerid_in(node.text("callerid"), ext or "Phone", ctx, section, name),
        "description": description_in(node.text("descr")),
        "enabled": not node.flag("disabled"),
        "ringlength": ringlength_in(node.text("ringlength"), ctx, section, name),
        "language": language_in(node.text("language"), ctx, section, name),
        "public_access": node.text("publicaccess") == "enabled",
        "public_name": public_name_in(node.text("publicname"), ctx, section, name),
    }
    vm_email = email_in(node.text("vmtoemailaddress"), ctx, section, name, "voicemail")
    data["vm_enabled"] = node.text("vmtoemail") == "enabled"
    data["vm_email"] = vm_email
    vm_pin = node.text("vmpin")
    if vm_pin and not vm_pin.isdigit():
        report.warning(section, name, "Voicemail PIN is not numeric, a new PIN is generated")
        vm_pin = ""
    data["vm_pin"] = vm_pin[:16]
    notify_email = email_in(node.text("emailcallnotifyaddress"), ctx, section, name, "notification")
    data["notify_missed"] = node.text("emailcallnotify") == "enabled" and bool(notify_email)
    if node.text("emailcallnotify") == "enabled" and not notify_email:
        report.warning(section, name, "Missed call notification disabled: no valid e-mail address")
    data["notify_email"] = notify_email

    if tech in ("sip", "iax"):
        data["secret"] = secret_in(node.text("secret"), ctx, section, name, generate=True)
        data["codecs"] = codecs_in(node.texts("codec"), ph.DEFAULT_CODECS, ctx, section, name)
        manual = manual_attributes_in(node.b64("manualattributes"), TECH_PHONE[tech], ctx, section, name)
        data["manual_attributes"] = manual
    if tech == "sip":
        data["dtmf_mode"] = dtmf_in(node.text("dtmfmode"), ctx, section, name)
        data["nat"] = nat_in(node.text("natmode"))
        busy = node.text("busylevel")
        data["busylevel"] = min(int(busy), 100) if busy.isdigit() and int(busy) > 0 else None
        if node.text("snom-mac"):
            report.info(section, name, "snom auto-provisioning MAC address not imported")
    if tech == "iax":
        auth = node.text("authentication")
        if auth and auth != "md5":
            report.info(section, name, f"IAX authentication {auth!r} not configurable per phone, md5 used")

    if tech in ("sip", "iax"):
        blocked = []
        for uniqid in node.texts("provider"):
            pid = ctx.provider_id(uniqid, section, name, "Blocked provider")
            if pid is not None and pid not in blocked:
                blocked.append(pid)
        data["blocked_provider_ids"] = blocked
        callerids: dict[int, str] = {}
        for cmap in node.nodes("outgoingcalleridmap"):
            uniqid = cmap.text("provideruniqid")
            cid = cmap.text("cidstring")
            if not uniqid or not cid:
                continue
            pid = ctx.provider_id(uniqid, section, name, "Outgoing caller ID")
            if pid is None:
                continue
            try:
                callerids[pid] = v.callerid_string(cid)
            except ValueError:
                report.warning(section, name, f"Invalid outgoing caller ID {cid!r} dropped")
        data["provider_callerids"] = callerids

    if tech == "external":
        dial = node.text("dialprovider") or "sipuri"
        data["dial_string"] = node.text("dialstring")
        if dial == "sipuri":
            data["dial_type"] = "sip_uri"
        elif dial == "iaxuri":
            data["dial_type"] = "iax_uri"
        else:
            ref = ctx.resolve(dial)
            if ref and ref[0] == "provider":
                data["dial_type"] = "provider"
                data["dial_provider_id"] = ref[1]
            elif dial in ctx.dropped:
                report.error(
                    section,
                    name,
                    f"Dials out through {ctx.dropped[dial]}, which is not supported: skipped. "
                    "Replace the provider with a SIP gateway and recreate this phone.",
                )
                return None
            else:
                report.error(section, name, f"Dials out through unknown provider {dial!r}: skipped")
                return None
    return data


def provider_label(node: Node) -> str:
    return node.text("name") or node.text("uniqid") or "?"


def provider_in(node: Node, tech: str, ctx: Context) -> dict[str, Any]:
    """Legacy sip/iax provider -> ``ProviderIn`` data without routes and failover."""
    section = "providers"
    name = provider_label(node)
    report = ctx.report
    port_raw = node.text("port")
    port: int | None = None
    if port_raw:
        if port_raw.isdigit() and 1 <= int(port_raw) <= 65535:
            port = int(port_raw)
        else:
            report.warning(section, name, f"Invalid port {port_raw!r} ignored")
    data: dict[str, Any] = {
        "tech": TECH_PROVIDER[tech],
        "name": name,
        "enabled": not node.flag("disabled"),
        "host": node.text("host"),
        "port": port,
        "username": node.text("username"),
        "secret": secret_in(node.text("secret"), ctx, section, name, generate=False),
        "registration": not node.flag("noregister"),
        "language": language_in(node.text("language"), ctx, section, name),
        "codecs": codecs_in(node.texts("codec"), pv.DEFAULT_CODECS, ctx, section, name),
        "qualify": qualify_in(node.text("qualify")),
    }
    if node.text("manualregister"):
        report.warning(
            section,
            name,
            f"Manual registration string {node.text('manualregister')!r} is not supported; "
            "the registration is generated from host, username and secret",
        )
    readback = node.text("readbacknumber")
    if readback and not readback.lstrip("+").isdigit():
        report.warning(section, name, f"Public number {readback!r} is not numeric, ignored")
        readback = ""
    data["readback_number"] = readback
    cid_string = node.text("calleridstring")
    if node.text("calleridsource") == "string" and cid_string:
        try:
            v.config_value(cid_string, "Caller ID")
            data["callerid_source"] = "string"
            data["callerid_string"] = cid_string
        except ValueError:
            report.warning(section, name, f"Outgoing caller ID {cid_string!r} invalid, using phones")
    override = node.text("override")
    if override in ("replacenamewithnum", "replace", "prepend"):
        ostring = node.text("overridestring")
        if override != "replacenamewithnum" and not ostring:
            report.warning(section, name, "Incoming caller ID override without string ignored")
        else:
            data["incoming_cid_override"] = override
            data["incoming_cid_string"] = ostring
    elif override and override != "disable":
        report.warning(section, name, f"Unknown incoming caller ID override {override!r} ignored")

    if tech == "sip":
        data["auth_user"] = node.text("authuser")
        data["from_user"] = node.text("fromuser")
        data["from_domain"] = node.text("fromdomain")
        data["dtmf_mode"] = dtmf_in(node.text("dtmfmode"), ctx, section, name)
        data["nat"] = nat_in(node.text("natmode"))
    else:
        auth = node.text("authentication") or "md5"
        if node.flag("useinkey") or node.flag("useoutkey"):
            report.warning(section, name, "RSA key authentication is not imported; md5 with the secret is used")
            auth = "md5"
        data["iax_auth"] = auth if auth in ("md5", "plaintext") else "md5"

    lines = []
    manual = manual_attributes_in(node.b64("manualattributes"), TECH_PROVIDER[tech], ctx, section, name)
    if manual:
        lines.append(manual)
    raw_list = [decode_b64(r) for r in node.texts("manual-attribute")]
    if raw_list:
        joined = "\n".join(r for r in raw_list if r)
        extra = manual_attributes_in(joined, TECH_PROVIDER[tech], ctx, section, name)
        if extra:
            lines.append(extra)
    data["manual_attributes"] = "\n".join(lines)

    patterns: list[str] = []
    for pattern in node.texts("dialpattern"):
        try:
            pattern = v.dialpattern(pattern)
        except ValueError as exc:
            report.warning(section, name, f"Dial pattern {pattern!r} dropped: {exc}")
            continue
        if pattern not in patterns:
            patterns.append(pattern)
    data["dialpatterns"] = patterns
    if node.text("defaultfax"):
        report.warning(section, name, "Default fax destination dropped (fax is not supported)")
    return data


def incoming_routes_in(node: Node, ctx: Context) -> list[dict[str, Any]]:
    section = "providers"
    name = provider_label(node)
    routes: list[dict[str, Any]] = []
    for imap in node.nodes("incomingextensionmap"):
        uniqid = imap.text("destinationid")
        pattern = imap.text("incomingpattern")
        where = f"Incoming route {pattern or '(catch-all)'}"
        if not uniqid:
            continue
        ref = ctx.resolve(uniqid)
        if ref is None or ref[0] not in pv.DEST_MODELS:
            if uniqid in ctx.dropped:
                ctx.report.warning(section, name, f"{where} to {ctx.dropped[uniqid]} dropped (not supported)")
            else:
                ctx.report.warning(section, name, f"{where}: unknown destination {uniqid!r} dropped")
            continue
        route = {"pattern": pattern, "dest_type": ref[0], "dest_id": ref[1]}
        try:
            pv.IncomingRouteIn.model_validate(route)
        except ValidationError:
            ctx.report.warning(section, name, f"{where}: invalid pattern, route dropped")
            continue
        routes.append(route)
    return routes


def callgroup_in(node: Node, ctx: Context) -> dict[str, Any] | None:
    section = "callgroups"
    name = node.text("name") or node.text("extension") or "?"
    members: list[int] = []
    for uniqid in node.texts("groupmember"):
        ref = ctx.resolve(uniqid)
        if ref and ref[0] == "phone":
            if ref[1] not in members:
                members.append(ref[1])
        elif uniqid in ctx.dropped:
            ctx.report.warning(section, name, f"Member {ctx.dropped[uniqid]} dropped (not supported)")
        else:
            ctx.report.warning(section, name, f"Unknown member {uniqid!r} dropped")
    if not members:
        ctx.report.error(section, name, "Call group has no (importable) members: skipped")
        return None
    return {
        "name": name,
        "extension": node.text("extension"),
        "description": description_in(node.text("descr")),
        "strategy": "ringall",
        "ringlength": ringlength_in(node.text("ringlength"), ctx, section, name),
        "public_access": node.text("publicaccess") == "enabled",
        "public_name": public_name_in(node.text("publicname"), ctx, section, name),
        "member_ids": members,
    }


def room_in(node: Node, ctx: Context) -> dict[str, Any]:
    section = "rooms"
    name = node.text("name") or node.text("number")
    pin = node.text("pin")
    admin_pin = node.text("adminpin")
    if admin_pin and admin_pin == pin:
        ctx.report.warning(section, name, "Admin PIN equals the PIN and was dropped")
        admin_pin = ""
    return {
        "number": node.text("number"),
        "name": name,
        "pin": pin,
        "admin_pin": admin_pin,
        "public_access": node.text("publicaccess") == "enabled",
        "public_name": public_name_in(node.text("publicname"), ctx, section, name),
    }


def application_in(node: Node, ctx: Context) -> tuple[dict[str, Any] | None, bool]:
    """Returns ``(ApplicationIn data, is_builtin)``; data None means skip."""
    section = "applications"
    name = node.text("name") or node.text("extension") or "?"
    ext = node.text("extension")
    base = {
        "name": name,
        "extension": ext,
        "description": description_in(node.text("descr")),
        "enabled": not node.flag("disabled"),
        "public_access": node.text("publicaccess") == "enabled",
        "public_name": public_name_in(node.text("publicname"), ctx, section, name),
    }
    if node.flag(BUILTIN_MARKER):
        builtin = BUILTIN_APPLICATIONS[ext]
        return {**base, **builtin, "enabled": base["enabled"]}, True
    app_type = node.text("type") or "plaintext"
    if app_type == "php":
        ctx.report.error(section, name, "PHP (AGI) applications are not supported: skipped")
        return None, False
    if app_type != "plaintext":
        ctx.report.error(section, name, f"Unknown application type {app_type!r}: skipped")
        return None, False
    logic = node.b64("applicationlogic")
    if logic is None:
        ctx.report.error(section, name, "Application logic is not valid base64: skipped")
        return None, False
    if ext in BUILTIN_APPLICATIONS and is_default_application(ext, logic):
        builtin = BUILTIN_APPLICATIONS[ext]
        ctx.report.info(section, name, "Factory default application: NG's built-in version is used")
        return {
            **base,
            **builtin,
            "enabled": base["enabled"],
            "public_access": base["public_access"],
            "public_name": base["public_name"],
        }, True
    logic, notes = rewrite_logic(logic)
    for level, message in notes:
        ctx.report.add(level, section, name, message)
    return {**base, "logic": logic}, False


def ami_user_in(node: Node, ctx: Context) -> dict[str, Any]:
    section = "ami_users"
    name = node.text("username")
    permit = []
    ip, mask = node.text("permitip"), node.text("permitnetmask")
    if ip:
        try:
            permit.append(v.network(f"{ip}/{mask}" if mask else ip))
        except ValueError:
            ctx.report.warning(section, name, f"Invalid permit {ip}/{mask}, using 127.0.0.1/32")
    deny = f"{node.text('denyip')}/{node.text('denynetmask')}"
    if deny not in ("/", "0.0.0.0/0.0.0.0", "0.0.0.0/0"):
        ctx.report.info(section, name, f"Deny rule {deny} not imported (NG denies all but permit)")

    def perms(key: str) -> list[str]:
        out = []
        for perm in node.texts(key):
            perm = perm.lower()
            if perm in mgr.PERMISSIONS:
                out.append(perm)
            else:
                ctx.report.warning(section, name, f"Unknown permission {perm!r} dropped")
        return out

    return {
        "username": name,
        "secret": secret_in(node.text("secret"), ctx, section, name, generate=True),
        "permit": permit or ["127.0.0.1/32"],
        "read_perms": perms("read-permission"),
        "write_perms": perms("write-permission"),
    }


# --- settings: legacy -> NG ------------------------------------------------------------


def _assign(model: st.SettingsGroup, name: str, value: Any, report: ImportReport, label: str) -> None:
    try:
        setattr(model, name, value)
    except (ValidationError, ValueError) as exc:
        msg = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
        msg = msg.removeprefix("Value error, ")
        report.warning("settings", label, f"Value {value!r} not imported: {msg}")


def _int(value: str) -> int | None:
    value = value.strip()
    return int(value) if value.isdigit() else None


def settings_in(root: Node, current: dict[str, st.SettingsGroup], report: ImportReport) -> list[st.SettingsGroup]:
    """Map the global legacy sections onto copies of the current settings."""
    system = current["system"].model_copy(deep=True)
    network = current["network"].model_copy(deep=True)
    sip = current["sip"].model_copy(deep=True)
    iax = current["iax"].model_copy(deep=True)
    rtp = current["rtp"].model_copy(deep=True)
    features = current["features"].model_copy(deep=True)
    vm = current["voicemail"].model_copy(deep=True)
    email = current["email"].model_copy(deep=True)
    assert isinstance(system, st.SystemSettings)
    assert isinstance(network, st.NetworkSettings)
    assert isinstance(sip, st.SipSettings)
    assert isinstance(iax, st.IaxSettings)
    assert isinstance(rtp, st.RtpSettings)
    assert isinstance(features, st.FeatureSettings)
    assert isinstance(vm, st.VoicemailSettings)
    assert isinstance(email, st.EmailSettings)

    # system
    sysn = root.node("system")
    if sysn.text("hostname"):
        _assign(system, "hostname", sysn.text("hostname").lower(), report, "system.hostname")
    if sysn.text("domain"):
        _assign(system, "domain", sysn.text("domain").lower(), report, "system.domain")
    if sysn.text("timezone"):
        tz = timezone_in(sysn.text("timezone"))
        if tz is None:
            report.warning(
                "settings",
                "system.timezone",
                f"Unknown time zone {sysn.text('timezone')!r}, using UTC",
            )
            tz = "UTC"
        _assign(system, "timezone", tz, report, "system.timezone")
    if sysn.text("tonezone"):
        _assign(system, "tonezone", sysn.text("tonezone").lower(), report, "system.tonezone")
    if sysn.text("timeservers"):
        _assign(
            system,
            "ntp_servers",
            sysn.text("timeservers").lower().split(),
            report,
            "system.ntp_servers",
        )
    ui_lang = sysn.node("webgui").text("language")
    if ui_lang:
        mapped = ui_language_in(ui_lang)
        if mapped is None:
            report.warning(
                "settings",
                "system.ui_language",
                f"Web UI language {ui_lang!r} not available, using English",
            )
            mapped = "en"
        _assign(system, "ui_language", mapped, report, "system.ui_language")
    webgui = sysn.node("webgui")
    if webgui.text("protocol") == "http" or webgui.text("port"):
        report.info(
            "settings",
            "system.webgui",
            "Web GUI protocol/port not imported (NG always uses HTTPS on port 443)",
        )
    for key in ("harddiskstandby", "disableconsolemenu", "notes", "polling"):
        if sysn.has(key):
            report.info("settings", f"system.{key}", "Not supported by NG, ignored")

    # network
    dns = sysn.texts("dnsserver")
    if dns:
        _assign(network, "dns_servers", dns, report, "network.dns_servers")
    lan = root.node("interfaces", "lan")
    if lan:
        if lan.has("dhcp") and lan.flag("dhcp"):
            _assign(network, "mode", "dhcp", report, "network.mode")
        else:
            _assign(network, "mode", "static", report, "network.mode")
        if lan.text("ipaddr"):
            _assign(network, "address", lan.text("ipaddr"), report, "network.address")
        if _int(lan.text("subnet")) is not None:
            _assign(network, "prefix", _int(lan.text("subnet")), report, "network.prefix")
        if lan.text("gateway"):
            _assign(network, "gateway", lan.text("gateway"), report, "network.gateway")
        topology = lan.text("topology")
        if topology in ("public", "natstatic", "natdynamichost"):
            _assign(network, "topology", topology, report, "network.topology")
        if lan.text("extipaddr"):
            _assign(
                network,
                "external_address",
                lan.text("extipaddr"),
                report,
                "network.external_address",
            )
        if lan.text("exthostname"):
            _assign(
                network,
                "external_hostname",
                lan.text("exthostname"),
                report,
                "network.external_hostname",
            )
        if lan.text("if") and lan.text("if") != network.interface:
            report.info(
                "settings",
                "network.interface",
                f"Legacy interface {lan.text('if')!r} mapped to the detected NIC {network.interface!r}",
            )
        if lan.text("spoofmac"):
            report.info("settings", "network.spoofmac", "MAC address spoofing not imported")
        report.info(
            "settings",
            "network",
            "Network settings take effect after 'Apply changes' - check them before applying",
        )

    # SIP / IAX / RTP
    services = root.node("services")
    sipn = services.node("sip")
    for src, dst in (
        ("port", "udp_port"),
        ("defaultexpiry", "default_expiry"),
        ("minexpiry", "min_expiry"),
        ("maxexpiry", "max_expiry"),
    ):
        if _int(sipn.text(src)) is not None:
            _assign(sip, dst, _int(sipn.text(src)), report, f"sip.{dst}")
    if sipn:
        _assign(sip, "srv_lookup", not sipn.flag("disablesrv"), report, "sip.srv_lookup")
    sip_manual = [decode_b64(r) or "" for r in sipn.texts("manual-attribute")]
    if any(sip_manual):
        report.warning(
            "settings",
            "sip.manual_attributes",
            "Review needed: chan_sip [general] manual attributes are not valid for PJSIP and "
            "were dropped: " + "; ".join(s for s in sip_manual if s),
        )
    iaxn = services.node("iax")
    if _int(iaxn.text("port")) is not None:
        _assign(iax, "port", _int(iaxn.text("port")), report, "iax.port")
    if iaxn:
        _assign(iax, "jitterbuffer", iaxn.flag("jbenable"), report, "iax.jitterbuffer")
        _assign(iax, "force_jitterbuffer", iaxn.flag("jbforce"), report, "iax.force_jitterbuffer")
    iax_manual = "\n".join(decode_b64(r) or "" for r in iaxn.texts("manual-attribute"))
    if iax_manual.strip():
        ctx = Context(report=report)
        _assign(
            iax,
            "manual_attributes",
            manual_attributes_in(iax_manual, "iax", ctx, "settings", "iax.manual_attributes"),
            report,
            "iax.manual_attributes",
        )
    rtpn = services.node("rtp")
    low, high = _int(rtpn.text("lowport")), _int(rtpn.text("highport"))
    # absent values keep NG's (wider) default range instead of legacy 10000-10200
    if low is not None or high is not None:
        low = low if low is not None else 10000
        high = high if high is not None else 10200
        if 1024 <= low < high <= 65535:
            _assign(rtp, "port_start", low, report, "rtp.port_start")
            _assign(rtp, "port_end", high, report, "rtp.port_end")
        else:
            report.warning("settings", "rtp", f"Invalid RTP port range {low}-{high} not imported")

    # features (absent values mean the legacy defaults, as features.conf was generated)
    dpn = root.node("dialplan")
    fmap, park = dpn.node("featuremap"), dpn.node("callparking")

    def feat(node: Node, key: str) -> str:
        return node.text(key) or FEATURE_DEFAULTS[key]

    _assign(
        features,
        "attended_transfer",
        feat(fmap, "attendedtransfer"),
        report,
        "features.attended_transfer",
    )
    _assign(features, "blind_transfer", feat(fmap, "blindtransfer"), report, "features.blind_transfer")
    _assign(features, "pickup", feat(fmap, "pickupexten"), report, "features.pickup")
    for key, dst in (
        ("featuredigittimeout", "feature_digit_timeout_ms"),
        ("atxfernoanswertimeout", "atxfer_noanswer_timeout_s"),
        ("transferdigittimeout", "transfer_digit_timeout_s"),
    ):
        if _int(feat(fmap, key)) is not None:
            _assign(features, dst, _int(feat(fmap, key)), report, f"features.{dst}")
    _assign(features, "park_ext", feat(park, "parkext"), report, "features.park_ext")
    start, end = _int(feat(park, "parkposstart")), _int(feat(park, "parkposend"))
    if start is not None and end is not None and start < end:
        _assign(features, "park_start", start, report, "features.park_start")
        _assign(features, "park_end", end, report, "features.park_end")
    if _int(feat(park, "parktime")) is not None:
        _assign(features, "park_time_s", _int(feat(park, "parktime")), report, "features.park_time_s")

    # voicemail
    vmn = root.node("voicemail")
    if vmn.text("fromaddress"):
        _assign(vm, "from_address", vmn.text("fromaddress"), report, "voicemail.from_address")
    if vmn.flag("user_defined"):
        subject = decode_b64(vmn.text("user_subject")) or ""
        body = decode_b64(vmn.text("user_body")) or ""
        for token, replacement in VOICEMAIL_TOKENS:
            subject = re.sub(rf"(?<![{{\w]){token}\b", replacement, subject)
            body = re.sub(rf"(?<![{{\w]){token}\b", replacement, body)
        _assign(
            vm,
            "custom_subject",
            subject.replace("\n", " ").strip(),
            report,
            "voicemail.custom_subject",
        )
        _assign(vm, "custom_body", body, report, "voicemail.custom_body")
    elif vmn.text("maillanguage") and not vmn.text("maillanguage").startswith("en"):
        report.info(
            "settings",
            "voicemail.maillanguage",
            f"Voicemail e-mail template {vmn.text('maillanguage')!r} not available, NG's English template is used",
        )

    # e-mail
    mailn = root.node("notifications", "email")
    if mailn:
        enctype = mailn.text("enctype")
        encryption = {"tls": "starttls", "smtps": "tls"}.get(enctype, "none")
        _assign(email, "host", mailn.text("host"), report, "email.host")
        _assign(email, "encryption", encryption, report, "email.encryption")
        port = _int(mailn.text("port")) or (465 if encryption == "tls" else 25)
        _assign(email, "port", port, report, "email.port")
        _assign(email, "username", mailn.text("username"), report, "email.username")
        _assign(email, "password", mailn.text("password"), report, "email.password")
        _assign(email, "auth", bool(mailn.text("username")), report, "email.auth")
        if mailn.text("username") and mailn.text("authtype") not in ("", "on"):
            report.info(
                "settings",
                "email.auth",
                f"SMTP auth method {mailn.text('authtype')!r} not configurable, msmtp negotiates it automatically",
            )
        if mailn.text("address"):
            _assign(email, "from_address", mailn.text("address"), report, "email.from_address")
        _assign(email, "verify_cert", not mailn.flag("disablecertcheck"), report, "email.verify_cert")

    media = root.node("media")
    if media.has("custom-moh") or media.has("custom-vmgreeting"):
        report.info(
            "settings",
            "media",
            "Custom music on hold / voicemail greetings are not part "
            "of config.xml; upload them again under Services > Media",
        )
    return [system, network, sip, iax, rtp, features, vm, email]


# --- NG -> legacy (export) -----------------------------------------------------------


def generated_uniqid(kind: str, tech: str, obj_id: int) -> str:
    """Stable legacy-looking uniqid (``PREFIX`` + digits + 13 hex chars)."""
    prefix = UNIQID_PREFIX[(kind, tech)]
    digest = hashlib.sha1(f"askozia-ng:{kind}:{tech}:{obj_id}".encode()).hexdigest()  # noqa: S324
    return f"{prefix}{1000000000 + obj_id}{digest[:13]}"


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def _enabled(flag: bool) -> str | None:
    return "enabled" if flag else None


def _ringlength_out(value: int | None) -> str:
    return "indefinitely" if value is None else str(value)


def phone_out(phone: Phone, uid: Callable[[str, int], str], report: ExportReport) -> dict[str, Any]:
    name = f"{phone.callerid} <{phone.extension}>"
    out: dict[str, Any] = {
        "extension": phone.extension,
        "callerid": phone.callerid,
        "descr": phone.description or None,
        "language": LANGUAGE_OUT.get(phone.language, "en-us"),
        "ringlength": _ringlength_out(phone.ringlength),
        "publicaccess": _enabled(phone.public_access),
        "publicname": phone.public_name or None,
        "emailcallnotify": _enabled(phone.notify_missed),
        "emailcallnotifyaddress": phone.notify_email or None,
        "vmtoemail": _enabled(phone.vm_enabled),
        "vmtoemailaddress": phone.vm_email or None,
        "vmpin": phone.vm_pin or None,
    }
    if phone.tech in ("pjsip", "iax"):
        out["secret"] = phone.secret
        out["codec"] = list(phone.codecs or [])
        out["provider"] = [uid("provider", p.id) for p in phone.blocked_providers]
        out["outgoingcalleridmap"] = [
            {"provideruniqid": uid("provider", c.provider_id), "cidstring": c.callerid}
            for c in phone.provider_callerids
        ]
        out["manualattributes"] = _b64(phone.manual_attributes) if phone.manual_attributes else None
        if phone.max_contacts != 1:
            report.omit("phones", name, f"max_contacts={phone.max_contacts}")
    if phone.tech == "pjsip":
        out["dtmfmode"] = DTMF_OUT.get(phone.dtmf_mode, "auto")
        out["natmode"] = "yes" if phone.nat else "no"
        out["busylevel"] = str(phone.busylevel) if phone.busylevel else None
    if phone.tech == "iax":
        out["authentication"] = "md5"
    if phone.tech == "external":
        if phone.dial_type == "sip_uri":
            out["dialprovider"] = "sipuri"
        elif phone.dial_type == "iax_uri":
            out["dialprovider"] = "iaxuri"
        elif phone.dial_provider_id:
            out["dialprovider"] = uid("provider", phone.dial_provider_id)
        out["dialstring"] = phone.dial_string
    out["uniqid"] = uid("phone", phone.id)
    out["disabled"] = not phone.enabled
    return out


def provider_out(
    provider: Provider,
    uid: Callable[[str, int], str],
    session_routes: list[tuple[str, str, int]],
    report: ExportReport,
) -> dict[str, Any]:
    name = provider.name
    out: dict[str, Any] = {
        "name": provider.name,
        "host": provider.host,
        "port": str(provider.port) if provider.port else None,
        "username": provider.username,
        "secret": provider.secret or None,
        "readbacknumber": provider.readback_number or None,
        "language": LANGUAGE_OUT.get(provider.language, "en-us"),
        "codec": list(provider.codecs or []),
        "qualify": "2" if provider.qualify else "0",
        "calleridsource": provider.callerid_source,
        "calleridstring": provider.callerid_string or None,
        "override": provider.incoming_cid_override or None,
        "overridestring": provider.incoming_cid_string or None,
        "noregister": None if provider.registration else "yes",
        "failover": uid("provider", provider.failover_provider_id) if provider.failover_provider_id else None,
        "dialpattern": [d.pattern for d in provider.dialpatterns],
        "manualattributes": _b64(provider.manual_attributes) if provider.manual_attributes else None,
    }
    maps = []
    for pattern, dest_type, dest_id in session_routes:
        entry: dict[str, Any] = {}
        if pattern:
            entry["incomingpattern"] = pattern
        entry["destinationid"] = uid(dest_type, dest_id)
        maps.append(entry)
    out["incomingextensionmap"] = maps
    if provider.tech == "pjsip":
        out["authuser"] = provider.auth_user or None
        out["fromuser"] = provider.from_user or None
        out["fromdomain"] = provider.from_domain or None
        out["dtmfmode"] = DTMF_OUT.get(provider.dtmf_mode, "auto")
        out["natmode"] = "yes" if provider.nat else "no"
        if provider.transport != "udp":
            report.omit("providers", name, f"transport={provider.transport}")
    else:
        if provider.iax_auth == "rsa":
            report.omit("providers", name, "RSA authentication (exported as md5)")
        out["authentication"] = provider.iax_auth if provider.iax_auth != "rsa" else "md5"
    if provider.qualify not in (0, 60):
        report.omit("providers", name, f"qualify frequency {provider.qualify}s")
    out["uniqid"] = uid("provider", provider.id)
    out["disabled"] = not provider.enabled
    return out


def callgroup_out(group: CallGroup, uid: Callable[[str, int], str], report: ExportReport) -> dict[str, Any]:
    if group.strategy != "ringall":
        report.omit("callgroups", group.name, f"strategy={group.strategy} (legacy rings all)")
    if not group.extension:
        report.warning(
            "callgroups",
            group.name,
            "Call group without extension; the legacy firmware requires one",
        )
    return {
        "name": group.name,
        "extension": group.extension or None,
        "descr": group.description or None,
        "groupmember": [uid("phone", m.phone_id) for m in group.members],
        "publicaccess": _enabled(group.public_access),
        "publicname": group.public_name or None,
        "ringlength": _ringlength_out(group.ringlength),
        "uniqid": uid("callgroup", group.id),
    }


def room_out(room: ConferenceRoom, uid: Callable[[str, int], str]) -> dict[str, Any]:
    return {
        "number": room.number,
        "name": room.name,
        "pin": room.pin or None,
        "adminpin": room.admin_pin or None,
        "publicaccess": _enabled(room.public_access),
        "publicname": room.public_name or None,
        "uniqid": uid("conference", room.id),
    }


def application_out(app: Application, uid: Callable[[str, int], str]) -> dict[str, Any]:
    return {
        "name": app.name,
        "extension": app.extension,
        "descr": app.description or None,
        "applicationlogic": _b64(app.logic),
        "publicaccess": _enabled(app.public_access),
        "publicname": app.public_name or None,
        "uniqid": uid("application", app.id),
        "type": "plaintext",
        "disabled": not app.enabled,
    }


def ami_user_out(user: AmiUser, report: ExportReport) -> dict[str, Any]:
    import ipaddress

    permit = user.permit[0] if user.permit else "127.0.0.1/32"
    net = ipaddress.ip_network(permit, strict=False)
    if len(user.permit) > 1:
        report.omit("ami_users", user.username, f"additional permitted networks {user.permit[1:]}")
    return {
        "username": user.username,
        "secret": user.secret,
        "denyip": "0.0.0.0",  # noqa: S104 - an ACL entry, not a bind address
        "denynetmask": "0.0.0.0",  # noqa: S104
        "permitip": str(net.network_address),
        "permitnetmask": str(net.netmask),
        "read-permission": list(user.read_perms),
        "write-permission": list(user.write_perms),
    }


def voicemail_tokens_out(text: str) -> str:
    for token, replacement in VOICEMAIL_TOKENS:
        text = text.replace(replacement, token)
    return text
