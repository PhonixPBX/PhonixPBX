"""Parse a legacy AskoziaPBX ``config.xml`` into an intermediate model.

The legacy PHP code (``etc/inc/xmlparse.inc``) turned the XML into nested PHP
arrays: elements named in ``$listtags`` always become lists, every other
element may occur only once, empty elements (``<dhcp/>``) mean "set" and
boolean ``false`` values were never written. :class:`Node` wraps exactly that
structure and offers typed accessors, so the mapping code reads like the
original ``$config['sip']['phone'][0]['extension']`` accesses.

Parsing uses ``defusedxml`` with DTDs forbidden, which rejects entity
expansion ("billion laughs") and external entities (XXE).
"""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

MAX_BYTES = 10 * 1024 * 1024
ROOT_TAG = "askoziapbx"

# port of $listtags in etc/inc/xmlparse.inc
LIST_TAGS = frozenset(
    (
        "key",
        "dnsserver",
        "route",
        "shellcmd",
        "cacert",
        "earlyshellcmd",
        "phone",
        "provider",
        "codec",
        "room",
        "dialpattern",
        "callgroup",
        "groupmember",
        "incomingextensionmap",
        "dahdi-port",
        "dahdi-portgroup",
        "redfone-gateway",
        "disk",
        "package",
        "loadzone",
        "bridge",
        "application",
        "application2",
        "manager-user",
        "read-permission",
        "write-permission",
        "app-command",
        "manual-attribute",
        "manual-file",
        "fax",
        "outgoingcalleridmap",
    )
)

_FALSE = ("no", "false", "0", "off", "disabled")


class LegacyParseError(ValueError):
    """The file cannot be read as a legacy configuration at all."""


class Node:
    """Read-only view on one parsed element (a PHP array)."""

    __slots__ = ("data",)

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data: dict[str, Any] = data if isinstance(data, dict) else {}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Node({self.data!r})"

    def __bool__(self) -> bool:
        return bool(self.data)

    def __contains__(self, key: str) -> bool:
        return key in self.data

    def __iter__(self) -> Iterator[str]:
        return iter(list(self.data))

    def keys(self) -> list[str]:
        return list(self.data)

    def has(self, key: str) -> bool:
        """PHP ``isset()``: the element exists (even if empty)."""
        return key in self.data

    def text(self, key: str, default: str = "") -> str:
        value = self.data.get(key)
        if isinstance(value, list):
            value = value[0] if value else None
        if isinstance(value, str):
            return value.strip()
        return default

    def flag(self, key: str) -> bool:
        """Boolean as written by PHP: present (usually empty) means true."""
        if key not in self.data:
            return False
        value = self.data[key]
        return not (isinstance(value, str) and value.strip().lower() in _FALSE)

    def node(self, *path: str) -> Node:
        data: Any = self.data
        for key in path:
            data = data.get(key) if isinstance(data, dict) else None
            if isinstance(data, list):
                data = data[0] if data else None
        return Node(data if isinstance(data, dict) else None)

    def nodes(self, key: str) -> list[Node]:
        value = self.data.get(key)
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            return []
        return [Node(v) for v in value if isinstance(v, dict)]

    def texts(self, key: str) -> list[str]:
        value = self.data.get(key)
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]

    def b64(self, key: str) -> str | None:
        """Base64 decoded text; ``""`` when absent, ``None`` when undecodable."""
        raw = self.text(key)
        return decode_b64(raw) if raw else ""

    def items(self) -> Iterator[tuple[str, Any]]:
        yield from self.data.items()


def decode_b64(raw: str) -> str | None:
    try:
        data = base64.b64decode(re.sub(r"\s+", "", raw), validate=True)
    except (binascii.Error, ValueError):
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


@dataclass
class LegacyConfig:
    """The parsed file: the root node plus notes collected while parsing."""

    root: Node
    version: str
    warnings: list[str] = field(default_factory=list)

    @property
    def data(self) -> dict[str, Any]:
        return self.root.data


def _element_to_value(elem: Element, path: str, warnings: list[str]) -> Any:
    children = list(elem)
    if not children:
        return (elem.text or "").strip()
    out: dict[str, Any] = {}
    for child in children:
        if not isinstance(child.tag, str):  # comments / processing instructions
            continue
        tag = child.tag.lower()
        value = _element_to_value(child, f"{path}/{tag}", warnings)
        if tag in LIST_TAGS:
            existing = out.setdefault(tag, [])
            if not isinstance(existing, list):  # pragma: no cover - defensive
                existing = out[tag] = [existing]
            existing.append(value)
        elif tag in out:
            # legacy xmlparse.inc died here; keep the first occurrence
            warnings.append(f"{path}/{tag} occurs more than once, using the first one")
        else:
            out[tag] = value
    return out


def _decode(data: bytes, warnings: list[str]) -> bytes:
    """Old PHP versions wrote whatever bytes the browser sent (often latin-1)."""
    try:
        data.decode("utf-8")
        return data
    except UnicodeDecodeError:
        warnings.append("file is not valid UTF-8, decoded as ISO-8859-1")
        text = data.decode("latin-1")
        text = re.sub(r"^<\?xml[^>]*\?>", '<?xml version="1.0" encoding="UTF-8"?>', text)
        return text.encode("utf-8")


_XML_ERROR_TAG_MISMATCH = 7
_CLOSING_TAG_LINE = re.compile(rb"^\s*</([A-Za-z0-9_-]+)>\s*$")
MAX_REPAIRS = 3


def _parse_xml(data: bytes, warnings: list[str]) -> Element:
    """Parse with defusedxml; repair stray closing tags on a line of their own.

    Some shipped factory configs (e.g. pbx-alvispbx) contain an unmatched
    ``</dialplan>`` - removing such a line is the only repair attempted.
    """
    first_error: ParseError | None = None
    repairs: list[str] = []
    for _attempt in range(MAX_REPAIRS + 1):
        try:
            root = fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
        except DefusedXmlException as exc:
            raise LegacyParseError(
                f"Refusing to parse XML with DTD, entity declarations or external references ({type(exc).__name__})"
            ) from None
        except ParseError as exc:
            first_error = first_error or exc
            line_no = exc.position[0] if exc.position else 0
            lines = data.split(b"\n")
            match = (
                _CLOSING_TAG_LINE.match(lines[line_no - 1])
                if exc.code == _XML_ERROR_TAG_MISMATCH and 0 < line_no <= len(lines)
                else None
            )
            if match is None:
                break
            repairs.append(f"Removed unmatched closing tag </{match.group(1).decode()}> in line {line_no}")
            data = b"\n".join(lines[: line_no - 1] + lines[line_no:])
        else:
            warnings.extend(repairs)
            return root
    raise LegacyParseError(f"Invalid XML: {first_error}")


def parse_bytes(data: bytes) -> LegacyConfig:
    """Parse ``config.xml`` content. Raises :class:`LegacyParseError`."""
    if len(data) > MAX_BYTES:
        raise LegacyParseError(f"File is too large ({len(data)} bytes, at most {MAX_BYTES})")
    if not data.strip():
        raise LegacyParseError("File is empty")
    warnings: list[str] = []
    data = _decode(data, warnings)
    root = _parse_xml(data, warnings)
    if not isinstance(root.tag, str) or root.tag.lower() != ROOT_TAG:
        raise LegacyParseError(f"Not an AskoziaPBX configuration: root element is <{root.tag}>, expected <{ROOT_TAG}>")
    value = _element_to_value(root, "", warnings)
    node = Node(value if isinstance(value, dict) else {})
    return LegacyConfig(root=node, version=node.text("version"), warnings=warnings)
