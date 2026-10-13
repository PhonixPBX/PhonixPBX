# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Asterisk Manager Interface (AMI) users configured by the administrator."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix.core import validation as v
from phonix.core.models import AmiUser
from phonix.i18n import _
from phonix.services.common import NotFound, ServiceError, audit, mark_dirty

# reserved for the PBX itself (see generators/asterisk.py)
INTERNAL_USER = "phonix"

PERMISSIONS = (
    "all",
    "system",
    "call",
    "log",
    "verbose",
    "command",
    "agent",
    "user",
    "config",
    "dtmf",
    "reporting",
    "cdr",
    "dialplan",
    "originate",
    "agi",
    "cc",
    "aoc",
    "test",
    "security",
    "message",
)

_NAME = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


class AmiUserIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str
    secret: str = ""
    permit: list[str] = Field(default_factory=lambda: ["127.0.0.1/32"])
    read_perms: list[str] = Field(default_factory=lambda: ["all"])
    write_perms: list[str] = Field(default_factory=list)

    @field_validator("username")
    @classmethod
    def _name(cls, value: str) -> str:
        value = value.strip()
        if not _NAME.match(value):
            raise ValueError(_("Username may contain letters, digits, '_' and '-'"))
        if value in (INTERNAL_USER, "general"):
            raise ValueError(_("This username is reserved"))
        return value

    @field_validator("secret")
    @classmethod
    def _secret(cls, value: str) -> str:
        return v.secret(value) if value else ""

    @field_validator("permit")
    @classmethod
    def _permit(cls, value: list[str]) -> list[str]:
        nets = [v.network(n) for n in value if n.strip()]
        if not nets:
            raise ValueError(_("At least one permitted network is required"))
        return nets

    @field_validator("read_perms", "write_perms")
    @classmethod
    def _perms(cls, value: list[str]) -> list[str]:
        for perm in value:
            if perm not in PERMISSIONS:
                raise ValueError(_("Unknown permission %(name)r", name=perm))
        return list(dict.fromkeys(value))


def list_ami_users(session: Session) -> list[AmiUser]:
    return list(session.scalars(select(AmiUser).order_by(AmiUser.username)))


def get_ami_user(session: Session, user_id: int) -> AmiUser:
    user = session.get(AmiUser, user_id)
    if user is None:
        raise NotFound(_("Manager user not found"))
    return user


def to_dict(u: AmiUser) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "permit": list(u.permit),
        "read_perms": list(u.read_perms),
        "write_perms": list(u.write_perms),
    }


def _apply(session: Session, user: AmiUser, data: AmiUserIn) -> None:
    other = session.scalar(select(AmiUser).where(AmiUser.username == data.username))
    if other is not None and other.id != user.id:
        raise ServiceError(fields={"username": _("Username already exists")})
    if not data.secret and not user.secret:
        raise ServiceError(fields={"secret": _("A secret is required")})
    user.username = data.username
    if data.secret:
        user.secret = data.secret
    user.permit = data.permit
    user.read_perms = data.read_perms
    user.write_perms = data.write_perms


def create_ami_user(session: Session, data: AmiUserIn, actor: str = "") -> AmiUser:
    user = AmiUser(secret="")
    _apply(session, user, data)
    session.add(user)
    session.flush()
    audit(session, actor, "create", "ami_user", user.id, user.username)
    mark_dirty(session, "manager")
    return user


def update_ami_user(session: Session, user_id: int, data: AmiUserIn, actor: str = "") -> AmiUser:
    user = get_ami_user(session, user_id)
    _apply(session, user, data)
    session.flush()
    audit(session, actor, "update", "ami_user", user.id, user.username)
    mark_dirty(session, "manager")
    return user


def delete_ami_user(session: Session, user_id: int, actor: str = "") -> None:
    user = get_ami_user(session, user_id)
    audit(session, actor, "delete", "ami_user", user.id, user.username)
    session.delete(user)
    session.flush()
    mark_dirty(session, "manager")
