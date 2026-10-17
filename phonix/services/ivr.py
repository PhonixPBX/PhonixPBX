# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""IVR menus (auto attendant): an announcement, then one destination per key."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix.core import validation as v
from phonix.core.models import IvrMenu, IvrOption, MediaFile
from phonix.i18n import N_, _
from phonix.services import destinations as dst
from phonix.services.common import NotFound, ServiceError, audit, diff_dicts, ensure_extension_free, mark_dirty
from phonix.services.phones import public_name

KEYS = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "*", "#")
PROMPT_KIND = "ivr_prompt"
# an Asterisk sound below the sounds directory, without extension
_SOUND = re.compile(r"^[a-z0-9][a-z0-9_/-]{0,63}$")
# suggestions for the "built-in sound" picker (Asterisk core sounds)
SOUNDS = ("welcome", "hello-world", "pls-hold-while-try", "demo-instruct", "vm-goodbye")


def _name(value: str) -> str:
    value = v.config_value(value, N_("Name"))
    if not value:
        raise ValueError(_("Name is required"))
    return value


class IvrOptionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    label: str = Field(default="", max_length=80)
    dest_type: dst.IvrType
    dest_id: int | None = None

    _dest = field_validator("dest_type", mode="before")(lambda cls, x: dst.required(x))

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        value = value.strip()
        if value not in KEYS:
            raise ValueError(_("Choose a key from 0-9, * or #"))
        return value

    @field_validator("label")
    @classmethod
    def _label(cls, value: str) -> str:
        return v.config_value(value, N_("Label"))


class IvrMenuIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    extension: str = ""
    description: str = ""
    enabled: bool = True
    public_access: bool = False
    public_name: str = ""
    prompt_mode: Literal["upload", "sound"] = "upload"
    prompt_media_id: int | None = None
    prompt_sound: str = ""
    prompt_text: str = Field(default="", max_length=4000)
    timeout: int = Field(default=5, ge=1, le=60)
    repeats: int = Field(default=2, ge=0, le=9)
    direct_dial: bool = False
    timeout_dest_type: dst.IvrTimeoutType = "hangup"
    timeout_dest_id: int | None = None
    invalid_dest_type: dst.IvrType = "repeat"
    invalid_dest_id: int | None = None
    options: list[IvrOptionIn] = Field(default_factory=list, max_length=len(KEYS))

    _name = field_validator("name")(lambda cls, x: _name(x))
    _dests = field_validator("timeout_dest_type", "invalid_dest_type", mode="before")(lambda cls, x: dst.required(x))
    _desc = field_validator("description")(lambda cls, x: v.no_control(x.strip(), N_("Description")))
    _pub = field_validator("public_name")(lambda cls, x: public_name(x))

    @field_validator("extension")
    @classmethod
    def _ext(cls, value: str) -> str:
        return v.extension(value) if value.strip() else ""

    @field_validator("prompt_sound")
    @classmethod
    def _sound(cls, value: str) -> str:
        value = value.strip()
        if value and not _SOUND.match(value):
            raise ValueError(_("Enter the name of an Asterisk sound, e.g. welcome"))
        return value


def list_menus(session: Session) -> list[IvrMenu]:
    return list(session.scalars(select(IvrMenu).order_by(IvrMenu.name, IvrMenu.id)))


def get_menu(session: Session, menu_id: int) -> IvrMenu:
    menu = session.get(IvrMenu, menu_id)
    if menu is None:
        raise NotFound(_("IVR menu not found"))
    return menu


def list_prompts(session: Session) -> list[MediaFile]:
    return list(session.scalars(select(MediaFile).where(MediaFile.kind == PROMPT_KIND).order_by(MediaFile.name)))


def to_dict(m: IvrMenu) -> dict[str, Any]:
    return {
        "id": m.id,
        "name": m.name,
        "extension": m.extension or "",
        "description": m.description,
        "enabled": m.enabled,
        "public_access": m.public_access,
        "public_name": m.public_name,
        "prompt_mode": m.prompt_mode,
        "prompt_media_id": m.prompt_media_id,
        "prompt_sound": m.prompt_sound,
        "prompt_text": m.prompt_text,
        "timeout": m.timeout,
        "repeats": m.repeats,
        "direct_dial": m.direct_dial,
        "timeout_dest_type": m.timeout_dest_type,
        "timeout_dest_id": m.timeout_dest_id,
        "invalid_dest_type": m.invalid_dest_type,
        "invalid_dest_id": m.invalid_dest_id,
        "options": [
            {"key": o.key, "label": o.label, "dest_type": o.dest_type, "dest_id": o.dest_id} for o in m.options
        ],
    }


