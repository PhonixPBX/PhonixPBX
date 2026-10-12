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

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def no_control(value: str, what: str = "Value") -> str:
    if _CONTROL.search(value):
        raise ValueError(f"{what} must not contain control characters or line breaks")
    return value


def config_value(value: str, what: str = "Value") -> str:
    """A value safe to place after ``key=`` in an Asterisk config file."""
    value = no_control(value.strip(), what)
    if ";" in value:
        raise ValueError(f"{what} must not contain ';'")
    return value


_EXTENSION = re.compile(r"^[0-9]{1,20}$")


def extension(value: str) -> str:
    value = value.strip()
    if not _EXTENSION.match(value):
        raise ValueError("Extension must consist of 1-20 digits")
    return value


_PATTERN_EXT = re.compile(r"^_?[0-9XNZxnz\[\]\-.!*#]{1,32}$")


def extension_or_pattern(value: str) -> str:
    """Application extensions may be Asterisk patterns (legacy extensions_patternify)."""
    value = value.strip()
    if _EXTENSION.match(value):
        return value
    if not _PATTERN_EXT.match(value):
        raise ValueError("Extension must be digits or an Asterisk pattern (X, N, Z, [], ., !)")
    return value.lstrip("_")


_CALLERID = re.compile(r'^[^"<>;\\\x00-\x1f\x7f]{1,80}$')


def callerid_name(value: str) -> str:
    value = value.strip()
    if not _CALLERID.match(value):
        raise ValueError('Caller ID may not be empty or contain " < > ; \\')
    return value


_CALLERID_STRING = re.compile(r'^(?:"?[^"<>;\\\x00-\x1f]*"?\s*)?<?\+?[0-9*#]{0,32}>?$')


def callerid_string(value: str) -> str:
    """Full caller id like ``Name <+4912345>`` or just a number."""
    value = value.strip()
    if not value or not _CALLERID_STRING.match(value):
        raise ValueError('Caller ID must look like "Name <number>" or a number')
    return value


_SECRET = re.compile(r"^[A-Za-z0-9!#$%&()*+,\-./:=?@\[\]^_{|}~]{4,128}$")


def secret(value: str) -> str:
    if not _SECRET.match(value):
        raise ValueError("Secret must be 4-128 characters without spaces, quotes, ';' or backslashes")
    return value


_PIN = re.compile(r"^[0-9]{0,16}$")


def pin(value: str) -> str:
    value = value.strip()
    if not _PIN.match(value):
        raise ValueError("PIN must consist of digits only")
    return value


_USERNAME = re.compile(r"^[A-Za-z0-9._@+\-]{1,128}$")


def sip_username(value: str) -> str:
    value = value.strip()
    if not _USERNAME.match(value):
        raise ValueError("Username may only contain letters, digits and . _ @ + -")
    return value


_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")


def hostname_label(value: str) -> str:
    value = value.strip()
    if not _LABEL.match(value):
        raise ValueError("Hostname must be 1-63 letters, digits or '-'")
    return value


def domain(value: str) -> str:
    value = value.strip().rstrip(".")
    if not value:
        raise ValueError("Domain must not be empty")
    for label in value.split("."):
        if not _LABEL.match(label):
            raise ValueError("Invalid domain name")
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
        raise ValueError("Must be a hostname or IP address") from None


def ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        raise ValueError("Must be an IP address") from None


def ipv4(value: str) -> str:
    try:
        return str(ipaddress.IPv4Address(value.strip()))
    except ValueError:
        raise ValueError("Must be an IPv4 address") from None


def network(value: str) -> str:
    try:
        return str(ipaddress.ip_network(value.strip(), strict=False))
    except ValueError:
        raise ValueError("Must be a network in CIDR notation (e.g. 192.168.1.0/24)") from None


_EMAIL = re.compile(r"^[^@\s;<>\"]+@[^@\s;<>\"]+\.[^@\s;<>\"]+$")


def email(value: str) -> str:
    value = value.strip()
    if not _EMAIL.match(value):
        raise ValueError("Must be a valid e-mail address")
    return value


_IFACE = re.compile(r"^[A-Za-z0-9._-]{1,15}$")


def interface_name(value: str) -> str:
    value = value.strip()
    if not _IFACE.match(value):
        raise ValueError("Invalid interface name")
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
    raise ValueError("Unknown time zone")


