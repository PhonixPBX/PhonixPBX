# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Input validation shared by settings, services, the API and the legacy importer.

Validators raise ``ValueError`` with a human readable message (pydantic turns
those into field errors). Many rules port ``etc/inc/verify.inc`` and
``pbx_is_valid_*`` from the legacy PHP code. In addition every value that ends
up in a generated Asterisk/system config file is checked so it cannot inject
new lines, sections or comments.
"""

from __future__ import annotations

import ipaddress
import re
from functools import lru_cache

from phonix.i18n import N_, _

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def no_control(value: str, what: str = N_("Value")) -> str:
    """``what`` names the value; pass it marked with ``N_`` (it is translated here)."""
    if _CONTROL.search(value):
        raise ValueError(_("%(what)s must not contain control characters or line breaks", what=_(what)))
    return value


def config_value(value: str, what: str = N_("Value")) -> str:
    """A value safe to place after ``key=`` in an Asterisk config file."""
    value = no_control(value.strip(), what)
    if ";" in value:
        raise ValueError(_("%(what)s must not contain ';'", what=_(what)))
    return value


_EXTENSION = re.compile(r"^[0-9]{1,20}$")


def extension(value: str) -> str:
    value = value.strip()
    if not _EXTENSION.match(value):
        raise ValueError(_("Extension must consist of 1-20 digits"))
    return value


_PATTERN_EXT = re.compile(r"^_?[0-9XNZxnz\[\]\-.!*#]{1,32}$")


def extension_or_pattern(value: str) -> str:
    """Application extensions may be Asterisk patterns (legacy extensions_patternify)."""
    value = value.strip()
    if _EXTENSION.match(value):
        return value
    if not _PATTERN_EXT.match(value):
        raise ValueError(_("Extension must be digits or an Asterisk pattern (X, N, Z, [], ., !)"))
    return value.lstrip("_")


_CALLERID = re.compile(r'^[^"<>;\\\x00-\x1f\x7f]{1,80}$')


def callerid_name(value: str) -> str:
    value = value.strip()
    if not _CALLERID.match(value):
        raise ValueError(_('Caller ID may not be empty or contain " < > ; \\'))
    return value


_CALLERID_STRING = re.compile(r'^(?:"?[^"<>;\\\x00-\x1f]*"?\s*)?<?\+?[0-9*#]{0,32}>?$')


def callerid_string(value: str) -> str:
    """Full caller id like ``Name <+4912345>`` or just a number."""
    value = value.strip()
    if not value or not _CALLERID_STRING.match(value):
        raise ValueError(_('Caller ID must look like "Name <number>" or a number'))
    return value


_SECRET = re.compile(r"^[A-Za-z0-9!#$%&()*+,\-./:=?@\[\]^_{|}~]{4,128}$")


def secret(value: str) -> str:
    if not _SECRET.match(value):
        raise ValueError(_("Secret must be 4-128 characters without spaces, quotes, ';' or backslashes"))
    return value


_PIN = re.compile(r"^[0-9]{0,16}$")


def pin(value: str) -> str:
    value = value.strip()
    if not _PIN.match(value):
        raise ValueError(_("PIN must consist of digits only"))
    return value


_USERNAME = re.compile(r"^[A-Za-z0-9._@+\-]{1,128}$")


def sip_username(value: str) -> str:
    value = value.strip()
    if not _USERNAME.match(value):
        raise ValueError(_("Username may only contain letters, digits and . _ @ + -"))
    return value


_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")


def hostname_label(value: str) -> str:
    value = value.strip()
    if not _LABEL.match(value):
        raise ValueError(_("Hostname must be 1-63 letters, digits or '-'"))
    return value


def domain(value: str) -> str:
    value = value.strip().rstrip(".")
    if not value:
        raise ValueError(_("Domain must not be empty"))
    for label in value.split("."):
        if not _LABEL.match(label):
            raise ValueError(_("Invalid domain name"))
    return value


def host(value: str) -> str:
    """Hostname, FQDN or IP address."""
    value = value.strip()
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    try:
        return domain(value)
    except ValueError:
        raise ValueError(_("Must be a hostname or IP address")) from None


def ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        raise ValueError(_("Must be an IP address")) from None


def ipv4(value: str) -> str:
    try:
        return str(ipaddress.IPv4Address(value.strip()))
    except ValueError:
        raise ValueError(_("Must be an IPv4 address")) from None


def network(value: str) -> str:
    try:
        return str(ipaddress.ip_network(value.strip(), strict=False))
    except ValueError:
        raise ValueError(_("Must be a network in CIDR notation (e.g. 192.168.1.0/24)")) from None


_EMAIL = re.compile(r"^[^@\s;<>\"]+@[^@\s;<>\"]+\.[^@\s;<>\"]+$")


def email(value: str) -> str:
    value = value.strip()
    if not _EMAIL.match(value):
        raise ValueError(_("Must be a valid e-mail address"))
    return value


_IFACE = re.compile(r"^[A-Za-z0-9._-]{1,15}$")


def interface_name(value: str) -> str:
    value = value.strip()
    if not _IFACE.match(value):
        raise ValueError(_("Invalid interface name"))
    return value


@lru_cache(maxsize=1)
def _timezones() -> frozenset[str]:
    try:
        import zoneinfo

        return frozenset(zoneinfo.available_timezones())
    except Exception:  # pragma: no cover - zoneinfo always present on 3.10+
        return frozenset()


def timezone(value: str) -> str:
    value = value.strip()
    zones = _timezones()
    if value == "UTC" or (zones and value in zones):
        return value
    if not zones and re.match(r"^[A-Za-z0-9_+\-/]{1,64}$", value):
        return value
    raise ValueError(_("Unknown time zone"))


_FEATURE = re.compile(r"^[0-9*#]{1,8}$")


def feature_code(value: str) -> str:
    value = value.strip()
    if not _FEATURE.match(value):
        raise ValueError(_("Feature codes consist of digits, '*' and '#'"))
    return value


def dialpattern(value: str, incoming: bool = False) -> str:
    """Port of ``pbx_is_valid_dialpattern``.

    Outgoing syntax: ``[prefix-to-add+][prefix-to-strip|]pattern`` e.g.
    ``0|X.`` (strip leading 0) or ``0049+0|X.`` (replace 0 with 0049).
    """
    value = value.strip().upper()
    allowed = r"^[XNZ0-9\-\[\].!]+$" if incoming else r"^[XNZ0-9\-\[\].!|+*#]+$"
    if not value or not re.match(allowed, value):
        raise ValueError(_("Dial pattern contains an invalid character"))
    for char in "|+":
        if value.count(char) > 1:
            raise ValueError(_("Dial pattern may contain only one '%(char)s'", char=char))
    is_open = False
    open_index = 0
    for idx, char in enumerate(value):
        if char == "[":
            if is_open:
                raise ValueError(_("Nested square brackets are not allowed"))
            is_open, open_index = True, idx
        elif char == "]":
            if not is_open:
                raise ValueError(_("Unmatched square bracket"))
            if idx - open_index < 2:
                raise ValueError(_("Empty square brackets"))
            is_open = False
    if is_open:
        raise ValueError(_("Unmatched square bracket"))
    rest = value
    if "+" in rest:
        add, rest = rest.split("+", 1)
        if not re.match(r"^[0-9*#]+$", add):
            raise ValueError(_("Prefixes to add may only contain digits, '*' and '#'"))
    if "|" in rest:
        strip = rest.split("|", 1)[0]
        if "." in strip or "!" in strip:
            raise ValueError(_("Wildcards '.' and '!' are not allowed before '|'"))
    if not rest.replace("|", ""):
        raise ValueError(_("Dial pattern is empty"))
    return value


def parse_dialpattern(value: str) -> tuple[str, str, int]:
    """Split a validated dial pattern into (asterisk_pattern, prefix_to_add, strip_count).

    Port of ``dialplan_parse_pattern``.
    """
    prefix = ""
    if "+" in value:
        prefix, value = value.split("+", 1)
    strip = 0
    if "|" in value:
        strip = value.index("|")
        value = value.replace("|", "")
    return value, prefix, strip


_ATTR_LINE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}\s*=>?\s*[^\x00-\x1f\[\]]*$")


def manual_attributes(value: str) -> str:
    """Raw ``key=value`` lines appended to a generated config section."""
    lines = []
    for raw in value.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if not _ATTR_LINE.match(line):
            raise ValueError(_("Invalid attribute line: %(line)r (expected key=value)", line=line[:40]))
        lines.append(line)
    return "\n".join(lines)


_APP_LINE = re.compile(r"^(?:[0-9]+|n|s)(?:\([A-Za-z0-9_\-]+\))?,\s*[A-Za-z][A-Za-z0-9_]*\(.*\)\s*$")
_INCLUDE_LINE = re.compile(r"^include\s*=>\s*[A-Za-z0-9_\-]+$", re.IGNORECASE)


def application_logic(value: str) -> str:
    """Dialplan lines in legacy format ``priority[(label)],App(args)``."""
    lines = []
    for raw in value.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        no_control(line, N_("Dialplan line"))
        if not (_APP_LINE.match(line) or _INCLUDE_LINE.match(line)):
            raise ValueError(
                _("Invalid dialplan line: %(line)r (expected e.g. '1,Answer()' or 'n,Hangup()')", line=line[:60])
            )
        lines.append(line)
    if not lines:
        raise ValueError(_("Application logic must contain at least one line"))
    return "\n".join(lines)


CODECS_AUDIO = ("ulaw", "alaw", "g722", "opus", "gsm", "g726", "g729", "ilbc", "speex", "slin")
CODECS_VIDEO = ("h264", "vp8", "vp9", "h263")
CODECS = CODECS_AUDIO + CODECS_VIDEO


def codecs(values: list[str]) -> list[str]:
    out: list[str] = []
    for codec in values:
        codec = codec.strip().lower()
        if not codec:
            continue
        if codec not in CODECS:
            raise ValueError(_("Unknown codec %(codec)r", codec=codec))
        if codec not in out:
            out.append(codec)
    if not out:
        raise ValueError(_("Select at least one codec"))
    return out


LANGUAGES = {
    "en": N_("English"),
    "en_GB": N_("English (UK)"),
    "de": N_("German"),
    "fr": N_("French"),
    "es": N_("Spanish"),
    "it": N_("Italian"),
    "nl": N_("Dutch"),
    "da": N_("Danish"),
    "sv": N_("Swedish"),
    "pl": N_("Polish"),
    "pt_BR": N_("Portuguese (Brazil)"),
    "ru": N_("Russian"),
    "ja": N_("Japanese"),
}


def language(value: str) -> str:
    if value not in LANGUAGES:
        raise ValueError(_("Unknown language"))
    return value


TONEZONES = {
    "at": N_("Austria"),
    "au": N_("Australia"),
    "be": N_("Belgium"),
    "br": N_("Brazil"),
    "ch": N_("Switzerland"),
    "cl": N_("Chile"),
    "cn": N_("China"),
    "cz": N_("Czech Republic"),
    "de": N_("Germany"),
    "dk": N_("Denmark"),
    "ee": N_("Estonia"),
    "es": N_("Spain"),
    "fi": N_("Finland"),
    "fr": N_("France"),
    "gr": N_("Greece"),
    "hu": N_("Hungary"),
    "il": N_("Israel"),
    "in": N_("India"),
    "it": N_("Italy"),
    "jp": N_("Japan"),
    "lt": N_("Lithuania"),
    "mx": N_("Mexico"),
    "my": N_("Malaysia"),
    "nl": N_("Netherlands"),
    "no": N_("Norway"),
    "nz": N_("New Zealand"),
    "ph": N_("Philippines"),
    "pl": N_("Poland"),
    "pt": N_("Portugal"),
    "ru": N_("Russia"),
    "se": N_("Sweden"),
    "sg": N_("Singapore"),
    "th": N_("Thailand"),
    "tw": N_("Taiwan"),
    "uk": N_("United Kingdom"),
    "us": N_("United States"),
    "us-old": N_("United States (old)"),
    "ve": N_("Venezuela"),
    "za": N_("South Africa"),
}


def tonezone(value: str) -> str:
    if value not in TONEZONES:
        raise ValueError(_("Unknown tone zone"))
    return value
