# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Jinja2 templates, navigation menu and flash messages."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2
from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from phonix import __version__, i18n
from phonix.core import validation as v
from phonix.i18n import N_
from phonix.services import platform, update
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
        N_("System"),
        "settings",
        [
            MenuItem(N_("General Setup"), "/system/general"),
            MenuItem(N_("Network"), "/system/network"),
            MenuItem(N_("Storage"), "/system/storage"),
            MenuItem(N_("Firmware"), "/system/firmware"),
            MenuItem(N_("Backup/Restore"), "/system/backup"),
            MenuItem(N_("Factory Defaults"), "/system/defaults"),
            MenuItem(N_("Reboot"), "/system/reboot"),
        ],
    ),
    MenuSection(
        "accounts",
        N_("Accounts"),
        "phone",
        [
            MenuItem(N_("Phones"), "/accounts/phones"),
            MenuItem(N_("Providers"), "/accounts/providers"),
        ],
    ),
    MenuSection(
        "dialplan",
        N_("Dialplan"),
        "route",
        [
            MenuItem(N_("Applications"), "/dialplan/applications"),
            MenuItem(N_("Call Groups"), "/dialplan/callgroups"),
            MenuItem(N_("IVR Menus"), "/dialplan/ivr"),
            MenuItem(N_("Business Hours"), "/dialplan/hours"),
            MenuItem(N_("Transfers & Parking"), "/dialplan/transfers"),
            MenuItem(N_("Overview (print)"), "/dialplan/print"),
        ],
    ),
    MenuSection(
        "services",
        N_("Services"),
        "server",
        [
            MenuItem(N_("Notifications"), "/services/email"),
            MenuItem(N_("Voicemail"), "/services/voicemail"),
            MenuItem(N_("Conferencing"), "/services/conferencing"),
            MenuItem(N_("Media"), "/services/media"),
        ],
    ),
    MenuSection(
        "status",
        N_("Status"),
        "activity",
        [
            MenuItem(N_("Summary"), "/", ("/",)),
            MenuItem(N_("Calls & Registrations"), "/status/calls"),
            MenuItem(N_("Graphs"), "/status/graphs"),
            MenuItem(N_("Logs"), "/status/logs"),
            MenuItem(N_("Audit Log"), "/status/audit"),
        ],
    ),
    MenuSection(
        "advanced",
        N_("Advanced"),
        "adjustments",
        [
            MenuItem(N_("SIP"), "/advanced/sip"),
            MenuItem(N_("IAX"), "/advanced/iax"),
            MenuItem(N_("RTP"), "/advanced/rtp"),
            MenuItem(N_("Manager (AMI)"), "/advanced/manager"),
            MenuItem(N_("Firewall"), "/advanced/firewall"),
            MenuItem(N_("Certificate"), "/advanced/certificate"),
            MenuItem(N_("Administrators"), "/advanced/users"),
            MenuItem(N_("API tokens"), "/advanced/tokens"),
            MenuItem(N_("GUI Options"), "/advanced/gui"),
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


# manual languages besides English (docs/manual/hugo.toml); other UI languages link to English
HELP_LANGUAGES = ("de",)


def help_url(page: str | None = None, anchor: str = "") -> str:
    """URL of the manual chapter for a menu URL (docs/manual mirrors the menu paths) in the UI language."""
    lang = i18n.get_language().split("_")[0]
    url = "/help/" + (f"{lang}/" if lang in HELP_LANGUAGES else "")
    if page is not None:
        url += (page.strip("/") or "status/summary") + "/"
    return f"{url}#{anchor}" if anchor else url


def flash(request: Request, message: str, level: str = "success") -> None:
    messages = request.session.setdefault("flash", [])
    messages.append({"level": level, "message": message})
    request.session["flash"] = messages


def pop_flashes(request: Request) -> list[dict[str, str]]:
    return list(request.session.pop("flash", []) or [])


# device, registration and peer states as Asterisk reports them (translated for display)
ASTERISK_STATES = (
    N_("Not in use"),
    N_("In use"),
    N_("Busy"),
    N_("Ringing"),
    N_("Ring+Inuse"),
    N_("On Hold"),
    N_("Unavailable"),
    N_("Invalid"),
    N_("Unknown"),
    N_("Registered"),
    N_("Unregistered"),
    N_("Rejected"),
    N_("Stopped"),
    N_("Reachable"),
    N_("Unreachable"),
    N_("Lagged"),
    N_("Avail"),
    N_("Unavail"),
    # channel states
    N_("Up"),
    N_("Down"),
    N_("Ring"),
    N_("Dialing"),
    N_("Pre-ring"),
    N_("Reserved"),
    N_("Off hook"),
)


def _state(value: str) -> str:
    """Translate an Asterisk state (no %-formatting: the value is not a template string)."""
    return i18n.translations(i18n.get_language()).gettext(value) if value else value


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


def _loader(directory: Path, dev: bool) -> jinja2.BaseLoader:
    """All templates, read once at the start.

    An in-place update (LXC) replaces the files on disk while this version runs on until
    the restart; its routes must keep rendering their own templates."""
    if dev:
        return jinja2.FileSystemLoader(directory)  # edits show up without a restart
    return jinja2.DictLoader(
        {p.relative_to(directory).as_posix(): p.read_text(encoding="utf-8") for p in sorted(directory.rglob("*.html"))}
    )


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.loader = _loader(TEMPLATES_DIR, os.environ.get("PHONIX_DEV") == "1")
templates.env.globals.update(
    {
        "MENU": MENU,
        "VERSION": __version__,
        "icon": _icon,
        "asset": _asset,
        "help_url": help_url,
        "options": _options,
        "LANGUAGES": v.LANGUAGES,
        "TONEZONES": v.TONEZONES,
        "CODECS_AUDIO": v.CODECS_AUDIO,
        "CODECS_VIDEO": v.CODECS_VIDEO,
    }
)
templates.env.add_extension("jinja2.ext.i18n")
templates.env.install_gettext_callables(  # type: ignore[attr-defined]
    gettext=lambda message: i18n.translations(i18n.get_language()).gettext(message),
    ngettext=lambda s, p, n: i18n.translations(i18n.get_language()).ngettext(s, p, n),
    newstyle=True,
)
templates.env.globals["UI_LANGUAGES"] = i18n.LANGUAGE_NAMES
templates.env.globals["ui_language"] = i18n.get_language
templates.env.filters["filesize"] = _filesize
templates.env.filters["state"] = _state
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
        # an installed update that waits for the reboot (banner on every page)
        "reboot_pending": update.pending_reboot(),
    }
    context.update(ctx or {})
    return templates.TemplateResponse(request, name, context, status_code=status_code)
