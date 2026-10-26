# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Click-to-call: ring a phone, then dial a number from it (AMI Originate).

The number is dialled in the phone's own ``phone-<ext>`` context, so its outgoing
rules, blocked providers and caller ID apply as if it had been dialled on the phone.
Used by the REST API and MCP only, so the messages are not translated.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from phonix import ami
from phonix.core.models import IvrMenu, Phone
from phonix.services.common import NotFound, ServiceError, audit

NUMBER_RE = re.compile(r"^[0-9*#+]{1,32}$")
CHANNEL_TECH = {"pjsip": "PJSIP", "iax": "IAX2"}
RING_TIMEOUT_MS = 30000


def phone_for_call(session: Session, extension: str) -> Phone:
    phone = session.scalar(select(Phone).where(Phone.extension == extension.strip()))
    if phone is None:
        raise NotFound(f"no phone with extension {extension!r}")
    if not phone.enabled:
        raise ServiceError(fields={"extension": "the phone is disabled"})
    if phone.tech not in CHANNEL_TECH:
        raise ServiceError(fields={"extension": "only SIP and IAX phones can place calls"})
    return phone


def originate_into(
    phone: Phone, context: str, exten: str, callerid: str, variables: dict[str, str] | None = None
) -> None:
    """Ring the phone; when it is answered, the call continues at ``context``/``exten``."""
    extra = {"Variable": ",".join(f"{k}={v}" for k, v in variables.items())} if variables else {}
    try:
        with ami.AmiClient() as client:
            resp = client.action(
                "Originate",
                Channel=f"{CHANNEL_TECH[phone.tech]}/{phone.extension}",
                Context=context,
                Exten=exten,
                Priority=1,
                CallerID=callerid,
                Timeout=RING_TIMEOUT_MS,
                Async="true",
                **extra,
            )
    except (ami.AmiError, OSError) as exc:
        raise ServiceError(f"Asterisk manager: {exc}") from exc
    if resp.get("Response") != "Success":
        raise ServiceError(resp.get("Message") or "the call could not be started")


def originate(session: Session, extension: str, number: str, actor: str, via: str = "API") -> dict[str, Any]:
    number = number.strip()
    if not NUMBER_RE.match(number):
        raise ServiceError(fields={"number": "digits, *, # and + only (up to 32)"})
    phone = phone_for_call(session, extension)
    originate_into(phone, f"phone-{phone.extension}", number, f'"Call to {number}" <{number}>')
    audit(session, actor, "originate", "phone", phone.id, f"{phone.extension} -> {number} ({via})")
    return {"extension": phone.extension, "number": number, "status": "ringing"}


def test_menu(session: Session, extension: str, menu: IvrMenu, actor: str) -> None:
    """Ring the phone and connect it to the (applied) IVR menu, as an internal caller."""
    phone = phone_for_call(session, extension)
    originate_into(phone, f"ivr-{menu.id}", "s", f'"IVR test" <{menu.extension or "ivr"}>')
    audit(session, actor, "originate", "ivr", menu.id, f"{phone.extension} -> IVR menu {menu.name} (test)")