def _check(session: Session, data: IvrMenuIn, own_id: int | None) -> None:
    if data.extension:
        ensure_extension_free(session, data.extension, "extension", own=(IvrMenu, own_id) if own_id else None)
    if data.prompt_mode == "upload":
        media = session.get(MediaFile, data.prompt_media_id) if data.prompt_media_id is not None else None
        if media is None or media.kind != PROMPT_KIND:
            raise ServiceError(fields={"prompt_media_id": _("Choose or upload an announcement")})
    elif not data.prompt_sound:
        raise ServiceError(fields={"prompt_sound": _("Choose a sound")})
    seen: dict[str, int] = {}
    for idx, option in enumerate(data.options):
        if option.key in seen:
            raise ServiceError(fields={f"options.{idx}": _("Key %(key)s is used more than once", key=option.key)})
        seen[option.key] = idx
        dst.check(session, option.dest_type, option.dest_id, f"options.{idx}")
    dst.check(session, data.timeout_dest_type, data.timeout_dest_id, "timeout_dest")
    if data.timeout_dest_type == "ivr" and own_id is not None and data.timeout_dest_id == own_id:
        raise ServiceError(fields={"timeout_dest": _("Use “Repeat the menu” to play this menu again")})
    dst.check(session, data.invalid_dest_type, data.invalid_dest_id, "invalid_dest")


def _apply(menu: IvrMenu, data: IvrMenuIn) -> None:
    for field in (
        "name",
        "description",
        "enabled",
        "public_access",
        "public_name",
        "prompt_mode",
        "prompt_sound",
        "prompt_text",
        "timeout",
        "repeats",
        "direct_dial",
        "timeout_dest_type",
        "invalid_dest_type",
    ):
        setattr(menu, field, getattr(data, field))
    menu.extension = data.extension or None
    # keep the stored file when switching to a sound, so switching back needs no new upload
    if data.prompt_media_id is not None or data.prompt_mode == "upload":
        menu.prompt_media_id = data.prompt_media_id
    menu.timeout_dest_id = None if data.timeout_dest_type in dst.ACTIONS else data.timeout_dest_id
    menu.invalid_dest_id = None if data.invalid_dest_type in dst.ACTIONS else data.invalid_dest_id
    # reuse rows by key: the flush inserts new options before it deletes orphans,
    # so a fresh row for a key that stays would violate (menu_id, key)
    existing = {o.key: o for o in menu.options}
    options = []
    for idx, o in enumerate(data.options):
        row = existing.get(o.key) or IvrOption(key=o.key)
        row.label = o.label
        row.dest_type = o.dest_type
        row.dest_id = None if o.dest_type in dst.ACTIONS else o.dest_id
        row.position = idx
        options.append(row)
    menu.options = options


def create_menu(session: Session, data: IvrMenuIn, user: str = "") -> IvrMenu:
    _check(session, data, None)
    menu = IvrMenu()
    _apply(menu, data)
    session.add(menu)
    session.flush()
    audit(session, user, "create", "ivr", menu.id, menu.name)
    mark_dirty(session, "dialplan")
    return menu


def update_menu(session: Session, menu_id: int, data: IvrMenuIn, user: str = "") -> IvrMenu:
    menu = get_menu(session, menu_id)
    _check(session, data, menu.id)
    before = to_dict(menu)
    _apply(menu, data)
    session.flush()
    audit(session, user, "update", "ivr", menu.id, menu.name, diff_dicts(before, to_dict(menu)))
    mark_dirty(session, "dialplan")
    return menu


def set_enabled(session: Session, menu_id: int, enabled: bool, user: str = "") -> IvrMenu:
    menu = get_menu(session, menu_id)
    menu.enabled = enabled
    audit(session, user, "enable" if enabled else "disable", "ivr", menu.id, menu.name)
    mark_dirty(session, "dialplan")
    return menu


def delete_menu(session: Session, menu_id: int, user: str = "") -> None:
    menu = get_menu(session, menu_id)
    audit(session, user, "delete", "ivr", menu.id, menu.name)
    dst.forget(session, "ivr", menu.id)
    session.delete(menu)
    session.flush()
    mark_dirty(session, "dialplan")


def spoken_key(key: str) -> str:
    if key == "*":
        return _("star")
    if key == "#":
        return _("the hash key")
    return key


def script(session: Session, options: list[IvrOptionIn]) -> str:
    """A recording script for the announcement, from the options in their order."""
    lines = []
    for o in options:
        key = spoken_key(o.key)
        if o.dest_type == "repeat":
            lines.append(_("To hear these options again, press %(key)s.", key=key))
        elif o.dest_type == "hangup":
            lines.append(_("To end the call, press %(key)s.", key=key))
        else:
            what = o.label or dst.label(session, o.dest_type, o.dest_id)
            lines.append(_("For %(what)s, press %(key)s.", what=what, key=key))
    return " ".join(lines)


def flow(session: Session, menu: IvrMenu, max_depth: int = 3) -> list[dict[str, Any]]:
    """The saved call flow below ``menu`` as rows of a tree: sub-menus are expanded,
    a menu already on the path is shown as a way back instead of again."""
    rows: list[dict[str, Any]] = []

    def walk(current: IvrMenu, depth: int, path: tuple[int, ...]) -> None:
        for o in current.options:
            row = {
                "depth": depth,
                "key": o.key,
                "label": o.label,
                "dest": dst.label(session, o.dest_type, o.dest_id),
                "menu_id": None,
                "back": False,
            }
            rows.append(row)
            if o.dest_type != "ivr" or o.dest_id is None:
                continue
            target = session.get(IvrMenu, o.dest_id)
            if target is None:
                continue
            row["menu_id"] = target.id
            if target.id in path:
                row["back"] = True
            elif depth < max_depth:
                walk(target, depth + 1, (*path, target.id))

    walk(menu, 0, (menu.id,))
    return rows
