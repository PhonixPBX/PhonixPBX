#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Fill an empty PBX with plausible demo data (for screenshots and demos).

Runs inside the dev container (``dev/run.sh --demo``) or locally with the
PHONIX_* variables from CLAUDE.md. Everything goes through the service layer,
so validation, audit log entries and the "apply" banner look real. Does
nothing if phones already exist.
"""

from __future__ import annotations

import datetime as dt
import sys

from phonix.core.db import session_scope
from phonix.services import dialplan as dp
from phonix.services import hours as hours_svc
from phonix.services import ivr as ivr_svc
from phonix.services import manager as ami_svc
from phonix.services import phones as phone_svc
from phonix.services import providers as provider_svc
from phonix.services import setup, tokens, users
from phonix.services.common import parse

ACTOR = "admin"

# extension, caller id, description, voicemail email
PHONES = [
    ("101", "Anna Keller", "Reception desk", "anna.keller@example.com"),
    ("102", "Marco Rossi", "Sales", "marco.rossi@example.com"),
    ("103", "Sofia Lindqvist", "Sales", "sofia.lindqvist@example.com"),
    ("104", "Jonas Weber", "Support", "jonas.weber@example.com"),
    ("105", "Lea Dubois", "Support", "lea.dubois@example.com"),
    ("106", "Tom Becker", "Support", ""),
    ("110", "Meeting Room", "Conference phone, 1st floor", ""),
    ("120", "Warehouse", "DECT base station", ""),
    ("201", "Claire Martin", "Accounting", "claire.martin@example.com"),
    ("202", "David Novak", "Management", "david.novak@example.com"),
]

# more staff on 301-420, so the phone list has several pages (50 per page)
FIRST = ("Nina", "Luca", "Emma", "Noah", "Mia", "Elias", "Lina", "Leon", "Sara", "Jan", "Laura", "Fabian")
LAST = ("Meier", "Müller", "Schmid", "Huber", "Brunner", "Gerber", "Frei", "Baumann", "Fischer", "Graf")
DEPARTMENTS = ("Sales", "Support", "Accounting", "Warehouse", "Production", "Marketing", "IT", "Logistics")


def staff() -> list[tuple[str, str, str, str]]:
    out = []
    for i in range(120):
        first, last = FIRST[i % len(FIRST)], LAST[(i // len(FIRST)) % len(LAST)]
        email = f"{first}.{last}@example.com".lower().replace("ü", "ue") if i % 3 == 0 else ""
        out.append((str(301 + i), f"{first} {last}", DEPARTMENTS[i % len(DEPARTMENTS)], email))
    return out


def main() -> int:
    setup.initialize()
    with session_scope() as session:
        if phone_svc.list_phones(session):
            print("demo data: phones exist already, nothing to do")
            return 0

        trunk = provider_svc.create_provider(
            session,
            provider_svc.parse_provider(
                {
                    "name": "SIP Trunk Example",
                    "host": "sip.example.net",
                    "username": "41445551234",
                    "secret": "demo-trunk-secret",
                    "readback_number": "+41445551234",
                    "dialpatterns": ["0|NXXXXXXXX", "00|X.", "0041+0|NX."],
                }
            ),
            user=ACTOR,
        )
        backup = provider_svc.create_provider(
            session,
            provider_svc.parse_provider(
                {
                    "name": "Backup Carrier",
                    "host": "voip.example.org",
                    "transport": "tls",
                    "username": "pbx-demo",
                    "secret": "demo-backup-secret",
                    "codecs": ["g722", "alaw", "opus"],
                    "dialpatterns": ["112", "117", "118", "144"],
                }
            ),
            user=ACTOR,
        )
        trunk_settings = provider_svc.to_dict(trunk, with_secret=True)
        trunk_settings["failover_provider_id"] = backup.id

        phones = {}
        for ext, name, desc, email in PHONES + staff():
            data = {
                "extension": ext,
                "callerid": name,
                "description": desc,
                "secret": f"demo-{ext}-secret",
                "vm_enabled": bool(email),
                "vm_pin": "1234" if email else "",
                "vm_email": email,
            }
            phones[ext] = phone_svc.create_phone(session, phone_svc.parse_phone(data), user=ACTOR)
        phone_svc.set_enabled(session, phones["120"].id, False, user=ACTOR)
        phone_svc.create_phone(
            session,
            phone_svc.parse_phone(
                {
                    "tech": "external",
                    "extension": "150",
                    "callerid": "Marco Mobile",
                    "description": "Forward to mobile",
                    "dial_type": "provider",
                    "dial_provider_id": trunk.id,
                    "dial_string": "0791234567",
                }
            ),
            user=ACTOR,
        )

        sales = dp.create_callgroup(
            session,
            parse(
                dp.CallGroupIn,
                {"name": "Sales", "extension": "600", "member_ids": [phones[e].id for e in ("102", "103")]},
            ),
            user=ACTOR,
        )
        support = dp.create_callgroup(
            session,
            parse(
                dp.CallGroupIn,
                {
                    "name": "Support",
                    "extension": "601",
                    "description": "First level support hotline",
                    "strategy": "linear",
                    "ringlength": 20,
                    "member_ids": [phones[e].id for e in ("104", "105", "106")],
                },
            ),
            user=ACTOR,
        )
        reception = dp.create_callgroup(
            session,
            parse(
                dp.CallGroupIn,
                {"name": "Reception", "extension": "602", "member_ids": [phones[e].id for e in ("101", "202")]},
            ),
            user=ACTOR,
        )

        dp.create_room(session, parse(dp.ConferenceRoomIn, {"number": "800", "name": "Team Meeting"}), user=ACTOR)
        dp.create_room(
            session,
            parse(dp.ConferenceRoomIn, {"number": "801", "name": "Board Room", "pin": "4711", "admin_pin": "0815"}),
            user=ACTOR,
        )

        dp.create_application(
            session,
            parse(
                dp.ApplicationIn,
                {
                    "name": "Echo Test",
                    "extension": "*43",
                    "description": "Test audio round trip",
                    "logic": "1,Answer()\nn,Playback(demo-echotest)\nn,Echo()\nn,Hangup()",
                },
            ),
            user=ACTOR,
        )
        dp.create_application(
            session,
            parse(
                dp.ApplicationIn,
                {
                    "name": "Speaking Clock",
                    "extension": "*60",
                    "logic": "1,Answer()\nn,SayUnixTime(,,HM)\nn,Hangup()",
                },
            ),
            user=ACTOR,
        )

        support_menu = ivr_svc.create_menu(
            session,
            parse(
                ivr_svc.IvrMenuIn,
                {
                    "name": "Support Menu",
                    "extension": "501",
                    "prompt_mode": "sound",
                    "prompt_sound": "pls-hold-while-try",
                    "prompt_text": "For technical support, press 1. To leave a message for support, press 2. "
                    "To return to the main menu, press star.",
                    "timeout_dest_type": "callgroup",
                    "timeout_dest_id": support.id,
                    "options": [
                        {"key": "1", "label": "Technical support", "dest_type": "callgroup", "dest_id": support.id},
                        {"key": "2", "label": "Leave a message", "dest_type": "voicemail", "dest_id": phones["104"].id},
                    ],
                },
            ),
            user=ACTOR,
        )
        main_menu = ivr_svc.create_menu(
            session,
            parse(
                ivr_svc.IvrMenuIn,
                {
                    "name": "Main Menu",
                    "extension": "500",
                    "description": "Greeting for the main number during business hours",
                    "prompt_mode": "sound",
                    "prompt_sound": "welcome",
                    "prompt_text": "Welcome to Example Ltd. For sales, press 1. For support, press 2. "
                    "For accounting, press 3. For the reception, press 0. "
                    "If you know the extension of your party, you can dial it at any time.",
                    "direct_dial": True,
                    "timeout_dest_type": "callgroup",
                    "timeout_dest_id": reception.id,
                    "options": [
                        {"key": "1", "label": "Sales", "dest_type": "callgroup", "dest_id": sales.id},
                        {"key": "2", "label": "Support", "dest_type": "ivr", "dest_id": support_menu.id},
                        {"key": "3", "label": "Accounting", "dest_type": "phone", "dest_id": phones["201"].id},
                        {"key": "0", "label": "Reception", "dest_type": "callgroup", "dest_id": reception.id},
                    ],
                },
            ),
            user=ACTOR,
        )
        ivr_svc.update_menu(
            session,
            support_menu.id,
            parse(
                ivr_svc.IvrMenuIn,
                {
                    **ivr_svc.to_dict(support_menu),
                    "options": [
                        *ivr_svc.to_dict(support_menu)["options"],
                        {"key": "*", "label": "Main menu", "dest_type": "ivr", "dest_id": main_menu.id},
                    ],
                },
            ),
            user=ACTOR,
        )

        year = dt.date.today().year
        office_hours = hours_svc.create_hours(
            session,
            parse(
                hours_svc.BusinessHoursIn,
                {
                    **hours_svc.defaults(),
                    "name": "Office Hours",
                    "description": "Main number: menu while open, reception voicemail while closed",
                    "feature_code": "*31",
                    "open_dest_type": "ivr",
                    "open_dest_id": main_menu.id,
                    "closed_dest_type": "voicemail",
                    "closed_dest_id": phones["101"].id,
                    "holidays": [
                        {"date": f"{year}-01-01", "name": "New Year's Day", "yearly": True},
                        {"date": f"{year}-08-01", "name": "National Day", "yearly": True},
                        {"date": f"{year}-12-24", "name": "Christmas Eve", "yearly": True},
                        {"date": f"{year}-12-25", "name": "Christmas Day", "yearly": True},
                        {"date": f"{year}-12-26", "name": "St Stephen's Day", "yearly": True},
                        {"date": f"{year}-12-27", "name": "Company outing"},
                    ],
                },
            ),
            user=ACTOR,
        )

        trunk_settings["incoming_routes"] = [
            {"pattern": "41445551299", "dest_type": "callgroup", "dest_id": support.id},
            {"pattern": "41445551288", "dest_type": "callgroup", "dest_id": sales.id},
            {"pattern": "", "dest_type": "hours", "dest_id": office_hours.id},
        ]
        provider_svc.update_provider(session, trunk.id, provider_svc.parse_provider(trunk_settings), user=ACTOR)

        ami_svc.create_ami_user(
            session,
            parse(
                ami_svc.AmiUserIn,
                {
                    "username": "crm",
                    "secret": "demo-ami-secret",
                    "permit": ["192.168.1.0/24"],
                    "read_perms": ["call", "cdr"],
                },
            ),
            actor=ACTOR,
        )

        admin = users.get_by_name(session, "admin")
        if admin is not None:
            tokens.create(session, admin, "Monitoring", read_only=True, actor=ACTOR)
            tokens.create(session, admin, "Provisioning script", read_only=False, expires_in_days=90, actor=ACTOR)

    print(
        "demo data: created phones, providers, call groups, conference rooms, applications,"
        " IVR menus and business hours"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
