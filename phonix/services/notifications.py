# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Texts of the voicemail and missed call e-mails per language.

The built-in texts live in ``phonix.notify`` (the sender) and are translated through the
catalogs; ``VoicemailSettings.templates`` holds the administrator's overrides per language.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy.orm import Session

from phonix import i18n
from phonix.core import settings as st
from phonix.core.models import Phone
from phonix.notify import DEFAULTS, REASONS, UNKNOWN, format_date, render
from phonix.services.common import audit, mark_dirty, parse

FIELDS = tuple(DEFAULTS)

# preview values per e-mail
SAMPLE = {
    "VM_NAME": "Alice",
    "VM_DUR": "0:42",
    "VM_MSGNUM": "1",
    "VM_MAILBOX": "101",
    "VM_CALLERID": '"Bob" <0441234567>',
    "NAME": "Alice",
    "EXTENSION": "101",
    "CALLERID": '"Bob" <0441234567>',
}


def default_texts(lang: str) -> dict[str, str]:
    with i18n.language(lang):
        return {key: i18n._(text) for key, text in DEFAULTS.items()}


def texts(vm: st.VoicemailSettings, lang: str) -> dict[str, str]:
    """The texts used for ``lang``: the override where set, else the translated default."""
    out = default_texts(lang)
    custom = vm.templates.get(lang)
    if custom:
        out.update({key: value for key, value in custom.model_dump().items() if value})
    return out


def runtime_texts(vm: st.VoicemailSettings, lang: str) -> dict[str, Any]:
    """Everything the sender needs for one language (phonix-notify.json)."""
    out: dict[str, Any] = texts(vm, lang)
    with i18n.language(lang):
        out["reasons"] = {cause: i18n._(text) for cause, text in REASONS.items()}
        out["unknown"] = i18n._(UNKNOWN)
    return out


def effective_language(phone: Phone) -> str:
    return phone.notify_language or phone.language or i18n.DEFAULT


def preview(vm: st.VoicemailSettings, lang: str) -> dict[str, str]:
    """The texts of ``lang`` filled in with sample values."""
    cause = REASONS["no-answer"]
    with i18n.language(lang):
        reason = i18n._(cause)
    date = format_date(dt.datetime(2026, 3, 14, 9, 26), lang)
    values = {**SAMPLE, "VM_DATE": date, "DATE": date, "REASON": reason}
    return {key: render(text, values) for key, text in texts(vm, lang).items()}


def save_texts(session: Session, lang: str, data: dict[str, str], user: str = "") -> st.VoicemailSettings:
    """Store the texts for ``lang``; a text equal to the default is not stored, so it keeps
    following the built-in translation."""
    lang = i18n.normalize(lang)
    defaults = default_texts(lang)
    clean: st.NotificationTexts = parse(st.NotificationTexts, {key: data.get(key, "") for key in FIELDS})
    values = clean.model_dump()
    for key in FIELDS:
        if values[key].strip() == defaults[key].strip():
            values[key] = ""
    vm = st.load(session, st.VoicemailSettings)
    templates = {k: t.model_dump() for k, t in vm.templates.items()}
    templates[lang] = values
    vm = st.VoicemailSettings.model_validate({**vm.model_dump(), "templates": templates})
    st.save(session, vm)
    audit(session, user, "update", "settings", "voicemail", f"voicemail e-mail texts ({lang})")
    mark_dirty(session, "services")
    return vm


def reset_texts(session: Session, lang: str, user: str = "") -> None:
    vm = st.load(session, st.VoicemailSettings)
    if lang not in vm.templates:
        return
    templates = {k: t.model_dump() for k, t in vm.templates.items() if k != lang}
    st.save(session, st.VoicemailSettings.model_validate({**vm.model_dump(), "templates": templates}))
    audit(session, user, "update", "settings", "voicemail", f"voicemail e-mail texts ({lang}) reset")
    mark_dirty(session, "services")
