"""Shared helpers for the legacy import/export tests.

``db_snapshot`` renders the importable part of the database as plain JSON with
references replaced by natural keys (extensions, names), so snapshots are
independent of database ids. ``legacy_view`` does the same for a config.xml
file, normalising only value spellings that are semantically equal.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from askozia.core import settings as st
from askozia.core.models import AmiUser, Application, CallGroup, ConferenceRoom, Phone, Provider
from askozia.legacy.parse import Node, decode_b64, parse_bytes
from askozia.services import dialplan as dp
from askozia.services import manager as mgr
from askozia.services import phones as ph
from askozia.services import providers as pv

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
GOLDEN = HERE / "golden"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# --- database snapshot -----------------------------------------------------------------


def db_snapshot(session: Session, uniqids: bool = True) -> dict[str, Any]:
    session.expire_all()
    phones = {p.id: p for p in session.scalars(select(Phone))}
    providers = {p.id: p for p in session.scalars(select(Provider))}
    groups = {g.id: g for g in session.scalars(select(CallGroup))}
    rooms = {r.id: r for r in session.scalars(select(ConferenceRoom))}
    apps = {a.id: a for a in session.scalars(select(Application))}

    def prov(pid: int | None) -> str | None:
        return providers[pid].name if pid else None

    def dest(dest_type: str, dest_id: int) -> str:
        if dest_type == "phone":
            return f"phone:{phones[dest_id].extension}"
        if dest_type == "callgroup":
            return f"callgroup:{groups[dest_id].name}"
        if dest_type == "conference":
            return f"conference:{rooms[dest_id].number}"
        return f"application:{apps[dest_id].extension}"

    def clean(data: dict[str, Any], obj: Any) -> dict[str, Any]:
        data.pop("id", None)
        if uniqids:
            data["legacy_uniqid"] = obj.legacy_uniqid
        return data

    out_phones = []
    for p in phones.values():
        d = ph.to_dict(p, with_secret=True)
        d["blocked_provider_ids"] = sorted(prov(i) or "" for i in d["blocked_provider_ids"])
        d["provider_callerids"] = {prov(k): c for k, c in sorted(d["provider_callerids"].items())}
        d["dial_provider_id"] = prov(d["dial_provider_id"])
        out_phones.append(clean(d, p))
    out_providers = []
    for p in providers.values():
        d = pv.to_dict(p, with_secret=True)
        d["failover_provider_id"] = prov(d["failover_provider_id"])
        d["incoming_routes"] = [
            {"pattern": r["pattern"], "dest": dest(r["dest_type"], r["dest_id"])} for r in d["incoming_routes"]
        ]
        out_providers.append(clean(d, p))
    out_groups = []
    for g in groups.values():
        d = dp.callgroup_to_dict(g)
        d["member_ids"] = [phones[i].extension for i in d["member_ids"]]
        out_groups.append(clean(d, g))
    out_ami = []
    for u in session.scalars(select(AmiUser)):
        d = mgr.to_dict(u)
        d["secret"] = u.secret
        out_ami.append(clean(d, u))
    return {
        "settings": {name: group.model_dump(mode="json") for name, group in sorted(st.load_all(session).items())},
        "phones": sorted(out_phones, key=lambda d: d["extension"]),
        "providers": sorted(out_providers, key=lambda d: (d["tech"], d["name"])),
        "callgroups": sorted(out_groups, key=lambda d: d["name"]),
        "rooms": sorted((clean(dp.room_to_dict(r), r) for r in rooms.values()), key=lambda d: d["number"]),
        "applications": sorted(
            (clean(dp.application_to_dict(a), a) for a in apps.values()),
            key=lambda d: d["extension"],
        ),
        "ami_users": sorted(out_ami, key=lambda d: d["username"]),
    }


def check_golden(name: str, data: dict[str, Any]) -> None:
    """Compare ``data`` with ``golden/<name>.json``; ``UPDATE_GOLDEN=1`` rewrites it."""
    path = GOLDEN / f"{name}.json"
    rendered = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1" or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered)
        if os.environ.get("UPDATE_GOLDEN") != "1":
            raise AssertionError(f"golden file {path} was missing and has been created")
        return
    expected = json.loads(path.read_text())
    assert json.loads(rendered) == expected, (
        f"import result differs from {path.name}; run with UPDATE_GOLDEN=1 to accept"
    )


# --- semantic view of a config.xml ------------------------------------------------------


def _opt(value: str) -> str | None:
    return value or None


def _ring(value: str) -> str:
    return value or "indefinitely"


def _nat(value: str) -> bool:
    return value.lower() not in ("no", "never")


def _phone(node: Node, tech: str) -> dict[str, Any]:
    d: dict[str, Any] = {
        "tech": tech,
        "extension": node.text("extension"),
        "callerid": node.text("callerid"),
        "descr": _opt(node.text("descr")),
        "language": node.text("language") or "en-us",
        "ringlength": _ring(node.text("ringlength")),
        "publicaccess": node.text("publicaccess") == "enabled",
        "publicname": _opt(node.text("publicname")),
        "vmtoemail": node.text("vmtoemail") == "enabled",
        "vmtoemailaddress": _opt(node.text("vmtoemailaddress")),
        "vmpin": _opt(node.text("vmpin")),
        "emailcallnotify": node.text("emailcallnotify") == "enabled",
        "emailcallnotifyaddress": _opt(node.text("emailcallnotifyaddress")),
        "disabled": node.flag("disabled"),
    }
    if tech in ("sip", "iax"):
        d["secret"] = node.text("secret")
        d["codec"] = node.texts("codec")
        d["provider"] = sorted(node.texts("provider"))
        d["outgoingcalleridmap"] = {
            m.text("provideruniqid"): m.text("cidstring") for m in node.nodes("outgoingcalleridmap")
        }
        d["manualattributes"] = decode_b64(node.text("manualattributes")) or None
    if tech == "sip":
        d["dtmfmode"] = node.text("dtmfmode") or "auto"
        d["nat"] = _nat(node.text("natmode"))
        d["busylevel"] = _opt(node.text("busylevel"))
    if tech == "external":
        d["dialprovider"] = node.text("dialprovider") or "sipuri"
        d["dialstring"] = node.text("dialstring")
    return d


def _provider(node: Node, tech: str) -> dict[str, Any]:
    d: dict[str, Any] = {
        "tech": tech,
        "name": node.text("name"),
        "host": node.text("host"),
        "port": _opt(node.text("port")),
        "username": node.text("username"),
        "secret": _opt(node.text("secret")),
        "noregister": node.flag("noregister"),
        "readbacknumber": _opt(node.text("readbacknumber")),
        "language": node.text("language") or "en-us",
        "codec": node.texts("codec"),
        "qualify": node.text("qualify") != "0",
        "calleridsource": node.text("calleridsource") or "phones",
        "calleridstring": _opt(node.text("calleridstring")),
        "override": node.text("override") if node.text("override") not in ("", "disable") else None,
        "overridestring": _opt(node.text("overridestring")),
        "failover": _opt(node.text("failover")),
        "dialpattern": node.texts("dialpattern"),
        "incomingextensionmap": sorted(
            (m.text("incomingpattern"), m.text("destinationid")) for m in node.nodes("incomingextensionmap")
        ),
        "disabled": node.flag("disabled"),
    }
    if tech == "sip":
        d.update(
            authuser=_opt(node.text("authuser")),
            fromuser=_opt(node.text("fromuser")),
            fromdomain=_opt(node.text("fromdomain")),
            dtmfmode=node.text("dtmfmode") or "auto",
            nat=_nat(node.text("natmode")),
        )
    else:
        d["authentication"] = node.text("authentication") or "md5"
    return d


def legacy_view(data: bytes) -> dict[str, Any]:
    """Supported subset of a config.xml, keyed by uniqid / natural keys."""
    root = parse_bytes(data).root
    view: dict[str, Any] = {"phones": {}, "providers": {}}
    for tech in ("sip", "iax", "external"):
        for node in root.node(tech).nodes("phone"):
            view["phones"][node.text("uniqid")] = _phone(node, tech)
    for tech in ("sip", "iax"):
        for node in root.node(tech).nodes("provider"):
            view["providers"][node.text("uniqid")] = _provider(node, tech)
    dpn = root.node("dialplan")
    view["callgroups"] = {
        g.text("uniqid"): {
            "name": g.text("name"),
            "extension": g.text("extension"),
            "descr": _opt(g.text("descr")),
            "groupmember": g.texts("groupmember"),
            "ringlength": _ring(g.text("ringlength")),
            "publicaccess": g.text("publicaccess") == "enabled",
            "publicname": _opt(g.text("publicname")),
        }
        for g in dpn.nodes("callgroup")
    }
    view["applications"] = {
        a.text("uniqid"): {
            "name": a.text("name"),
            "extension": a.text("extension"),
            "descr": _opt(a.text("descr")),
            "logic": decode_b64(a.text("applicationlogic")),
            "type": a.text("type") or "plaintext",
            "publicaccess": a.text("publicaccess") == "enabled",
            "publicname": _opt(a.text("publicname")),
            "disabled": a.flag("disabled"),
        }
        for a in dpn.nodes("application")
    }
    view["rooms"] = {
        r.text("uniqid"): {
            "number": r.text("number"),
            "name": r.text("name"),
            "pin": _opt(r.text("pin")),
            "adminpin": _opt(r.text("adminpin")),
            "publicaccess": r.text("publicaccess") == "enabled",
            "publicname": _opt(r.text("publicname")),
        }
        for r in root.node("conferencing").nodes("room")
    }
    view["manager"] = {
        u.text("username"): {
            "secret": u.text("secret"),
            "permit": f"{u.text('permitip')}/{u.text('permitnetmask')}",
            "read": u.texts("read-permission"),
            "write": u.texts("write-permission"),
        }
        for u in root.node("services", "manager").nodes("manager-user")
    }
    sysn = root.node("system")
    lan = root.node("interfaces", "lan")
    services = root.node("services")
    view["settings"] = {
        "system": {k: sysn.text(k) for k in ("hostname", "domain", "timezone", "tonezone", "timeservers")}
        | {"dnsserver": sysn.texts("dnsserver"), "ui": sysn.node("webgui").text("language")},
        "lan": {
            "dhcp": lan.flag("dhcp"),
            **{k: _opt(lan.text(k)) for k in ("ipaddr", "subnet", "gateway", "extipaddr", "exthostname")},
            "topology": lan.text("topology") or "public",
        },
        "sip": {k: _opt(services.node("sip").text(k)) for k in ("port", "defaultexpiry", "minexpiry", "maxexpiry")}
        | {"disablesrv": services.node("sip").flag("disablesrv")},
        "iax": {
            "port": services.node("iax").text("port"),
            "jbenable": services.node("iax").flag("jbenable"),
            "jbforce": services.node("iax").flag("jbforce"),
            "manual": [decode_b64(x) for x in services.node("iax").texts("manual-attribute")],
        },
        "rtp": {k: services.node("rtp").text(k) for k in ("lowport", "highport")},
        "callparking": dict(dpn.node("callparking").items()),
        "featuremap": dict(dpn.node("featuremap").items()),
        "voicemail": {
            "fromaddress": root.node("voicemail").text("fromaddress"),
            "user_defined": root.node("voicemail").flag("user_defined"),
            "subject": decode_b64(root.node("voicemail").text("user_subject")),
            "body": decode_b64(root.node("voicemail").text("user_body")),
        },
        "email": {
            k: root.node("notifications", "email").text(k)
            for k in ("host", "port", "username", "password", "address", "enctype")
        }
        | {"disablecertcheck": root.node("notifications", "email").flag("disablecertcheck")},
    }
    return view


def view_diff(before: Any, after: Any, path: str = "") -> set[str]:
    """Paths where two views differ (``-`` missing after, ``+`` new after)."""
    if isinstance(before, dict) and isinstance(after, dict):
        out: set[str] = set()
        for key in set(before) | set(after):
            sub = f"{path}/{key}"
            if key not in after:
                out.add(f"-{sub}")
            elif key not in before:
                out.add(f"+{sub}")
            else:
                out |= view_diff(before[key], after[key], sub)
        return out
    return set() if before == after else {path}