_FEATURE = re.compile(r"^[0-9*#]{1,8}$")


def feature_code(value: str) -> str:
    value = value.strip()
    if not _FEATURE.match(value):
        raise ValueError("Feature codes consist of digits, '*' and '#'")
    return value


def dialpattern(value: str, incoming: bool = False) -> str:
    """Port of ``pbx_is_valid_dialpattern``.

    Outgoing syntax: ``[prefix-to-add+][prefix-to-strip|]pattern`` e.g.
    ``0|X.`` (strip leading 0) or ``0049+0|X.`` (replace 0 with 0049).
    """
    value = value.strip().upper()
    allowed = r"^[XNZ0-9\-\[\].!]+$" if incoming else r"^[XNZ0-9\-\[\].!|+*#]+$"
    if not value or not re.match(allowed, value):
        raise ValueError("Dial pattern contains an invalid character")
    for char in "|+":
        if value.count(char) > 1:
            raise ValueError(f"Dial pattern may contain only one '{char}'")
    is_open = False
    open_index = 0
    for idx, char in enumerate(value):
        if char == "[":
            if is_open:
                raise ValueError("Nested square brackets are not allowed")
            is_open, open_index = True, idx
        elif char == "]":
            if not is_open:
                raise ValueError("Unmatched square bracket")
            if idx - open_index < 2:
                raise ValueError("Empty square brackets")
            is_open = False
    if is_open:
        raise ValueError("Unmatched square bracket")
    rest = value
    if "+" in rest:
        add, rest = rest.split("+", 1)
        if not re.match(r"^[0-9*#]+$", add):
            raise ValueError("Prefixes to add may only contain digits, '*' and '#'")
    if "|" in rest:
        strip = rest.split("|", 1)[0]
        if "." in strip or "!" in strip:
            raise ValueError("Wildcards '.' and '!' are not allowed before '|'")
    if not rest.replace("|", ""):
        raise ValueError("Dial pattern is empty")
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
            raise ValueError(f"Invalid attribute line: {line[:40]!r} (expected key=value)")
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
        no_control(line, "Dialplan line")
        if not (_APP_LINE.match(line) or _INCLUDE_LINE.match(line)):
            raise ValueError(f"Invalid dialplan line: {line[:60]!r} (expected e.g. '1,Answer()' or 'n,Hangup()')")
        lines.append(line)
    if not lines:
        raise ValueError("Application logic must contain at least one line")
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
            raise ValueError(f"Unknown codec {codec!r}")
        if codec not in out:
            out.append(codec)
    if not out:
        raise ValueError("Select at least one codec")
    return out


LANGUAGES = {
    "en": "English",
    "en_GB": "English (UK)",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "nl": "Dutch",
    "da": "Danish",
    "sv": "Swedish",
    "pl": "Polish",
    "pt_BR": "Portuguese (Brazil)",
    "ru": "Russian",
    "ja": "Japanese",
}


def language(value: str) -> str:
    if value not in LANGUAGES:
        raise ValueError("Unknown language")
    return value


TONEZONES = {
    "at": "Austria",
    "au": "Australia",
    "be": "Belgium",
    "br": "Brazil",
    "ch": "Switzerland",
    "cl": "Chile",
    "cn": "China",
    "cz": "Czech Republic",
    "de": "Germany",
    "dk": "Denmark",
    "ee": "Estonia",
    "es": "Spain",
    "fi": "Finland",
    "fr": "France",
    "gr": "Greece",
    "hu": "Hungary",
    "il": "Israel",
    "in": "India",
    "it": "Italy",
    "jp": "Japan",
    "lt": "Lithuania",
    "mx": "Mexico",
    "my": "Malaysia",
    "nl": "Netherlands",
    "no": "Norway",
    "nz": "New Zealand",
    "ph": "Philippines",
    "pl": "Poland",
    "pt": "Portugal",
    "ru": "Russia",
    "se": "Sweden",
    "sg": "Singapore",
    "th": "Thailand",
    "tw": "Taiwan",
    "uk": "United Kingdom",
    "us": "United States",
    "us-old": "United States (old)",
    "ve": "Venezuela",
    "za": "South Africa",
}


def tonezone(value: str) -> str:
    if value not in TONEZONES:
        raise ValueError("Unknown tone zone")
    return value
