# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Minute sync between the Asterisk database and SQLite for business hours.

Phones switch modes, overrides and special periods in AstDB. This job removes stale
runtime entries, copies special period switches made by phones into SQLite (so they
survive an Asterisk database loss and show in the UI), restores missing switches and
refreshes the phone lamps (which also covers an Asterisk restart).
"""

from __future__ import annotations

import datetime as dt
import logging
import threading

from sqlalchemy.orm import Session

from phonix import ami
from phonix.core.db import session_scope
from phonix.generators.dialplan import HOURS_DB, OVERRIDE_DB, SPECIAL_DB
from phonix.services import hours

log = logging.getLogger(__name__)


def sync_once(session: Session, client: ami.AmiClient, now: dt.datetime) -> None:
    all_hours = hours.list_hours(session)
    others = {h.id: h for h in all_hours}
    specials = {sp.id: sp for h in all_hours for sp in h.specials}

    # unknown ids and unparseable values
    raw_modes = hours._astdb_family(client, HOURS_DB)
    raw_overrides = hours._astdb_family(client, OVERRIDE_DB)
    raw_special = hours._astdb_family(client, SPECIAL_DB)
    for family, raw, known, valid in (
        (HOURS_DB, raw_modes, others, lambda x: x in ("open", "closed")),
        (OVERRIDE_DB, raw_overrides, others, lambda x: hours.parse_override(x) is not None),
        (SPECIAL_DB, raw_special, specials, lambda x: x in ("0", "1")),
    ):
        for key, value in raw.items():
            if key not in known or not valid(value):
                client.command(f"database del {family} {key}")

    # special period switches: a phone's value wins, a missing value is restored
    for sp in specials.values():
        switch = raw_special.get(sp.id)
        if switch in ("0", "1"):
            sp.enabled = switch == "1"
        else:
            client.command(f"database put {SPECIAL_DB} {sp.id} {int(sp.enabled)}")
    session.flush()

    # overrides end at midnight or when the automatic state reaches the overridden value
    rt = hours.read_runtime(client)
    for hours_id, (state, day) in rt.overrides.items():
        h = others.get(hours_id)
        if h is None:
            continue
        if day != now.date() or (state == "open") == hours.automatic(h, rt, now, others)["open"]:
            client.command(f"database del {OVERRIDE_DB} {hours_id}")

    hours.refresh_lamps(session, client, hours.read_runtime(client), now)


def run_forever(interval: float = 60.0, stop: threading.Event | None = None) -> None:
    stop = stop or threading.Event()
    while not stop.is_set():
        try:
            with ami.AmiClient() as client, session_scope() as session:
                sync_once(session, client, hours.local_now(session))
        except (ami.AmiError, OSError) as exc:
            log.info("business hours sync: Asterisk unavailable (%s)", exc)
        except Exception:
            log.exception("business hours sync failed")
        stop.wait(interval)
