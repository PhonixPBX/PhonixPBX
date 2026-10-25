# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""API bearer tokens: random ``phx_...`` strings, stored as sha256 only."""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from phonix.core.models import ApiToken, User, utcnow
from phonix.i18n import _
from phonix.services.common import NotFound, ServiceError, audit

PREFIX = "phx_"
MAX_DAYS = 3653  # 10 years
# last_used_at is updated at most this often (no DB write per API request)
LAST_USED_RESOLUTION = dt.timedelta(minutes=5)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def status(token: ApiToken, now: dt.datetime | None = None) -> str:
    if not token.enabled:
        return "disabled"
    if token.expires_at is not None and token.expires_at <= (now or utcnow()):
        return "expired"
    return "active"


def create(
    session: Session,
    user: User,
    name: str,
    read_only: bool = True,
    allow_calls: bool = False,
    expires_in_days: int | None = None,
    actor: str = "",
) -> tuple[ApiToken, str]:
    """Create a token; the plain text is returned once and never stored."""
    name = name.strip()
    if not name or len(name) > 64:
        raise ServiceError(fields={"name": _("Enter a name of up to 64 characters")})
    if expires_in_days is not None and not 1 <= expires_in_days <= MAX_DAYS:
        raise ServiceError(fields={"expires_in_days": _("Choose 1 to %(max)s days", max=MAX_DAYS)})
    plain = PREFIX + secrets.token_urlsafe(32)
    now = utcnow()
    token = ApiToken(
        name=name,
        token_hash=_hash(plain),
        prefix=plain[:12],
        read_only=read_only,
        allow_calls=allow_calls,
        enabled=True,
        user=user,
        created_at=now,
        expires_at=now + dt.timedelta(days=expires_in_days) if expires_in_days else None,
    )
    session.add(token)
    session.flush()
    access = "read-only" if read_only else "read-write"
    if allow_calls:
        access += ", calls"
    audit(session, actor or user.username, "create", "api_token", token.id, f"{name} ({access})")
    return token, plain


def authenticate(session: Session, plain: str) -> ApiToken | None:
    if not plain.startswith(PREFIX):
        return None
    token = session.scalar(
        select(ApiToken).options(joinedload(ApiToken.user)).where(ApiToken.token_hash == _hash(plain))
    )
    now = utcnow()
    if token is None or status(token, now) != "active":
        return None
    if token.last_used_at is None or now - token.last_used_at >= LAST_USED_RESOLUTION:
        token.last_used_at = now
    return token


def list_tokens(session: Session) -> list[ApiToken]:
    return list(session.scalars(select(ApiToken).options(joinedload(ApiToken.user)).order_by(ApiToken.id)))


def get(session: Session, token_id: int) -> ApiToken:
    token = session.get(ApiToken, token_id)
    if token is None:
        raise NotFound(_("Token not found"))
    return token


def set_enabled(session: Session, token_id: int, enabled: bool, actor: str = "") -> ApiToken:
    token = get(session, token_id)
    if token.enabled != enabled:
        token.enabled = enabled
        audit(session, actor, "enable" if enabled else "disable", "api_token", token.id, token.name)
    return token


def delete(session: Session, token_id: int, actor: str = "") -> None:
    token = get(session, token_id)
    audit(session, actor, "delete", "api_token", token.id, token.name)
    session.delete(token)


def search_fields(t: ApiToken) -> tuple[object, ...]:
    return (t.name, t.prefix, t.user.username if t.user else "")


def to_dict(token: ApiToken) -> dict[str, Any]:
    return {
        "id": token.id,
        "name": token.name,
        "prefix": token.prefix,
        "read_only": token.read_only,
        "allow_calls": token.allow_calls,
        "enabled": token.enabled,
        "status": status(token),
        "user": token.user.username,
        "created_at": token.created_at,
        "last_used_at": token.last_used_at,
        "expires_at": token.expires_at,
    }
