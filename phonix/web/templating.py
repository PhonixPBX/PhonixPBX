"""Jinja2 templates, navigation menu and flash messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from phonix import __version__
from phonix.core import validation as v
from phonix.services import platform
from phonix.services.common import AREAS
from phonix.web.security import csrf_token

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


@dataclass
class MenuItem:
    title: str
    url: str
    match: tuple[str, ...] = ()


@dataclass
class MenuSection:
    key: str
    title: str
    icon: str
    items: list[MenuItem] = field(default_factory=list)


# mirrors the legacy usr/www/fbegin.inc menu
MENU: list[MenuSection] = [
    MenuSection(
        "system",
        "System",
        "settings",
        [
            MenuItem("General Setup", "/system/general"),
            MenuItem("Network", "/system/network"),
            MenuItem("Storage", "/system/storage"),
            MenuItem("Firmware", "/system/firmware"),
            MenuItem("Backup/Restore", "/system/backup"),
            MenuItem("Factory Defaults", "/system/defaults"),
            MenuItem("Reboot", "/system/reboot"),
        ],
    ),
    MenuSection(
        "accounts",
        "Accounts",
        "phone",
        [
            MenuItem("Phones", "/accounts/phones"),
            MenuItem("Providers", "/accounts/providers"),
        ],
    ),
    MenuSection(
        "dialplan",
        "Dialplan",
        "route",
        [
            MenuItem("Applications", "/dialplan/applications"),
            MenuItem("Call Groups", "/dialplan/callgroups"),
            MenuItem("Transfers & Parking", "/dialplan/transfers"),
            MenuItem("Overview (print)", "/dialplan/print"),
        ],
    ),
    MenuSection(
        "services",
        "Services",
        "server",
        [
            MenuItem("Notifications", "/services/email"),
            MenuItem("Voicemail", "/services/voicemail"),
            MenuItem("Conferencing", "/services/conferencing"),
            MenuItem("Media", "/services/media"),
        ],
    ),
    MenuSection(
        "status",
        "Status",
        "activity",
        [
            MenuItem("Summary", "/", ("/",)),
            MenuItem("Calls & Registrations", "/status/calls"),
            MenuItem("Graphs", "/status/graphs"),
            MenuItem("Logs", "/status/logs"),
            MenuItem("Audit Log", "/status/audit"),
        ],
    ),
    MenuSection(
        "advanced",
        "Advanced",
        "adjustments",
        [
            MenuItem("SIP", "/advanced/sip"),
            MenuItem("IAX", "/advanced/iax"),
            MenuItem("RTP", "/advanced/rtp"),
            MenuItem("Manager (AMI)", "/advanced/manager"),
            MenuItem("Firewall", "/advanced/firewall"),
            MenuItem("Certificate", "/advanced/certificate"),
            MenuItem("Administrators", "/advanced/users"),
            MenuItem("API tokens", "/advanced/tokens"),
            MenuItem("GUI Options", "/advanced/gui"),
        ],
    ),
]


def active_item(path: str) -> tuple[MenuSection | None, MenuItem | None]:
    best: tuple[int, MenuSection | None, MenuItem | None] = (0, None, None)
    for section in MENU:
        for item in section.items:
            if item.url == "/":
                if path == "/":
                    return section, item
                continue
            if (path == item.url or path.startswith(item.url + "/")) and len(item.url) > best[0]:
                best = (len(item.url), section, item)
    return best[1], best[2]


def flash(request: Request, message: str, level: str = "success") -> None:
    messages = request.session.setdefault("flash", [])
    messages.append({"level": level, "message": message})
    request.session["flash"] = messages


def pop_flashes(request: Request) -> list[dict[str, str]]:
    return list(request.session.pop("flash", []) or [])


def _icon(name: str, cls: str = "") -> Markup:
    return Markup(f'<i class="ti ti-{name} {cls}" aria-hidden="true"></i>')  # noqa: S704


def _asset(path: str) -> str:
    """URL of a static file with its mtime as cache buster, so browsers pick up changes."""
    try:
        version = int((STATIC_DIR / path).stat().st_mtime)
    except OSError:
        return f"/static/{path}"
    return f"/static/{path}?v={version}"


def _filesize(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024:
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} PB"


def _options(objs: Any, value: str = "id", label: str = "name") -> list[tuple[Any, Any]]:
    return [(getattr(o, value), getattr(o, label)) for o in objs]


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals.update(
    {
        "MENU": MENU,
        "VERSION": __version__,
        "icon": _icon,
        "asset": _asset,
        "options": _options,
        "LANGUAGES": v.LANGUAGES,
        "TONEZONES": v.TONEZONES,
        "CODECS_AUDIO": v.CODECS_AUDIO,
        "CODECS_VIDEO": v.CODECS_VIDEO,
    }
)
templates.env.filters["filesize"] = _filesize
templates.env.trim_blocks = True
templates.env.lstrip_blocks = True


def render(request: Request, name: str, ctx: dict[str, Any] | None = None, status_code: int = 200) -> Any:
    section, item = active_item(request.url.path)
    context: dict[str, Any] = {
        "request": request,
        "csrf_token": csrf_token(request),
        "active_section": section,
        "active_item": item,
        "flashes": pop_flashes(request),
        "user": getattr(request.state, "user", None),
        "dirty": [AREAS.get(a, a) for a in getattr(request.state, "dirty", [])],
        "is_htmx": request.headers.get("hx-request") == "true",
        "errors": {},
        # "appliance", "lxc", "oci" or "dev" (containers: host-managed network)
        "platform": platform.kind(),
    }
    context.update(ctx or {})
    return templates.TemplateResponse(request, name, context, status_code=status_code)
