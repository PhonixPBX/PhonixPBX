"""Build a representative PBX configuration through the service layer."""

from __future__ import annotations

from sqlalchemy.orm import Session

from phonix.core import settings as st
from phonix.services import dialplan, manager, phones, providers


def sample_pbx(session: Session) -> dict[str, int]:
    email = st.EmailSettings(
        host="smtp.example.com", port=587, username="pbx", password='p"w;d', from_address="pbx@example.com"
    )
    st.save(session, email)

    alice = phones.create_phone(
        session,
        phones.parse_phone(
            {
                "extension": "101",
                "callerid": "Alice",
                "secret": "alicesecret1",
                "vm_enabled": True,
                "vm_pin": "1234",
                "vm_email": "alice@example.com",
                "notify_missed": True,
                "notify_email": "alice@example.com",
                "ringlength": 25,
            }
        ),
    )
    bob = phones.create_phone(
        session,
        phones.parse_phone(
            {
                "extension": "102",
                "callerid": "Bob",
                "secret": "bobsecret12",
                "max_contacts": 2,
            }
        ),
    )
    carol = phones.create_phone(
        session,
        phones.parse_phone(
            {
                "tech": "iax",
                "extension": "103",
                "callerid": "Carol IAX",
                "secret": "carolsecret",
            }
        ),
    )
    trunk = providers.create_provider(
        session,
        providers.parse_provider(
            {
                "name": "Example Trunk",
                "host": "sip.example.com",
                "username": "4930123456",
                "secret": "trunksecret",
                "dialpatterns": ["0|X.", "49+0|1XX."],
                "callerid_source": "string",
                "callerid_string": "Example <4930123456>",
                "incoming_routes": [
                    {"pattern": "", "dest_type": "phone", "dest_id": alice.id},
                    {"pattern": "", "dest_type": "phone", "dest_id": bob.id},
                    {"pattern": "4930123457", "dest_type": "phone", "dest_id": bob.id},
                ],
            }
        ),
    )
    second = providers.create_provider(
        session,
        providers.parse_provider(
            {
                "name": "Second Account",
                "host": "sip.example.com",
                "username": "4930999",
                "secret": "secondsecret",
                "dialpatterns": ["00X."],
            }
        ),
    )
    iax_trunk = providers.create_provider(
        session,
        providers.parse_provider(
            {
                "tech": "iax",
                "name": "IAX Trunk",
                "host": "iax.example.org",
                "username": "phonix",
                "secret": "iaxsecret",
                "dialpatterns": ["9|X."],
                "failover_provider_id": trunk.id,
            }
        ),
    )
    ext = phones.create_phone(
        session,
        phones.parse_phone(
            {
                "tech": "external",
                "extension": "201",
                "callerid": "Mobile Alice",
                "dial_type": "provider",
                "dial_provider_id": trunk.id,
                "dial_string": "01701234567",
            }
        ),
    )
    phones.update_phone(
        session,
        bob.id,
        phones.parse_phone(
            {
                **phones.to_dict(bob),
                "blocked_provider_ids": [iax_trunk.id],
                "provider_callerids": {trunk.id: "Bob <4930123457>"},
            }
        ),
    )
    group = dialplan.create_callgroup(
        session,
        dialplan.CallGroupIn(
            name="Sales",
            extension="300",
            member_ids=[alice.id, bob.id],
            public_access=True,
        ),
    )
    linear = dialplan.create_callgroup(
        session,
        dialplan.CallGroupIn(
            name="Hunt",
            extension="301",
            member_ids=[bob.id, alice.id],
            strategy="linear",
            ringlength=15,
        ),
    )
    room = dialplan.create_room(
        session,
        dialplan.ConferenceRoomIn(
            number="2664",
            name="Secret Room",
            pin="4711",
            admin_pin="0815",
        ),
    )
    manager.create_ami_user(
        session,
        manager.AmiUserIn(
            username="monitor",
            secret="monitorsecret",
            permit=["192.168.1.0/24"],
            read_perms=["call", "system"],
            write_perms=[],
        ),
    )
    session.flush()
    return {
        "alice": alice.id,
        "bob": bob.id,
        "carol": carol.id,
        "trunk": trunk.id,
        "second": second.id,
        "iax_trunk": iax_trunk.id,
        "external": ext.id,
        "group": group.id,
        "linear": linear.id,
        "room": room.id,
    }
