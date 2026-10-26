# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Settings groups as JSON objects for the REST API and MCP: secrets are never returned."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from phonix.core import settings as st
from phonix.services.common import NotFound, ServiceError, audit, errors_from_validation, mark_dirty

SETTINGS = {st.group_name(m): m for m in st.ALL_GROUPS}
SECRET_SETTINGS = {
    "email": ("password",),
    "system": ("ssh_password_hash",),
    "acme": ("eab_hmac", "dns_env"),
    "tts": ("token",),
}
# a kept secret belongs to the server it was entered for: changing that address without a new
# secret drops it, so a changed address never receives the old credential
SECRET_BOUND = {"tts": {"token": "url"}}
SETTINGS_AREAS = {
    "system": ("system", "network", "telephony", "firewall"),
    "network": ("network", "telephony"),
    "rtp": ("telephony", "firewall"),
    "sip": ("telephony", "firewall"),
    "iax": ("telephony", "firewall"),
    "voicemail": ("services",),
    "email": ("email", "dialplan", "services"),
    "features": ("dialplan",),
    "media": ("services",),
    "firewall": ("firewall",),
}


def _model(group: str) -> type[st.SettingsGroup]:
    model = SETTINGS.get(group)
    if model is None:
        raise NotFound("unknown settings group")
    return model


def read_group(session: Session, group: str) -> dict[str, Any]:
    data = st.load(session, _model(group)).model_dump()
    for name in SECRET_SETTINGS.get(group, ()):
        # credential maps keep their keys so clients know what is set
        data[name] = dict.fromkeys(data[name], "") if isinstance(data[name], dict) else ""
    return data


def patch_group(session: Session, group: str, body: dict[str, Any], actor: str, via: str = "API") -> dict[str, Any]:
    """Merge ``body`` into the stored group; empty secrets keep the stored value."""
    model = _model(group)
    stored = st.load(session, model)
    current = stored.model_dump()
    body = dict(body)
    for name in SECRET_SETTINGS.get(group, ()):
        if isinstance(body.get(name), dict) and isinstance(current.get(name), dict):
            stored = current[name]
            body[name] = {k: val or stored.get(k, "") for k, val in body[name].items()}
        elif not body.get(name):
            body.pop(name, None)  # reads return secrets empty: keep the stored one
    current.update(body)
    try:
        new = model.model_validate(current)
    except ValidationError as exc:
        raise ServiceError(fields=errors_from_validation(exc)) from None
    drop_bound_secrets(stored, new, set(body))
    st.save(session, new)
    audit(session, actor, "update", "settings", group, summary=f"{group} ({via})")
    if SETTINGS_AREAS.get(group):
        mark_dirty(session, *SETTINGS_AREAS[group])
    return read_group(session, group)


def drop_bound_secrets(old: st.SettingsGroup, new: st.SettingsGroup, submitted: set[str]) -> None:
    """Clear a secret that was kept (not submitted) while the address it belongs to changed."""
    for secret, address in SECRET_BOUND.get(st.group_name(type(new)), {}).items():
        if secret not in submitted and getattr(old, address) != getattr(new, address):
            setattr(new, secret, "")
